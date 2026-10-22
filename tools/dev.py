"""PC 개발용 실행기: 웹(8080) + 워커를 함께 띄운다.

    python tools/dev.py                 # 실제 카메라에서 스냅샷 (프로필의 snapshot_url)
    python tools/dev.py --replay        # samples/<카메라IP>/*.jpg 재생

- 설정 파일: data/config.json (없으면 examples/config.example.json을 복사)
- 모델이 없으면 fixture 검출기 사용 (이미지 옆 *.json 박스, 없으면 검출 없음 = 전부 빈칸)
- 웹: http://localhost:8080
- Ctrl+C로 둘 다 종료
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true", help="samples 폴더 이미지로 재생")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--backend", default="fixture", choices=["fixture", "onnx", "auto"])
    ap.add_argument("--no-worker", action="store_true", help="웹만 실행")
    args = ap.parse_args()

    data, run, samples = ROOT / "data", ROOT / "run", ROOT / "samples"
    for d in (data, run, samples):
        d.mkdir(exist_ok=True)
    cfg = data / "config.json"
    if not cfg.exists():
        shutil.copy(ROOT / "examples" / "config.example.json", cfg)
        print(f"설정 파일 생성: {cfg}")

    if not (ROOT / "parkai" / "web" / "static" / "index.html").exists():
        print(
            "웹 화면이 아직 빌드되지 않았습니다. 한 번 실행하세요:  cd frontend && npm install && npm run build"
        )
        print("(화면을 고치는 중이면 frontend 에서 npm run dev → http://localhost:5173)")

    env = dict(os.environ, PARKAI_CONFIG=str(cfg), PARKAI_RUN_DIR=str(run), PARKAI_SAMPLES=str(samples))
    web = subprocess.Popen([sys.executable, "-m", "parkai.web", "--port", str(args.port)], cwd=ROOT, env=env)
    print(f"웹: http://localhost:{args.port}")
    try:
        if args.no_worker:
            web.wait()
            return
        cmd = [
            sys.executable,
            "-m",
            "parkai.worker",
            "--config",
            str(cfg),
            "--backend",
            args.backend,
            "--run-dir",
            str(run),
            "--data-dir",
            str(data),
            "--models-dir",
            str(ROOT / "models"),
        ]
        if args.replay:
            cmd += ["--replay", str(samples)]
        subprocess.run(cmd, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        pass
    finally:
        web.terminate()


if __name__ == "__main__":
    main()
