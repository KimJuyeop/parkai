"""서버 전송을 받아 보기만 하는 시험용 서버 (실제 주차 서버가 없을 때).

    python3 tools/fake_server.py --port 9000

웹 화면 '서버 전송' 에서 주소를 http://<이 프로그램을 띄운 곳의 IP>:9000 으로 두면, 보드가 보내는
칸 상태(ps01~ps12)를 받을 때마다 한 줄씩 보여 준다. 보드 안에서 띄우면 주소는 http://127.0.0.1:9000.
- 파이썬 표준 라이브러리만 쓴다 (보드, 윈도우 PC 어디서든). 받기만 하고 아무 데도 저장하지 않는다
- --fail 을 주면 500 으로 답해 '서버 전송 오류' 표시와 복구를 시험할 수 있다
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--fail", action="store_true", help="모든 요청에 500 으로 답한다")
    args = ap.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server 이름 규칙)
            body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            try:
                data = json.loads(body).get("data", {})
                ps = " ".join(f"{k[2:]}:{v}" for k, v in sorted(data.items()) if k.startswith("ps"))
                line = f"{data.get('ipaddress')} (보드 {data.get('boardip')}) {ps}"
            except (ValueError, AttributeError):
                line = f"JSON 아님: {body[:200]!r}"
            print(f"{datetime.now():%H:%M:%S} {self.path} {line}", flush=True)
            self.send_response(500 if args.fail else 200)
            self.end_headers()

        def log_message(self, *a) -> None:  # 기본 접속 로그는 끈다
            pass

    print(f"서버 전송 받기: 포트 {args.port}{' (모두 500 으로 답함)' if args.fail else ''}. 끝내려면 Ctrl+C")
    try:
        ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
