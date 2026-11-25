"""웹 설정 툴 API (FastAPI) + 정적 화면.

환경변수
  PARKAI_CONFIG   설정 파일 (기본 /var/lib/parkai/config.json)
  PARKAI_RUN_DIR  워커 상태/최신 이미지 (기본 /run/parkai)
  PARKAI_SAMPLES  카메라에 접속할 수 없을 때 쓸 샘플 이미지 폴더 (<폴더>/<카메라IP>/[ch<렌즈>/]*.jpg)
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import requests
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .. import BUILD, __version__
from ..core.config import LED_RGB, AppConfig, load_config
from ..core.system import board_ip, board_model, device_id, resources
from ..outputs.indicator import LedUrlError, led_ok, led_url
from ..outputs.server import build_payload
from ..worker.sources import IMAGE_EXT, HttpSnapshotSource, SourceError, image_media_type, replay_folder

CONFIG = Path(os.environ.get("PARKAI_CONFIG", "/var/lib/parkai/config.json"))
RUN_DIR = Path(os.environ.get("PARKAI_RUN_DIR", "/run/parkai"))
MODELS = Path(os.environ.get("PARKAI_MODELS", "/var/lib/parkai/models"))
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
        "version": BUILD,
        "device_id": device_id(),
        "board_model": board_model(),
        "board_ip": board_ip(cfg.server.base_url),
        "site": cfg.site.model_dump(),
        "model": cfg.detection.model,
        "preset": cfg.detection.preset,
        "config_path": str(CONFIG),
        "resources": resources(CONFIG.parent),
    }


MODEL_FILES = ("model.nb", "model.onnx", "model.tflite", "model.weights")


@app.get("/api/v1/models")
def models():
    """모델 폴더 아래에서 쓸 수 있는 모델 (model.json 과 모델 파일이 있는 폴더)."""
    out = []
    if MODELS.is_dir():
        for d in sorted(MODELS.iterdir()):
            if not (d / "model.json").is_file():
                continue
            files = [f for f in MODEL_FILES if (d / f).is_file()]
            note = ""
            try:
                note = str(json.loads((d / "model.json").read_text(encoding="utf-8")).get("note", ""))
            except (OSError, ValueError):
                pass
            out.append({"name": d.name, "files": files, "note": note})
    return {"models": out}


@app.get("/api/v1/status")
def status():
    p = RUN_DIR / "status.json"
    if not p.exists():
        return JSONResponse({"running": False, "cameras": {}}, status_code=200)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["running"] = True
    # 보드 시각: 화면이 '몇 초 전'·워커 정지를 보드 시계끼리 비교하게 한다. 현장은 인터넷(시간 동기화)이 없어
    # 보드 시계가 틀릴 수 있는데, 브라우저 시계와 비교하면 워커가 돌아도 '정지'로 보인다
    data["now"] = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
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


@app.get("/api/v1/images.zip")
def images_zip():
    """워커가 지금 갖고 있는 렌즈별 최신 원본 사진과 status.json 을 ZIP 으로 (현장 분석용).
    JPEG 는 이미 압축돼 있어 압축하지 않고 담는다 (보드 CPU 를 쓰지 않게)."""
    files = sorted((RUN_DIR / "latest").glob("*.jpg"))
    if not files:
        raise HTTPException(404, "최신 이미지가 없습니다 (워커가 판정 중이 아님)")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, f"images/{f.name}")
        st = RUN_DIR / "status.json"
        if st.exists():
            z.write(st, "status.json")
    name = f"parkai-images-{datetime.now().astimezone().strftime('%Y%m%d_%H%M')}.zip"
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
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
    try:
        url = led_url(cam, profile, color)
    except LedUrlError as e:
        return {"ok": False, "url": profile.led_url, "error": str(e)}
    try:
        r = requests.get(url, auth=auth, timeout=cfg.runtime.fetch_timeout_sec)
    except requests.RequestException as e:
        return {"ok": False, "url": url, "error": str(e)}
    ok, code = led_ok(r.status_code, r.text)
    return {"ok": ok, "url": url, "status_code": r.status_code, "return_code": code}


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
    payload = build_payload(ip, board_ip(cfg.server.base_url), states)
    try:
        r = requests.post(cfg.server.url, json=payload, timeout=cfg.server.timeout_sec)
        return {"url": cfg.server.url, "status_code": r.status_code, "body": r.text[:500], "payload": payload}
    except requests.RequestException as e:
        return {"url": cfg.server.url, "error": str(e), "payload": payload}


if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
