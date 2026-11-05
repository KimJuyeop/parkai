"""현장 카메라 렌즈 사진을 정해진 간격으로 모은다 (밤·시간대별 정확도 시험용).

    python collect_snapshots.py --ip 192.168.20.1 192.168.20.2 --user admin --password **** \\
        --out 사진 --interval 600 --hours 24

- 파이썬 3 와 requests 만 있으면 된다 (윈도우 PC, Jetson, 보드 어디서든). parkai 설치 불필요
- 저장: <out>/<카메라IP>/ch<렌즈>/<날짜_시각>.jpg  → compare_judge·load_test 재생 폴더 형식과 같다
- 기본 주소는 IDIS 스냅샷 (2번 스트림, 렌즈별 channel). 다른 기종은 --url 로 바꾼다
- 카메라 하나가 응답하지 않아도 나머지는 계속 모은다
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

IDIS_URL = (
    "http://{ip}/cgi-bin/webSetup.cgi?action=videoStreamSnapshot&mode=1&streamIndex=2&channel={channel}"
)


def is_image(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def fetch(url: str, user: str, password: str, timeout: float) -> bytes:
    """기본 인증으로 받고, 401 이면 다이제스트 인증으로 다시 받는다."""
    r = requests.get(url, auth=HTTPBasicAuth(user, password), timeout=timeout)
    if r.status_code == 401:
        r = requests.get(url, auth=HTTPDigestAuth(user, password), timeout=timeout)
    r.raise_for_status()
    if not is_image(r.content):
        raise ValueError(f"이미지가 아닌 응답: {r.content[:60]!r}")
    return r.content


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ip", nargs="+", required=True, help="카메라 IP 여러 개")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--lenses", type=int, default=2, help="카메라 렌즈 수")
    ap.add_argument("--url", default=IDIS_URL, help="{ip}, {channel}(렌즈 번호, 1부터)이 들어가는 주소")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--interval", type=float, default=600, help="몇 초마다 (기본 10분)")
    ap.add_argument("--hours", type=float, default=24, help="몇 시간 동안")
    ap.add_argument("--timeout", type=float, default=5)
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    end = time.monotonic() + args.hours * 3600
    n = 0
    while True:
        n += 1
        start = time.monotonic()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ok, fail = 0, []
        for ip in args.ip:
            for ch in range(1, args.lenses + 1):
                try:
                    data = fetch(args.url.format(ip=ip, channel=ch), args.user, args.password, args.timeout)
                except Exception as e:  # 카메라 하나의 오류로 멈추지 않는다
                    fail.append(f"{ip} 렌즈{ch} ({type(e).__name__})")
                    continue
                d = args.out / ip / f"ch{ch}"
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{stamp}.jpg").write_bytes(data)
                ok += 1
        print(f"[{stamp}] {n}회: 저장 {ok}장" + (f", 실패 {len(fail)}: " + "; ".join(fail) if fail else ""))
        wait = args.interval - (time.monotonic() - start)
        if time.monotonic() + max(wait, 0) >= end:
            break
        if wait > 0:
            time.sleep(wait)
    print(f"끝: {args.out}")


if __name__ == "__main__":
    main()
