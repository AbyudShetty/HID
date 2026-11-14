"""E3 network probe (plan section 9.6): RTT, uplink throughput and the bytes-per-frame matrix.

    .venv\\Scripts\\python.exe tools\\net_probe.py --base http://127.0.0.1:8000 --token <operator token> --name local

Run it from the kiosk network against each candidate region's backend. Against localhost it only validates the tool; it says
nothing about a real network. Pass rule (plan): chosen upload config uses <= 50 percent of the measured p10 uplink and RTT p95 <= 300 ms.
Throughput uses HTTP POST of random bodies (not the WebSocket path); treat it as a conservative proxy.
Output: experiments/E3_network/<name>.json
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import cv2

ROOT = Path(__file__).resolve().parent.parent


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q / 100 * (len(xs) - 1))))]


def frame_matrix() -> dict:
    """Real JPEG sizes for a 256/192 px face crop at q 0.8/0.9 from the reference photo (content-dependent)."""
    img = cv2.imread(str(ROOT / "backend/tests/fixtures/minifas_samples/image_T1.jpg"))
    src = img[40:440, 60:460]
    out = {}
    for size in (192, 256):
        crop = cv2.resize(src, (size, size))
        for q in (0.8, 0.9):
            ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, int(q * 100)])
            n = len(buf)
            out[f"{size}px_q{q}"] = {"bytes_per_frame": n, **{f"mbit_s_at_{fps}fps": round(n * 8 * fps / 1e6, 2) for fps in (30, 20, 15)}}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--rtt-samples", type=int, default=50)
    ap.add_argument("--uploads", type=int, default=20)
    ap.add_argument("--chunk-kb", type=int, default=256)
    args = ap.parse_args()
    u = urlparse(args.base)
    Conn = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = Conn(u.hostname, u.port or (443 if u.scheme == "https" else 80), timeout=15)
    hdr = {"Authorization": f"Bearer {args.token}"}

    t = time.perf_counter()
    conn.request("GET", "/api/v1/health")
    conn.getresponse().read()
    first = (time.perf_counter() - t) * 1000  # includes TCP (+TLS) setup
    rtt = []
    for _ in range(args.rtt_samples):
        t = time.perf_counter()
        conn.request("GET", "/api/v1/health")
        conn.getresponse().read()
        rtt.append((time.perf_counter() - t) * 1000)

    body = os.urandom(args.chunk_kb * 1024)
    rates = []
    for _ in range(args.uploads):
        t = time.perf_counter()
        conn.request("POST", "/api/v1/experiments/probe/upload", body=body, headers={**hdr, "Content-Type": "application/octet-stream"})
        r = conn.getresponse()
        r.read()
        if r.status != 200:
            print(f"upload failed: HTTP {r.status}")
            return 2
        dt = time.perf_counter() - t
        rates.append(len(body) * 8 / dt / 1e6)
    matrix = frame_matrix()
    p10 = pct(rates, 10)
    chosen = matrix["256px_q0.9"]["mbit_s_at_30fps"]
    result = {
        "name": args.name, "base": args.base, "note": "HTTP proxy for uplink; localhost runs validate the tool only",
        "first_request_ms": round(first, 1),
        "rtt_ms": {"n": len(rtt), "p50": round(statistics.median(rtt), 2), "p95": round(pct(rtt, 95), 2), "max": round(max(rtt), 2)},
        "uplink_mbit_s": {"n": len(rates), "p10": round(p10, 1), "p50": round(statistics.median(rates), 1)},
        "frame_matrix": matrix,
        "check_default_config": {"config": "256px q0.9 30fps", "needs_mbit_s": chosen, "fraction_of_p10": round(chosen / p10, 3),
                                 "pass_uplink_le_50pct_of_p10": chosen <= 0.5 * p10, "pass_rtt_p95_le_300ms": pct(rtt, 95) <= 300},
    }
    out = ROOT / "experiments" / "E3_network"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
