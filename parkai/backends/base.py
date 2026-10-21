"""모델 패키지와 검출기 인터페이스.

모델 패키지 폴더 구조:
    models/<name>/
        model.nb     보드 NPU용
        model.onnx   PC용 (같은 모델)
        model.json   {"arch": "yolox", "input_size": [416, 416], "classes": ["car"], ...}
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..core.geometry import Box, Letterbox


@dataclass
class ModelPackage:
    path: Path
    arch: str
    input_size: tuple[int, int]  # (w, h)
    classes: list[str]
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> ModelPackage:
        p = Path(path)
        meta = json.loads((p / "model.json").read_text(encoding="utf-8"))
        return cls(
            path=p,
            arch=meta["arch"],
            input_size=tuple(meta["input_size"]),
            classes=list(meta["classes"]),
            extra={k: v for k, v in meta.items() if k not in ("arch", "input_size", "classes")},
        )


class Detector(ABC):
    """화면 하나(BGR 이미지)를 받아 그 화면 좌표계의 박스를 돌려준다."""

    name = "base"

    @abstractmethod
    def detect(
        self, image_bgr: np.ndarray, conf: dict[str, float], nms_iou: float, source_key: str | None = None
    ) -> list[Box]: ...


class ModelDetector(Detector):
    """레터박스 전처리 + 백엔드 실행 + 구조별 후처리."""

    def __init__(self, pkg: ModelPackage):
        from ..postprocess import get_postprocessor

        self.pkg = pkg
        self.post = get_postprocessor(pkg.arch)

    @abstractmethod
    def _run(self, tensor: np.ndarray) -> list[np.ndarray]: ...

    def preprocess(self, image_bgr: np.ndarray) -> tuple[np.ndarray, Letterbox]:
        in_w, in_h = self.pkg.input_size
        h, w = image_bgr.shape[:2]
        lb = Letterbox.compute(w, h, in_w, in_h)
        resized = cv2.resize(image_bgr, (lb.new_w, lb.new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((in_h, in_w, 3), 114, dtype=np.uint8)
        x0, y0 = int(lb.pad_x), int(lb.pad_y)
        canvas[y0 : y0 + lb.new_h, x0 : x0 + lb.new_w] = resized
        if self.pkg.extra.get("color", "rgb") == "rgb":
            canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        return canvas, lb

    def detect(self, image_bgr, conf, nms_iou, source_key=None):
        tensor, lb = self.preprocess(image_bgr)
        outputs = self._run(tensor)
        boxes = self.post(outputs, self.pkg, conf, nms_iou)
        return [lb.to_source(b) for b in boxes]


def load_detector(backend: str, model_dir: str | Path | None) -> Detector:
    """backend: auto | stai | onnx | fixture"""
    if backend == "fixture":
        from .fixture import FixtureDetector

        return FixtureDetector()
    if model_dir is None:
        raise ValueError("모델이 지정되지 않았습니다")
    pkg = ModelPackage.load(model_dir)
    if backend == "auto":
        backend = "stai" if _on_board() else "onnx"
    if backend == "stai":
        from .stai import StaiDetector

        return StaiDetector(pkg)
    if backend == "onnx":
        from .onnx import OnnxDetector

        return OnnxDetector(pkg)
    raise ValueError(f"알 수 없는 백엔드: {backend}")


def _on_board() -> bool:
    try:
        compat = Path("/proc/device-tree/compatible").read_bytes()
    except OSError:
        return False
    return b"st,stm32mp25" in compat or os.environ.get("PARKAI_BACKEND") == "stai"
