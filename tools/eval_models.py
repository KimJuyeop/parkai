"""라벨이 있는 화면(darknet 형식: jpg + 같은 이름 txt)으로 모델들의 기준값별 정밀도·재현율을 잰다.

    python tools/eval_models.py split/test \\
        --model onnx=models/st_yoloxn_car_480 --model tflite=models/st_yoloxn_car_480_pt \\
        --conf 0.3 0.4 0.5 0.6 0.7 --nms 0.45

- 정답은 txt 의 박스(자동 라벨이면 YOLOv4 박스). IoU 0.5 이상이면 맞춘 것으로 센다
- 정밀도 = 낸 박스 중 맞은 비율, 재현율 = 정답 중 찾은 비율
- 차량 인식 기준값(설정의 classes.car.conf)을 고르는 데 쓴다
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
from tools.compare_models import match  # noqa: E402


def load_labels(txt: Path, w: int, h: int) -> np.ndarray:
    rows = []
    if txt.exists():
        for line in txt.read_text().split("\n"):
            p = line.split()
            if len(p) == 5:
                _, cx, cy, bw, bh = map(float, p)
                rows.append([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
    return np.array(rows, np.float32).reshape(-1, 4)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data", type=Path)
    ap.add_argument("--model", action="append", required=True, help="백엔드=모델폴더 (예: onnx=models/x)")
    ap.add_argument("--conf", type=float, nargs="+", default=[0.3, 0.4, 0.5, 0.6, 0.7])
    ap.add_argument("--nms", type=float, default=0.45, help="겹친 박스 제거 기준 (IoU)")
    args = ap.parse_args()

    images = sorted(p for p in args.data.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    data = []
    for p in images:
        img = cv2.imread(str(p))
        h, w = img.shape[:2]
        data.append((img, load_labels(p.with_suffix(".txt"), w, h)))
    n_gt = sum(len(g) for _, g in data)
    print(f"화면 {len(data)}개, 정답 박스 {n_gt}개\n")
    print(f"{'모델':<34} {'기준값':>6} {'정밀도':>7} {'재현율':>7} {'F1':>6} {'오검출':>6} {'놓침':>5}")

    low = min(args.conf)
    for spec in args.model:
        backend, path = spec.split("=", 1)
        det = load_detector(backend, path)
        preds, t = [], []
        for img, _ in data:
            t0 = time.perf_counter()
            bs = det.detect(img, {"car": low}, args.nms)
            t.append(time.perf_counter() - t0)
            preds.append(np.array([[b.x1, b.y1, b.x2, b.y2, b.score] for b in bs], np.float32).reshape(-1, 5))
        for c in args.conf:
            tp = fp = fn = 0
            for (_, gt), pr in zip(data, preds, strict=True):
                pr = pr[pr[:, 4] >= c][:, :4]
                hr, hp = match(gt, pr)
                tp, fp, fn = tp + hp, fp + len(pr) - hp, fn + len(gt) - hr
            prec = tp / max(tp + fp, 1)
            rec = (n_gt - fn) / max(n_gt, 1)
            f1 = 2 * prec * rec / max(prec + rec, 1e-9)
            name = f"{backend}:{Path(path).name}"
            row = f"{prec * 100:>6.1f}% {rec * 100:>6.1f}% {f1 * 100:>5.1f} {fp:>6} {fn:>5}"
            print(f"{name:<34} {c:>6.2f} {row}")
        print(f"{'':<34} 화면당 {1000 * float(np.mean(t[1:])):.0f}ms (이 PC CPU)\n")


if __name__ == "__main__":
    main()
