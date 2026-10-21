"""저장된 검출 결과에 legacy / standard 판정 규칙을 모두 적용해 결과가 다른 칸을 출력한다.

    python tools/compare_rules.py --config examples/config.example.json --samples samples

samples/<카메라IP>/*.json 의 박스(원본 좌표)를 사용한다.
결과가 다른 칸만 사람이 이미지로 확인하면 된다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from parkai.core.config import PRESETS, load_config
from parkai.core.geometry import Box
from parkai.core.judge import judge


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--samples", type=Path, required=True)
    args = ap.parse_args()

    cfg = load_config(args.config)
    legacy, standard = PRESETS["legacy"][0], PRESETS["standard"][0]
    total = diff = 0
    for cam in cfg.cameras:
        for f in sorted((args.samples / cam.ip).glob("*.json")):
            rows = json.loads(f.read_text(encoding="utf-8")).get("boxes", [])
            boxes = [Box(*r[:4], r[4] if len(r) > 4 else 1.0) for r in rows]
            a, b = judge(cam.slots, boxes, legacy), judge(cam.slots, boxes, standard)
            for no in a:
                total += 1
                if a[no].occupied != b[no].occupied:
                    diff += 1
                    print(
                        f"{cam.ip} {f.stem} {no}번: legacy={a[no].occupied} "
                        f"standard={b[no].occupied} (덮임 {b[no].ratio:.2f})"
                    )
    print(f"전체 {total}칸 중 {diff}칸 다름")


if __name__ == "__main__":
    main()
