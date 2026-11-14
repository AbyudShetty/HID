"""Spike/collect REST path: issue a real challenge, upload a bundle (plan §8.2, T1.2-T1.3)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.challenge.sequence import ChallengeConfig
from app.main import create_app
from app.pipeline.bundle_io import pack_bundle
from app.schemas import Challenge
from tests.bundle_factory import make_entries

AUTH = {"Authorization": "Bearer test-operator-token"}
CT = {"Content-Type": "application/x-hid-bundle"}


@pytest.fixture()
def client(tmp_settings):
    with TestClient(create_app(tmp_settings)) as c:
        yield c


def issue(client, palette=None):
    url = "/api/v1/collect/challenge" + (f"?palette_id={palette}" if palette else "")
    r = client.get(url, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    return body["session_id"], Challenge.model_validate(body["challenge"]), body


def test_challenge_endpoint_requires_operator_token_and_returns_session_ready(client):
    assert client.get("/api/v1/collect/challenge").status_code == 401
    sid, challenge, body = issue(client)
    assert body["type"] == "session.ready"
    assert sid.startswith("s_") and 0 < body["expires_in_ms"] <= 30_000
    assert challenge.palette_id == ChallengeConfig().palette_id


def test_palette_can_be_forced_for_e2_and_rejects_unknown(client):
    _, challenge, _ = issue(client, "P2")
    assert challenge.palette_id == "P2"
    assert client.get("/api/v1/collect/challenge?palette_id=P9", headers=AUTH).status_code == 422


def test_upload_stores_the_bundle_and_returns_qc(client, tmp_settings):
    sid, challenge, _ = issue(client)
    blob = pack_bundle(make_entries(sid, challenge))
    r = client.post("/api/v1/collect/bundles", content=blob, headers={**AUTH, **CT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == sid and body["stored"] == f"sessions/{sid}"
    assert body["qc"]["n_keyframes"] == 2 and body["qc"]["covers_challenge"] is True
    stored = tmp_settings.data_dir / "sessions" / sid
    assert (stored / "label.json").exists() and (stored / "keyframes" / "k0.jpg").exists()
    assert json.loads((stored / "challenge.json").read_text())["challenge"]["nonce"] == challenge.nonce


def test_a_session_can_be_uploaded_only_once(client):
    sid, challenge, _ = issue(client)
    blob = pack_bundle(make_entries(sid, challenge))
    assert client.post("/api/v1/collect/bundles", content=blob, headers={**AUTH, **CT}).status_code == 200
    again = client.post("/api/v1/collect/bundles", content=blob, headers={**AUTH, **CT})
    assert again.status_code == 409


def test_fabricated_challenge_is_rejected(client):
    sid, challenge, _ = issue(client)
    forged = challenge.model_copy(update={"nonce": "forged-nonce-0123456789"})
    r = client.post("/api/v1/collect/bundles", content=pack_bundle(make_entries(sid, forged)), headers={**AUTH, **CT})
    assert r.status_code == 400
    assert "does not match" in r.json()["detail"]
    # the session is burnt: the genuine bundle can no longer be uploaded
    assert client.post("/api/v1/collect/bundles", content=pack_bundle(make_entries(sid, challenge)), headers={**AUTH, **CT}).status_code == 409


def test_unknown_session_is_rejected(client):
    _, challenge, _ = issue(client)
    r = client.post("/api/v1/collect/bundles", content=pack_bundle(make_entries("s_ffffffffffffffff", challenge)), headers={**AUTH, **CT})
    assert r.status_code == 409


def test_malformed_requests_are_rejected_with_reasons(client):
    sid, challenge, _ = issue(client)
    blob = pack_bundle(make_entries(sid, challenge))
    assert client.post("/api/v1/collect/bundles", content=blob, headers=AUTH).status_code == 415
    assert client.post("/api/v1/collect/bundles", content=blob, headers=CT).status_code == 401
    trunc = client.post("/api/v1/collect/bundles", content=blob[:-7], headers={**AUTH, **CT})
    assert trunc.status_code == 400 and "truncated" in trunc.json()["detail"]
    no_label = client.post("/api/v1/collect/bundles", content=pack_bundle(make_entries(sid, challenge, label=None)), headers={**AUTH, **CT})
    assert no_label.status_code == 400 and "label.json" in no_label.json()["detail"]
    # a rejected-before-consume request leaves the session usable
    assert client.post("/api/v1/collect/bundles", content=blob, headers={**AUTH, **CT}).status_code == 200
