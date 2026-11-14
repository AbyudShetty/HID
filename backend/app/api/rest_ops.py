"""Operator REST endpoints (plan §8.2). Implemented so far: ``GET /config``."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..model_registry import verify_models
from .auth import require_operator

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_operator)])


@router.get("/config")
async def get_config(request: Request) -> dict:
    """Policy (with ``source`` per threshold) and model versions for the operator banner."""
    settings = request.app.state.settings
    policy = request.app.state.policy
    statuses = getattr(request.app.state, "model_status", None) or verify_models(settings.models_dir)
    return {
        "policy": policy.to_public(),
        "models": {n: {"version": s.version, "state": s.state, "sha256": s.sha256_actual, "license": s.license} for n, s in statuses.items()},
        "storage": settings.storage_backend,
        "audit_save_frames": settings.audit_save_frames,
    }
