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
- **렌즈 원본**을 쓴다. 렌즈 2개 카메라는 Jetson 이 저장한 `*.jpgleft.jpg` / `*.jpgright.jpg`(1280×720)가 원본이고,
  같은 이름의 `*.jpg`(1280×960)는 두 렌즈를 640×480 으로 줄여 붙인 합친 사진이라 쓰지 않는다 (autolabel 이 건너뜀).
- 학습 화면은 판정 화면(parkai 프로필의 분석 영역)과 같게 자른다: `--views full`(렌즈 사진 전체) 또는
  `--views square2`(가운데가 겹치는 정사각형 두 조각). **full 을 쓴다** (아래 비교).

렌즈 원본 학습(2026-10-30, 카메라 451대, 카메라 단위 361/45/45), per-channel ONNX, 38대 231칸 정답표:

| 입력 | 시험 mAP (float) | standard 틀린 칸 | legacy 틀린 칸 | 렌즈당 추론 |
| --- | --- | --- | --- | --- |
| YOLOv4 (기존, 참고) | - | 1 | 4 | - |
| full | 98.1 | 1 (.66 #2) | 7 | 1회 |
| square2 | 98.8 | 2 (.66 #2, .77 #6) | 5 | 2회 |

- 틀린 칸은 모두 '빈칸을 차로'이고 놓친 차는 없다. .66 #2 는 선분 위치 문제(모든 ST 모델 공통)
- square2 는 두 조각 경계(렌즈 가로 560~720px)에서 잘린 박스가 남는다 (박스 265개 중 42개, full 192개).
  잘린 박스가 옆 칸을 덮을 수 있고 추론도 2배라 full 로 정했다
- 38대 카메라 사진 일부가 학습 폴더에도 있어 절대 점수는 낙관적이다 (두 방식 상대 비교는 공정)
- 첫 학습(2026-10-26)은 렌즈 원본을 다시 좌우로 잘라(반쪽 화면) 학습했고, 판정은 합친 사진의 640×480 화면으로 해서
  학습과 판정 화면이 달랐다 (시험 세트의 62%가 반쪽 화면).
- 만차, 빈칸 많을 때, 시간대를 섞는다. 처음엔 2,000~5,000장

## 2. 자동 라벨링 (윈도우 또는 WSL, GPU 불필요)

darknet 모델은 OpenCV 4.x 에서만 읽힌다.

```sh
python -m venv .venv-label && . .venv-label/bin/activate      # 윈도우: .venv-label\Scripts\activate
pip install "opencv-python-headless<5" numpy
python tools/autolabel.py 사진 --cfg yolo.cfg --weights yolov4_best.weights --out dataset --views full --preview
```

- `dataset/preview/` 를 훑어본다. `review.txt` 에 애매한 화면 목록이 있다.
- 고칠 게 있으면 Label Studio 로 `dataset` 을 YOLO 형식으로 가져와 수정한다 (autolabel.py 설명 참고).

## 3. 학습/검증/시험 나누기

```sh
python tools/train/split_dataset.py dataset --out dataset_split
```

같은 카메라(파일 이름의 IP)의 화면은 학습/검증/시험 중 한쪽에만 들어간다 (`--group camera`, 기본).

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

보드 목표(카메라 30대 x 화면 2개, 10초 사이클)에는 per-channel(60화면 x 118ms = 7초)이 빠듯해서 per-tensor 를 쓴다.

parkai 후처리로 잰 시험 198화면 (정답 745대, `tools/eval_models.py`, 기준값 0.5):

| 모델 | NMS 0.45 정밀도/재현율 | NMS 0.3 정밀도/재현율 |
| --- | --- | --- |
| ONNX per-channel | 92.2 / 98.8 | 94.8 / 97.2 |
| TFLite per-tensor | 63.2 / 98.3 | 87.0 / 96.2 |

per-tensor 의 오검출은 대부분 한 차에 박스가 두 개 겹치거나 차보다 크게(두 대에 걸쳐) 나온 박스다.
'차가 없는 곳' 박스(NMS 0.3 에서 33개)는 대부분 YOLOv4 라벨이 놓친 화면 끝 잘린 차·오토바이다.
원인은 출력 합치기(concat)가 아니라 (per-channel ONNX 도 출력 눈금은 하나로 같다) 가중치 전체를 텐서당 눈금 하나로
양자화해서 생기는 차량 점수(obj) 흔들림이다 (ONNX 와 비교해 obj 로짓 평균 1.2~1.5 차이, 상자 크기는 0.1~0.2).
ST 의 per-tensor 최적화(`+quantization.optimize=true`: BN 접기, 층간 균등화 CLE, 클립)는 효과가 없었다
(Model Zoo 평가 66.0 / 96.0 / 94.9, 2026-10-27). setup_wsl.sh 가 이 기능의 Model Zoo 버그(model.input 이 list)는 고쳐 둔다.
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
