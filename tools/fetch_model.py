"""ST 사전학습 모델 받기 (PC·보드 공통, 인터넷 필요).

    python tools/fetch_model.py                      # models/ 아래 model.json 이 있는 모든 모델
    python tools/fetch_model.py st_yoloxn_coco80_480

model.json 의 source.repo / source.path 에서 model.onnx 를 받아 sha256 을 확인한다.
모델 파일은 Git에 올리지 않는다 (.gitignore). 라이선스: ST SLA0044.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"


def media_url(repo: str, path: str, branch: str = "main") -> str:
    # GitHub LFS 파일은 raw 주소가 아니라 media 주소에서 받는다
    owner_repo = repo.rstrip("/").split("github.com/")[1]
    return f"https://media.githubusercontent.com/media/{owner_repo}/{branch}/{path}"


def fetch(name: str) -> None:
    d = MODELS / name
    meta = json.loads((d / "model.json").read_text(encoding="utf-8"))
    src = meta.get("source")
    if not src:
        print(f"{name}: source 정보 없음, 건너뜀")
        return
    out = d / "model.onnx"
    if out.exists() and hashlib.sha256(out.read_bytes()).hexdigest() == src["sha256"]:
        print(f"{name}: 이미 있음")
        return
    url = media_url(src["repo"], src["path"], src.get("branch", "main"))
    print(f"{name}: 받는 중 {url}")
    data = urllib.request.urlopen(url, timeout=60).read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != src["sha256"]:
        sys.exit(f"{name}: sha256 불일치 ({digest})")
    out.write_bytes(data)
    print(f"{name}: 완료 ({len(data) / 1e6:.1f}MB)")


def main() -> None:
    names = sys.argv[1:] or sorted(p.parent.name for p in MODELS.glob("*/model.json"))
    for n in names:
        fetch(n)


if __name__ == "__main__":
    main()
