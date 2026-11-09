"""마지막 출력 층만 float 로 두고 나머지는 NPU 용 per-tensor int8 로 양자화한다 (학습 노트북 WSL).

    python quantize_head_float.py best_model.keras ~/work/split_full/train out.tflite

왜: yolov2t 는 박스 위치·크기·물체 점수 30채널을 출력 층 하나로 낸다. 전부 int8 이면 이 30채널이
눈금 하나를 같이 써서(학습이 잘될수록 물체 점수 범위가 커져 눈금이 거칠어짐) 박스 크기가 뭉개진다.
앵커를 고친 yolov2t 차량 모델은 이 눈금이 0.5 (박스 크기 1.6배 단위)였고 mAP 가 float 98.1 → int8 69.8.
출력 층은 15x15 격자 x 30채널이라 계산이 아주 작아 NPU 밖에서 돌아도 속도 손해가 적다.

- Model Zoo venv 에서 실행. 입력 uint8 (1/255, 0), 출력 float32
- 전처리는 학습 설정과 같다 (rgb, fit, nearest, /255)
- 보정 사진: 폴더 아래 *.jpg 에서 고르게 --n 장 (기본 200)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf
from tensorflow.lite.python import convert
from tensorflow.python.framework import dtypes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("model", type=Path, help="float 모델 (best_model.keras)")
    ap.add_argument("images", type=Path, help="보정용 사진 폴더 (학습 사진)")
    ap.add_argument("out", type=Path, help="결과 .tflite")
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()

    m = tf.keras.models.load_model(args.model, compile=False)
    h, w = m.input_shape[1:3]
    paths = sorted(p for p in args.images.rglob("*.jpg"))
    if not paths:
        raise SystemExit(f"사진이 없습니다: {args.images}")
    paths = paths[:: max(1, len(paths) // args.n)][: args.n]

    def rep():
        for p in paths:
            im = cv2.imread(str(p))
            if im is None:
                continue
            im = cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2RGB), (w, h), interpolation=cv2.INTER_NEAREST)
            yield [im[None].astype(np.float32) / 255]

    # 1) 보정만 (각 층 값의 범위를 잰다)
    c = tf.lite.TFLiteConverter.from_keras_model(m)
    c.optimizations = [tf.lite.Optimize.DEFAULT]
    c.representative_dataset = rep
    c._experimental_calibrate_only = True
    calibrated = c.convert()

    # 2) 마지막 합성곱(출력 층)을 찾아 그 층만 양자화에서 뺀다
    it = tf.lite.Interpreter(model_content=calibrated)
    it.allocate_tensors()
    convs = [o for o in it._get_ops_details() if o["op_name"] == "CONV_2D"]
    head = it.get_tensor_details()[convs[-1]["outputs"][0]]["name"]
    q = convert.mlir_quantize(
        calibrated,
        disable_per_channel=True,  # NPU 용 per-tensor
        fully_quantize=False,  # 뺀 층은 float 로 남긴다
        input_data_type=dtypes.uint8,
        output_data_type=dtypes.float32,
        denylisted_nodes=[head],
    )
    args.out.write_bytes(q)

    # 확인: 입력 형식과 마지막 연산들
    it2 = tf.lite.Interpreter(model_content=q)
    it2.allocate_tensors()
    d = it2.get_input_details()[0]
    ops = [o["op_name"] for o in it2._get_ops_details()]
    n_int8 = sum(1 for t in it2.get_tensor_details() if t["dtype"] == np.int8)
    print(f"보정 사진 {len(paths)}장, 출력 층 '{head}' 만 float")
    print(f"입력 {d['dtype'].__name__} {d['quantization']}, 마지막 연산 {ops[-3:]}, int8 텐서 {n_int8}개")
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
