"""Session bundles: wire framing, validation, and on-disk layout (plan §8.5, ADR-001).

Upload body (``Content-Type: application/x-hid-bundle``) = repeated entries::

    [u32 LE name_len][name utf-8][u32 LE data_len][data bytes]

Entry names are bundle-relative paths: ``meta.json``, ``challenge.json``, ``frames.jsonl``, ``keyframes.jsonl``,
``label.json`` (optional), ``result.json`` / ``server_timing.json`` (server-written, optional), ``crops/<n>.jpg|png``,
``keyframes/<n>.jpg|png``. On disk the same names live under ``data/sessions/<session_id>/``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ..schemas import ChallengeRecord, CollectLabel, FrameRecord, KeyframeRecord, SessionMeta

MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_BYTES = 48 * 1024 * 1024
MAX_ENTRIES = 400

_JSON_ENTRIES = {"meta.json", "challenge.json", "label.json", "result.json", "server_timing.json"}
_JSONL_ENTRIES = {"frames.jsonl", "keyframes.jsonl"}
_IMAGE_RE = re.compile(r"^(crops|keyframes)/[A-Za-z0-9_\-]{1,40}\.(jpg|png)$")
_REQUIRED = ("meta.json", "challenge.json", "frames.jsonl", "keyframes.jsonl")
_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"


class BundleError(ValueError):
    """The bundle is malformed, truncated, unsafe or inconsistent."""


def valid_entry_name(name: str) -> bool:
    return name in _JSON_ENTRIES or name in _JSONL_ENTRIES or bool(_IMAGE_RE.match(name))


def pack_bundle(entries: dict[str, bytes]) -> bytes:
    out = bytearray()
    for name, data in entries.items():
        if not valid_entry_name(name):
            raise BundleError(f"invalid entry name {name!r}")
        raw = name.encode("utf-8")
        out += struct.pack("<I", len(raw)) + raw + struct.pack("<I", len(data)) + data
    return bytes(out)


def unpack_bundle(blob: bytes) -> dict[str, bytes]:
    """Parse the wire framing. Enforces size limits and name safety *before* anything is touched on disk."""
    if len(blob) > MAX_BUNDLE_BYTES:
        raise BundleError(f"bundle too large: {len(blob)} > {MAX_BUNDLE_BYTES} bytes")
    entries: dict[str, bytes] = {}
    pos, n = 0, len(blob)
    while pos < n:
        if pos + 4 > n:
            raise BundleError("truncated bundle: incomplete name length")
        (name_len,) = struct.unpack_from("<I", blob, pos)
        pos += 4
        if name_len == 0 or name_len > 128 or pos + name_len > n:
            raise BundleError("truncated or invalid entry name")
        try:
            name = blob[pos : pos + name_len].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BundleError("entry name is not valid utf-8") from exc
        pos += name_len
        if not valid_entry_name(name):
            raise BundleError(f"invalid entry name {name!r}")
        if name in entries:
            raise BundleError(f"duplicate entry {name!r}")
        if pos + 4 > n:
            raise BundleError(f"truncated bundle: missing data length for {name!r}")
        (data_len,) = struct.unpack_from("<I", blob, pos)
        pos += 4
        if data_len > MAX_ENTRY_BYTES:
            raise BundleError(f"entry {name!r} too large: {data_len} > {MAX_ENTRY_BYTES}")
        if pos + data_len > n:
            raise BundleError(f"truncated bundle: entry {name!r} is cut short")
        entries[name] = blob[pos : pos + data_len]
        pos += data_len
        if len(entries) > MAX_ENTRIES:
            raise BundleError(f"too many entries (> {MAX_ENTRIES})")
    return entries


@dataclass
class Bundle:
    meta: SessionMeta
    challenge: ChallengeRecord
    frames: list[FrameRecord]
    keyframes: list[KeyframeRecord]
    label: CollectLabel | None
    files: dict[str, bytes] = field(default_factory=dict)  # image entries only (name -> bytes)
    extras: dict[str, bytes] = field(default_factory=dict)  # result.json, server_timing.json

    @property
    def session_id(self) -> str:
        return self.meta.session_id


def _parse_json(name: str, data: bytes):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"{name} is not valid JSON: {exc}") from exc


def _parse_jsonl(name: str, data: bytes) -> list[dict]:
    rows = []
    for i, line in enumerate(data.decode("utf-8", errors="replace").splitlines()):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise BundleError(f"{name} line {i + 1} is not valid JSON: {exc}") from exc
    return rows


def _check_image(name: str, data: bytes) -> None:
    magic = _PNG if name.endswith(".png") else _JPEG
    if not data.startswith(magic):
        raise BundleError(f"{name} is not a valid {'PNG' if name.endswith('.png') else 'JPEG'}")


def build_bundle(entries: dict[str, bytes]) -> Bundle:
    """Validate a set of entries into a :class:`Bundle`. Raises :class:`BundleError` with a reason."""
    for req in _REQUIRED:
        if req not in entries:
            raise BundleError(f"missing required entry {req!r}")
    try:
        meta = SessionMeta.model_validate(_parse_json("meta.json", entries["meta.json"]))
        challenge = ChallengeRecord.model_validate(_parse_json("challenge.json", entries["challenge.json"]))
        frames = [FrameRecord.model_validate(r) for r in _parse_jsonl("frames.jsonl", entries["frames.jsonl"])]
        keyframes = [KeyframeRecord.model_validate(r) for r in _parse_jsonl("keyframes.jsonl", entries["keyframes.jsonl"])]
        label = CollectLabel.model_validate(_parse_json("label.json", entries["label.json"])) if "label.json" in entries else None
    except ValidationError as exc:
        raise BundleError(f"schema validation failed: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}") from exc

    if not re.fullmatch(r"s_[0-9a-f]{16}", meta.session_id):
        raise BundleError(f"invalid session_id {meta.session_id!r}")
    if not frames:
        raise BundleError("bundle has no crop frames")
    if not keyframes:
        raise BundleError("bundle has no keyframes")

    images = {n: d for n, d in entries.items() if _IMAGE_RE.match(n)}
    referenced = {f.file for f in frames} | {k.file for k in keyframes}
    for ref in referenced:
        if ref not in images:
            raise BundleError(f"referenced file {ref!r} is missing from the bundle")
    for name in images:
        if name not in referenced:
            raise BundleError(f"unreferenced image {name!r} in the bundle")
    for f in frames:
        if not f.file.startswith("crops/"):
            raise BundleError(f"frame file {f.file!r} must be under crops/")
    for k in keyframes:
        if not k.file.startswith("keyframes/"):
            raise BundleError(f"keyframe file {k.file!r} must be under keyframes/")
    for name, data in images.items():
        _check_image(name, data)
    seqs = [f.seq for f in frames]
    if len(set(seqs)) != len(seqs):
        raise BundleError("duplicate crop seq numbers")
    times = [f.t_capture for f in sorted(frames, key=lambda f: f.seq)]
    if any(b < a for a, b in zip(times, times[1:], strict=False)):
        raise BundleError("crop t_capture is not non-decreasing in seq order")

    extras = {n: entries[n] for n in ("result.json", "server_timing.json") if n in entries}
    return Bundle(meta, challenge, frames, keyframes, label, images, extras)


def write_bundle(bundle: Bundle, entries: dict[str, bytes], root: Path) -> Path:
    """Write ``entries`` under ``root/<session_id>/`` (never overwrites an existing bundle)."""
    target = root / bundle.session_id
    if target.exists():
        raise BundleError(f"bundle {bundle.session_id} already exists")
    tmp = root / f".{bundle.session_id}.partial"
    tmp.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in entries.items():
            path = tmp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        os.replace(tmp, target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return target


def read_bundle(path: Path) -> Bundle:
    """Load a bundle directory written by :func:`write_bundle` (or by the online pipeline later)."""
    if not path.is_dir():
        raise BundleError(f"not a bundle directory: {path}")
    entries: dict[str, bytes] = {}
    for p in sorted(path.rglob("*")):
        if p.is_file():
            name = p.relative_to(path).as_posix()
            if valid_entry_name(name):
                entries[name] = p.read_bytes()
    return build_bundle(entries)


@dataclass(frozen=True)
class BundleQC:
    n_crops: int
    n_keyframes: int
    crop_fps: float | None
    capture_span_ms: float | None
    covers_challenge: bool
    warnings: tuple[str, ...]


def quality_check(bundle: Bundle, expected_fps: float = 30.0) -> BundleQC:
    """Cheap structural QC shown to the operator after an upload (not a liveness measurement)."""
    times = sorted(f.t_capture for f in bundle.frames)
    span = times[-1] - times[0] if len(times) > 1 else None
    fps = (len(times) - 1) / (span / 1000.0) if span and span > 0 else None
    warnings: list[str] = []
    if fps is not None and abs(fps - expected_fps) > 3.0:
        warnings.append(f"crop rate {fps:.1f} fps is outside {expected_fps:.0f}±3")
    if len(bundle.keyframes) < 2:
        warnings.append("fewer than 2 keyframes")
    need = float(bundle.challenge.challenge.total_ms)
    covers = span is not None and span >= need * 0.9
    if not covers:
        warnings.append("captured span is shorter than 90% of the challenge duration")
    if len(bundle.challenge.displayed) < len(bundle.challenge.challenge.segments) + 1:
        warnings.append("not every segment has a recorded t_display")
    return BundleQC(len(times), len(bundle.keyframes), fps, span, covers, tuple(warnings))
