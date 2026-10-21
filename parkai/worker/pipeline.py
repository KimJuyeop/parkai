"""추론 워커.

사이클 흐름 (docs/design.md 4단계):
  수신+디코딩+화면검사 (스레드 풀, 병렬)  ->  추론 (NPU, 순차)  ->  판정  ->  안정화  ->  출력

- 화면 이상 view에 속한 칸은 판정하지 않고 마지막 상태를 유지한다.
- 모든 view가 이상이거나 아직 상태가 없는 칸이 있으면 그 카메라는 전송하지 않는다.
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
from ..core.config import AppConfig, Camera, Slot, load_config
from ..core.geometry import Box
from ..core.image_check import FrozenDetector, ImageStatus, check_view
from ..core.judge import judge
from ..core.layout import View, split_views
from ..core.stabilizer import CameraStabilizer
from ..core.system import board_ip, device_id
from ..outputs.indicator import IndicatorController, decide_color
from ..outputs.server import ServerSender, build_payload
from .draw import annotate
from .sources import BrokenSource, HttpSnapshotSource, ReplaySource, SourceError

log = logging.getLogger(__name__)


@dataclass
class Prepared:
    cam: Camera
    status: str
    image: np.ndarray | None = None
    views: list[View] = field(default_factory=list)
    view_ok: list[bool] = field(default_factory=list)
    source_key: str | None = None
    timings: dict[str, float] = field(default_factory=dict)
    error: str | None = None


class CameraRuntime:
    def __init__(self, cam: Camera, source, stable_count: int):
        self.cam = cam
        self.source = source
        self.stabilizer = CameraStabilizer(stable_count)
        self.frozen = FrozenDetector()
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
        self.indicator = IndicatorController()
        self.pool = ThreadPoolExecutor(self.cfg.runtime.fetch_concurrency, thread_name_prefix="fetch")
        (run_dir / "latest").mkdir(parents=True, exist_ok=True)
        (data_dir / "results").mkdir(parents=True, exist_ok=True)
        self._sync_cameras()

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
        self._sync_cameras()
        log.info("설정 반영 (카메라 %d대)", len(self.cams))

    def _make_source(self, cam: Camera):
        if self.replay_dir is not None:
            return ReplaySource(self.replay_dir / cam.ip)
        rt = self.cfg.runtime
        profile = self.cfg.camera_profiles[cam.profile]
        try:
            return HttpSnapshotSource(cam, profile, rt.fetch_timeout_sec, rt.fetch_retries)
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
                rt = CameraRuntime(cam, self._make_source(cam), stab.count)
                rt.sig = sig  # 카메라나 프로필(주소, 계정)이 바뀌면 입력을 새로 만든다
                if old is not None and old.cam.slots == cam.slots:
                    rt.stabilizer, rt.states = old.stabilizer, old.states
                self.cams[ip] = rt
            rt.stabilizer.set_count(stab.count)

    # ---------- 단계 1: 수신 + 디코딩 + 화면 검사 (스레드 풀) ----------

    def _prepare(self, rt: CameraRuntime) -> Prepared:
        cam = rt.cam
        t = time.perf_counter()
        try:
            jpeg, key = rt.source.fetch()
        except SourceError as e:
            return Prepared(cam, "no_response", error=str(e), timings={"fetch": time.perf_counter() - t})
        t_fetch = time.perf_counter() - t

        t = time.perf_counter()
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        t_decode = time.perf_counter() - t
        if img is None:
            return Prepared(cam, "decode_error", timings={"fetch": t_fetch, "decode": t_decode})

        t = time.perf_counter()
        chk = self.cfg.detection.image_check
        if self.replay_dir is None and rt.frozen.update(jpeg, chk.frozen_cycles):
            return Prepared(cam, "frozen", image=img, timings={"fetch": t_fetch, "decode": t_decode})
        profile = self.cfg.camera_profiles[cam.profile]
        views = split_views(img, profile.views, self.cfg.camera_ref_size(cam))
        view_ok = []
        statuses = []
        for v in views:
            st = check_view(cv2.cvtColor(v.image, cv2.COLOR_BGR2GRAY), chk)
            statuses.append(st)
            view_ok.append(st == ImageStatus.OK)
        if all(view_ok):
            status = "ok"
        elif any(view_ok):
            status = "partial"
        else:
            status = statuses[0].value
        return Prepared(
            cam,
            status,
            img,
            views,
            view_ok,
            key,
            {"fetch": t_fetch, "decode": t_decode, "check": time.perf_counter() - t},
        )

    # ---------- 단계 2: 추론 + 판정 + 안정화 + 출력 (순차) ----------

    def _view_of(self, slot: Slot, views: list[View], profile_views) -> int | None:
        (x1, y1), (x2, y2) = slot.line
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        for i, (vx, vy, vw, vh) in enumerate(profile_views):
            if vx <= mx < vx + vw and vy <= my < vy + vh:
                return i
        return None

    def _detect(self, p: Prepared) -> list[Box]:
        det = self.cfg.detection
        conf = {k: c.conf for k, c in det.classes.items() if c.enabled}
        ref_w, _ = self.cfg.camera_ref_size(p.cam)
        if getattr(self.detector, "full_frame", False):
            s = ref_w / p.image.shape[1]
            boxes = self.detector.detect(p.image, conf, det.nms_iou, p.source_key)
            return [b.shifted(0, 0, s) for b in boxes]
        boxes: list[Box] = []
        for v, ok in zip(p.views, p.view_ok, strict=True):
            if not ok:
                continue
            for b in self.detector.detect(v.image, conf, det.nms_iou):
                boxes.append(b.shifted(v.offset[0], v.offset[1], v.to_ref))
        return boxes

    def _process(self, rt: CameraRuntime, p: Prepared) -> dict:
        cam = rt.cam
        info: dict = {
            "status": p.status,
            "timings": p.timings,
            "error": p.error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        if p.status not in ("ok", "partial"):
            info["states"] = {str(k): v for k, v in rt.states.items()}
            if p.image is not None:  # 화면 이상이어도 무엇이 보이는지는 대시보드에 표시
                self._save_images(rt, p, [], changed=False)
            return info

        t = time.perf_counter()
        boxes = self._detect(p)
        p.timings["infer"] = time.perf_counter() - t

        t = time.perf_counter()
        judge_cfg, _ = self.cfg.detection.effective()
        profile = self.cfg.camera_profiles[cam.profile]
        judgeable = [
            s
            for s in cam.slots
            if (vi := self._view_of(s, p.views, profile.views)) is not None and p.view_ok[vi]
        ]
        results = judge(judgeable, boxes, judge_cfg)
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
            if self.cfg.indicator.enabled:
                color = decide_color(cam.slots, rt.states, self.cfg.slot_types)
                if color:
                    self.indicator.send(cam.ip, cam.controller_ip, color)
        changed = prev != rt.states
        self._save_images(rt, p, boxes, changed)
        p.timings["output"] = time.perf_counter() - t

        info["states"] = {str(k): v for k, v in rt.states.items()}
        info["sent"] = complete
        info["boxes"] = len(boxes)
        return info

    def _crop_to_views(self, img: np.ndarray, cam: Camera) -> np.ndarray:
        views = self.cfg.camera_profiles[cam.profile].views
        if not views:
            return img
        ref_w, ref_h = self.cfg.camera_ref_size(cam)
        h, w = img.shape[:2]
        sx, sy = w / ref_w, h / ref_h
        x0 = min(v[0] for v in views)
        y0 = min(v[1] for v in views)
        x1 = max(v[0] + v[2] for v in views)
        y1 = max(v[1] + v[3] for v in views)
        return img[round(y0 * sy) : round(y1 * sy), round(x0 * sx) : round(x1 * sx)]

    def _save_images(self, rt: CameraRuntime, p: Prepared, boxes: list[Box], changed: bool) -> None:
        cam = rt.cam
        img = annotate(
            p.image,
            self.cfg.camera_ref_size(cam),
            cam.slots,
            {s.no: rt.states.get(s.no) for s in cam.slots},
            boxes,
            "",
        )
        img = self._crop_to_views(img, cam)  # 영상이 없는 영역(아래 검은 부분 등) 제외
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return
        latest = self.run_dir / "latest" / f"{cam.ip}.jpg"
        tmp = latest.with_suffix(".tmp")
        tmp.write_bytes(buf.tobytes())
        for _ in range(3):  # Windows: 웹이 읽는 중이면 교체가 잠시 실패할 수 있음
            try:
                os.replace(tmp, latest)  # RAM 디스크, 매 사이클
                break
            except PermissionError:
                time.sleep(0.05)

        now = time.time()
        if changed or now - rt.last_saved >= self.cfg.runtime.results.save_interval_sec:
            d = self.data_dir / "results" / cam.ip
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{datetime.now():%Y%m%d_%H%M%S}.jpg").write_bytes(buf.tobytes())
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
            "updated_at": datetime.now().isoformat(timespec="seconds"),
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
        self.sender.stop()
