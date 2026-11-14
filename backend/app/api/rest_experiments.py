"""Operator experiment endpoints. E1 analysis keeps ONE metric implementation (app.experiments.e1) for browser and native probes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..experiments.e1 import full_report
from .auth import require_operator

router = APIRouter(prefix="/api/v1/experiments", dependencies=[Depends(require_operator)])


class E1Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_ms: float
    state: str = Field(pattern="^(color|neutral)$")


class E1Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_ms: list[float] = Field(min_length=10, max_length=6000)
    rgb: list[list[float]] = Field(min_length=10, max_length=6000)
    events: list[E1Event] = Field(min_length=2, max_length=64)
    neutral_window_ms: tuple[float, float] = (200.0, 1900.0)


@router.post("/e1/analyze")
async def e1_analyze(req: E1Request) -> dict:
    if len(req.t_ms) != len(req.rgb) or any(len(p) != 3 for p in req.rgb):
        raise HTTPException(400, "rgb must have one [r,g,b] per timestamp")
    try:
        return full_report(req.t_ms, req.rgb, [e.model_dump() for e in req.events], req.neutral_window_ms)
    except ValueError as exc:
        raise HTTPException(400, f"invalid probe data: {exc}") from exc


MAX_PROBE_BYTES = 4 * 1024 * 1024


@router.post("/probe/upload")
async def probe_upload(request: Request) -> dict:
    """E3 network probe sink: reads and discards the body (bounded) so clients can measure uplink throughput."""
    n = 0
    async for chunk in request.stream():
        n += len(chunk)
        if n > MAX_PROBE_BYTES:
            raise HTTPException(413, "probe body too large")
    return {"bytes": n}
