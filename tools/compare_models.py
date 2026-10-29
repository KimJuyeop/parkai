"""학습한 모델을 현장 YOLOv4 와 같은 사진으로 비교한다.

    python tools/compare_models.py <사진 폴더> --model models/st_yoloxn_car_480 \\
        --cfg yolo.cfg --weights yolov4_best.weights --out compare

- 판정과 같은 단위로 자른 화면마다 두 모델을 돌린다 (autolabel.py 와 같은 자르기)
- YOLOv4 를 정답으로 보고, 학습 모델이 그 차를 몇 % 찾았는지(찾음)와
  YOLOv4 에 없는 박스를 몇 % 냈는지(잘못 찾음)를 센다 (IoU 0.5 기준)
- compare/*.jpg: 왼쪽 YOLOv4(초록), 오른쪽 학습 모델(빨강).
  파일 이름 앞에 놓친 수(miss03__…)가 붙어 정렬하면 모아 볼 수 있다

필요: OpenCV 4.x (darknet), onnxruntime
    pip install "opencv-python-headless<5" numpy onnxruntime
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parkai.backends import load_detector  # noqa: E402
from tools.autolabel import IMAGE_EXT, views_for  # noqa: E402


def iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a (N,4), b (M,4) xyxy -> (N,M)"""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


def match(ref: np.ndarray, pred: np.ndarray, thr: float = 0.5) -> tuple[int, int]:
    """(ref 중 찾은 수, pred 중 ref 와 맞은 수) — 한 박스는 한 번만 짝짓는다."""
    m = iou(ref, pred)
    hit_ref = hit_pred = 0
    used = set()
    for i in np.argsort(-m.max(1)) if m.size else []:
        j = int(m[i].argmax())
        if m[i, j] >= thr and j not in used:
            used.add(j)
            hit_ref += 1
    hit_pred = len(used)
    return hit_ref, hit_pred


def draw(img: np.ndarray, boxes: np.ndarray, color: tuple[int, int, int], label: str) -> np.ndarray:
    out = img.copy()
    for x1, y1, x2, y2 in boxes.astype(int):
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
    cv2.rectangle(out, (0, 0), (len(label) * 11 + 10, 26), (0, 0, 0), -1)
    cv2.putText(out, label, (5, 19), 0, 0.6, (255, 255, 255), 2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path)
    ap.add_argument("--model", type=Path, required=True, help="parkai 모델 폴더 (model.json + model.onnx)")
    ap.add_argument("--cfg", type=Path, required=True)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("compare"))
    ap.add_argument("--conf", type=float, default=0.45, help="두 모델 공통 차량 기준값")
    ap.add_argument("--views", default="full", help="full | square2 | x,y,w,h;… (autolabel.py 와 같음)")
    args = ap.parse_args()

    net = cv2.dnn.readNetFromDarknet(str(args.cfg), str(args.weights))
    teacher = cv2.dnn.DetectionModel(net)
    teacher.setInputParams(size=(416, 416), scale=1 / 255, swapRB=True)
    student = load_detector("onnx", args.model)
    args.out.mkdir(parents=True, exist_ok=True)

    tot_ref = tot_pred = hit_ref = hit_pred = 0
    t_student: list[float] = []
    files = sorted(p for p in args.src.rglob("*") if p.suffix.lower() in IMAGE_EXT)
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            continue
        h, w = img.shape[:2]
        for vi, (x, y, vw, vh) in enumerate(views_for(w, h, args.views)):
            v = img[y : y + vh, x : x + vw]
            if v.mean() < 10:
                continue
            _, _, tb = teacher.detect(v, confThreshold=args.conf, nmsThreshold=0.45)
            ref = np.array([[bx, by, bx + bw, by + bh] for bx, by, bw, bh in tb], np.float32).reshape(-1, 4)
            t0 = time.perf_counter()
            sb = student.detect(v, {"car": args.conf}, 0.45)
            t_student.append(time.perf_counter() - t0)
            pred = np.array([[b.x1, b.y1, b.x2, b.y2] for b in sb], np.float32).reshape(-1, 4)
            hr, hp = match(ref, pred)
            tot_ref, tot_pred, hit_ref, hit_pred = (
                tot_ref + len(ref),
                tot_pred + len(pred),
                hit_ref + hr,
                hit_pred + hp,
            )
            missed = len(ref) - hr
            pair = np.hstack(
                [
                    draw(v, ref, (0, 200, 0), f"YOLOv4 {len(ref)}"),
                    draw(v, pred, (0, 0, 255), f"new {len(pred)} (miss {missed}, extra {len(pred) - hp})"),
                ]
            )
            name = f"miss{missed:02d}__{'__'.join(f.relative_to(args.src).with_suffix('').parts)}_v{vi}.jpg"
            cv2.imwrite(str(args.out / name), pair, [cv2.IMWRITE_JPEG_QUALITY, 85])

    found = 100 * hit_ref / max(tot_ref, 1)
    extra = 100 * (tot_pred - hit_pred) / max(tot_pred, 1)
    ms = 1000 * float(np.mean(t_student[1:] or t_student)) if t_student else 0.0
    print(f"YOLOv4 차량 {tot_ref}대 중 학습 모델이 찾음 {hit_ref}대 ({found:.1f}%)")
    print(f"학습 모델 박스 {tot_pred}개 중 YOLOv4 에 없는 박스 {tot_pred - hit_pred}개 ({extra:.1f}%)")
    print(f"학습 모델 화면당 {ms:.0f}ms (이 PC CPU)  ·  비교 사진: {args.out}")


if __name__ == "__main__":
    main()
