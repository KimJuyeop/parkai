# 차량 검출 모델 학습 (st_yoloxn)

ST 사전학습 모델을 그대로 쓰면 현장 시점(천장 광각)의 차를 대부분 놓친다. 현장 사진으로 추가 학습한다.
정답 박스는 기존 현장 YOLOv4가 자동으로 만든다. 사람이 박스를 그리지 않는다.

```
현장 사진 ─▶ autolabel.py (YOLOv4) ─▶ split_dataset.py ─▶ ST Model Zoo 학습 ─▶ ONNX int8 ─▶ (보드 NPU .nb 변환)
```

학습 PC: 윈도우 + WSL2 Ubuntu 22.04, RTX 4070 Laptop 8GB.
TensorFlow 2.11 이후는 윈도우에서 직접 GPU를 쓰지 못해서 WSL 안에서 학습한다.

## 1. 사진 모으기

- 현장별 폴더: `사진/<현장>/<카메라IP>/*.jpg` (카메라 폴더까지 나누면 학습/시험을 카메라 단위로 나눌 수 있다)
- 카메라 원본 스냅샷 그대로. 1280×720, 1280×960 모두
- 만차, 빈칸 많을 때, 시간대를 섞는다. 처음엔 2,000~5,000장

## 2. 자동 라벨링 (윈도우 또는 WSL, GPU 불필요)

darknet 모델은 OpenCV 4.x 에서만 읽힌다.

```sh
python -m venv .venv-label && . .venv-label/bin/activate      # 윈도우: .venv-label\Scripts\activate
pip install "opencv-python-headless<5" numpy
python tools/autolabel.py 사진 --cfg yolo.cfg --weights yolov4_best.weights --out dataset --preview
```

- `dataset/preview/` 를 훑어본다. `review.txt` 에 애매한 화면 목록이 있다.
- 고칠 게 있으면 Label Studio 로 `dataset` 을 YOLO 형식으로 가져와 수정한다 (autolabel.py 설명 참고).

## 3. 학습/검증/시험 나누기

```sh
python tools/train/split_dataset.py dataset --out dataset_split --by-folder
```

`--by-folder`: 같은 카메라 사진은 한쪽에만 들어간다. 카메라 폴더가 적으면 빼고 실행한다.

## 4. 학습 환경 설치 (WSL, 한 번)

윈도우에 NVIDIA 드라이버만 최신으로 깔려 있으면 된다 (WSL 안에는 드라이버를 깔지 않는다).

```sh
bash tools/train/setup_wsl.sh          # ~/st_train 에 Model Zoo, 가상환경, 출발점 모델
```

끝에 `TensorFlow 2.18.0 GPU: [...]` 가 보이면 정상.

## 5. 학습

`tools/train/st_yoloxn_finetune.yaml` 을 복사해 `<HOME>`, `<SPLIT>` 경로를 바꾼다.
WSL 에서 윈도우 폴더는 `/mnt/c/Users/...` 로 보인다 (사진이 많으면 WSL 홈으로 복사하는 게 빠르다).

```sh
. ~/st_train/venv/bin/activate
cd ~/st_train/stm32ai-modelzoo-services/object_detection
# 1) 학습
python stm32ai_main.py --config-path /path/to/config --config-name st_yoloxn_finetune
# 2) 평가 → ONNX int8 양자화 → 양자화 모델 평가
# 학습 결과(best_model.keras)가 있는 가장 최근 폴더 (평가 실행도 폴더를 만들어서 단순히 최신 폴더를 고르면 안 된다)
OUT=$(dirname "$(ls -t tf/src/experiments_outputs/*/saved_models/best_model.keras | head -1)")/..
python stm32ai_main.py --config-path /path/to/config --config-name st_yoloxn_finetune \
  operation_mode=chain_eqe model.model_path=$(realpath $OUT)/saved_models/best_model.keras
```

두 번에 나누는 이유: Model Zoo 는 학습과 평가를 한 번(chain_tqe)에 돌리면 darknet_yolo 시험 세트를
변환하지 않아 `test_path 'None'` 오류로 멈춘다.

결과: 1번 폴더의 `saved_models/best_model.keras`, 2번 폴더의 `quantized_models/*.onnx` 와 평가 점수(mAP).

## 6. 확인 → parkai 모델 패키지

1. PC 확인용: 양자화된 `.onnx` 를 `models/st_yoloxn_car_480/model.onnx` 로, 보드용: `.nb` 를 `model.nb` 로
2. `model.json` 은 이미 있다 (입력 NCHW float, 출력 3개 NCHW, 1클래스)
3. 같은 사진으로 YOLOv4 와 비교: `python tools/compare_models.py <사진> --model models/st_yoloxn_car_480 --cfg ... --weights ...`

첫 학습(2026-10-26): 카메라 993대 x 1장, 150회 57분. 시험 198화면 mAP 99.0% (int8 98.3%).
샘플 12장 비교: YOLOv4 차량 89대 중 88대 찾음, YOLOv4 에 없는 박스 6.4% (학습 전 ST 모델 50.6% / 44.4%).

## 7. 보드 NPU 용 변환 (.nb)

ST Edge AI Core 는 MP2 모듈이 있는 2.2.0 을 쓴다 (3.x, 4.x 에는 MP2 모듈이 없다).

```sh
QT_QPA_PLATFORM=offscreen ./stedgeai-linux-onlineinstaller --root $HOME/ST/STEdgeAI \
  --accept-licenses --default-answer --confirm-command install stedgeai0202 stedgeai0202.stm32mpu
$HOME/ST/STEdgeAI/2.2/Utilities/linux/stedgeai generate --model quantized_model.tflite --target stm32mp25 --output out
```

양자화는 TFLite per-tensor (학습 설정 기본값). 보드 x-linux-ai-benchmark 결과 (480x480, 2026-10-27):

| 양자화 | .nb 변환 | 1회 추론 | NPU | 시험 198화면 정밀도/재현율/mAP |
| --- | --- | --- | --- | --- |
| ONNX per-channel | 됨 | 118.5ms | 6% (GPU 94%) | 94.8 / 96.4 / 98.3 |
| ONNX per-tensor | 실패 (E010) | - | - | 74.1 / 96.6 / 95.8 |
| TFLite per-tensor | 됨 | 21.6ms | 98.7% | 72.5 / 96.1 / 94.5 |

per-tensor 는 엉뚱한 박스(정밀도)가 늘어 차량 인식 기준값을 현장 사진으로 다시 맞춘다.
보드용 .nb 는 입력 NHWC uint8 (PC 용 model.onnx 는 NCHW float) — 백엔드가 .nb 에서 직접 읽는다.

## 라벨 기준 (Label Studio 로 고칠 때도 같게)

- 박스는 보이는 차체 전체에 딱 맞게 (범퍼·미러·바퀴 바깥에 가장자리가 닿게). 여유도, 줄이기도 하지 않는다.
- 가려지거나 화면 끝에 잘린 차는 보이는 부분만.
- 화면에 보이는 차는 옆 칸·뒤쪽 차까지 전부 친다. 판정할 칸은 parkai 칸 선분이 고른다.
  (옆 차를 빼면 '차인데 차 아님'을 배워서 판정 칸의 차까지 덜 잡는다)
- 사람도 알아보기 힘든 아주 작은 먼 차는 빼도 되지만, 항상 같은 기준으로.
- 가장 중요한 것은 일관성. 비스듬한 각도에서 박스가 옆 칸 선분을 덮는 문제는 모델이 아니라
  판정(개선 방식: 덮인 비율 + 한 박스는 가장 잘 맞는 칸에만)으로 막는다.

## 주의

- 전처리(1/255, fit, nearest, rgb)와 앵커는 학습 설정과 `model.json` 이 반드시 같아야 한다.
- 학습 PC(WSL2, RTX 4070 Laptop 8GB)에서 2026-10-26 검증. setup_wsl.sh 에 torch CPU판·평가 배치 8 패치 포함.
