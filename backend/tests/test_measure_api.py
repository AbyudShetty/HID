"""/collect/measure: auth, exact-challenge enforcement, single use, and no persistence."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.main import create_app
from app.pipeline.bundle_io import pack_bundle
from app.schemas import Challenge
from tests.bundle_factory import make_entries

AUTH = {"Authorization": "Bearer test-operator-token"}
CT = {"Content-Type": "application/x-hid-bundle"}


def issue(client):
    body = client.get("/api/v1/collect/challenge", headers=AUTH).json()
    return body["session_id"], Challenge.model_validate(body["challenge"])


@pytest.fixture()
def client(tmp_settings):
    with TestClient(create_app(tmp_settings)) as c:
        yield c


def test_measure_requires_operator_token(client):
    assert client.post("/api/v1/collect/measure", content=b"x", headers=CT).status_code == 401
    assert client.post("/api/v1/collect/preview", content=b"x", headers={"Content-Type": "image/jpeg"}).status_code == 401


def test_forged_challenge_is_rejected_before_any_processing(client, tmp_settings):
    client.app.state.chroma_instrument.detector = object()  # admission passes; the forged-challenge check is what is under test
    sid, ch = issue(client)
    forged = ch.model_copy(update={"nonce": "forged-nonce-0123456789"})
    r = client.post("/api/v1/collect/measure", content=pack_bundle(make_entries(sid, forged, label=None)), headers={**AUTH, **CT})
    assert r.status_code == 400 and "does not match" in r.json()["detail"]
    assert not (tmp_settings.data_dir / "sessions").exists()


def test_unavailable_model_is_503_and_nothing_is_stored(client, tmp_settings):
    sid, ch = issue(client)  # tmp models dir is empty: SCRFD is not available
    r = client.post("/api/v1/collect/measure", content=pack_bundle(make_entries(sid, ch, label=None)), headers={**AUTH, **CT})
    assert r.status_code == 503
    assert not (tmp_settings.data_dir / "sessions").exists()
    # the challenge was NOT consumed: retrying the same capture reports the same 503, not "already used" (409)
    again = client.post("/api/v1/collect/measure", content=pack_bundle(make_entries(sid, ch, label=None)), headers={**AUTH, **CT})
    assert again.status_code == 503


def test_busy_instrument_is_429_and_does_not_consume_the_challenge(client):
    sid, ch = issue(client)
    blob = pack_bundle(make_entries(sid, ch, label=None))
    inst = client.app.state.chroma_instrument
    inst.detector = object()  # pretend loaded so only the busy check matters
    assert inst.lock.acquire(blocking=False)
    try:
        r = client.post("/api/v1/collect/measure", content=blob, headers={**AUTH, **CT})
        assert r.status_code == 429 and r.headers["retry-after"] == "1"
    finally:
        inst.lock.release()
    inst.detector = None
    # still unconsumed: the next attempt fails for the model (503), not because the session was burnt (409)
    assert client.post("/api/v1/collect/measure", content=blob, headers={**AUTH, **CT}).status_code == 503


@pytest.mark.models
def test_measure_with_real_models_is_transient_and_single_use(tmp_path):
    settings = Settings(kiosk_token="k", operator_token="test-operator-token", data_dir=tmp_path / "data", models_dir=REPO_ROOT / "models", _env_file=None)
    with TestClient(create_app(settings)) as c:
        sid, ch = issue(c)
        blob = pack_bundle(make_entries(sid, ch, label=None))
        r = c.post("/api/v1/collect/measure", content=blob, headers={**AUTH, **CT})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "unavailable"  # solid-colour synthetic crops contain no face; no invented score
        assert not (tmp_path / "data" / "sessions").exists()
        assert c.post("/api/v1/collect/measure", content=blob, headers={**AUTH, **CT}).status_code == 409
