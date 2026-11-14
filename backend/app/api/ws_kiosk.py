"""Persistent kiosk WebSocket (plan §8.1).

Implemented so far (T0.3): authenticate with ``hello`` -> ``hello_ack``, ``ping``/``pong``. Every other message
type is answered with an explicit ``error PROTOCOL`` ("not supported in this build") until the session manager and
online pipeline land (T3.1-T3.3). Nothing here fabricates a session or a decision.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from .. import __version__
from ..schemas import (
    CaptureConfig,
    ClientMessage,
    ErrorMsg,
    Hello,
    HelloAck,
    Ping,
    PolicyInfo,
    Pong,
)
from .auth import kiosk_token_ok

router = APIRouter()
_CLIENT = TypeAdapter(ClientMessage)
HELLO_TIMEOUT_S = 10.0
WS_PROTOCOL_ERROR = 1002
WS_POLICY_VIOLATION = 1008


async def _send(ws: WebSocket, msg) -> None:
    await ws.send_text(msg.model_dump_json(by_alias=True))


async def _fail(ws: WebSocket, code: str, message: str, close_code: int) -> None:
    await _send(ws, ErrorMsg(code=code, message=message))
    await ws.close(code=close_code)


@router.websocket("/api/v1/kiosk/ws")
async def kiosk_ws(ws: WebSocket) -> None:
    settings = ws.app.state.settings
    policy = ws.app.state.policy
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=HELLO_TIMEOUT_S)
    except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
        await ws.close(code=WS_POLICY_VIOLATION)
        return
    try:
        hello = _CLIENT.validate_json(first)
    except ValidationError:
        await _fail(ws, "PROTOCOL", "first message must be a valid hello", WS_PROTOCOL_ERROR)
        return
    if not isinstance(hello, Hello):
        await _fail(ws, "PROTOCOL", "first message must be hello", WS_PROTOCOL_ERROR)
        return
    if not kiosk_token_ok(settings, hello.kiosk_token):
        await _fail(ws, "BAD_TOKEN", "invalid kiosk token", WS_POLICY_VIOLATION)
        return

    await _send(
        ws,
        HelloAck(
            server_version=__version__,
            server_time_iso=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            capture_config=CaptureConfig(),
            policy=PolicyInfo(version=policy.version, provisional=policy.provisional),
            kiosk_profile_version=None,
        ),
    )

    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                await _send(ws, ErrorMsg(code="PROTOCOL", message="binary frames are not supported in this build (needs a session)"))
                continue
            try:
                msg = _CLIENT.validate_json(text)
            except ValidationError:
                await _send(ws, ErrorMsg(code="PROTOCOL", message="invalid message"))
                continue
            if isinstance(msg, Ping):
                await _send(ws, Pong())
            elif isinstance(msg, Pong):
                continue
            else:
                await _send(ws, ErrorMsg(code="PROTOCOL", message=f"{msg.type} is not supported in this build"))
    except WebSocketDisconnect:
        return
