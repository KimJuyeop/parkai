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

    got["cameras"][0]["slots"].append({"no": 6, "type": "ev", "line": [[1, 2], [3, 4]]})
    assert client.put("/api/v1/config", json=got).status_code == 200

    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["cameras"][0]["password"] == "secret"  # 마스킹 값으로 덮어쓰지 않음
    assert saved["cameras"][0]["slots"][-1]["type"] == "ev"


def test_invalid_config_rejected(tmp_path, monkeypatch):
    client, cfg = make_client(tmp_path, monkeypatch)
    got = client.get("/api/v1/config").json()
    got["cameras"][0]["slots"].append({"no": 1, "line": [[0, 0], [1, 1]]})  # 번호 중복
    r = client.put("/api/v1/config", json=got)
    assert r.status_code == 422
    assert "중복" in " ".join(r.json()["detail"])


def test_status_when_worker_not_running(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/status").json()["running"] is False
