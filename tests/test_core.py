import numpy as np
import pytest
from pydantic import ValidationError

from parkai.core.config import AppConfig, JudgeCfg, Slot, load_config
from parkai.core.geometry import Box, Letterbox, segment_inside_fraction
from parkai.core.judge import judge
from parkai.core.layout import split_views
from parkai.core.stabilizer import SlotStabilizer
from parkai.outputs.indicator import decide_color
from parkai.outputs.server import build_payload


def slot(no, p, q, type_="normal"):
    return Slot(no=no, type=type_, line=(p, q))


# ---------- geometry ----------


def test_segment_fully_inside():
    assert segment_inside_fraction((1, 1), (3, 3), Box(0, 0, 4, 4)) == pytest.approx(1.0)


def test_segment_half_inside():
    assert segment_inside_fraction((0, 0), (4, 0), Box(2, -1, 10, 1)) == pytest.approx(0.5)


def test_segment_outside():
    assert segment_inside_fraction((0, 0), (1, 1), Box(5, 5, 6, 6)) == 0.0


def test_letterbox_roundtrip():
    lb = Letterbox.compute(640, 480, 416, 416)
    assert (lb.new_w, lb.new_h) == (416, 312)
    b = lb.to_source(Box(0, lb.pad_y, 416, lb.pad_y + 312))
    assert (b.x1, b.y1, b.x2, b.y2) == pytest.approx((0, 0, 640, 480))


def test_stretch_roundtrip():
    lb = Letterbox.stretch(640, 480, 480, 480)
    b = lb.to_source(Box(0, 0, 480, 480))
    assert (b.x1, b.y1, b.x2, b.y2) == pytest.approx((0, 0, 640, 480))


# ---------- judge ----------


def test_intersect_touch_is_occupied():
    s = [slot(1, (0, 0), (10, 0))]
    r = judge(s, [Box(9, -1, 20, 1)], JudgeCfg(mode="intersect"))
    assert r[1].occupied  # 10%만 걸려도 점유 (기존 방식)


def test_cover_ratio_rejects_small_overlap():
    s = [slot(1, (0, 0), (10, 0))]
    r = judge(s, [Box(9, -1, 20, 1)], JudgeCfg(mode="cover_ratio", cover_ratio=0.6))
    assert not r[1].occupied


def test_cover_ratio_assigns_box_to_best_slot():
    # 박스 하나가 두 칸 선분을 모두 덮지만 중심은 1번 칸에 가까움
    s = [slot(1, (10, 10), (10, 30)), slot(2, (30, 10), (30, 30))]
    car = Box(0, 0, 32, 40)
    r = judge(s, [car], JudgeCfg(mode="cover_ratio", cover_ratio=0.6, cover_ratio_shared=1.1))
    assert r[1].occupied and not r[2].occupied


def test_no_boxes_all_empty():
    s = [slot(1, (0, 0), (1, 1)), slot(2, (2, 2), (3, 3))]
    r = judge(s, [], JudgeCfg())
    assert not r[1].occupied and not r[2].occupied


# ---------- stabilizer ----------


def test_stabilizer_n1_passthrough():
    st = SlotStabilizer(1)
    assert [st.update(x) for x in (True, False, True)] == [True, False, True]


def test_stabilizer_n2_ignores_single_glitch():
    st = SlotStabilizer(2)
    seq = [True, True, False, True, True]
    assert [st.update(x) for x in seq] == [True] * 5


def test_stabilizer_n2_follows_real_change():
    st = SlotStabilizer(2)
    seq = [True, True, False, False, False]
    assert [st.update(x) for x in seq] == [True, True, True, False, False]


# ---------- layout ----------


def test_split_dual_top_half():
    img = np.zeros((960, 1280, 3), np.uint8)
    views = split_views(img, [(0, 0, 640, 480), (640, 0, 640, 480)], (1280, 960))
    assert [v.image.shape[:2] for v in views] == [(480, 640), (480, 640)]
    assert views[1].offset == (640.0, 0.0)


def test_split_scales_when_resolution_differs():
    img = np.zeros((480, 640, 3), np.uint8)  # ref의 절반 해상도
    views = split_views(img, [(640, 0, 640, 480)], (1280, 960))
    assert views[0].image.shape[:2] == (240, 320)
    assert views[0].to_ref == pytest.approx(2.0)


def test_split_maps_boxes_back_when_aspect_differs():
    # 사진(1280x480)과 ref(640x360)의 가로세로 비율이 다르면 세로 배율이 가로와 달라야 한다
    img = np.zeros((480, 1280, 3), np.uint8)
    (v,) = split_views(img, [(0, 0, 640, 360)], (640, 360))
    b = v.box_to_ref(Box(100, 400, 300, 480, 0.9))
    assert (b.x1, b.y1, b.x2, b.y2) == pytest.approx((50, 300, 150, 360))


# ---------- payload / indicator ----------


def test_payload_values():
    p = build_payload("192.168.11.3", "192.168.20.1", {1: True, 2: False})["data"]
    assert p["ipaddress"] == "192.168.11.3" and p["boardip"] == "192.168.20.1"
    assert (p["ps01"], p["ps02"], p["ps03"], p["ps12"]) == ("1", "2", "unknown", "unknown")
    assert len([k for k in p if k.startswith("ps")]) == 12


def test_indicator_full_and_available():
    cfg = AppConfig()
    s = [slot(1, (0, 0), (1, 1)), slot(2, (0, 0), (1, 1))]
    assert decide_color(s, {1: True, 2: True}, cfg.slot_types) == "red"
    assert decide_color(s, {1: True, 2: False}, cfg.slot_types) == "green"


# ---------- config ----------


def test_example_config_loads():
    cfg = load_config("examples/config.example.json")
    assert len(cfg.cameras_for_board()) == 1


def test_max_12_slots():
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "camera_profiles": {"p": {"snapshot_url": "x"}},
                "cameras": [
                    {
                        "ip": "1.1.1.1",
                        "profile": "p",
                        "slots": [{"no": i, "line": [[0, 0], [1, 1]]} for i in range(1, 14)],
                    }
                ],
            }
        )


def test_unknown_slot_type_rejected():
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "camera_profiles": {"p": {"snapshot_url": "x"}},
                "cameras": [
                    {
                        "ip": "1.1.1.1",
                        "profile": "p",
                        "slots": [{"no": 1, "type": "vip", "line": [[0, 0], [1, 1]]}],
                    }
                ],
            }
        )
