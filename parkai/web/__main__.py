"""웹 서버 실행: python -m parkai.web [--port 80]"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(prog="parkai.web")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=80)
    args = ap.parse_args()
    uvicorn.run("parkai.web.app:app", host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
