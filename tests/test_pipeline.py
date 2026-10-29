"""재생 모드 + fixture 검출기로 파이프라인 전체를 한 사이클 돌려본다."""

import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from parkai.backends import load_detector
from parkai.worker.pipeline import Worker


def make_frame() -> np.ndarray:
    rng = np.random.default_rng(0)
    img = np.zeros((960, 1280, 3), np.uint8)
    img[:480] = rng.integers(40, 200, (480, 1280, 3), dtype=np.uint8)  # 위 절반에만 영상
    return img


def test_one_cycle(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    shutil.copy("examples/config.example.json", cfg_path)

    cam_dir = tmp_path / "replay" / "192.168.13.21"
    cam_dir.mkdir(parents=True)
    cv2.imwrite(str(cam_dir / "0001.jpg"), make_frame())
    # 1번 칸 선분 위에 차량 박스 하나
    (cam_dir / "0001.json").write_text(json.dumps({"boxes": [[100, 150, 240, 280, 0.9]]}))

    w = Worker(
        cfg_path,
        load_detector("fixture", None),
        tmp_path / "run",
        tmp_path / "data",
        replay_dir=tmp_path / "replay",
    )
    st = w.run_cycle(1)
    w.stop()

    cam = st["cameras"]["192.168.13.21"]
    assert cam["status"] == "ok"
    # 시각에는 시간대가 붙어야 한다 (보드는 UTC, 브라우저는 KST라 없으면 9시간 차이로 '워커 정지'로 보임)
    from datetime import datetime

    assert datetime.fromisoformat(st["updated_at"]).tzinfo is not None
    assert datetime.fromisoformat(cam["updated_at"]).tzinfo is not None
    assert cam["states"] == {"1": True, "2": False, "3": False, "4": False, "5": False}
    assert (tmp_path / "run" / "status.json").exists()
    # 웹 화면이 직접 그릴 수 있도록 검출 박스 [렌즈, x1, y1, x2, y2, 점수] (렌즈 사진 대비 비율)
    assert cam["dets"] == [
        [0, round(100 / 1280, 4), round(150 / 960, 4), round(240 / 1280, 4), round(280 / 960, 4), 0.9]
    ]

    # 최신 이미지는 받은 원본 그대로(다시 인코딩하지 않음), 기록 이미지는 선·박스를 그린 것
    on_line = [
        (int(136 + (175 - 136) * t), int(236 + (198 - 236) * t)) for t in (0.3, 0.5, 0.7)
    ]  # 1번 칸 선분 위

    def line_is_green(img):  # draw.py 가 차량 있는 칸을 (0, 200, 0) 으로 그림
        return all(np.abs(img[y, x].astype(int) - (0, 200, 0)).sum() < 90 for x, y in on_line)

    latest = tmp_path / "run" / "latest" / "192.168.13.21_0.jpg"
    assert latest.read_bytes() == (cam_dir / "0001.jpg").read_bytes()
    assert not line_is_green(cv2.imread(str(latest)))
    records = list((tmp_path / "data" / "results" / "192.168.13.21").glob("*.jpg"))
    assert len(records) == 1 and line_is_green(cv2.imread(str(records[0])))


def test_black_screen_not_judged(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    shutil.copy("examples/config.example.json", cfg_path)
    cam_dir = tmp_path / "replay" / "192.168.13.21"
    cam_dir.mkdir(parents=True)
    cv2.imwrite(str(cam_dir / "0001.jpg"), np.zeros((960, 1280, 3), np.uint8))

    w = Worker(
        cfg_path,
        load_detector("fixture", None),
        tmp_path / "run",
        tmp_path / "data",
        replay_dir=tmp_path / "replay",
    )
    st = w.run_cycle(1)
    w.stop()
    assert st["cameras"]["192.168.13.21"]["status"] == "black"
    assert st["cameras"]["192.168.13.21"]["states"] == {}


def test_replay_falls_back_to_camera_without_samples(tmp_path: Path):
    """재생 모드여도 샘플 폴더가 없는 카메라는 실제 카메라(HTTP)에서 받는다."""
    from parkai.worker.sources import HttpSnapshotSource, ReplaySource

    cfg_path = tmp_path / "config.json"
    shutil.copy("examples/config.example.json", cfg_path)
    cam_dir = tmp_path / "replay" / "192.168.13.21"
    cam_dir.mkdir(parents=True)
    cv2.imwrite(str(cam_dir / "0001.jpg"), make_frame())

    w = Worker(
        cfg_path,
        load_detector("fixture", None),
        tmp_path / "run",
        tmp_path / "data",
        replay_dir=tmp_path / "replay",
    )
    cam = w.cfg.cameras[0]
    assert isinstance(w._make_source(cam), ReplaySource)
    other = cam.model_copy(update={"ip": "192.168.13.99"})
    assert isinstance(w._make_source(other), HttpSnapshotSource)
    w.stop()


def test_two_lens_camera(tmp_path: Path):
    """렌즈 2개 카메라: 렌즈별로 받아 그 렌즈의 칸만 그 렌즈의 박스로 판정한다."""
    data = json.loads(Path("examples/config.example.json").read_text(encoding="utf-8"))
    cam = data["cameras"][0]
    cam["profile"] = "IDIS 렌즈 2개"
    cam["slots"] = [
        {"no": 1, "lens": 0, "line": [[0.2, 0.5], [0.3, 0.5]]},  # 렌즈1 박스 안
        {"no": 2, "lens": 1, "line": [[0.2, 0.5], [0.3, 0.5]]},  # 렌즈2 같은 자리지만 렌즈2에는 박스 없음
        {"no": 3, "lens": 1, "line": [[0.7, 0.5], [0.8, 0.5]]},  # 렌즈2 박스 안
    ]
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")
    rng = np.random.default_rng(1)
    for ch, box in [(1, [100, 150, 450, 450]), (2, [800, 150, 1100, 450])]:
        d = tmp_path / "replay" / "192.168.13.21" / f"ch{ch}"
        d.mkdir(parents=True)
        cv2.imwrite(str(d / "0001.jpg"), rng.integers(40, 200, (720, 1280, 3), dtype=np.uint8))
        (d / "0001.json").write_text(json.dumps({"boxes": [box + [0.9]]}))

    w = Worker(
        cfg_path, load_detector("fixture", None), tmp_path / "run", tmp_path / "data", tmp_path / "replay"
    )
    st = w.run_cycle(1)
    w.stop()
    cam = st["cameras"]["192.168.13.21"]
    assert cam["status"] == "ok"
    assert cam["states"] == {"1": True, "2": False, "3": True}
    assert sorted(d[0] for d in cam["dets"]) == [0, 1]
    assert (tmp_path / "run" / "latest" / "192.168.13.21_1.jpg").exists()
    rec = list((tmp_path / "data" / "results" / "192.168.13.21").glob("*.jpg"))
    assert len(rec) == 1 and cv2.imread(str(rec[0])).shape[:2] == (720, 2560)  # 두 렌즈를 나란히


def test_one_lens_missing_keeps_other_lens(tmp_path: Path):
    """렌즈 하나만 응답하면 그 렌즈의 칸만 판정하고, 상태가 다 차지 않았으니 전송하지 않는다."""
    data = json.loads(Path("examples/config.example.json").read_text(encoding="utf-8"))
    cam = data["cameras"][0]
    cam["profile"] = "IDIS 렌즈 2개"
    cam["port"] = 1  # 렌즈2 는 실제 카메라로 가서 실패
    cam["slots"] = [
        {"no": 1, "lens": 0, "line": [[0.2, 0.5], [0.3, 0.5]]},
        {"no": 2, "lens": 1, "line": [[0.2, 0.5], [0.3, 0.5]]},
    ]
    data["runtime"]["fetch_timeout_sec"] = 0.5
    data["runtime"]["fetch_retries"] = 0
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data), encoding="utf-8")
    d = tmp_path / "replay" / "192.168.13.21" / "ch1"
    d.mkdir(parents=True)
    cv2.imwrite(
        str(d / "0001.jpg"), np.random.default_rng(2).integers(40, 200, (720, 1280, 3), dtype=np.uint8)
    )

    w = Worker(
        cfg_path, load_detector("fixture", None), tmp_path / "run", tmp_path / "data", tmp_path / "replay"
    )
    st = w.run_cycle(1)
    w.stop()
    cam = st["cameras"]["192.168.13.21"]
    assert cam["status"] == "partial"
    assert cam["states"] == {"1": False}
    assert cam["sent"] is False
    assert "렌즈2" in cam["error"]
