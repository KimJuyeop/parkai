"""주차면 상태 서버 전송.

POST {base_url}/api/camerastatuses
{"data": {"ipaddress": <카메라 IP>, "boardip": <보드 IP>, "ps01": "1"|"2"|"unknown", ... "ps12"}}
  "1" 차량 있음 / "2" 차량 없음 / "unknown" 설정 안 된 칸

- 카메라마다 매 사이클 최신 상태를 보낸다 (대기열 없음, 실패 시 다음 사이클에 다시 감)
- 판정할 수 없는 카메라(응답 없음, 화면 이상)는 보내지 않는다
- 이전 전송이 밀려 있으면 최신 것만 보낸다
"""

from __future__ import annotations

import logging
import threading

import requests

from ..core.config import MAX_SLOTS_PER_CAMERA, ServerCfg

log = logging.getLogger(__name__)

OCCUPIED, EMPTY, UNKNOWN = "1", "2", "unknown"


def build_payload(camera_ip: str, board_ip: str, states: dict[int, bool]) -> dict:
    data: dict[str, str] = {"ipaddress": camera_ip, "boardip": board_ip}
    for no in range(1, MAX_SLOTS_PER_CAMERA + 1):
        st = states.get(no)
        data[f"ps{no:02d}"] = UNKNOWN if st is None else (OCCUPIED if st else EMPTY)
    return {"data": data}


class ServerSender:
    """전송 전용 스레드. submit()은 즉시 반환한다."""

    def __init__(self, cfg: ServerCfg):
        self.cfg = cfg
        self._pending: dict[str, dict] = {}  # 카메라 IP -> 최신 payload
        self._cv = threading.Condition()
        self._session = requests.Session()
        self._stop = False
        self.last_error: str | None = None
        self._thread = threading.Thread(target=self._loop, name="server-sender", daemon=True)
        self._thread.start()

    def update_cfg(self, cfg: ServerCfg) -> None:
        self.cfg = cfg

    def submit(self, camera_ip: str, payload: dict) -> None:
        if not self.cfg.enabled or not self.cfg.base_url:
            return
        with self._cv:
            self._pending[camera_ip] = payload  # 밀린 것은 덮어씀
            self._cv.notify()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._pending and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                cam_ip, payload = self._pending.popitem()
            try:
                r = self._session.post(self.cfg.url, json=payload, timeout=self.cfg.timeout_sec)
                r.raise_for_status()
                self.last_error = None
            except requests.RequestException as e:
                self.last_error = str(e)
                log.warning("서버 전송 실패 (%s): %s", cam_ip, e)
