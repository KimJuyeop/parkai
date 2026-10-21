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
    assert (tmp_path / "run" / "latest" / "192.168.13.21.jpg").exists()
    assert (tmp_path / "run" / "status.json").exists()


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
