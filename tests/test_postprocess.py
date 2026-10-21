import numpy as np

from parkai.backends.base import ModelPackage
from parkai.postprocess import get_postprocessor


def test_yolox_decoded_output_with_nms():
    pkg = ModelPackage(
        path=None, arch="yolox", input_size=(416, 416), classes=["car"], extra={"decoded": True}
    )
    pred = np.zeros((1, 3, 6), np.float32)
    pred[0, 0] = [100, 100, 40, 40, 0.9, 1.0]  # 차량
    pred[0, 1] = [102, 101, 40, 40, 0.8, 1.0]  # 같은 차량 중복 -> NMS로 제거
    pred[0, 2] = [300, 300, 40, 40, 0.2, 1.0]  # 신뢰도 미달
    boxes = get_postprocessor("yolox")([pred], pkg, {"car": 0.45}, 0.45)
    assert len(boxes) == 1
    b = boxes[0]
    assert (round(b.x1), round(b.y1), round(b.x2), round(b.y2)) == (80, 80, 120, 120)
