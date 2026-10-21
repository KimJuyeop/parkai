"""웹 설정 툴 API (FastAPI).

1차 골격: 시스템 정보, 상태, 카메라 목록, 최신 결과 이미지.
설정 수정 API와 화면은 시안 확정 후 추가한다 (docs/design.md 5단계).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..core.config import load_config
from ..core.system import board_ip, board_model, device_id

CONFIG = Path(os.environ.get("PARKAI_CONFIG", "/var/lib/parkai/config.json"))
RUN_DIR = Path(os.environ.get("PARKAI_RUN_DIR", "/run/parkai"))
STATIC = Path(os.environ.get("PARKAI_STATIC", Path(__file__).resolve().parents[2] / "frontend" / "dist"))

app = FastAPI(title="parkai", version=__version__)


@app.get("/api/v1/system")
def system():
    cfg = load_config(CONFIG)
    return {
        "version": __version__,
        "device_id": device_id(),
        "board_model": board_model(),
        "board_ip": board_ip(cfg.network.board_ip),
        "site": cfg.site.model_dump(),
        "model": cfg.detection.model,
        "preset": cfg.detection.preset,
    }


@app.get("/api/v1/status")
def status():
    p = RUN_DIR / "status.json"
    if not p.exists():
        raise HTTPException(503, "워커 상태 없음 (워커가 실행 중인지 확인)")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/v1/cameras")
def cameras():
    cfg = load_config(CONFIG)
    out = []
    for c in cfg.cameras:
        d = c.model_dump(mode="json")
        d["password"] = "****" if c.password else ""
        out.append(d)
    return out


@app.get("/api/v1/cameras/{ip}/latest")
def latest_image(ip: str):
    p = RUN_DIR / "latest" / f"{ip}.jpg"
    if not p.exists() or p.parent != (RUN_DIR / "latest"):
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
