#!/usr/bin/env bash
# 학습 환경 설치 (WSL2 Ubuntu 22.04, NVIDIA GPU). 한 번만 실행한다.
#
#   bash tools/train/setup_wsl.sh            # ~/st_train 아래에 설치
#
# 전제: 윈도우에 NVIDIA 드라이버가 깔려 있다 (WSL 안에는 드라이버를 깔지 않는다).
#       WSL 안에서 `nvidia-smi` 가 GPU를 보여야 한다.
set -euo pipefail

BASE=${ST_TRAIN_DIR:-$HOME/st_train}
ZOO_COMMIT=a07f68a173bb42169e0dea9dbe0ae3a73f9e35a3   # stm32ai-modelzoo-services (2026-10-07), 검증한 버전
PRE=object_detection/st_yoloxn/ST_pretrainedmodel_public_dataset/coco_2017_80_classes/st_yoloxn_d100_w025_480
MODELZOO_COMMIT=1423c78953a830903485135febe1dd98ff31aed8   # stm32ai-modelzoo (사전학습 모델)
PRE_SHA=d76686df31f61d0cb93d676cd269a80aa65dfaed3eb4948aa24e0fba13242825

echo "[1/5] GPU 확인"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader \
  || { echo "WSL에서 GPU가 안 보입니다. 윈도우 NVIDIA 드라이버를 최신으로 설치하세요."; exit 1; }

echo "[2/5] Python 3.12 (Model Zoo 요구 버전)"
if ! command -v python3.12 >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt-get update
  sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
fi
sudo apt-get install -y git git-lfs libgl1 libglib2.0-0

echo "[3/5] ST Model Zoo services ($ZOO_COMMIT)"
mkdir -p "$BASE"
cd "$BASE"
if [ ! -d stm32ai-modelzoo-services ]; then
  git clone https://github.com/STMicroelectronics/stm32ai-modelzoo-services.git
fi
git -C stm32ai-modelzoo-services fetch -q origin
git -C stm32ai-modelzoo-services checkout -q "$ZOO_COMMIT"

echo "[4/5] 가상환경 + 패키지 (몇 GB, 시간이 걸린다)"
python3.12 -m venv "$BASE/venv"
. "$BASE/venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r stm32ai-modelzoo-services/requirements.txt
pip install -q "tensorflow[and-cuda]==2.18.0"   # 리눅스(WSL)에서 GPU 사용
python - <<'PY'
import tensorflow as tf
gpus = tf.config.list_physical_devices("GPU")
print("TensorFlow", tf.__version__, "GPU:", gpus)
assert gpus, "TensorFlow 가 GPU 를 못 찾았습니다"
PY

echo "[5/5] 출발점 모델 (ST 사전학습 st_yoloxn COCO 80, 480)"
mkdir -p "$BASE/pretrained"
URL="https://raw.githubusercontent.com/STMicroelectronics/stm32ai-modelzoo/$MODELZOO_COMMIT/$PRE/st_yoloxn_d100_w025_480.keras"
curl -fL -o "$BASE/pretrained/st_yoloxn_d100_w025_480.keras" "$URL"
echo "$PRE_SHA  $BASE/pretrained/st_yoloxn_d100_w025_480.keras" | sha256sum -c -

echo "완료: $BASE  (활성화: . $BASE/venv/bin/activate)"
