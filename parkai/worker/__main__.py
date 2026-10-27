"""추론 워커 실행.

python -m parkai.worker --config examples/config.example.json --replay samples/ --backend fixture
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..backends import load_detector
from ..core.config import load_config
from .pipeline import Worker


def main() -> None:
    ap = argparse.ArgumentParser(prog="parkai.worker")
    ap.add_argument("--config", type=Path, default=Path("/var/lib/parkai/config.json"))
    ap.add_argument("--backend", default="auto", choices=["auto", "stai", "onnx", "tflite", "fixture"])
    ap.add_argument("--models-dir", type=Path, default=Path("/var/lib/parkai/models"))
    ap.add_argument("--replay", type=Path, help="재생 모드: <폴더>/<카메라IP>/*.jpg")
    ap.add_argument("--run-dir", type=Path, default=Path("/run/parkai"))
    ap.add_argument("--data-dir", type=Path, default=Path("/var/lib/parkai"))
    ap.add_argument("--cycles", type=int, help="지정한 횟수만 돌고 종료")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config(args.config)
    model_dir = args.models_dir / cfg.detection.model if cfg.detection.model else None
    detector = load_detector(args.backend, model_dir)
    Worker(args.config, detector, args.run_dir, args.data_dir, args.replay).run_forever(args.cycles)


if __name__ == "__main__":
    main()
