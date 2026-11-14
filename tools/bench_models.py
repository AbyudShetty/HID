"""E4 model latency (plan section 9.6): warm p50/p95 per model, input size and thread count on THIS machine.

    .venv\\Scripts\\python.exe tools\\bench_models.py [--runs 100] [--warmup 20]

Covers SCRFD det_10g / det_500m at 640 and 256, ArcFace R50 / MBF at 112, MiniFASNet V2 / V1SE at 80, threads 1/2/4. P1 candidates
(YOLOX-tiny, DINOv2-S) are not downloaded or measured (they are not P0). Run it on each candidate EC2 type for the real E4 decision.
Compute only (ORT run on a real reference image/crop), not decision latency. Output: experiments/E4_models/bench_models.json + report.md
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.vision.onnx_runtime import make_session  # noqa: E402
from app.vision.scrfd import Scrfd  # noqa: E402

MODELS = ROOT / "models"
IMG = cv2.imread(str(ROOT / "backend/tests/fixtures/minifas_samples/image_T1.jpg"))


def timed(fn, warmup: int, runs: int) -> dict:
    for _ in range(warmup):
        fn()
    xs = []
    for _ in range(runs):
        t = perf_counter()
        fn()
        xs.append((perf_counter() - t) * 1000)
    a = np.array(xs)
    return {"p50_ms": round(float(np.percentile(a, 50)), 2), "p95_ms": round(float(np.percentile(a, 95)), 2), "max_ms": round(float(a.max()), 2), "n": runs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=20)
    args = ap.parse_args()
    results = []
    face112 = cv2.resize(IMG[100:400, 120:420], (112, 112))
    arc_in = ((face112[..., ::-1].astype(np.float32) - 127.5) / 127.5).transpose(2, 0, 1)[None]
    fas_in = cv2.resize(IMG[100:400, 120:420], (80, 80)).astype(np.float32).transpose(2, 0, 1)[None]
    for threads in (1, 2, 4):
        for det in ("det_10g", "det_500m"):
            d = Scrfd(MODELS / f"{det}.onnx", intra_op_threads=threads)
            for size in (640, 256):
                r = timed(lambda d=d, size=size: d.detect(IMG, size), args.warmup, args.runs)
                results.append({"model": det, "input": size, "threads": threads, **r})
        for name, f in (("arcface_w600k_r50", "w600k_r50.onnx"), ("arcface_w600k_mbf", "w600k_mbf.onnx")):
            s = make_session(MODELS / f, threads)
            nm = s.get_inputs()[0].name
            results.append({"model": name, "input": 112, "threads": threads, **timed(lambda s=s, nm=nm: s.run(None, {nm: arc_in}), args.warmup, args.runs)})
        for name, f in (("minifasnet_v2", "minifasnet_v2_2.7_80x80.onnx"), ("minifasnet_v1se", "minifasnet_v1se_4.0_80x80.onnx")):
            s = make_session(MODELS / f, threads)
            results.append({"model": name, "input": 80, "threads": threads, **timed(lambda s=s: s.run(None, {"input": fas_in}), args.warmup, args.runs)})
    doc = {"machine": {"cpu_threads": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version()},
           "note": "compute only; one machine; one reference image; P1 models not measured", "results": results}
    out = ROOT / "experiments" / "E4_models"
    out.mkdir(parents=True, exist_ok=True)
    (out / "bench_models.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    lines = ["# E4 model latency (this machine; compute only)", "", f"{doc['machine']}", "", "| model | input | threads | p50 ms | p95 ms |", "|---|---|---|---|---|"]
    lines += [f"| {r['model']} | {r['input']} | {r['threads']} | {r['p50_ms']} | {r['p95_ms']} |" for r in results]
    lines += ["", "Plan budgets (p95, chosen instance): per-crop work (det@256 + regions) <= 20 ms; keyframe work (det@640 + ArcFace + 2x MiniFASNet) <= 300 ms.", "These are a laptop, not the target instance: the E4 decision for AWS is still open."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
