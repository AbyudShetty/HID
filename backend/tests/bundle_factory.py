"""Builds synthetic session bundles for tests (not part of the application)."""
from __future__ import annotations

import json

import cv2
import numpy as np

from app.schemas import Challenge


def jpeg(color_bgr=(120, 140, 160), size=(64, 64)) -> bytes:
    img = np.full((size[1], size[0], 3), color_bgr, np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def make_entries(session_id: str, challenge: Challenge, n_crops: int | None = None, label: dict | None = "default") -> dict[str, bytes]:
    total = challenge.total_ms
    n = n_crops if n_crops is not None else int(total / 1000 * 30) + 2
    meta = {
        "session_id": session_id, "purpose": "collect", "mode": "face", "kiosk_id": "kiosk-test",
        "created_at": "2026-11-14T10:00:00Z", "client_version": "0.1.0", "server_version": "0.1.0",
        "camera": {"width": 1280, "height": 720, "fps": 30, "lock_method": "browser", "settings": {}, "label": "test cam"},
        "display": {"width": 1920, "height": 1080, "device_pixel_ratio": 1}, "capture_time_source": "now",
        "jpeg_quality": 0.9, "crop_size": 64, "palette_id": challenge.palette_id,
    }
    displayed = [{"index": -1, "t_display": 2.0}]
    t = challenge.neutral.duration_ms
    for i, seg in enumerate(challenge.segments):
        displayed.append({"index": i, "t_display": float(t)})
        t += seg.duration_ms
    entries: dict[str, bytes] = {
        "meta.json": json.dumps(meta).encode(),
        "challenge.json": json.dumps({"challenge": challenge.model_dump(mode="json"), "displayed": displayed}).encode(),
    }
    frames, keyframes = [], []
    for i in range(n):
        name = f"crops/{i:06d}.jpg"
        entries[name] = jpeg((i * 3 % 255, 100, 150))
        frames.append({"seq": i, "t_capture": i * (total / (n - 1)), "crop_box": [0, 0, 64, 64], "frame_size": [1280, 720], "file": name})
    for k in range(2):
        name = f"keyframes/k{k}.jpg"
        entries[name] = jpeg((40, 40 + k, 40))
        keyframes.append({"seq": k, "t_capture": 100.0 + k * 40, "frame_size": [1280, 720], "file": name})
    entries["frames.jsonl"] = ("\n".join(json.dumps(f) for f in frames)).encode()
    entries["keyframes.jsonl"] = ("\n".join(json.dumps(k) for k in keyframes)).encode()
    if label == "default":
        label = {
            "subject_id": "S001", "presenter_id": "S001", "class": "bona_fide", "enrolled": True, "capture_procedure": "standard",
            "pai_family": "none", "pai_species": "none", "lighting": "office", "consent_id": "C-2026-001", "operator": "op1",
        }
    if label is not None:
        entries["label.json"] = json.dumps(label).encode()
    return entries
