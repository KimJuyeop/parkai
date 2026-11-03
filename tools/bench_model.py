"""모델 하나의 단계별 시간을 잰다 (보드에서 NPU/GPU 속도 확인용).

    M=/var/lib/parkai/models
    ./venv/bin/python tools/bench_model.py $M/st_full_pc /tmp/parkai_compare/192.168.0.201_0_raw.jpg

- 전처리(크기 바꾸기·색 변환) / 입력 변환(정수화) / 실행(net.run) / 출력 읽기 / 후처리(디코딩·NMS) 로 나눈다
- 모델을 하나만 올려 반복하므로 compare_judge(두 모델을 번갈아 실행)보다 실제 워커에 가깝다
- 워커와 같이 돌면 시간이 섞이니 워커를 멈추고 잰다: systemctl stop parkai-worker
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("model", help="[백엔드=]모델폴더")
    ap.add_argument("image", type=Path, help="렌즈 사진 한 장")
    ap.add_argument("-n", type=int, default=30, help="반복 횟수 (처음 3번은 빼고 평균)")
    ap.add_argument("--conf", type=float, default=0.45)
    args = ap.parse_args()

    backend, path = args.model.split("=", 1) if "=" in args.model else ("auto", args.model)
    det = load_detector(backend, path)
    img = cv2.imread(str(args.image))
    if img is None:
        sys.exit(f"사진을 읽지 못했습니다: {args.image}")

    steps = ("전처리", "입력 변환", "실행", "출력 읽기", "후처리", "합계")
    t: dict[str, list[float]] = {k: [] for k in steps}
    net = getattr(det, "net", None)
    if net is not None:  # stai: net.run 과 출력 읽기를 따로 잰다
        run, get_output = net.run, net.get_output

        def timed_run():
            s = time.perf_counter()
            run()
            t["실행"].append(time.perf_counter() - s)

        def timed_get(*a, **k):
            s = time.perf_counter()
            o = get_output(*a, **k)
            t["출력 읽기"][-1] += time.perf_counter() - s
            return o

        net.run, net.get_output = timed_run, timed_get

    n_boxes = 0
    for _ in range(args.n):
        s0 = time.perf_counter()
        tensor, lb = det.preprocess(img)
        s1 = time.perf_counter()
        t["출력 읽기"].append(0.0)
        outs = det._run(tensor)
        s2 = time.perf_counter()
        boxes = det.post(outs, det.pkg, {"car": args.conf}, 0.45)
        s3 = time.perf_counter()
        t["전처리"].append(s1 - s0)
        t["후처리"].append(s3 - s2)
        t["합계"].append(s3 - s0)
        if net is not None:
            t["입력 변환"].append((s2 - s1) - t["실행"][-1] - t["출력 읽기"][-1])
        else:
            t["실행"].append(s2 - s1)
        n_boxes = len(boxes)

    h, w = img.shape[:2]
    print(f"{Path(path).name} ({det.name}), 사진 {w}x{h}, {args.n}회, 박스 {n_boxes}개")
    for k, v in t.items():
        if len(v) > 3:
            print(f"  {k:6s} {1000 * float(np.mean(v[3:])):7.1f}ms")


if __name__ == "__main__":
    main()
