"""여러 모델의 칸 판정을 같은 카메라 사진으로 비교한다 (보드에서 실제 카메라로, 또는 PC 에서 샘플로).

    # 보드: 설정의 카메라·칸 선분으로 10바퀴
    M=/var/lib/parkai/models
    python3 tools/compare_judge.py --config /var/lib/parkai/config.json \\
        --model $M/st_yoloxn_car_480_pt --model $M/st_yoloxn_car_480 --rounds 10

    # PC: 샘플 사진(samples/<카메라IP>/*.jpg)
    python tools/compare_judge.py --config examples/config.example.json --replay samples \\
        --model tflite=models/st_yoloxn_car_480_pt --model onnx=models/st_yoloxn_car_480

    # PC: 기존 YOLOv4 를 기준으로 (Jetson 설정은 tools/import_jetson.py 로 옮긴다)
    python tools/compare_judge.py --config jetson.json --replay 사진 \\
        --model darknet=models/yolov4 --model tflite=models/st_yoloxn_car_480_pt

- 같은 사진 한 장을 모든 모델에 넣고, 판정 방식 legacy(선분에 닿으면 점유)와
  standard(덮인 비율)로 각각 칸을 판정한다. 첫 번째 --model 이 기준(A)이다
- 기준과 판정이 다른 칸만 출력하고, 그 사진은 --out 에 모델 결과를 나란히 그려 저장한다
  (기본 /tmp: 보드 eMMC 에 쓰지 않음)
- 첫 바퀴의 원본 사진(<IP>_raw.jpg)과 박스 점수도 남긴다
- 마지막에 모델별 카메라 1대당 추론 시간과 판정 일치율을 보여준다
- --model 은 "백엔드=폴더" 또는 폴더만 (백엔드 auto: 보드면 stai, PC 면 onnx)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parkai.backends import load_detector  # noqa: E402
from parkai.core.config import PRESETS, Camera, load_config  # noqa: E402
from parkai.core.geometry import Box  # noqa: E402
from parkai.core.judge import judge  # noqa: E402
from parkai.core.layout import split_views  # noqa: E402
from parkai.worker.draw import annotate  # noqa: E402
from parkai.worker.sources import HttpSnapshotSource, ReplaySource, SourceError  # noqa: E402


def detect_camera(det, img, cam: Camera, cfg) -> tuple[list[Box], float]:
    """워커와 같은 방식: 화면(view)마다 검출해서 기준 좌표로 옮긴다."""
    d = cfg.detection
    conf = {k: c.conf for k, c in d.classes.items() if c.enabled}
    views = split_views(img, cfg.camera_profiles[cam.profile].views, cfg.camera_ref_size(cam))
    t = time.perf_counter()
    boxes = []
    for v in views:
        boxes += [v.box_to_ref(b) for b in det.detect(v.image, conf, d.nms_iou)]
    return boxes, time.perf_counter() - t


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument(
        "--model", action="append", required=True, help="[백엔드=]모델폴더, 두 개 이상 (첫째가 기준)"
    )
    ap.add_argument("--replay", type=Path, help="카메라 대신 <폴더>/<카메라IP>/*.jpg")
    ap.add_argument("--rounds", type=int, default=1, help="카메라 전체를 몇 바퀴 돌지")
    ap.add_argument("--out", type=Path, default=Path("/tmp/parkai_compare"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(args.model) < 2:
        sys.exit("--model 을 두 개 이상 주세요")

    cfg = load_config(args.config)
    cams = [c for c in cfg.cameras_for_board() if c.slots]
    if not cams:
        sys.exit("칸 선분이 있는 카메라가 없습니다")
    dets, names = [], []
    for spec in args.model:
        backend, path = spec.split("=", 1) if "=" in spec else ("auto", spec)
        dets.append(load_detector(backend, path))
        names.append(f"{Path(path).name}({dets[-1].name})")
    tags = "ABCDEFGH"[: len(names)]
    print("  /  ".join(f"모델 {t}: {n}" for t, n in zip(tags, names, strict=True)) + "  (A 가 기준)")
    args.out.mkdir(parents=True, exist_ok=True)

    rt = cfg.runtime
    sources = {}
    for cam in cams:
        if args.replay:
            sources[cam.ip] = ReplaySource(args.replay / cam.ip)
        else:
            profile = cfg.camera_profiles[cam.profile]
            sources[cam.ip] = HttpSnapshotSource(cam, profile, rt.fetch_timeout_sec, rt.fetch_retries)

    presets = {"legacy": PRESETS["legacy"][0], "standard": PRESETS["standard"][0]}
    total = 0
    diff = {(k, p): 0 for k in range(1, len(dets)) for p in presets}
    times: list[list[float]] = [[] for _ in dets]
    for rnd in range(1, args.rounds + 1):
        for cam in cams:
            try:
                jpeg, _ = sources[cam.ip].fetch()
            except SourceError as e:
                print(f"{cam.ip}: 응답 없음 ({e})")
                continue
            if rnd == 1:  # 원본(선 없는 사진)은 첫 바퀴에 그대로 남긴다 (PC 에서 같은 사진으로 확인용)
                (args.out / f"{cam.ip}_raw.jpg").write_bytes(jpeg)
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                print(f"{cam.ip}: 이미지 디코딩 실패")
                continue
            boxes = []
            for k, det in enumerate(dets):
                b, t = detect_camera(det, img, cam, cfg)
                boxes.append(b)
                times[k].append(t)
            total += len(cam.slots)
            bad = []
            for pname, jcfg in presets.items():
                res = [judge(cam.slots, bx, jcfg) for bx in boxes]
                for k in range(1, len(res)):
                    nos = [no for no in res[0] if res[0][no].occupied != res[k][no].occupied]
                    diff[(k, pname)] += len(nos)
                    for no in nos:
                        sa, sb = ("차" if r[no].occupied else "빈" for r in (res[0], res[k]))
                        bad.append(f"{pname} {no}번 A={sa} {tags[k]}={sb}")
            counts = " / ".join(f"{t} {len(b)}" for t, b in zip(tags, boxes, strict=True))
            line = f"[{rnd}] {cam.ip}: 칸 {len(cam.slots)}개, 박스 {counts}"
            print(line + (" — 다름: " + ", ".join(bad) if bad else " — 같음"))
            if rnd == 1:
                for k, t in enumerate(tags):
                    sc = " ".join(f"{b.score:.2f}" for b in sorted(boxes[k], key=lambda b: -b.score))
                    print(f"    {t} 점수: {sc or '-'}  (사진 {img.shape[1]}x{img.shape[0]})")
            if bad:
                ref = cfg.camera_ref_size(cam)
                std = presets["standard"]
                pics = []
                for name, bx in zip(names, boxes, strict=True):
                    st = {no: r.occupied for no, r in judge(cam.slots, bx, std).items()}
                    pics.append(annotate(img, ref, cam.slots, st, bx, name))
                out = args.out / f"{cam.ip}_r{rnd}.jpg"
                pic = cv2.resize(np.hstack(pics), None, fx=0.5, fy=0.5)
                cv2.imwrite(str(out), pic, [cv2.IMWRITE_JPEG_QUALITY, 80])

    print()
    for k, name in enumerate(names):
        t = times[k][1:] or times[k]
        if t:
            print(f"{name}: 카메라 1대 추론 평균 {1000 * float(np.mean(t)):.0f}ms")
    for (k, pname), n in diff.items():
        if total:
            pct = 100 * (total - n) / total
            print(f"판정 {pname} A↔{tags[k]}: 칸 {total}개 중 다름 {n}개 (일치 {pct:.1f}%)")
    print(f"다른 칸 사진: {args.out}")


if __name__ == "__main__":
    main()
