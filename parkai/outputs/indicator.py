"""만공등 제어.

표시 규칙: 설정된 칸 중 빈칸이 하나라도 있으면 '빈칸 색', 모두 차면 '만차 색'.
주차 종류(일반/전기차/장애인/경차)별 색은 설정의 slot_types에서 정한다.

제어 프로토콜(전송 대상, 패킷 형식)은 테스트 카메라 사양 확인 후 구현한다.
판정할 수 없을 때는 명령을 보내지 않아 마지막 상태를 유지한다.
"""

from __future__ import annotations

from ..core.config import Slot, SlotType

# 여러 종류의 빈칸이 섞여 있을 때 우선할 종류 (사양 확인 후 조정)
TYPE_PRIORITY = ["normal", "compact", "ev", "disabled"]


def decide_color(slots: list[Slot], states: dict[int, bool], types: list[SlotType]) -> str | None:
    """카메라 하나의 만공등 색. 설정된 칸이 없으면 None."""
    if not slots:
        return None
    by_id = {t.id: t for t in types}
    empty_types = {s.type for s in slots if states.get(s.no) is False}
    if not empty_types:
        base = by_id.get("normal") or types[0]
        return base.color_full
    order = TYPE_PRIORITY + sorted(empty_types - set(TYPE_PRIORITY))
    for tid in order:
        if tid in empty_types:
            return by_id[tid].color_available
    return None


class IndicatorController:
    """프로토콜 미정. 구현 전까지는 아무것도 보내지 않는다."""

    def send(self, camera_ip: str, controller_ip: str | None, color: str) -> None:
        return None
