"""스냅샷을 추론할 화면 영역으로 분할.

프로필의 views는 ref_size 기준이다. 실제 이미지 크기가 다르면 비율로 환산한다.
각 View는 잘라낸 이미지와, 그 좌표를 ref_size 좌표로 되돌리는 변환을 가진다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import Box


@dataclass
class View:
    index: int
    image: np.ndarray  # 잘라낸 영역 (실제 해상도)
    offset: tuple[float, float]  # ref 좌표계에서의 시작점
    to_ref: float  # 실제 픽셀 -> ref 픽셀 배율 (가로)
    to_ref_y: float  # 세로. 카메라 사진과 ref_size 의 가로세로 비율이 다르면 가로와 다르다

    def box_to_ref(self, b: Box) -> Box:
        """이 화면 안의 박스(실제 픽셀)를 카메라 ref_size 좌표로."""
        return b.shifted(self.offset[0], self.offset[1], self.to_ref, self.to_ref_y)


def split_views(
    img: np.ndarray,
    views: list[tuple[int, int, int, int]],
    ref_size: tuple[int, int],
) -> list[View]:
    h, w = img.shape[:2]
    sx, sy = w / ref_size[0], h / ref_size[1]
    out = []
    for i, (x, y, vw, vh) in enumerate(views):
        x0, y0 = round(x * sx), round(y * sy)
        x1, y1 = round((x + vw) * sx), round((y + vh) * sy)
        out.append(View(i, img[y0:y1, x0:x1], (float(x), float(y)), 1.0 / sx, 1.0 / sy))
    return out
