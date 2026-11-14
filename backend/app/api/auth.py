"""Token checks (plan §8.2): constant-time comparison, fail closed when no token is configured."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from ..config import Settings


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def token_ok(expected: str, presented: str | None) -> bool:
    """False when the server has no token configured (fail closed) or the presented token differs."""
    if not expected or not presented:
        return False
    return constant_time_equals(expected, presented)


def kiosk_token_ok(settings: Settings, presented: str | None) -> bool:
    return token_ok(settings.kiosk_token, presented)


def require_operator(request: Request) -> None:
    """FastAPI dependency: ``Authorization: Bearer <OPERATOR_TOKEN>``."""
    settings: Settings = request.app.state.settings
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not token_ok(settings.operator_token, presented.strip()):
        raise HTTPException(status_code=401, detail="operator token required", headers={"WWW-Authenticate": "Bearer"})
