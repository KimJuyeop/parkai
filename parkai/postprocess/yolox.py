"""YOLOX 계열 후처리 (표준 YOLOX 헤드 출력 기준).

출력: (1, N, 5 + C)  [cx, cy, w, h, obj, cls...]
model.json의 "decoded": false 이면 grid/stride 디코딩을 여기서 수행한다.

주의: ST 모델 주의 st_yoloxn 출력 형식(양자화 텐서, 출력 개수)은
학습/변환 후 확인하여 맞춰야 한다.
"""

from __future__ import annotations

import numpy as np

from ..core.geometry import Box
from . import nms, register


def _dequant(t: np.ndarray, q: dict | None) -> np.ndarray:
    if q is None or t.dtype == np.float32:
        return t.astype(np.float32)
    return (t.astype(np.float32) - q.get("zero_point", 0)) * q["scale"]


def _decode_grid(pred: np.ndarray, in_w: int, in_h: int, strides: list[int]) -> np.ndarray:
    grids, exp_strides = [], []
    for s in strides:
        gw, gh = in_w // s, in_h // s
        yv, xv = np.meshgrid(np.arange(gh), np.arange(gw), indexing="ij")
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        exp_strides.append(np.full((gw * gh, 1), s))
    grid = np.concatenate(grids).astype(np.float32)
    st = np.concatenate(exp_strides).astype(np.float32)
    pred = pred.copy()
    pred[:, :2] = (pred[:, :2] + grid) * st
    pred[:, 2:4] = np.exp(pred[:, 2:4]) * st
    return pred


@register("yolox")
def postprocess(outputs, pkg, conf: dict[str, float], nms_iou: float) -> list[Box]:
    pred = _dequant(outputs[0], pkg.extra.get("output_quant"))
    pred = pred.reshape(-1, pred.shape[-1])
    in_w, in_h = pkg.input_size
    if not pkg.extra.get("decoded", False):
        pred = _decode_grid(pred, in_w, in_h, pkg.extra.get("strides", [8, 16, 32]))

    obj = pred[:, 4:5]
    cls_scores = pred[:, 5:] * obj
    cls_idx = cls_scores.argmax(1)
    scores = cls_scores[np.arange(len(pred)), cls_idx]

    names = pkg.classes
    thr = np.array([conf.get(names[c], 1.1) for c in cls_idx])  # 비활성 클래스는 1.1로 제외
    m = scores >= thr
    if not m.any():
        return []
    p, s, c = pred[m], scores[m], cls_idx[m]
    xyxy = np.stack(
        [p[:, 0] - p[:, 2] / 2, p[:, 1] - p[:, 3] / 2, p[:, 0] + p[:, 2] / 2, p[:, 1] + p[:, 3] / 2], 1
    )
    keep = nms(xyxy, s, nms_iou)
    return [Box(*map(float, xyxy[k]), float(s[k]), names[c[k]]) for k in keep]
