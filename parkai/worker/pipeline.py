"""추론 워커.

사이클 흐름 (docs/design.md 4단계):
  수신+디코딩+화면검사 (스레드 풀, 카메라별 병렬, 렌즈별 사진)
  ->  추론 (NPU, 순차)  ->  판정  ->  안정화  ->  출력

- 화면 이상인 분석 영역(또는 받지 못한 렌즈)의 칸은 판정하지 않고 마지막 상태를 유지한다.
- 모든 렌즈가 이상이거나 아직 상태가 없는 칸이 있으면 그 카메라는 전송하지 않는다.
- 최신 이미지는 카메라에서 받은 렌즈 원본을 그대로 둔다 (다시 인코딩하지 않음).
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .. import __version__
from ..backends import Detector
from ..core.config import AppConfig, Camera, load_config
from ..core.geometry import Box
from ..core.image_check import FrozenDetector, ImageStatus, check_view
from ..core.layout import split_views
from ..core.stabilizer import CameraStabilizer
from ..core.system import board_ip, device_id
from ..outputs.indicator import IndicatorController, decide_color
from ..outputs.server import ServerSender, build_payload
from .analyze import LensFrame, detect_lens, dets_for_web, judge_camera, slot_in_px
from .draw import annotate
from .sources import BrokenSource, HttpSnapshotSource, ReplaySource, SourceError, replay_folder

log = logging.getLogger(__name__)


@dataclass
class Prepared:
    cam: Camera
    status: str
    frames: list[LensFrame] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    error: str | None = None


def _now_iso() -> str:
    """시간대를 붙인 현재 시각. 보드(UTC)와 브라우저(KST)의 시간대가 달라도 같은 시점으로 읽힌다."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def camera_status(frames: list[LensFrame]) -> str:
    """렌즈 상태를 카메라 상태 하나로: 모두 정상 ok, 일부 정상 partial, 모두 이상이면 첫 렌즈의 이상."""
    sts = [f.status for f in frames]
    if sts and all(s == "ok" for s in sts):
        return "ok"
    if any(s in ("ok", "partial") for s in sts):
        return "partial"
    return sts[0] if sts else "no_response"


class CameraRuntime:
    def __init__(self, cam: Camera, sources: list, stable_count: int):
        self.cam = cam
        self.sources = sources  # 렌즈별 입력
        self.stabilizer = CameraStabilizer(stable_count)
        self.frozen = [FrozenDetector() for _ in sources]
        self.states: dict[int, bool] = {}
        self.last_saved = 0.0
        self.sig: tuple | None = None


class Worker:
    def __init__(
        self,
        config_path: Path,
        detector: Detector,
        run_dir: Path,
        data_dir: Path,
        replay_dir: Path | None = None,
    ):
        self.config_path = config_path
        self.detector = detector
        self.run_dir = run_dir
        self.data_dir = data_dir
        self.replay_dir = replay_dir
        self.device_id = device_id()
        self.cfg: AppConfig = load_config(config_path)
        self._cfg_mtime = config_path.stat().st_mtime
        self.cams: dict[str, CameraRuntime] = {}
        self.sender = ServerSender(self.cfg.server)
        self.indicator = IndicatorController(self.cfg.indicator)
        self.pool = ThreadPoolExecutor(self.cfg.runtime.fetch_concurrency, thread_name_prefix="fetch")
        (run_dir / "latest").mkdir(parents=True, exist_ok=True)
        (data_dir / "results").mkdir(parents=True, exist_ok=True)
        self._sync_cameras()

    def stop(self) -> None:
        self.sender.stop()
        self.indicator.stop()

    # ---------- 설정 ----------

    def _reload_if_changed(self) -> None:
        mtime = self.config_path.stat().st_mtime
        if mtime == self._cfg_mtime:
            return
        try:
            self.cfg = load_config(self.config_path)
        except Exception as e:  # 잘못된 설정이면 기존 설정 유지
            log.error("설정 다시 읽기 실패, 기존 설정 유지: %s", e)
            return
        self._cfg_mtime = mtime
        self.sender.update_cfg(self.cfg.server)
        self.indicator.update_cfg(self.cfg.indicator)
        self._sync_cameras()
        log.info("설정 반영 (카메라 %d대)", len(self.cams))

    def _make_source(self, cam: Camera, lens: int = 0):
        if self.replay_dir is not None:
            replay = ReplaySource(replay_folder(self.replay_dir, cam.ip, lens))
            if replay.files:
                return replay
            # 샘플이 없는 카메라는 실제 카메라에서 받는다 (재생과 실제 카메라를 섞어 쓸 수 있게)
        rt = self.cfg.runtime
        profile = self.cfg.camera_profiles[cam.profile]
        try:
            return HttpSnapshotSource(cam, profile, rt.fetch_timeout_sec, rt.fetch_retries, lens)
        except SourceError as e:  # URL 설정 오류 등: 워커는 계속 돌고 해당 카메라만 오류
            return BrokenSource(str(e))

    def _sync_cameras(self) -> None:
        _, stab = self.cfg.detection.effective()
        wanted = {c.ip: c for c in self.cfg.cameras_for_board()}
        for ip in list(self.cams):
            if ip not in wanted:
                del self.cams[ip]
        for ip, cam in wanted.items():
            rt = self.cams.get(ip)
            sig = (cam.model_dump(), self.cfg.camera_profiles[cam.profile].model_dump())
            if rt is None or rt.sig != sig:
                old = rt
                sources = [self._make_source(cam, i) for i in range(self.cfg.camera_lenses(cam))]
                rt = CameraRuntime(cam, sources, stab.count)
                rt.sig = sig  # 카메라나 프로필(주소, 계정, 렌즈)이 바뀌면 입력을 새로 만든다
                if old is not None and old.cam.slots == cam.slots:
                    rt.stabilizer, rt.states = old.stabilizer, old.states
                self.cams[ip] = rt
            rt.stabilizer.set_count(stab.count)

    # ---------- 단계 1: 수신 + 디코딩 + 화면 검사 (스레드 풀) ----------

    def _prepare_lens(self, rt: CameraRuntime, lens: int, timings: dict[str, float]) -> LensFrame:
        cam = rt.cam
        t = time.perf_counter()
        try:
            jpeg, key = rt.sources[lens].fetch()
        except SourceError as e:
            timings["fetch"] = timings.get("fetch", 0) + time.perf_counter() - t
            return LensFrame(lens, "no_response", error=str(e))
        timings["fetch"] = timings.get("fetch", 0) + time.perf_counter() - t

        t = time.perf_counter()
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        timings["decode"] = timings.get("decode", 0) + time.perf_counter() - t
        if img is None:
            return LensFrame(lens, "decode_error", error="이미지를 읽을 수 없습니다")

        t = time.perf_counter()
        chk = self.cfg.detection.image_check
        if self.replay_dir is None and rt.frozen[lens].update(jpeg, chk.frozen_cycles):
            timings["check"] = timings.get("check", 0) + time.perf_counter() - t
            return LensFrame(lens, "frozen", img, jpeg, key)
        views = split_views(img, self.cfg.camera_profiles[cam.profile].views)
        statuses = [check_view(cv2.cvtColor(v.image, cv2.COLOR_BGR2GRAY), chk) for v in views]
        view_ok = [st == ImageStatus.OK for st in statuses]
        status = "ok" if all(view_ok) else "partial" if any(view_ok) else statuses[0].value
        timings["check"] = timings.get("check", 0) + time.perf_counter() - t
        return LensFrame(lens, status, img, jpeg, key, views, view_ok)

    def _prepare(self, rt: CameraRuntime) -> Prepared:
        timings: dict[str, float] = {}
        frames = [self._prepare_lens(rt, i, timings) for i in range(len(rt.sources))]
        errors = [f"렌즈{f.lens + 1}: {f.error}" if len(frames) > 1 else f.error for f in frames if f.error]
        return Prepared(rt.cam, camera_status(frames), frames, timings, "; ".join(errors) or None)

    # ---------- 단계 2: 추론 + 판정 + 안정화 + 출력 (순차) ----------

    def _process(self, rt: CameraRuntime, p: Prepared) -> dict:
        cam = rt.cam
        info: dict = {
            "status": p.status,
            "timings": p.timings,
            "error": p.error,
            "updated_at": _now_iso(),
        }
        if p.status not in ("ok", "partial"):
            info["states"] = {str(k): v for k, v in rt.states.items()}
            self._save_images(rt, p, {}, changed=False)  # 화면 이상이어도 무엇이 보이는지는 대시보드에 표시
            return info

        det = self.cfg.detection
        conf = {k: c.conf for k, c in det.classes.items() if c.enabled}
        t = time.perf_counter()
        boxes = {f.lens: detect_lens(self.detector, f, conf, det.nms_iou) for f in p.frames}
        p.timings["infer"] = time.perf_counter() - t

        t = time.perf_counter()
        judge_cfg, _ = det.effective()
        profile = self.cfg.camera_profiles[cam.profile]
        results = judge_camera(cam.slots, p.frames, boxes, profile.views, judge_cfg)
        stable = rt.stabilizer.update({no: r.occupied for no, r in results.items()})
        prev = dict(rt.states)
        for s in cam.slots:  # 판정 못 한 칸은 마지막 상태 유지
            if s.no in stable:
                rt.states[s.no] = stable[s.no]
        rt.states = {s.no: rt.states[s.no] for s in cam.slots if s.no in rt.states}
        p.timings["judge"] = time.perf_counter() - t

        t = time.perf_counter()
        complete = len(rt.states) == len(cam.slots)
        if complete:
            bip = board_ip(self.cfg.network.board_ip)
            self.sender.submit(cam.ip, build_payload(cam.ip, bip, rt.states))
            color = decide_color(cam.slots, rt.states, self.cfg.slot_types)
            if color:
                user, password = self.cfg.camera_account(cam)
                self.indicator.send(cam, profile, user, password, color)
        changed = prev != rt.states
        self._save_images(rt, p, boxes, changed)
        p.timings["output"] = time.perf_counter() - t

        info["states"] = {str(k): v for k, v in rt.states.items()}
        info["sent"] = complete
        info["boxes"] = sum(len(b) for b in boxes.values())
        # 웹 화면이 원본 위에 직접 그리도록 검출 박스 [렌즈, x1, y1, x2, y2, 점수] (렌즈 사진 대비 비율)
        info["dets"] = dets_for_web(p.frames, boxes)
        return info

    def _save_images(
        self, rt: CameraRuntime, p: Prepared, boxes: dict[int, list[Box]], changed: bool
    ) -> None:
        cam = rt.cam
        # 최신 이미지: 받은 렌즈 원본 그대로 (웹 화면이 분석 영역만 보여 주고 선·박스를 직접 그림). RAM 디스크
        for f in p.frames:
            if f.jpeg is None:
                continue
            latest = self.run_dir / "latest" / f"{cam.ip}_{f.lens}.jpg"
            tmp = latest.with_suffix(".tmp")
            tmp.write_bytes(f.jpeg)
            for _ in range(3):  # Windows: 웹이 읽는 중이면 교체가 잠시 실패할 수 있음
                try:
                    os.replace(tmp, latest)
                    break
                except PermissionError:
                    time.sleep(0.05)
        if p.status not in ("ok", "partial"):
            return

        # 기록 이미지: 상태가 바뀌었을 때 + 주기마다, 렌즈를 나란히 붙여 선·박스를 그려 저장 (이때만 인코딩)
        now = time.time()
        if not (changed or now - rt.last_saved >= self.cfg.runtime.results.save_interval_sec):
            return
        states = {s.no: rt.states.get(s.no) for s in cam.slots}
        pics = []
        for f in p.frames:
            if f.image is None:
                continue
            w, h = f.size
            slots = [slot_in_px(s, w, h) for s in cam.slots if s.lens == f.lens]
            pics.append(annotate(f.image, (w, h), slots, states, boxes.get(f.lens, []), ""))
        if not pics:
            return
        hh = min(x.shape[0] for x in pics)
        pics = [
            x if x.shape[0] == hh else cv2.resize(x, (round(x.shape[1] * hh / x.shape[0]), hh)) for x in pics
        ]
        ok, rec = cv2.imencode(".jpg", np.hstack(pics), [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            d = self.data_dir / "results" / cam.ip
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{datetime.now():%Y%m%d_%H%M%S}.jpg").write_bytes(rec.tobytes())
        rt.last_saved = now

    def _enforce_results_limit(self) -> None:
        limit = self.cfg.runtime.results.max_mb * 1024 * 1024
        files = sorted((self.data_dir / "results").rglob("*.jpg"), key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        for f in files:
            if total <= limit:
                break
            total -= f.stat().st_size
            f.unlink(missing_ok=True)

    # ---------- 사이클 ----------

    def run_cycle(self, cycle_no: int) -> dict:
        self._reload_if_changed()
        t0 = time.perf_counter()
        futures = {self.pool.submit(self._prepare, rt): rt for rt in self.cams.values()}
        cameras: dict[str, dict] = {}
        for fut in as_completed(futures):
            rt = futures[fut]
            try:
                cameras[rt.cam.ip] = self._process(rt, fut.result())
            except Exception as e:  # 카메라 하나의 오류가 사이클 전체를 멈추지 않게
                log.exception("카메라 %s 처리 실패", rt.cam.ip)
                cameras[rt.cam.ip] = {"status": "error", "error": str(e)}
        elapsed = time.perf_counter() - t0
        if cycle_no % 30 == 0:
            self._enforce_results_limit()
        status = {
            "version": __version__,
            "device_id": self.device_id,
            "cycle": cycle_no,
            "cycle_sec": round(elapsed, 3),
            "updated_at": _now_iso(),
            "server_error": self.sender.last_error,
            "cameras": cameras,
        }
        self._write_status(status)
        return status

    def _write_status(self, status: dict) -> None:
        p = self.run_dir / "status.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)

    def run_forever(self, max_cycles: int | None = None) -> None:
        n = 0
        while max_cycles is None or n < max_cycles:
            n += 1
            start = time.monotonic()
            st = self.run_cycle(n)
            bad = [ip for ip, c in st["cameras"].items() if c.get("status") != "ok"]
            log.info(
                "사이클 %d: %.2fs, 카메라 %d대, 이상 %s",
                n,
                st["cycle_sec"],
                len(st["cameras"]),
                bad or "없음",
            )
            wait = self.cfg.runtime.cycle_target_sec - (time.monotonic() - start)
            if wait > 0 and (max_cycles is None or n < max_cycles):
                time.sleep(wait)
        self.stop()
