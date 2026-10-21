"""화면 이상 검사: 검은 화면, 흐림, 정지. 이상이면 판정/전송하지 않는다.

기준값은 현장 영상으로 보정 필요 (특히 야간 IR 화면).
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

import cv2
import numpy as np

from .config import ImageCheckCfg


class ImageStatus(StrEnum):
    OK = "ok"
    BLACK = "black"
    BLUR = "blur"
    FROZEN = "frozen"


def check_view(gray: np.ndarray, cfg: ImageCheckCfg) -> ImageStatus:
    if float(gray.mean()) < cfg.black_mean:
        return ImageStatus.BLACK
    if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < cfg.blur_var:
        return ImageStatus.BLUR
    return ImageStatus.OK


class FrozenDetector:
    """같은 이미지가 연속으로 들어오면 정지로 판단."""

    def __init__(self) -> None:
        self._last: str | None = None
        self._repeat = 0

    def update(self, jpeg: bytes, limit: int) -> bool:
        h = hashlib.blake2b(jpeg, digest_size=16).hexdigest()
        self._repeat = self._repeat + 1 if h == self._last else 0
        self._last = h
        return self._repeat >= limit
