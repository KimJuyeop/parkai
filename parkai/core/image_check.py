"""화면 이상 검사: 검은 화면, 흐림, 정지. 이상이면 판정/전송하지 않는다.
같은 계산으로 잡음이 많은 화면(밤)도 알려 준다 → 모델에 넣을 때 화소를 평균해 줄인다 (backends/base.py).

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


def inspect_view(gray: np.ndarray, cfg: ImageCheckCfg) -> tuple[ImageStatus, bool]:
    """(화면 상태, 잡음이 많은지). 잡음은 정상 화면에서만 본다."""
    # 모두 OpenCV 안에서 계산한다 (numpy 실수 배열을 만들지 않아 보드 CPU 부담과 스레드 간 대기가 적다)
    if cv2.mean(gray)[0] < cfg.black_mean:
        return ImageStatus.BLACK, False
    # 8비트 사진의 라플라시안은 -1020~1020 이라 16비트 정수에 정확히 담긴다 (실수로 구한 값과 같음)
    _, std = cv2.meanStdDev(cv2.Laplacian(gray, cv2.CV_16S))
    var = float(std[0, 0]) ** 2
    if var < cfg.blur_var:
        return ImageStatus.BLUR, False
    # 밤 저조도 화면은 화소마다 잡음이 커서 라플라시안 분산이 낮 화면보다 훨씬 크다
    # (2026-11-18: 낮 149장 최대 2,787, 밤 2장 15,639·18,125)
    return ImageStatus.OK, cfg.noise_var > 0 and var >= cfg.noise_var


def check_view(gray: np.ndarray, cfg: ImageCheckCfg) -> ImageStatus:
    return inspect_view(gray, cfg)[0]


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
