#!/usr/bin/env bash
# 설정 여러 개를 차례로 학습하고 보드용 TFLite per-tensor 로 양자화한다 (학습 노트북 WSL).
#
#   nohup bash tools/train/train_and_quantize.sh st_full st_square2 > ~/work/train.log 2>&1 &
#
# - 설정 파일: ~/work/config/<이름>.yaml (CONFIG_DIR 로 바꿀 수 있음)
# - 결과: <OUT_DIR>/<이름>.tflite (기본 /mnt/c/st_yoloxn, 윈도우 C:\st_yoloxn)
# - 학습(training)과 평가+양자화(chain_eqe)를 두 번에 나눠 돌린다 (docs/training.md 5절)
set -euo pipefail

CONFIG_DIR=${CONFIG_DIR:-$HOME/work/config}
OUT_DIR=${OUT_DIR:-/mnt/c/st_yoloxn}
ZOO=${ZOO:-$HOME/st_train/stm32ai-modelzoo-services/object_detection}

. "$HOME/st_train/venv/bin/activate"
cd "$ZOO"
for c in "$@"; do
  echo "== $c 학습 시작 $(date '+%H:%M')"
  python stm32ai_main.py --config-path "$CONFIG_DIR" --config-name "$c" operation_mode=training
  m=$(realpath "$(ls -t tf/src/experiments_outputs/*/saved_models/best_model.keras | head -1)")
  echo "== $c 평가+양자화: $m"
  python stm32ai_main.py --config-path "$CONFIG_DIR" --config-name "$c" operation_mode=chain_eqe \
    model.model_path="$m" quantization.quantizer=TFlite_converter quantization.granularity=per_tensor
  q=$(ls -td tf/src/experiments_outputs/*/quantized_models | head -1)
  mkdir -p "$OUT_DIR"
  cp "$q/quantized_model.tflite" "$OUT_DIR/$c.tflite"
  echo "== $c 끝 $(date '+%H:%M') → $OUT_DIR/$c.tflite"
done
