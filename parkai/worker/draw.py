"""결과 이미지 그리기: 검출 박스, 칸 선분(점유 초록 / 빈칸 빨강 / 판정 불가 회색)."""

from __future__ import annotations

import cv2
import numpy as np

from ..core.config import Slot
from ..core.geometry import Box

GREEN, RED, GRAY, BOX = (0, 200, 0), (0, 0, 230), (160, 160, 160), (0, 255, 0)


def annotate(
    img: np.ndarray,
    ref_size: tuple[int, int],
    slots: list[Slot],
    states: dict[int, bool | None],
    boxes: list[Box],
    title: str,
) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    sx, sy = w / ref_size[0], h / ref_size[1]

    def pt(p):
        return (int(p[0] * sx), int(p[1] * sy))

    for b in boxes:
        cv2.rectangle(out, pt((b.x1, b.y1)), pt((b.x2, b.y2)), BOX, 2)
        cv2.putText(
            out, f"{b.cls}: {int(b.score * 100)}", pt((b.x1, b.y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, BOX, 2
        )
    for s in slots:
        st = states.get(s.no)
        color = GRAY if st is None else (GREEN if st else RED)
        cv2.line(out, pt(s.line[0]), pt(s.line[1]), color, 6)
        cv2.putText(out, str(s.no), pt(s.line[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    if title:
        cv2.putText(out, title, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 5)
        cv2.putText(out, title, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
    return out
