"""Write a Y4M video (looping still image) for Chrome's fake camera: ``--use-file-for-fake-video-capture=<file>``.

Used only for automated browser tests of the capture pipeline (tools/cdp_spike_e2e.mjs). The default image is the
Apache-2.0 reference face photo in backend/tests/fixtures/minifas_samples/. This is NOT test data for liveness.

    .venv\\Scripts\\python.exe tools\\make_fake_camera_video.py [--image PATH] [--out PATH] [--frames 90] [--fps 30]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=str(ROOT / "backend/tests/fixtures/minifas_samples/image_T1.jpg"))
    ap.add_argument("--out", default=str(ROOT / "data/fake_camera/face.y4m"))
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        raise SystemExit(f"cannot read {args.image}")
    h, w = img.shape[:2]
    w -= w % 2
    h -= h % 2
    img = img[:h, :w]
    i420 = cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420)  # (h*3/2, w): Y plane, then U, then V
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(f"YUV4MPEG2 W{w} H{h} F{args.fps}:1 Ip A1:1 C420jpeg\n".encode())
        frame = i420.tobytes()
        for _ in range(args.frames):
            fh.write(b"FRAME\n")
            fh.write(frame)
    print(f"wrote {out} ({w}x{h}, {args.frames} frames @ {args.fps} fps, {out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
