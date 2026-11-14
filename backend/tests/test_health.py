from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_degraded_until_required_models_exist(tmp_settings):
    (tmp_settings.models_dir / "manifest.json").write_text(
        json.dumps({"version": 1, "models": [{"name": "scrfd", "file": "det.onnx", "required": True, "sha256": "ab" * 32}]}),
        encoding="utf-8",
    )
    with TestClient(create_app(tmp_settings)) as client:
        body = client.get("/api/v1/health").json()
    assert body["status"] == "degraded"
    assert body["models_loaded"] == {"scrfd": False}
    assert body["models"]["scrfd"]["state"] == "missing"
    assert body["storage"] == "local"
    assert body["policy_provisional"] is True


def test_health_ok_with_no_required_models(tmp_settings):
    with TestClient(create_app(tmp_settings)) as client:
        body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["policy_version"]
