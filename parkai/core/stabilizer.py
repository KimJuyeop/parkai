"""칸 상태 안정화: 새 상태가 연속 N회 관측되어야 바꾼다. N=1이면 그대로 통과.
N 은 방향마다 따로 정할 수 있다 (빈칸 → 차량 있음, 차량 있음 → 빈칸)."""

from __future__ import annotations


class SlotStabilizer:
    def __init__(self, to_occupied: int = 1, to_empty: int | None = None):
        self.set_counts(to_occupied, to_occupied if to_empty is None else to_empty)
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
        if self._streak >= (self.to_occupied if observed else self.to_empty):
            self.state = observed
            self._candidate, self._streak = None, 0
        return self.state

    def set_counts(self, to_occupied: int, to_empty: int) -> None:
        self.to_occupied = max(1, to_occupied)
        self.to_empty = max(1, to_empty)


class CameraStabilizer:
    """카메라 하나의 칸별 안정화기 묶음.

    현장 시험용으로 워커가 켜진 뒤의 횟수를 센다 (판정에는 영향 없음):
    - blips  : 판정이 한 주기만 달랐다가 돌아온 횟수. 연속 1회였다면 깜빡였을 횟수
               blips_empty = 차 있는 칸이 한 주기만 빈칸(차-빈-차)
               blips_occupied = 빈칸이 한 주기만 차(빈-차-빈)
    - changes: 실제로 상태를 바꾼 횟수 (시작 직후 첫 판정은 빼고)
    판정하지 못한 주기(화면 이상, 응답 없음)가 끼면 그 앞뒤는 이어 보지 않는다.
    """

    def __init__(self, to_occupied: int = 1, to_empty: int | None = None):
        self.to_occupied = to_occupied
        self.to_empty = to_occupied if to_empty is None else to_empty
        self._slots: dict[int, SlotStabilizer] = {}
        self._recent: dict[int, tuple[bool, ...]] = {}  # 칸별 최근 판정 (최대 2개)
        self.blips: dict[int, int] = {}
        self.blips_dir = {True: 0, False: 0}  # 한 주기만 나온 판정이 차량 있음(True)/빈칸(False)
        self.changes: dict[int, int] = {}

    def set_counts(self, to_occupied: int, to_empty: int) -> None:
        self.to_occupied, self.to_empty = to_occupied, to_empty
        for s in self._slots.values():
            s.set_counts(to_occupied, to_empty)

    def update(self, observed: dict[int, bool]) -> dict[int, bool]:
        out = {}
        for no, occ in observed.items():
            st = self._slots.setdefault(no, SlotStabilizer(self.to_occupied, self.to_empty))
            before = st.state
            out[no] = st.update(occ)
            if before is not None and out[no] != before:
                self.changes[no] = self.changes.get(no, 0) + 1
            recent = self._recent.get(no, ())
            if len(recent) == 2 and recent[0] != recent[1] and occ == recent[0]:
                self.blips[no] = self.blips.get(no, 0) + 1
                self.blips_dir[recent[1]] += 1
            self._recent[no] = (*recent[-1:], occ)
        for no in list(self._slots):  # 삭제된 칸 정리
            if no not in observed:
                del self._slots[no]
                self._recent.pop(no, None)
        return out

    def stats(self) -> dict:
        """status.json 용: 워커가 켜진 뒤 합계와, 한 주기 깜빡임이 있었던 칸별 횟수."""
        return {
            "blips": sum(self.blips.values()),
            "blips_empty": self.blips_dir[False],
            "blips_occupied": self.blips_dir[True],
            "changes": sum(self.changes.values()),
            "blip_slots": {str(no): n for no, n in sorted(self.blips.items())},
        }
