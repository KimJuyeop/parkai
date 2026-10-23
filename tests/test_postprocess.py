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


def test_st_yoloxn_anchor_decode_nchw():
    """ST Model Zoo st_yoloxn: 앵커 3개 x (5+C), NCHW 출력 3개. class_map 으로 truck 을 car 로 판단."""
    names = ["person", "car", "truck"]
    pkg = ModelPackage(
        path=None,
        arch="st_yoloxn",
        input_size=(480, 480),
        classes=names,
        extra={"anchors": [[0.5, 0.5], [0.07, 0.25], [0.23, 0.7]], "class_map": {"truck": "car"}},
    )
    na, nc = 3, len(names)
    outs = []
    for g in (60, 30, 15):
        t = np.full((1, na * (5 + nc), g, g), -10.0, np.float32)  # 모두 점수 거의 0
        outs.append(t)
    # 15x15 격자 (7, 7) 칸, 앵커 0 에 truck 하나: 중심 = (0.5+7)/15*480 = 240, 크기 = exp(0)*0.5*480 = 240
    t = outs[2]
    base = 0 * (5 + nc)
    t[0, base + 0, 7, 7] = 0.0
    t[0, base + 1, 7, 7] = 0.0
    t[0, base + 2, 7, 7] = 0.0
    t[0, base + 3, 7, 7] = 0.0
    t[0, base + 4, 7, 7] = 10.0  # obj
    t[0, base + 5 + 2, 7, 7] = 10.0  # truck
    boxes = get_postprocessor("st_yoloxn")(outs, pkg, {"car": 0.5}, 0.45)
    assert len(boxes) == 1
    b = boxes[0]
    assert b.cls == "car"
    assert (round(b.x1), round(b.y1), round(b.x2), round(b.y2)) == (120, 120, 360, 360)
    # car 기준값이 없으면(설정에 없는 클래스) 아무것도 안 나온다
    assert get_postprocessor("st_yoloxn")(outs, pkg, {}, 0.45) == []
