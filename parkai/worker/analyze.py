"""렌즈 사진 한 장의 검출과 카메라 단위 판정. 워커와 비교 도구(tools/compare_judge.py)가 같이 쓴다.

좌표 규칙
- 설정(칸 선분, 분석 영역): 렌즈 사진 대비 비율 (0~1)
- 검출 박스와 판정: 렌즈 사진 픽셀 (판정은 렌즈별로, 그 렌즈의 칸과 박스만)
- 웹 화면으로 보내는 박스(dets): 다시 비율
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..backends import Detector
from ..core.config import JudgeCfg, Rect, Slot
from ..core.geometry import Box
from ..core.judge import SlotResult, judge
from ..core.layout import View, view_of


@dataclass
class LensFrame:
    lens: int  # 0부터
    status: str  # ok | partial | black | blur | frozen | no_response | decode_error
    image: np.ndarray | None = None
    jpeg: bytes | None = None
    source_key: str | None = None
    views: list[View] = field(default_factory=list)
    view_ok: list[bool] = field(default_factory=list)
    error: str | None = None

    @property
    def size(self) -> tuple[int, int]:
        h, w = self.image.shape[:2]
        return w, h


def detect_lens(detector: Detector, frame: LensFrame, conf: dict[str, float], nms_iou: float) -> list[Box]:
    """정상인 분석 영역마다 검출해서 렌즈 사진 픽셀 좌표로 돌려준다."""
    if frame.image is None or frame.status not in ("ok", "partial"):
        return []
    if getattr(detector, "full_frame", False):  # fixture: 렌즈 사진 좌표 박스를 그대로
        return detector.detect(frame.image, conf, nms_iou, frame.source_key)
    boxes: list[Box] = []
    for v, ok in zip(frame.views, frame.view_ok, strict=True):
        if ok:
            boxes += [v.box_to_lens(b) for b in detector.detect(v.image, conf, nms_iou)]
    return boxes


def slot_in_px(slot: Slot, w: int, h: int) -> Slot:
    (ax, ay), (bx, by) = slot.line
    return slot.model_copy(update={"line": ((ax * w, ay * h), (bx * w, by * h))})


def judge_camera(
    slots: list[Slot],
    frames: list[LensFrame],
    boxes: dict[int, list[Box]],
    views: list[Rect],
    cfg: JudgeCfg,
) -> dict[int, SlotResult]:
    """렌즈별로 판정해서 합친다. 사진이 없거나 선분이 이상 화면에 있는 칸은 결과에 없다 (마지막 상태 유지)."""
    results: dict[int, SlotResult] = {}
    for f in frames:
        if f.image is None or f.status not in ("ok", "partial"):
            continue
        w, h = f.size
        judgeable = []
        for s in slots:
            if s.lens != f.lens:
                continue
            (ax, ay), (bx, by) = s.line
            vi = view_of(((ax + bx) / 2, (ay + by) / 2), views)
            if vi is not None and f.view_ok[vi]:
                judgeable.append(slot_in_px(s, w, h))
        results.update(judge(judgeable, boxes.get(f.lens, []), cfg))
    return results


def dets_for_web(frames: list[LensFrame], boxes: dict[int, list[Box]]) -> list[list[float]]:
    """[렌즈, x1, y1, x2, y2, 점수] (렌즈 사진 대비 비율)."""
    out = []
    for f in frames:
        if f.image is None:
            continue
        w, h = f.size
        for b in boxes.get(f.lens, []):
            out.append(
                [
                    f.lens,
                    round(b.x1 / w, 4),
                    round(b.y1 / h, 4),
                    round(b.x2 / w, 4),
                    round(b.y2 / h, 4),
                    round(b.score, 2),
                ]
            )
    return out
