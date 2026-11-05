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
    # 모두 OpenCV 안에서 계산한다 (numpy 실수 배열을 만들지 않아 보드 CPU 부담과 스레드 간 대기가 적다)
    if cv2.mean(gray)[0] < cfg.black_mean:
        return ImageStatus.BLACK
    # 8비트 사진의 라플라시안은 -1020~1020 이라 16비트 정수에 정확히 담긴다 (실수로 구한 값과 같음)
    _, std = cv2.meanStdDev(cv2.Laplacian(gray, cv2.CV_16S))
    if float(std[0, 0]) ** 2 < cfg.blur_var:
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
