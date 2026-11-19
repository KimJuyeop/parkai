import numpy as np
import pytest
from pydantic import ValidationError

from parkai.core.config import AppConfig, JudgeCfg, Slot, load_config
from parkai.core.geometry import Box, Letterbox, segment_inside_fraction
from parkai.core.judge import judge
from parkai.core.layout import split_views, view_of
from parkai.core.stabilizer import SlotStabilizer
from parkai.outputs.indicator import decide_color
from parkai.outputs.server import build_payload


def slot(no, p, q, type_="normal"):
    """판정은 렌즈 사진 픽셀 좌표로 하므로 비율(0~1) 검사 없이 만든다 (워커의 slot_in_px 와 같음)."""
    return Slot(no=no, type=type_, line=((0, 0), (0, 0))).model_copy(update={"line": (p, q)})


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
    views = split_views(img, [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5)])
    assert [v.image.shape[:2] for v in views] == [(480, 640), (480, 640)]
    assert views[1].offset == (640, 0)


def test_split_same_place_at_any_resolution():
    # 비율 영역이라 해상도가 달라도 같은 곳을 자른다
    for w, h in [(640, 360), (1280, 720), (1920, 1080)]:
        (v,) = split_views(np.zeros((h, w, 3), np.uint8), [(0.5, 0, 0.5, 1)])
        assert v.image.shape[:2] == (h, w // 2) and v.offset == (w // 2, 0)
        b = v.box_to_lens(Box(10, 20, 30, 40, 0.9))
        assert (b.x1, b.y1) == (w // 2 + 10, 20)


def test_view_of_point():
    views = [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5)]
    assert view_of((0.2, 0.2), views) == 0
    assert view_of((0.7, 0.2), views) == 1
    assert view_of((0.7, 0.8), views) is None


def test_v1_config_migrates_to_lens_ratios():
    c = AppConfig.model_validate(
        {
            "camera_profiles": {
                "p": {
                    "snapshot_url": "x",
                    "ref_size": [1280, 960],
                    "views": [[0, 0, 640, 480], [640, 0, 640, 480]],
                }
            },
            "cameras": [
                {"ip": "1.1.1.1", "profile": "p", "slots": [{"no": 1, "line": [[128, 96], [640, 480]]}]},
                {
                    "ip": "1.1.1.2",
                    "profile": "p",
                    "ref_size": [640, 480],
                    "slots": [{"no": 1, "line": [[64, 48], [320, 240]]}],
                },
            ],
            "indicator": {"enabled": False, "protocol": None},
        }
    )
    assert c.schema_version == 2
    assert c.indicator.protocol == "idis"
    prof = c.camera_profiles["p"]
    assert prof.lenses == 1 and prof.views == [(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5)]
    for cam in c.cameras:  # 카메라별 기준 해상도도 반영
        assert cam.slots[0].lens == 0
        assert cam.slots[0].line == ((0.1, 0.1), (0.5, 0.5))


def test_slot_lens_must_exist():
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "schema_version": 2,
                "camera_profiles": {"p": {"snapshot_url": "x", "lenses": 1}},
                "cameras": [
                    {
                        "ip": "1.1.1.1",
                        "profile": "p",
                        "slots": [{"no": 1, "lens": 1, "line": [[0, 0], [1, 1]]}],
                    }
                ],
            }
        )


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


def test_idis_led_command():
    from parkai.core.config import Camera, IndicatorCfg
    from parkai.outputs.indicator import led_url, return_code

    cam = Camera(ip="192.168.0.201", port=80, profile="p")
    url = led_url(cam, IndicatorCfg(), "purple")
    assert (
        url
        == "http://192.168.0.201:80/cgi-bin/webSetup.cgi?action=ledControl&mode=0&type=internal&color=0x8000ff"
    )
    assert led_url(cam, IndicatorCfg(), "red").endswith("color=0xff0000")
    assert return_code("returnCode=0\r\n") == 0
    assert return_code("returnCode=9999") == 9999
    assert return_code("") is None


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


def test_image_check_blur_matches_float_laplacian():
    """흐림 판단을 정수 라플라시안으로 바꿔도 예전(실수) 계산과 값이 같다."""
    import cv2

    from parkai.core.config import ImageCheckCfg
    from parkai.core.image_check import ImageStatus, check_view

    rng = np.random.default_rng(1)
    sharp = rng.integers(0, 256, (72, 128), dtype=np.uint8)
    flat = np.full((72, 128), 128, np.uint8)
    for g in (sharp, flat):
        old = float(cv2.Laplacian(g, cv2.CV_64F).var())
        _, std = cv2.meanStdDev(cv2.Laplacian(g, cv2.CV_16S))
        assert abs(float(std[0, 0]) ** 2 - old) <= 1e-9 * max(old, 1)
    cfg = ImageCheckCfg()
    assert check_view(sharp, cfg) == ImageStatus.OK
    assert check_view(flat, cfg) == ImageStatus.BLUR
    assert check_view(np.zeros((72, 128), np.uint8), cfg) == ImageStatus.BLACK


def test_image_check_marks_noisy_night_view():
    """밤 저조도 화면처럼 화소마다 잡음이 크면 '잡음 많음'으로 표시한다. 상태는 그대로 정상 (판정은 한다)."""
    from parkai.core.config import ImageCheckCfg
    from parkai.core.image_check import ImageStatus, inspect_view

    yy, xx = np.mgrid[0:144, 0:256]
    day = ((xx // 32 + yy // 32) % 2 * 120 + 60).astype(np.uint8)  # 큰 무늬: 경계에서만 밝기가 바뀜
    rng = np.random.default_rng(2)
    night = np.clip(day + rng.normal(0, 40, day.shape), 0, 255).astype(np.uint8)
    cfg = ImageCheckCfg()
    assert inspect_view(day, cfg) == (ImageStatus.OK, False)
    assert inspect_view(night, cfg) == (ImageStatus.OK, True)
    assert inspect_view(night, ImageCheckCfg(noise_var=0)) == (ImageStatus.OK, False)  # 0 이면 끔
    assert inspect_view(np.zeros_like(day), cfg) == (ImageStatus.BLACK, False)


def test_judge_preset_is_fixed_to_standard():
    """판정 방식은 개선 방식(standard)으로 고정: 예전 파일의 기존·직접 설정도 읽을 때 바꾼다.
    기본 모델·기준값도 확인."""
    import json
    from pathlib import Path

    from parkai.core.config import PRESETS, AppConfig

    data = json.loads(Path("examples/config.example.json").read_text(encoding="utf-8"))
    for old in ("legacy", "custom", "standard"):
        data["detection"]["preset"] = old
        det = AppConfig.model_validate(json.loads(json.dumps(data))).detection
        assert det.preset == "standard"
        assert det.effective()[0] == PRESETS["standard"][0]
    det = AppConfig().detection
    assert (det.preset, det.model, det.classes["car"].conf) == ("standard", "yolov2t_hf", 0.7)


def test_camera_stabilizer_counts_single_cycle_blips():
    """한 주기만 달랐다가 돌아온 판정(깜빡임)과 실제 상태 변경을 센다.
    판정 못 한 주기를 사이에 두면 잇지 않는다."""
    from parkai.core.stabilizer import CameraStabilizer

    st = CameraStabilizer(2)
    seq = [True, False, True, True, False, False, False, True]  # 깜빡임 1, 실제 변경 1 (2회 뒤 빈칸)
    states = [st.update({1: x})[1] for x in seq]
    assert states == [True, True, True, True, True, False, False, False]
    assert st.stats() == {
        "blips": 1,
        "blips_empty": 1,
        "blips_occupied": 0,
        "changes": 1,
        "blip_slots": {"1": 1},
    }

    st = CameraStabilizer(1)  # 연속 1회면 깜빡임이 그대로 상태 변경 두 번이 된다
    for x in (True, False, True):
        st.update({1: x})
    assert st.stats() == {
        "blips": 1,
        "blips_empty": 1,
        "blips_occupied": 0,
        "changes": 2,
        "blip_slots": {"1": 1},
    }

    st = CameraStabilizer(2)
    st.update({1: True})
    st.update({1: False})
    st.update({})  # 화면 이상 등으로 이 칸을 판정하지 못한 주기
    st.update({1: True})
    assert st.stats()["blips"] == 0


def test_stabilizer_counts_per_direction():
    """차량 있음(만차)과 빈칸(공차)으로 바꾸는 연속 횟수를 따로 정할 수 있다."""
    st = SlotStabilizer(1, 3)  # 차가 들어오면 바로, 빈칸은 3회 연속일 때
    seq = [False, True, False, False, True, False, False, False]
    assert [st.update(x) for x in seq] == [False, True, True, True, True, True, True, False]


def test_stabilize_counts_migrate_from_single_count():
    """예전 설정의 연속 횟수 하나(count)는 직접 설정일 때만 쓰였다 → 그 값, 아니면 개선 방식의 2회."""
    import json
    from pathlib import Path

    from parkai.core.config import AppConfig

    base = json.loads(Path("examples/config.example.json").read_text(encoding="utf-8"))

    def stab(preset, stabilize):
        d = json.loads(json.dumps(base))
        d["detection"]["preset"] = preset
        if stabilize is not None:
            d["detection"]["stabilize"] = stabilize
        s = AppConfig.model_validate(d).detection.effective()[1]
        return s.to_occupied, s.to_empty

    assert stab("standard", {"count": 1}) == (2, 2)  # 개선 방식은 늘 2회였다
    assert stab("legacy", None) == (2, 2)
    assert stab("custom", {"count": 3}) == (3, 3)
    assert stab("standard", {"to_occupied": 1, "to_empty": 4}) == (1, 4)


def test_lamp_color_follows_priority():
    """빈칸이 여러 종류면 우선순위 앞쪽 종류의 색. 순서 설정은 빠진·모르는 종류를 정리한다."""
    from parkai.core.config import AppConfig, IndicatorCfg, Slot

    cfg = AppConfig()
    line = ((0.1, 0.5), (0.3, 0.5))
    s = [Slot(no=1, line=line, type="normal"), Slot(no=2, line=line, type="disabled")]
    both_empty = {1: False, 2: False}
    assert decide_color(s, both_empty, cfg.slot_types, cfg.indicator.priority) == "green"  # 기본: 일반 먼저
    first_disabled = IndicatorCfg(priority=["disabled", "normal"]).priority
    assert first_disabled == ["disabled", "normal", "compact", "ev"]
    assert decide_color(s, both_empty, cfg.slot_types, first_disabled) == "blue"
    assert decide_color(s, {1: False, 2: True}, cfg.slot_types, first_disabled) == "green"  # 빈 종류만 본다
    assert decide_color(s, {1: True, 2: True}, cfg.slot_types, first_disabled) == "red"
    assert IndicatorCfg(priority=["ev", "ev", "truck"]).priority == ["ev", "normal", "compact", "disabled"]


def test_failure_log_only_on_change_interval_and_recovery(caplog):
    """같은 실패는 처음, 내용이 바뀔 때, 10분마다, 복구될 때만 남긴다."""
    import logging

    from parkai.core.logutil import FailureLog

    now = [0.0]
    fl = FailureLog(logging.getLogger("t"), "서버 전송", every=600, clock=lambda: now[0])
    with caplog.at_level(logging.INFO, logger="t"):
        for _ in range(100):  # 5초마다 실패 100번 (약 8분)
            fl.fail("", "timeout")
            now[0] += 5
        assert len(caplog.records) == 1
        fl.fail("", "refused")  # 내용이 바뀜
        now[0] += 700
        fl.fail("", "refused")  # 10분 지남
        fl.ok("")
        fl.ok("")  # 이미 복구됨: 다시 남기지 않음
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 4
    assert "실패 계속" in msgs[1] and "refused" in msgs[1] and "복구" in msgs[3]


def test_cycle_log_summarizes_and_reports_camera_changes(caplog):
    """사이클마다 남기지 않고 첫 사이클, 이상 카메라가 바뀔 때, 10분 요약만."""
    import logging

    from parkai.core.logutil import CycleLog

    now = [0.0]
    cl = CycleLog(logging.getLogger("c"), every=600, clock=lambda: now[0])
    with caplog.at_level(logging.INFO, logger="c"):
        for i in range(241):  # 5초마다 20분
            bad = ["1.2.3.4(no_response)"] if 100 <= i < 110 else []
            cl.add(1.9 if i != 50 else 6.0, 5.0, 20, bad)
            now[0] += 5
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs[0].startswith("첫 사이클")
    assert sum("이상 카메라 ['1.2.3.4(no_response)']" in m for m in msgs) == 1
    assert sum("이상 카메라 없음" in m for m in msgs) == 1
    summaries = [m for m in msgs if m.startswith("최근")]
    assert len(summaries) == 2 and "주기 넘김 1회" in summaries[0]
    assert len(msgs) == 5
