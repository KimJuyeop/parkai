"""만공등 제어 (카메라마다 하나).

표시 규칙: 설정된 칸 중 빈칸이 하나라도 있으면 '빈칸 색', 모두 차면 '만차 색'(항상 빨강).
빈칸 색은 주차 종류(일반/경차/장애인/전기차)별로 정한다.
판정할 수 없을 때는 명령을 보내지 않아 마지막 상태를 유지한다.

IDIS 카메라 Web API v1.6 (docs/design.md 6절)
    GET http://<ip>:<port>/cgi-bin/webSetup.cgi?action=ledControl&mode=0&type=internal&color=0xRRGGBB
    응답 본문 returnCode=0 이면 성공 (9999: 외부 등 없음 등)
- 색이 바뀔 때 보내고, 같은 색이어도 resend_sec 마다 다시 보낸다 (카메라 재부팅 대비)
- 전송은 별도 스레드에서 한다 (카메라가 응답하지 않아도 판정 주기가 밀리지 않게)
"""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import parse_qs

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from ..core.config import FULL_COLOR, LED_RGB, Camera, CameraProfile, IndicatorCfg, Slot, SlotType

log = logging.getLogger(__name__)

# 여러 종류의 빈칸이 섞여 있을 때 우선할 종류
TYPE_PRIORITY = ["normal", "compact", "disabled", "ev"]


def decide_color(slots: list[Slot], states: dict[int, bool], types: list[SlotType]) -> str | None:
    """카메라 하나의 만공등 색. 설정된 칸이 없으면 None."""
    if not slots:
        return None
    by_id = {t.id: t for t in types}
    empty_types = {s.type for s in slots if states.get(s.no) is False}
    if not empty_types:
        return FULL_COLOR
    order = TYPE_PRIORITY + sorted(empty_types - set(TYPE_PRIORITY))
    for tid in order:
        if tid in empty_types:
            return by_id[tid].color_available
    return None


def led_url(cam: Camera, cfg: IndicatorCfg, color: str) -> str:
    rgb = LED_RGB.get(color, LED_RGB["green"])
    return (
        f"http://{cam.ip}:{cam.port}/cgi-bin/webSetup.cgi"
        f"?action=ledControl&mode=0&type={cfg.led_type}&color=0x{rgb:06x}"
    )


def return_code(body: str) -> int | None:
    try:
        return int(parse_qs(body.strip()).get("returnCode", [""])[0])
    except ValueError:
        return None


class IndicatorController:
    """카메라별 마지막 색을 기억하고, 바뀌었거나 오래됐을 때만 보낸다."""

    def __init__(self, cfg: IndicatorCfg):
        self.cfg = cfg
        self._sent: dict[str, tuple[str, float]] = {}  # ip -> (색, 보낸 시각)
        self._pending: dict[str, tuple[Camera, CameraProfile, str]] = {}
        self._cv = threading.Condition()
        self._stop = False
        self.last_error: dict[str, str] = {}
        self._thread = threading.Thread(target=self._loop, name="indicator", daemon=True)
        self._thread.start()

    def update_cfg(self, cfg: IndicatorCfg) -> None:
        self.cfg = cfg

    def send(self, cam: Camera, profile: CameraProfile, user: str, password: str, color: str) -> None:
        if not self.cfg.enabled:
            return
        last = self._sent.get(cam.ip)
        if last and last[0] == color and time.monotonic() - last[1] < self.cfg.resend_sec:
            return
        with self._cv:
            self._pending[cam.ip] = (
                cam,
                profile.model_copy(update={"user": user, "password": password}),
                color,
            )
            self._cv.notify()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()

    def _loop(self) -> None:
        session = requests.Session()
        while True:
            with self._cv:
                while not self._pending and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                ip, (cam, prof, color) = self._pending.popitem()
            auth = None
            if prof.auth == "basic":
                auth = HTTPBasicAuth(prof.user, prof.password)
            elif prof.auth == "digest":
                auth = HTTPDigestAuth(prof.user, prof.password)
            try:
                r = session.get(led_url(cam, self.cfg, color), auth=auth, timeout=3)
                r.raise_for_status()
                code = return_code(r.text)
                if code != 0:
                    raise RuntimeError(f"returnCode={code}")
                self._sent[ip] = (color, time.monotonic())
                self.last_error.pop(ip, None)
            except (requests.RequestException, RuntimeError) as e:
                self.last_error[ip] = str(e)
                log.warning("만공등 전송 실패 (%s, %s): %s", ip, color, e)
