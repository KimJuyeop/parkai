"""보드 정보: device_id, 보드 IP, 보드 모델."""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path


def device_id() -> str:
    """바뀌지 않는 보드 식별자. 칩 시리얼 -> machine-id -> 호스트명 순."""
    for p in ("/proc/device-tree/serial-number", "/etc/machine-id"):
        try:
            raw = Path(p).read_bytes().strip(b"\0\n ")
            if raw:
                return hashlib.sha1(raw).hexdigest()[:12]
        except OSError:
            continue
    return hashlib.sha1(socket.gethostname().encode()).hexdigest()[:12]


def board_model() -> str:
    try:
        return Path("/proc/device-tree/model").read_text().strip("\0\n ")
    except OSError:
        return "pc"


def board_ip(preferred: str | None = None) -> str:
    """설정값이 있으면 그 값, 없으면 기본 경로로 나가는 인터페이스의 IP."""
    if preferred:
        return preferred
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # 실제로 패킷을 보내지 않음
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()
