"""모델 없이 개발하기 위한 검출기.

재생 모드에서 이미지 `xxx.jpg` 옆에 `xxx.json`이 있으면 그 박스를 돌려준다.
좌표는 원본 스냅샷(ref_size) 기준이며, 화면 분할과 무관하게 동작하도록
파이프라인이 view 단위가 아니라 카메라 단위로 호출한다 (detect_full).

    {"boxes": [[x1, y1, x2, y2, score], ...]}
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.geometry import Box
from .base import Detector


class FixtureDetector(Detector):
    name = "fixture"
    full_frame = True  # 파이프라인이 화면 분할 없이 원본 좌표로 사용

    def detect(self, image_bgr, conf, nms_iou, source_key=None):
        if not source_key:
            return []
        p = Path(source_key).with_suffix(".json")
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        out = []
        for row in data.get("boxes", []):
            x1, y1, x2, y2 = row[:4]
            score = row[4] if len(row) > 4 else 1.0
            out.append(Box(x1, y1, x2, y2, score, "car"))
        return out
