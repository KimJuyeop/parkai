"""Keras 모델의 입력 크기를 바꿔 저장한다 (가중치는 그대로). 학습 노트북 WSL 의 Model Zoo venv 에서.

    python resize_keras_input.py yolov2t_416.keras yolov2t_480.keras 480

- ST Model Zoo 는 이어서 학습할 때 입력 크기를 모델 파일에서 읽는다 (설정의 input_shape 보다 우선).
  사전학습 yolov2t 는 416 뿐이라, 판정 모델과 같은 480 으로 학습하려면 먼저 바꿔 둔다
- 합성곱만 있는 모델(yolov2t, st_yoloxn)은 입력 크기와 상관없이 같은 가중치를 쓴다
"""

from __future__ import annotations

import sys

import keras


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src, dst, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
    m = keras.models.load_model(src, compile=False)
    cfg = m.get_config()
    first = cfg["layers"][0]["config"]
    key = "batch_shape" if "batch_shape" in first else "batch_input_shape"
    first[key] = [None, size, size, first[key][-1]]
    m2 = keras.Model.from_config(cfg)
    m2.set_weights(m.get_weights())
    m2.save(dst)
    print(f"{src} {m.input_shape} → {dst} {m2.input_shape}, 출력 {m2.output_shape}")


if __name__ == "__main__":
    main()
