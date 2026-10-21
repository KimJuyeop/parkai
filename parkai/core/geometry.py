"""좌표 계산: 박스, 레터박스 변환, 선분-박스 교차."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float
    score: float = 1.0
    cls: str = "car"

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def shifted(self, dx: float, dy: float, scale: float = 1.0) -> Box:
        """(x * scale + dx) 변환. 화면 분할 좌표를 원본 좌표로 되돌릴 때 사용."""
        return Box(
            self.x1 * scale + dx,
            self.y1 * scale + dy,
            self.x2 * scale + dx,
            self.y2 * scale + dy,
            self.score,
            self.cls,
        )


@dataclass(frozen=True)
class Letterbox:
    """원본(w, h)을 비율 유지로 모델 입력(in_w, in_h)에 맞추는 변환."""

    scale: float
    pad_x: float
    pad_y: float
    new_w: int
    new_h: int

    @classmethod
    def compute(cls, w: int, h: int, in_w: int, in_h: int) -> Letterbox:
        scale = min(in_w / w, in_h / h)
        new_w, new_h = round(w * scale), round(h * scale)
        return cls(scale, (in_w - new_w) / 2, (in_h - new_h) / 2, new_w, new_h)

    def to_source(self, b: Box) -> Box:
        """모델 입력 좌표 -> 원본 좌표."""
        s = self.scale
        return Box(
            (b.x1 - self.pad_x) / s,
            (b.y1 - self.pad_y) / s,
            (b.x2 - self.pad_x) / s,
            (b.y2 - self.pad_y) / s,
            b.score,
            b.cls,
        )


def segment_inside_fraction(p: tuple[float, float], q: tuple[float, float], b: Box) -> float:
    """선분 p-q 중 박스 안에 들어간 길이 비율 (0~1). Liang-Barsky 클리핑."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    if dx == 0 and dy == 0:
        inside = b.x1 <= p[0] <= b.x2 and b.y1 <= p[1] <= b.y2
        return 1.0 if inside else 0.0
    t0, t1 = 0.0, 1.0
    for pk, qk in (
        (-dx, p[0] - b.x1),
        (dx, b.x2 - p[0]),
        (-dy, p[1] - b.y1),
        (dy, b.y2 - p[1]),
    ):
        if pk == 0:
            if qk < 0:
                return 0.0
            continue
        t = qk / pk
        if pk < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return 0.0
    return t1 - t0


def point_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def scale_point(p: tuple[float, float], sx: float, sy: float) -> tuple[float, float]:
    return (p[0] * sx, p[1] * sy)
