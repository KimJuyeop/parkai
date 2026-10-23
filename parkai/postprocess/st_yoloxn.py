"""ST Model Zoo st_yoloxn 후처리 (앵커 방식 YOLO 헤드, 출력 3개).

출력: 크기별 3개 텐서, 각 (1, A*(5+C), H, W) [ONNX, NCHW] 또는 (1, H, W, A*(5+C)) [NHWC].
채널은 앵커 순서대로 [tx, ty, tw, th, obj, cls...] 가 A번 이어진다.
디코딩은 ST Model Zoo(object_detection/tf/src/postprocessing/postprocess.py)와 같다.
    xy  = (sigmoid(txy) + 격자 위치) / 격자 크기
    wh  = exp(twh) * anchor           (anchor는 입력 대비 비율, 모든 크기에 같은 값)
    점수 = sigmoid(obj) * softmax(cls)

model.json:
    anchors      [[w, h], ...] 입력 대비 비율 (ST 설정 파일의 postprocessing.yolo_anchors)
    class_map    {"truck": "car", "bus": "car"}  여러 클래스를 하나로 묶어 그 클래스 기준값으로 판단
    output_quant [{"scale", "zero_point"}, ...]  NPU 출력이 정수일 때 (출력 순서대로)
"""

from __future__ import annotations

import numpy as np

from ..core.geometry import Box
from . import nms, register


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


def _to_nhwc(t: np.ndarray, ch: int) -> np.ndarray:
    t = t.reshape(t.shape[-3:]) if t.ndim == 4 else t
    if t.shape[-1] == ch:
        return t
    if t.shape[0] == ch:
        return t.transpose(1, 2, 0)
    raise ValueError(f"st_yoloxn 출력 모양을 알 수 없습니다: {t.shape} (채널 {ch})")


@register("st_yoloxn")
def postprocess(outputs, pkg, conf: dict[str, float], nms_iou: float) -> list[Box]:
    names = pkg.classes
    anchors = np.asarray(pkg.extra["anchors"], np.float32)  # (A, 2)
    na, nc = len(anchors), len(names)
    ch = na * (5 + nc)
    quant = pkg.extra.get("output_quant") or [None] * len(outputs)
    in_w, in_h = pkg.input_size
    class_map = pkg.extra.get("class_map", {})
    # 각 클래스를 판정용 이름으로 바꾸고 기준값을 정한다 (설정에 없는 클래스는 1.1로 제외)
    judged = [class_map.get(n, n) for n in names]
    thr_by_cls = np.array([conf.get(j, 1.1) for j in judged], np.float32)

    all_xyxy, all_scores, all_cls = [], [], []
    for t, q in zip(outputs, quant, strict=False):
        t = (
            t.astype(np.float32)
            if q is None
            else (t.astype(np.float32) - q.get("zero_point", 0)) * q["scale"]
        )
        f = _to_nhwc(t, ch)
        gh, gw = f.shape[:2]
        f = f.reshape(gh, gw, na, 5 + nc)
        score = _sigmoid(f[..., 4:5]) * _softmax(f[..., 5:])  # (gh, gw, A, C)
        cls_idx = score.argmax(-1)
        best = np.take_along_axis(score, cls_idx[..., None], -1)[..., 0]
        m = best >= thr_by_cls[cls_idx]
        if not m.any():
            continue
        gy, gx, ga = np.nonzero(m)
        p = f[gy, gx, ga]
        cx = (_sigmoid(p[:, 0]) + gx) / gw * in_w
        cy = (_sigmoid(p[:, 1]) + gy) / gh * in_h
        w = np.exp(p[:, 2]) * anchors[ga, 0] * in_w
        h = np.exp(p[:, 3]) * anchors[ga, 1] * in_h
        xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
        all_xyxy.append(np.clip(xyxy, 0, [in_w, in_h, in_w, in_h]))
        all_scores.append(best[m])
        all_cls.append(cls_idx[m])

    if not all_xyxy:
        return []
    xyxy, s, c = np.concatenate(all_xyxy), np.concatenate(all_scores), np.concatenate(all_cls)
    keep = nms(xyxy, s, nms_iou)  # 클래스 구분 없이: 한 차량이 car/truck 으로 겹쳐 나오는 것을 하나로
    return [Box(*map(float, xyxy[k]), float(s[k]), judged[c[k]]) for k in keep]
