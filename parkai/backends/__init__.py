"""추론 백엔드.

- stai   : 보드 NPU (X-LINUX-AI stai_mpu, .nb)
- onnx   : PC 개발용 (onnxruntime, .onnx)
- fixture: 모델 없이 이미지 옆 JSON의 박스를 그대로 돌려줌 (판정/파이프라인 개발용)
"""

from __future__ import annotations

from .base import Detector, ModelPackage, load_detector

__all__ = ["Detector", "ModelPackage", "load_detector"]
