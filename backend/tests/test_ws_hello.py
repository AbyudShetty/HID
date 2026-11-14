"""Kiosk WebSocket hello round trip and auth (plan §8.1, T0.3)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app

WS = "/api/v1/kiosk/ws"


@pytest.fixture()
def client(tmp_settings):
    with TestClient(create_app(tmp_settings)) as c:
        yield c


def _hello(samples, token="test-kiosk-token"):
    return dict(samples["client"]["hello"], kiosk_token=token)


def test_hello_round_trip(client, samples):
    with client.websocket_connect(WS) as ws:
        ws.send_json(_hello(samples))
        ack = ws.receive_json()
    assert ack["type"] == "hello_ack"
    assert ack["policy"]["provisional"] is True
    assert ack["capture_config"]["crop_size"] == 256


def test_bad_token_is_rejected_and_closed(client, samples):
    with client.websocket_connect(WS) as ws:
        ws.send_json(_hello(samples, token="wrong"))
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "BAD_TOKEN"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_server_with_no_configured_token_fails_closed(tmp_settings, samples):
    tmp_settings.kiosk_token = ""
    with TestClient(create_app(tmp_settings)) as c, c.websocket_connect(WS) as ws:
        ws.send_json(_hello(samples, token=""))
        assert ws.receive_json()["code"] == "BAD_TOKEN"


def test_first_message_must_be_hello(client, samples):
    with client.websocket_connect(WS) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["code"] == "PROTOCOL"
    with client.websocket_connect(WS) as ws:
        ws.send_text("{not json")
        assert ws.receive_json()["code"] == "PROTOCOL"


def test_ping_pong_and_honest_errors_for_unbuilt_messages(client, samples):
    with client.websocket_connect(WS) as ws:
        ws.send_json(_hello(samples))
        ws.receive_json()
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        ws.send_json(samples["client"]["session.request"])
        err = ws.receive_json()
        assert err["code"] == "PROTOCOL"
        assert "not supported" in err["message"]
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_json()["code"] == "PROTOCOL"
        ws.send_text(json.dumps({"type": "nope"}))
        assert ws.receive_json()["message"] == "invalid message"


def test_config_requires_operator_token(client):
    assert client.get("/api/v1/config").status_code == 401
    assert client.get("/api/v1/config", headers={"Authorization": "Bearer nope"}).status_code == 401
    ok = client.get("/api/v1/config", headers={"Authorization": "Bearer test-operator-token"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["policy"]["provisional"] is True
    assert body["policy"]["thresholds"]["identity.tau_match_1to1"] == {"value": None, "source": "uncalibrated"}


def test_config_fails_closed_without_configured_operator_token(tmp_settings):
    tmp_settings.operator_token = ""
    with TestClient(create_app(tmp_settings)) as c:
        assert c.get("/api/v1/config", headers={"Authorization": "Bearer "}).status_code == 401
