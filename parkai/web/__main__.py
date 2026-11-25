"""웹 서버 실행: python -m parkai.web [--port 80]"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(prog="parkai.web")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=80)
    args = ap.parse_args()
    print(f"웹 설정 화면: http://localhost:{args.port}  (다른 PC에서는 http://<이 PC의 IP>:{args.port})")
    # 요청마다 남는 접속 로그는 끈다: 모니터링 화면이 몇 초마다 상태·사진을 요청해서, 보드 로그(RAM 50MB)를
    # 몇 시간 만에 채우고 워커 로그를 밀어냈다 (현장 하루 시험에서 워커 로그가 6.5시간치만 남음)
    uvicorn.run("parkai.web.app:app", host=args.host, port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
