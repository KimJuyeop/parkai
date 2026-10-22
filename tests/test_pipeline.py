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
    w.sender.stop()

    cam = st["cameras"]["192.168.13.21"]
    assert cam["status"] == "ok"
    assert cam["states"] == {"1": True, "2": False, "3": False, "4": False, "5": False}
    assert (tmp_path / "run" / "status.json").exists()
    # 웹 화면이 직접 그릴 수 있도록 검출 박스 좌표(기준 해상도)를 함께 전달
    assert cam["dets"] == [[100, 150, 240, 280, 0.9]]

    # 최신 이미지는 선을 그리지 않은 원본(분석 영역만), 기록 이미지는 선·박스를 그린 것
    on_line = [
        (int(136 + (175 - 136) * t), int(236 + (198 - 236) * t)) for t in (0.3, 0.5, 0.7)
    ]  # 1번 칸 선분 위

    def line_is_green(img):  # draw.py 가 차량 있는 칸을 (0, 200, 0) 으로 그림
        return all(np.abs(img[y, x].astype(int) - (0, 200, 0)).sum() < 90 for x, y in on_line)

    latest = cv2.imread(str(tmp_path / "run" / "latest" / "192.168.13.21.jpg"))
    assert latest.shape[:2] == (480, 1280)
    assert not line_is_green(latest)
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
    w.sender.stop()
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
    w.sender.stop()
