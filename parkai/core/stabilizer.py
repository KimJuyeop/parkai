"""칸 상태 안정화: 새 상태가 연속 N회 관측되어야 바꾼다. N=1이면 그대로 통과."""

from __future__ import annotations


class SlotStabilizer:
    def __init__(self, count: int = 1):
        self.count = max(1, count)
        self.state: bool | None = None
        self._candidate: bool | None = None
        self._streak = 0

    def update(self, observed: bool) -> bool:
        if self.state is None:  # 시작 직후 첫 판정은 바로 채택
            self.state = observed
            return observed
        if observed == self.state:
            self._candidate, self._streak = None, 0
            return self.state
        if observed == self._candidate:
            self._streak += 1
        else:
            self._candidate, self._streak = observed, 1
        if self._streak >= self.count:
            self.state = observed
            self._candidate, self._streak = None, 0
        return self.state


class CameraStabilizer:
    """카메라 하나의 칸별 안정화기 묶음."""

    def __init__(self, count: int = 1):
        self.count = count
        self._slots: dict[int, SlotStabilizer] = {}

    def set_count(self, count: int) -> None:
        if count != self.count:
            self.count = count
            for s in self._slots.values():
                s.count = max(1, count)

    def update(self, observed: dict[int, bool]) -> dict[int, bool]:
        out = {}
        for no, occ in observed.items():
            st = self._slots.setdefault(no, SlotStabilizer(self.count))
            out[no] = st.update(occ)
        for no in list(self._slots):  # 삭제된 칸 정리
            if no not in observed:
                del self._slots[no]
        return out
