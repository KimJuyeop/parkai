"""렌즈 사진을 추론할 화면 영역(분석 영역)으로 분할.

분석 영역은 렌즈 사진 대비 비율 [x, y, w, h] (0~1) 이라 사진 해상도와 상관없이 같은 곳을 자른다.
각 View 는 잘라낸 이미지와 렌즈 사진 안의 시작점(픽셀)을 가진다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import Box


@dataclass
class View:
    index: int
    image: np.ndarray  # 잘라낸 영역 (렌즈 사진 해상도 그대로)
    offset: tuple[int, int]  # 렌즈 사진 안의 시작점 (픽셀)

    def box_to_lens(self, b: Box) -> Box:
        """이 화면 안의 박스를 렌즈 사진 픽셀 좌표로."""
        return b.shifted(self.offset[0], self.offset[1])


def view_rect_px(rect: tuple[float, float, float, float], w: int, h: int) -> tuple[int, int, int, int]:
    """비율 영역 → 픽셀 (x0, y0, x1, y1). 사진 밖으로 나가지 않게 자른다."""
    x, y, vw, vh = rect
    x0, y0 = max(0, round(x * w)), max(0, round(y * h))
    x1, y1 = min(w, round((x + vw) * w)), min(h, round((y + vh) * h))
    return x0, y0, x1, y1


def split_views(img: np.ndarray, views: list[tuple[float, float, float, float]]) -> list[View]:
    h, w = img.shape[:2]
    out = []
    for i, rect in enumerate(views):
        x0, y0, x1, y1 = view_rect_px(rect, w, h)
        out.append(View(i, img[y0:y1, x0:x1], (x0, y0)))
    return out


def view_of(point: tuple[float, float], views: list[tuple[float, float, float, float]]) -> int | None:
    """비율 좌표 점이 들어 있는 분석 영역 번호. 어느 영역에도 없으면 None."""
    px, py = point
    for i, (x, y, w, h) in enumerate(views):
        if x <= px < x + w and y <= py < y + h:
            return i
    return None
