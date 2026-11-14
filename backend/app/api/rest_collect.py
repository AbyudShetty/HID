"""M1 spike / collect path (plan §8.2, T1.2-T1.3): get a real server challenge and upload the captured bundle.

``POST /collect/bundles`` accepts one ``application/x-hid-bundle`` body (ADR-001). Before anything is written the
server (1) parses and validates the bundle, (2) consumes the issued session (single use, not expired) and (3) checks
that the challenge in the bundle is *exactly* the one it issued — a bundle cannot carry a made-up challenge.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .. import __version__
from ..pipeline.bundle_io import (
    MAX_BUNDLE_BYTES,
    BundleError,
    build_bundle,
    quality_check,
    unpack_bundle,
    write_bundle,
)
from ..pipeline.chroma_instrument import InstrumentBusy, InstrumentUnavailable
from ..pipeline.measurement import validate_measurement
from ..schemas import CaptureConfig
from ..sessions.manager import SessionError
from ..vision.decode import DecodeError
from .auth import require_operator

router = APIRouter(prefix="/api/v1/collect", dependencies=[Depends(require_operator)])
BUNDLE_CONTENT_TYPE = "application/x-hid-bundle"


@router.get("/challenge")
async def get_challenge(request: Request, palette_id: Literal["P1", "P2"] | None = None) -> dict:
    """Issue a collect session: ``{type: 'session.ready', session_id, expires_in_ms, challenge}``."""
    sessions = request.app.state.sessions
    issued = sessions.issue(purpose="collect", mode="face", palette_id=palette_id)
    body = sessions.ready_message(issued).model_dump(mode="json")
    # REST-only extras so the spike page can fill meta.json without a WebSocket
    body["server_version"] = __version__
    body["policy_version"] = request.app.state.policy.version
    body["capture_config"] = CaptureConfig().model_dump(mode="json")
    return body


async def read_bundle(request: Request, *, require_label: bool):
    if request.headers.get("content-type", "").split(";")[0].strip() != BUNDLE_CONTENT_TYPE:
        raise HTTPException(status_code=415, detail=f"Content-Type must be {BUNDLE_CONTENT_TYPE}")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="bundle too large")
    # Content-Length is optional/untrusted: bound bytes while reading, not after allocation.
    blob = bytearray()
    async for chunk in request.stream():
        if len(blob) + len(chunk) > MAX_BUNDLE_BYTES:
            raise HTTPException(status_code=413, detail="bundle too large")
        blob.extend(chunk)
    try:
        entries = unpack_bundle(blob)
        if {"result.json", "server_timing.json"} & entries.keys():
            raise BundleError("client cannot supply server result or timing entries")
        bundle = build_bundle(entries)
        validate_measurement(bundle, request.app.state.sessions.cfg)
    except BundleError as exc:
        raise HTTPException(status_code=400, detail=f"invalid bundle: {exc}") from exc
    if require_label and bundle.label is None:
        raise HTTPException(status_code=400, detail="invalid bundle: collect bundles require label.json")
    if bundle.meta.purpose != "collect":
        raise HTTPException(status_code=400, detail="invalid bundle: meta.purpose must be 'collect'")

    sessions = request.app.state.sessions
    try:
        issued = sessions.consume(bundle.session_id)
    except SessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if issued.challenge != bundle.challenge.challenge:
        raise HTTPException(status_code=400, detail="invalid bundle: the challenge does not match the one the server issued")

    return bundle, entries


async def process(request: Request, method, *args):
    try:
        return await run_in_threadpool(method, *args)
    except InstrumentBusy as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "1"}) from exc
    except InstrumentUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (DecodeError, ValueError) as exc:
        raise HTTPException(400, f"invalid measurement: {exc}") from exc


@router.post("/preview")
async def preview(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
        raise HTTPException(415, "Content-Type must be image/jpeg")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > 400 * 1024:
            raise HTTPException(413, "preview image too large")
        data.extend(chunk)
    return await process(request, request.app.state.chroma_instrument.preview, bytes(data))


@router.post("/measure")
async def measure(request: Request) -> dict:
    """Single-use issued capture; analyze in memory without persisting biometrics."""
    bundle, entries = await read_bundle(request, require_label=False)
    return await process(request, request.app.state.chroma_instrument.analyze,
                         bundle, entries, request.app.state.sessions.cfg)


@router.post("/bundles")
async def post_bundle(request: Request, analyze: bool = False) -> dict:
    bundle, entries = await read_bundle(request, require_label=True)
    report = None
    if analyze:
        report = await process(request, request.app.state.chroma_instrument.analyze,
                               bundle, entries, request.app.state.sessions.cfg)
    root = request.app.state.settings.data_dir / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    try:
        write_bundle(bundle, entries, root)
    except BundleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    qc = quality_check(bundle)
    return {
        **({"measurement": report} if report is not None else {}),
        "session_id": bundle.session_id,
        "stored": f"sessions/{bundle.session_id}",
        "qc": {
            "n_crops": qc.n_crops,
            "n_keyframes": qc.n_keyframes,
            "crop_fps": qc.crop_fps,
            "capture_span_ms": qc.capture_span_ms,
            "covers_challenge": qc.covers_challenge,
            "warnings": list(qc.warnings),
        },
    }
