"""모델 구조별 후처리. model.json의 arch 값으로 선택한다."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from ..core.geometry import Box

PostFn = Callable[[list[np.ndarray], object, dict[str, float], float], list[Box]]

_REGISTRY: dict[str, PostFn] = {}


def register(arch: str):
    def deco(fn: PostFn) -> PostFn:
        _REGISTRY[arch] = fn
        return fn

    return deco


def get_postprocessor(arch: str) -> PostFn:
    from . import st_yoloxn, yolox  # noqa: F401  (등록)

    if arch not in _REGISTRY:
        raise ValueError(f"지원하지 않는 모델 구조: {arch} (지원: {sorted(_REGISTRY)})")
    return _REGISTRY[arch]


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    """boxes: (N, 4) xyxy

    점수가 같은 박스(1.0 으로 포화된 경우가 많다)는 원래 순서대로 남긴다 (안정 정렬).
    그냥 argsort 는 동점 순서가 후보 수에 따라 바뀌어, 기준값만 바꿔도 같은 차에 다른 박스가 남았다.
    """
    order = np.argsort(-scores, kind="stable")
    keep: list[int] = []
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        ovr = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][ovr <= iou]
    return keep
