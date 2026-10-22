"""보드 정보: device_id, 보드 IP, 보드 모델."""

from __future__ import annotations

import hashlib
import shutil
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


_cpu_prev: tuple[int, int] | None = None


def _cpu_percent() -> float | None:
    """직전 호출 이후 CPU 사용률(%). /proc/stat 기준, 첫 호출은 부팅 이후 평균."""
    global _cpu_prev
    try:
        vals = [int(x) for x in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
    except (OSError, ValueError):
        return None
    idle, total = vals[3] + (vals[4] if len(vals) > 4 else 0), sum(vals)
    prev, _cpu_prev = _cpu_prev, (idle, total)
    d_idle, d_total = (idle - prev[0], total - prev[1]) if prev else (idle, total)
    return round(100 * (1 - d_idle / d_total), 1) if d_total > 0 else None


def _memory_mb() -> tuple[int, int] | None:
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0])  # kB
        total, avail = info["MemTotal"], info.get("MemAvailable", info["MemFree"])
        return (total - avail) // 1024, total // 1024
    except (OSError, KeyError, ValueError):
        return None


def _temperature_c() -> float | None:
    for p in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        try:
            return round(int(p.read_text().strip()) / 1000, 1)
        except (OSError, ValueError):
            continue
    return None


def resources(storage_dir: Path) -> dict:
    """웹 상태 줄용 자원 사용량. 읽을 수 없는 값은 None (PC 개발 환경 등)."""
    mem = _memory_mb()
    try:
        du = shutil.disk_usage(storage_dir if storage_dir.exists() else storage_dir.parent)
        disk = {"used_mb": du.used // 2**20, "total_mb": du.total // 2**20}
    except OSError:
        disk = None
    return {
        "cpu_percent": _cpu_percent(),
        "memory": {"used_mb": mem[0], "total_mb": mem[1]} if mem else None,
        "temperature_c": _temperature_c(),
        "storage": disk,
    }


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
