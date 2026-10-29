import json
import shutil

from fastapi.testclient import TestClient


def make_client(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    shutil.copy("examples/config.example.json", cfg)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data["cameras"][0]["password"] = "secret"
    cfg.write_text(json.dumps(data), encoding="utf-8")

    import parkai.web.app as appmod

    monkeypatch.setattr(appmod, "CONFIG", cfg)
    monkeypatch.setattr(appmod, "RUN_DIR", tmp_path / "run")
    return TestClient(appmod.app), cfg


def test_password_masked_and_kept(tmp_path, monkeypatch):
    client, cfg = make_client(tmp_path, monkeypatch)
    got = client.get("/api/v1/config").json()
    assert got["cameras"][0]["password"] == "****"

    got["cameras"][0]["slots"].append({"no": 6, "type": "ev", "line": [[0.1, 0.2], [0.3, 0.4]]})
    assert client.put("/api/v1/config", json=got).status_code == 200

    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["cameras"][0]["password"] == "secret"  # 마스킹 값으로 덮어쓰지 않음
    assert saved["cameras"][0]["slots"][-1]["type"] == "ev"


def test_invalid_config_rejected(tmp_path, monkeypatch):
    client, cfg = make_client(tmp_path, monkeypatch)
    got = client.get("/api/v1/config").json()
    got["cameras"][0]["slots"].append({"no": 1, "line": [[0, 0], [0.1, 0.1]]})  # 번호 중복
    r = client.put("/api/v1/config", json=got)
    assert r.status_code == 422
    assert "중복" in " ".join(r.json()["detail"])


def test_status_when_worker_not_running(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/status").json()["running"] is False


def test_snapshot_bad_url_template_is_clear_error(tmp_path, monkeypatch):
    client, cfg = make_client(tmp_path, monkeypatch)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data["camera_profiles"]["2분할 카메라"]["snapshot_url"] = "http://{camip}/snap.jpg"
    cfg.write_text(json.dumps(data), encoding="utf-8")
    r = client.get("/api/v1/cameras/192.168.13.21/snapshot")
    assert r.status_code == 502  # 500이 아니라 원인 메시지
    assert "URL 형식" in r.json()["detail"]


def test_snapshot_url_accepts_ipaddress():
    from parkai.core.config import Camera
    from parkai.worker.sources import build_snapshot_url

    cam = Camera(ip="192.168.0.5", port=8080, profile="p")
    url = "http://{ipaddress}/cgi-bin/webSetup.cgi?action=videoStreamSnapshot&mode=1"
    assert build_snapshot_url(url, cam).startswith("http://192.168.0.5/cgi-bin")
    assert build_snapshot_url("http://{ip}:{port}/x", cam) == "http://192.168.0.5:8080/x"


def test_profile_account_masked_and_used(tmp_path, monkeypatch):
    client, cfg = make_client(tmp_path, monkeypatch)
    got = client.get("/api/v1/config").json()
    got["camera_profiles"]["2분할 카메라"]["password"] = "common-pw"
    got["cameras"][0]["own_account"] = False  # 공통 계정 사용
    assert client.put("/api/v1/config", json=got).status_code == 200
    got = client.get("/api/v1/config").json()
    assert got["camera_profiles"]["2분할 카메라"]["password"] == "****"
    assert client.put("/api/v1/config", json=got).status_code == 200  # 마스킹 그대로 다시 저장

    from parkai.core.config import load_config

    c = load_config(cfg)
    cam = c.cameras[0]
    assert c.camera_profiles[cam.profile].password == "common-pw"
    assert c.camera_account(cam) == ("admin", "common-pw")  # 개별 계정이 아니면 프로필 계정
    cam.own_account = True
    assert c.camera_account(cam) == (cam.user, "secret")


def test_old_config_with_camera_password_keeps_own_account():
    from parkai.core.config import AppConfig

    c = AppConfig.model_validate(
        {
            "camera_profiles": {"p": {"snapshot_url": "x"}},
            "cameras": [{"ip": "1.1.1.1", "profile": "p", "user": "u", "password": "pw"}],
        }
    )
    assert c.cameras[0].own_account and c.camera_account(c.cameras[0]) == ("u", "pw")


def test_system_reports_resources(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    res = client.get("/api/v1/system").json()["resources"]
    assert set(res) == {"cpu_percent", "memory", "temperature_c", "storage"}
    if res["memory"]:  # Linux에서는 /proc/meminfo 로 읽힘
        assert 0 < res["memory"]["used_mb"] <= res["memory"]["total_mb"]


def test_default_indicator_colors_per_slot_type():
    from parkai.core.config import AppConfig

    colors = {t.id: t.color_available for t in AppConfig().slot_types}
    assert colors == {"normal": "green", "compact": "purple", "disabled": "blue", "ev": "cyan"}
    # 저장된 색은 그대로 유지
    cfg = AppConfig.model_validate({"slot_types": [{"id": "ev", "name": "x", "color_available": "white"}]})
    assert {t.id: t.color_available for t in cfg.slot_types}["ev"] == "white"


def test_snapshot_per_lens_from_samples(tmp_path, monkeypatch):
    """렌즈마다 사진을 따로 준다. 샘플 폴더는 <IP>/ch<렌즈>/ (첫 렌즈는 <IP>/ 도 됨)."""
    client, cfg = make_client(tmp_path, monkeypatch)
    import parkai.web.app as appmod

    data = json.loads(cfg.read_text(encoding="utf-8"))
    data["cameras"][0]["profile"] = "IDIS 렌즈 2개"
    data["cameras"][0]["port"] = 1  # 실제 카메라는 없음 → 샘플로
    cfg.write_text(json.dumps(data), encoding="utf-8")
    for ch, body in [(1, b"\xff\xd8\xff lens1"), (2, b"\xff\xd8\xff lens2")]:
        d = tmp_path / "samples" / "192.168.13.21" / f"ch{ch}"
        d.mkdir(parents=True)
        (d / "0001.jpg").write_bytes(body)
    monkeypatch.setattr(appmod, "SAMPLES", tmp_path / "samples")
    monkeypatch.setattr(
        appmod.HttpSnapshotSource, "fetch", lambda self: (_ for _ in ()).throw(appmod.SourceError("x"))
    )
    assert client.get("/api/v1/cameras/192.168.13.21/snapshot?lens=0").content.endswith(b"lens1")
    assert client.get("/api/v1/cameras/192.168.13.21/snapshot?lens=1").content.endswith(b"lens2")
    assert client.get("/api/v1/cameras/192.168.13.21/snapshot?lens=2").status_code == 404
