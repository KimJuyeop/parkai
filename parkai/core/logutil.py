"""로그를 적게 남기는 도우미.

보드 로그(journald)는 RAM 에 상한을 두고 오래된 것부터 지운다. 매 사이클·매 실패마다 줄을 남기면
정작 필요한 장애 기록이 금방 밀려 사라지므로, 바뀔 때와 주기 요약만 남긴다.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable

SUMMARY_SEC = 600.0  # 요약·같은 실패를 다시 남기는 간격 (10분)


def rss_mb() -> float | None:
    """이 프로세스의 실제 메모리(VmRSS, MB). /proc 이 없으면(PC 윈도우 등) None."""
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


class FailureLog:
    """같은 실패를 매번 남기지 않는다.

    처음 실패, 오류 내용이 바뀔 때, 계속되면 every 초마다 한 번, 복구될 때만 남긴다.
    key 는 실패를 나눠 셀 단위 (카메라 IP 등, 하나뿐이면 빈 문자열).
    """

    def __init__(
        self,
        log: logging.Logger,
        what: str,
        every: float = SUMMARY_SEC,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._log = log
        self.what = what
        self.every = every
        self._clock = clock
        self._state: dict[str, tuple[str, float, int]] = {}  # key -> (오류, 마지막으로 남긴 시각, 그 뒤 횟수)

    def _name(self, key: str) -> str:
        return f"{self.what} ({key})" if key else self.what

    def fail(self, key: str, err: str) -> None:
        now = self._clock()
        prev = self._state.get(key)
        if prev is None:
            self._log.warning("%s 실패: %s", self._name(key), err)
            self._state[key] = (err, now, 0)
            return
        last_err, last_at, n = prev
        n += 1
        if err != last_err or now - last_at >= self.every:
            self._log.warning("%s 실패 계속 (지난 기록 뒤 %d회): %s", self._name(key), n, err)
            self._state[key] = (err, now, 0)
        else:
            self._state[key] = (last_err, last_at, n)

    def ok(self, key: str) -> None:
        if self._state.pop(key, None) is not None:
            self._log.info("%s 복구", self._name(key))

    def failing(self) -> list[str]:
        return list(self._state)


_SHORT = (
    ("Read timed out", "응답 시간 초과"),
    ("ConnectTimeout", "연결 시간 초과"),
    ("timed out", "시간 초과"),
    ("Connection refused", "연결 거부"),
    ("No route to host", "연결 안 됨"),
    ("Host is unreachable", "연결 안 됨"),
    ("Network is unreachable", "연결 안 됨"),
    ("인증 실패", "인증 실패 (401)"),
)


def short_error(error: str | None, limit: int = 80) -> str:
    """로그용으로 줄인 카메라 오류. 렌즈 앞머리('렌즈2: ')는 남기고, 긴 requests 오류는 원인만 남긴다."""
    if not error:
        return ""
    parts = []
    for part in error.split("; "):
        head, sep, body = part.partition(": ") if part.startswith("렌즈") else ("", "", part)
        m = re.search(r"returnCode=\d+", body)
        reason = m.group(0) if m else next((v for k, v in _SHORT if k in body), body[:limit])
        parts.append(f"{head}{sep}{reason}")
    return "; ".join(parts)


class CycleLog:
    """워커 사이클 기록: 첫 사이클, 이상 카메라가 바뀔 때는 바로, 평소에는 every 초마다 요약 한 줄."""

    def __init__(
        self,
        log: logging.Logger,
        every: float = SUMMARY_SEC,
        clock: Callable[[], float] = time.monotonic,
        rss: Callable[[], float | None] = rss_mb,
    ):
        self._log = log
        self.every = every
        self._clock = clock
        self._rss = rss
        self._bad: list[str] | None = None
        self._reset(clock())

    def _reset(self, now: float) -> None:
        self._t0 = now
        self._n = 0
        self._sum = 0.0
        self._max = 0.0
        self._over = 0

    def add(
        self,
        cycle_sec: float,
        target_sec: float,
        cameras: int,
        bad: list[str],
        reasons: dict[str, str] | None = None,
    ) -> None:
        """bad: 정상이 아닌 카메라 ('IP(상태)'). reasons: IP → 줄인 오류 (이상 카메라가 바뀔 때 같이 남김)."""
        now = self._clock()
        if self._bad is None:
            self._log.info("첫 사이클 %.2fs, 카메라 %d대, 이상 %s", cycle_sec, cameras, bad or "없음")
            self._bad = bad
            self._reset(now)
            return
        if bad != self._bad:
            if bad:
                why = "; ".join(f"{ip} {r}" for ip, r in sorted((reasons or {}).items()) if r)
                self._log.warning("이상 카메라 %s%s", bad, f" — {why}" if why else "")
            else:
                self._log.info("이상 카메라 없음 (모두 정상)")
            self._bad = bad
        self._n += 1
        self._sum += cycle_sec
        self._max = max(self._max, cycle_sec)
        if target_sec > 0 and cycle_sec > target_sec:
            self._over += 1
        if now - self._t0 >= self.every:
            # 메모리: 밤새 늘어나는지(누수) 다음 날 로그만으로 볼 수 있게
            mem = self._rss()
            self._log.info(
                "최근 %d분: 사이클 %d회, 처리 평균 %.2fs, 최대 %.2fs, 주기 넘김 %d회, "
                "카메라 %d대, 이상 %s, 메모리 %s",
                round((now - self._t0) / 60),
                self._n,
                self._sum / self._n,
                self._max,
                self._over,
                cameras,
                bad or "없음",
                f"{mem:.0f}MB" if mem is not None else "-",
            )
            self._reset(now)
