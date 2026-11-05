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


def test_yolov2t_grid_anchor_decode_nhwc():
    """ST yolov2t: 출력 1개(NHWC), 앵커는 격자 단위 → 크기 = exp(tw) * 앵커 / 격자 수 * 입력."""
    anchors = [[0.076023, 0.258508], [0.748154, 0.857092]]
    pkg = ModelPackage(
        path=None,
        arch="yolov2t",
        input_size=(480, 480),
        classes=["car"],
        extra={"anchors": anchors, "anchor_units": "grid"},
    )
    g, na = 15, 2
    t = np.full((1, g, g, na * 6), -10.0, np.float32)
    # (y=3, x=10) 칸, 앵커 1: 중심 x = (0.5+10)/15*480 = 336, y = (0.5+3)/15*480 = 112
    # 크기 = exp(2) * 앵커 / 15 * 480
    base = 1 * 6
    t[0, 3, 10, base : base + 4] = [0, 0, 2.0, 2.0]
    t[0, 3, 10, base + 4] = 10.0
    t[0, 3, 10, base + 5] = 10.0
    boxes = get_postprocessor("yolov2t")([t], pkg, {"car": 0.5}, 0.45)
    assert len(boxes) == 1
    b = boxes[0]
    w, h = np.exp(2.0) * 0.748154 / 15 * 480, np.exp(2.0) * 0.857092 / 15 * 480
    assert abs((b.x1 + b.x2) / 2 - 336) < 1e-3 and abs((b.y1 + b.y2) / 2 - 112) < 1e-3
    assert abs((b.x2 - b.x1) - w) < 1e-3 and abs((b.y2 - b.y1) - h) < 1e-3


def test_stai_fast_input_matches_general_quantization():
    """보드 입력 변환의 빠른 길(그대로 / 비트 뒤집기)이 일반 양자화 식과 같은 값을 낸다."""
    from parkai.backends.stai import to_input

    rng = np.random.default_rng(0)
    x = rng.integers(0, 256, (1, 32, 32, 3), dtype=np.uint8)
    scale = float(np.float32(1 / 255))  # .nb 에 float32 로 저장된 눈금

    def general(a, dtype, zp):
        info = np.iinfo(dtype)
        v = a.astype(np.float32) / 255.0
        return np.clip(np.round(v / scale + zp), info.min, info.max).astype(dtype)

    nchw = x.transpose(0, 3, 1, 2)
    fast = to_input(nchw, np.dtype(np.int8), (scale, -128), 255.0)
    assert fast.dtype == np.int8 and fast.flags.c_contiguous
    assert np.array_equal(fast, general(nchw, np.int8, -128))
    assert np.array_equal(to_input(x, np.dtype(np.uint8), (scale, 0), 255.0), general(x, np.uint8, 0))
