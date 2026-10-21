"""선분-박스 판정.

- intersect  : 선분이 박스에 조금이라도 들어가면 점유 (기존 Jetson 방식)
- cover_ratio: 선분이 박스에 덮인 비율로 판단하고, 한 박스가 여러 칸 선분을
               덮으면 가장 잘 맞는 칸에 먼저 배정 (옆 칸 차량 오판 방지)
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import JudgeCfg, Slot
from .geometry import Box, point_distance, segment_inside_fraction


@dataclass
class SlotResult:
    no: int
    occupied: bool
    ratio: float  # 가장 많이 덮은 박스의 덮임 비율
    box_index: int | None  # 판정 근거 박스


def _midpoint(slot: Slot) -> tuple[float, float]:
    (x1, y1), (x2, y2) = slot.line
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def judge(slots: list[Slot], boxes: list[Box], cfg: JudgeCfg) -> dict[int, SlotResult]:
    """slots, boxes는 같은 좌표계(카메라 ref_size 기준)여야 한다."""
    ratios = [[segment_inside_fraction(s.line[0], s.line[1], b) for b in boxes] for s in slots]

    results: dict[int, SlotResult] = {}
    for i, s in enumerate(slots):
        best = max(range(len(boxes)), key=lambda j: ratios[i][j], default=None)
        r = ratios[i][best] if best is not None else 0.0
        results[s.no] = SlotResult(s.no, False, r, best if r > 0 else None)

    if cfg.mode == "intersect":
        for res in results.values():
            res.occupied = res.ratio > 0
        return results

    # cover_ratio
    def threshold(s: Slot) -> float:
        if s.judge and s.judge.cover_ratio is not None:
            return s.judge.cover_ratio
        return cfg.cover_ratio

    for j, b in enumerate(boxes):
        cands = [i for i, s in enumerate(slots) if ratios[i][j] >= threshold(s)]
        if not cands:
            continue
        diag = max(point_distance((b.x1, b.y1), (b.x2, b.y2)), 1e-6)
        # 덮임 비율이 높고, 박스 중심이 선분 중점에 가까운 칸 우선
        primary = max(
            cands,
            key=lambda i: ratios[i][j] - point_distance(b.center, _midpoint(slots[i])) / diag,
        )
        for i in cands:
            if i == primary or ratios[i][j] >= cfg.cover_ratio_shared:
                res = results[slots[i].no]
                res.occupied = True
                res.ratio = ratios[i][j]
                res.box_index = j
    return results
