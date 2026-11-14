"""Measure C2 instrument timings on THIS machine (cold load, warm per-frame, feature extraction).

    .venv\Scripts\python.exe tools\bench_chroma.py [--runs 100]

Uses the Apache-2.0 reference face photo, so numbers cover compute cost only. They are NOT decision latency
(capture takes >=1.2 s by design) and say nothing about liveness accuracy. Output: experiments/E4_models/chroma_bench.json
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings, load_policy  # noqa: E402
from app.liveness.chroma_features import extract_features  # noqa: E402
from app.model_registry import verify_models  # noqa: E402
from app.pipeline.chroma_instrument import ChromaInstrument  # noqa: E402
from tests.synth import signal  # noqa: E402


def pct(xs, q):
    return float(np.percentile(xs, q))


def summary(xs):
    return {"n": len(xs), "p50_ms": round(pct(xs, 50), 2), "p95_ms": round(pct(xs, 95), 2), "max_ms": round(max(xs), 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=100)
    args = ap.parse_args()
    settings = Settings(_env_file=None)
    policy = load_policy(settings.policy_path)
    inst = ChromaInstrument(settings, verify_models(settings.models_dir), policy)

    img = cv2.imread(str(ROOT / "backend/tests/fixtures/minifas_samples/image_T1.jpg"))
    ok, full = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    crop_src = cv2.resize(img[40:440, 60:460], (256, 256))
    ok2, crop = cv2.imencode(".jpg", crop_src, [cv2.IMWRITE_JPEG_QUALITY, 90])
    full, crop = full.tobytes(), crop.tobytes()

    t = perf_counter()
    inst.load()
    cold_load = (perf_counter() - t) * 1000
    t = perf_counter()
    inst.observe(full, crop=False)
    first_call = (perf_counter() - t) * 1000

    preview, per_crop = [], []
    for _ in range(args.runs):
        t = perf_counter()
        inst.observe(full, crop=False, outlines=True)
        preview.append((perf_counter() - t) * 1000)
    for _ in range(args.runs):
        t = perf_counter()
        inst.observe(crop, crop=True, outlines=False)
        per_crop.append((perf_counter() - t) * 1000)

    rec, _, series = signal(seed=1)
    feats = []
    for _ in range(args.runs):
        t = perf_counter()
        extract_features(series, rec)
        feats.append((perf_counter() - t) * 1000)

    out = {
        "machine": {"cpu_threads": __import__("os").cpu_count(), "platform": platform.platform(), "python": platform.python_version()},
        "scrfd_load_ms": round(cold_load, 1),
        "first_preview_call_ms": round(first_call, 1),
        "preview_640_warm": summary(preview),
        "captured_crop_320_warm": summary(per_crop),
        "feature_extraction_synthetic_36_frames": summary(feats),
        "note": "compute only; one machine; reference photo. Not decision latency. 36 crops x per-crop time approximates server work during a capture, which overlaps the >=1.2 s capture.",
    }
    out["estimated_server_ms_for_36_crops_serial"] = round(36 * out["captured_crop_320_warm"]["p50_ms"], 1)
    dest = ROOT / "experiments" / "E4_models" / "chroma_bench.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
