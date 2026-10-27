"""기존 현장 YOLOv4(darknet) 검출기. PC 비교 도구 전용 (보드에서 쓰지 않음).

모델 폴더: model.json {"arch": "darknet", "input_size": [416, 416], "classes": ["car"]}
         + *.cfg + *.weights (기존 Jetson 파일 그대로)
OpenCV 4.x 가 필요하다 (5.x 에서 darknet 읽기가 빠짐): pip install "opencv-python-headless<5"
"""

from __future__ import annotations

import cv2

from ..core.geometry import Box
from .base import Detector, ModelPackage


class DarknetDetector(Detector):
    name = "darknet"

    def __init__(self, pkg: ModelPackage):
        if not hasattr(cv2.dnn, "readNetFromDarknet"):
            hint = 'pip install "opencv-python-headless<5"'
            raise RuntimeError(f"OpenCV {cv2.__version__} 은 darknet 을 읽지 못합니다: {hint}")
        cfg = next(pkg.path.glob("*.cfg"))
        weights = next(pkg.path.glob("*.weights"))
        self.classes = pkg.classes
        self.model = cv2.dnn.DetectionModel(cv2.dnn.readNetFromDarknet(str(cfg), str(weights)))
        self.model.setInputParams(size=tuple(pkg.input_size), scale=1 / 255, swapRB=True)

    def detect(self, image_bgr, conf, nms_iou, source_key=None):
        low = min(conf.values(), default=1.0)
        ids, scores, boxes = self.model.detect(image_bgr, confThreshold=low, nmsThreshold=nms_iou)
        out = []
        for c, s, (x, y, w, h) in zip(np_ravel(ids), np_ravel(scores), boxes, strict=False):
            name = self.classes[int(c)] if int(c) < len(self.classes) else str(int(c))
            if s >= conf.get(name, 1.1):
                out.append(Box(float(x), float(y), float(x + w), float(y + h), float(s), name))
        return out


def np_ravel(a):
    return [] if a is None or len(a) == 0 else list(a.ravel())
