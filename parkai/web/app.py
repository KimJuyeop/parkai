"""웹 설정 툴 API (FastAPI) + 정적 화면.

환경변수
  PARKAI_CONFIG   설정 파일 (기본 /var/lib/parkai/config.json)
  PARKAI_RUN_DIR  워커 상태/최신 이미지 (기본 /run/parkai)
  PARKAI_SAMPLES  카메라에 접속할 수 없을 때 쓸 샘플 이미지 폴더 (<폴더>/<카메라IP>/[ch<렌즈>/]*.jpg)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

import requests
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .. import __version__
from ..core.config import LED_RGB, AppConfig, load_config
from ..core.system import board_ip, board_model, device_id, resources
from ..outputs.indicator import led_url, return_code
from ..outputs.server import build_payload
from ..worker.sources import IMAGE_EXT, HttpSnapshotSource, SourceError, image_media_type, replay_folder

CONFIG = Path(os.environ.get("PARKAI_CONFIG", "/var/lib/parkai/config.json"))
RUN_DIR = Path(os.environ.get("PARKAI_RUN_DIR", "/run/parkai"))
SAMPLES = Path(os.environ["PARKAI_SAMPLES"]) if os.environ.get("PARKAI_SAMPLES") else None
STATIC = Path(os.environ.get("PARKAI_STATIC", Path(__file__).resolve().parent / "static"))

MASK = "****"

app = FastAPI(title="parkai", version=__version__)


def _cfg() -> AppConfig:
    try:
        return load_config(CONFIG)
    except FileNotFoundError:
        return AppConfig()


def _camera(cfg: AppConfig, ip: str):
    for c in cfg.cameras:
        if c.ip == ip:
            return c
    raise HTTPException(404, f"카메라 없음: {ip}")


def _write_config(cfg: AppConfig) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG)  # 워커는 파일 변경을 감지해 다음 사이클에 반영


def _errors(e: ValidationError) -> list[str]:
    out = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        out.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return out


# ---------- 시스템 / 상태 ----------


@app.get("/api/v1/system")
def system():
    cfg = _cfg()
    return {
        "version": __version__,
        "device_id": device_id(),
        "board_model": board_model(),
        "board_ip": board_ip(cfg.network.board_ip),
        "site": cfg.site.model_dump(),
        "model": cfg.detection.model,
        "preset": cfg.detection.preset,
        "config_path": str(CONFIG),
        "resources": resources(CONFIG.parent),
    }


@app.get("/api/v1/status")
def status():
    p = RUN_DIR / "status.json"
    if not p.exists():
        return JSONResponse({"running": False, "cameras": {}}, status_code=200)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["running"] = True
    return data


# ---------- 설정 ----------


@app.get("/api/v1/config")
def get_config():
    data = _cfg().model_dump(mode="json")
    for item in [*data["cameras"], *data["camera_profiles"].values()]:
        item["password"] = MASK if item["password"] else ""
    return data


@app.put("/api/v1/config")
def put_config(data: dict = Body(...)):
    """설정 전체 저장. 비밀번호가 '****'이면 기존 값을 유지한다."""
    cur = _cfg()
    old_cam = {c.ip: c.password for c in cur.cameras}
    old_prof = {k: p.password for k, p in cur.camera_profiles.items()}
    for cam in data.get("cameras", []):
        if cam.get("password") == MASK:
            cam["password"] = old_cam.get(cam.get("ip"), "")
    for name, prof in (data.get("camera_profiles") or {}).items():
        if prof.get("password") == MASK:
            prof["password"] = old_prof.get(name, "")
    try:
        cfg = AppConfig.model_validate(data)
    except ValidationError as e:
        raise HTTPException(422, _errors(e)) from e
    _write_config(cfg)
    return {"ok": True}


@app.get("/api/v1/config/export")
def export_config(passwords: bool = False):
    data = _cfg().model_dump(mode="json")
    if not passwords:
        for item in [*data["cameras"], *data["camera_profiles"].values()]:
            item["password"] = ""
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="parkai-config.json"'},
    )


# ---------- 카메라 영상 ----------


def _sample_image(ip: str, lens: int) -> Path | None:
    if SAMPLES is None:
        return None
    d = replay_folder(SAMPLES, ip, lens)
    files = sorted(p for p in d.glob("*") if p.suffix.lower() in IMAGE_EXT) if d.is_dir() else []
    return files[-1] if files else None


@app.get("/api/v1/cameras/{ip}/snapshot")
def snapshot(
    ip: str,
    lens: int = Query(0, ge=0),
    source: str = Query("auto", pattern="^(auto|live|sample)$"),
):
    """렌즈 하나의 스냅샷 (받은 원본 그대로). auto: 카메라 실패 시 샘플 이미지.
    화면이 분석 영역만 잘라 보여 주므로 여기서는 다시 인코딩하지 않는다."""
    cfg = _cfg()
    cam = _camera(cfg, ip)
    if lens >= cfg.camera_lenses(cam):
        raise HTTPException(404, f"렌즈 {lens + 1}이 없습니다")
    error = None
    data = None
    headers = {"Cache-Control": "no-store"}
    if source in ("auto", "live"):
        profile = cfg.camera_profiles[cam.profile]
        try:
            data, _ = HttpSnapshotSource(cam, profile, cfg.runtime.fetch_timeout_sec, 0, lens).fetch()
            headers["X-Parkai-Source"] = "live"
        except SourceError as e:
            error = str(e)
    if data is None and source in ("auto", "sample"):
        sample = _sample_image(ip, lens)
        if sample is not None:
            data = sample.read_bytes()
            headers["X-Parkai-Source"] = "sample"
            if error:  # 헤더는 latin-1만 가능하므로 URL 인코딩
                headers["X-Parkai-Error"] = quote(error[:300])
    if data is None:
        raise HTTPException(502, f"스냅샷을 가져오지 못했습니다: {error or '샘플 없음'}")
    return Response(data, media_type=image_media_type(data), headers=headers)


@app.get("/api/v1/cameras/{ip}/latest")
def latest_image(ip: str, lens: int = Query(0, ge=0)):
    """워커가 받은 렌즈 원본 (매 사이클 갱신)."""
    p = RUN_DIR / "latest" / f"{ip}_{lens}.jpg"
    if not p.exists() or p.parent != (RUN_DIR / "latest"):
        raise HTTPException(404)
    media = image_media_type(p.read_bytes()[:16])
    return FileResponse(p, media_type=media, headers={"Cache-Control": "no-store"})


# ---------- 만공등 테스트 ----------


@app.post("/api/v1/cameras/{ip}/led")
def led_test(ip: str, color: str = Body(..., embed=True)):
    """만공등에 색 하나를 바로 보내 본다 (설정의 만공등 사용 여부와 상관없이)."""
    cfg = _cfg()
    cam = _camera(cfg, ip)
    if color not in LED_RGB:
        raise HTTPException(422, f"색: {', '.join(LED_RGB)}")
    profile = cfg.camera_profiles[cam.profile]
    user, password = cfg.camera_account(cam)
    auth = None
    if profile.auth == "basic":
        auth = HTTPBasicAuth(user, password)
    elif profile.auth == "digest":
        auth = HTTPDigestAuth(user, password)
    url = led_url(cam, cfg.indicator, color)
    try:
        r = requests.get(url, auth=auth, timeout=cfg.runtime.fetch_timeout_sec)
    except requests.RequestException as e:
        return {"ok": False, "url": url, "error": str(e)}
    code = return_code(r.text)
    return {
        "ok": r.status_code == 200 and code == 0,
        "url": url,
        "status_code": r.status_code,
        "return_code": code,
    }


# ---------- 서버 전송 테스트 ----------


@app.post("/api/v1/server/test")
def server_test(camera_ip: str | None = Body(None, embed=True)):
    """현재 상태(없으면 전부 unknown)로 서버에 한 번 보내 본다."""
    cfg = _cfg()
    if not cfg.server.base_url:
        raise HTTPException(400, "서버 주소가 비어 있습니다")
    ip = camera_ip or (cfg.cameras[0].ip if cfg.cameras else "0.0.0.0")
    states: dict[int, bool] = {}
    p = RUN_DIR / "status.json"
    if p.exists():
        cam = json.loads(p.read_text(encoding="utf-8")).get("cameras", {}).get(ip, {})
        states = {int(k): v for k, v in cam.get("states", {}).items()}
    payload = build_payload(ip, board_ip(cfg.network.board_ip), states)
    try:
        r = requests.post(cfg.server.url, json=payload, timeout=cfg.server.timeout_sec)
        return {"url": cfg.server.url, "status_code": r.status_code, "body": r.text[:500], "payload": payload}
    except requests.RequestException as e:
        return {"url": cfg.server.url, "error": str(e), "payload": payload}


if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
