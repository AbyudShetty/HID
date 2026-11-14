"""E1 native probe (plan §9.6, path H1b/H1c): does the camera hold steady while the SCREEN changes colour?

    .venv-host\\Scripts\\python.exe tools\\camera_probe_native.py --mode auto   --name laptop_auto
    .venv-host\\Scripts\\python.exe tools\\camera_probe_native.py --mode manual --exposure -6 --wb 4500 --name laptop_manual

Shows full-screen colours on the primary monitor (neutral 2 s -> colour 2 s, x5, then neutral), records the mean linear RGB of a
region of interest per frame, and applies the plan's E1 criteria via app.experiments.e1 (the same code the tests cover).
ONLY ROI means are stored; no frames are saved or displayed. Put the matte white/grey card (or a face) in the ROI, 45-65 cm
from the display. Press q to abort. Colour steps are 2 s apart (<= 0.5 changes/s: well inside the 3/s safety rule).

Property semantics differ by driver: the script reads every property back, and `applied` records what actually changed.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.experiments.e1 import full_report  # noqa: E402

LUT = np.where((np.arange(256) / 255.0) <= 0.04045, (np.arange(256) / 255.0) / 12.92, (((np.arange(256) / 255.0) + 0.055) / 1.055) ** 2.4).astype(np.float64)
NEUTRAL = (205, 205, 205)
COLORS = [(80, 120, 255), (255, 235, 80), (80, 255, 255), (255, 120, 255), (120, 255, 120)]  # plan palette P1 (BGR order set below)
PROPS = {"auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE, "exposure": cv2.CAP_PROP_EXPOSURE, "auto_wb": cv2.CAP_PROP_AUTO_WB,
         "wb_temperature": cv2.CAP_PROP_WB_TEMPERATURE, "gain": cv2.CAP_PROP_GAIN, "brightness": cv2.CAP_PROP_BRIGHTNESS,
         "fps": cv2.CAP_PROP_FPS, "width": cv2.CAP_PROP_FRAME_WIDTH, "height": cv2.CAP_PROP_FRAME_HEIGHT}


def read_props(cap) -> dict:
    return {k: float(cap.get(v)) for k, v in PROPS.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--mode", choices=["auto", "manual"], default="auto")
    ap.add_argument("--exposure", type=float, default=None, help="driver units (DirectShow usually log2 seconds, e.g. -6)")
    ap.add_argument("--wb", type=float, default=None, help="white balance temperature in K (manual mode)")
    ap.add_argument("--fourcc", default="MJPG", help="MJPG avoids the ~10 fps cap of uncompressed YUY2 on USB2 cameras; use YUY2 to compare")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--roi", default="0.35,0.35,0.3,0.3", help="x,y,w,h as fractions of the frame")
    ap.add_argument("--name", default=None)
    ap.add_argument("--out-dir", default=str(ROOT / "experiments" / "E1_camera" / "raw"))
    args = ap.parse_args()

    backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
    cap = cv2.VideoCapture(args.camera, backend)
    if not cap.isOpened():
        print("cannot open the camera")
        return 2
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    before = read_props(cap)
    if args.mode == "manual":
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # DirectShow: 0.25 = manual, 0.75 = auto
        if args.exposure is not None:
            cap.set(cv2.CAP_PROP_EXPOSURE, args.exposure)
        cap.set(cv2.CAP_PROP_AUTO_WB, 0)
        if args.wb is not None:
            cap.set(cv2.CAP_PROP_WB_TEMPERATURE, args.wb)
    else:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
        cap.set(cv2.CAP_PROP_AUTO_WB, 1)
    time.sleep(0.5)
    after = read_props(cap)
    for _ in range(15):  # let the driver settle, discard
        cap.read()

    rx, ry, rw, rh = (float(v) for v in args.roi.split(","))
    wnd = "E1 probe (q = abort)"
    cv2.namedWindow(wnd, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(wnd, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    schedule = [("neutral", NEUTRAL, 2.0)]
    for k in range(args.steps):
        schedule += [("color", COLORS[k % len(COLORS)], 2.0), ("neutral", NEUTRAL, 2.0)]
    t0 = time.perf_counter()
    ts, rgbs, events = [], [], []
    ok = True
    seg_start = 0.0
    for state, rgb_rgb, dur in schedule:
        bgr = (rgb_rgb[2], rgb_rgb[1], rgb_rgb[0])
        canvas = np.full((720, 1280, 3), bgr, np.uint8)
        cv2.imshow(wnd, canvas)
        cv2.waitKey(1)
        applied = (time.perf_counter() - t0) * 1000.0
        events.append({"t_ms": applied, "state": state, "rgb": list(rgb_rgb)})
        seg_start = applied
        while (time.perf_counter() - t0) * 1000.0 - seg_start < dur * 1000.0:
            good, frame = cap.read()
            now = (time.perf_counter() - t0) * 1000.0
            if not good:
                ok = False
                break
            h, w = frame.shape[:2]
            roi = frame[int(ry * h): int((ry + rh) * h), int(rx * w): int((rx + rw) * w)]
            rgbs.append(LUT[roi[..., ::-1]].reshape(-1, 3).mean(axis=0).tolist())
            ts.append(now)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                ok = False
                break
        if not ok:
            break
    cv2.destroyAllWindows()
    final = read_props(cap)
    cap.release()
    if not ok:
        print("aborted or the camera stopped delivering frames; nothing saved")
        return 1

    report = full_report(ts, rgbs, [e for e in events], (200.0, 1900.0))
    name = args.name or f"native_{args.mode}_{int(time.time())}"
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = {"name": name, "tool": "camera_probe_native", "mode": args.mode, "roi_fraction": [rx, ry, rw, rh], "fourcc_requested": args.fourcc, "resolution_requested": [args.width, args.height], "props_before": before,
           "props_after_set": after, "props_final": final, "platform": platform.platform(), "opencv": cv2.__version__,
           "note": "Only ROI means stored. Event times are when imshow returned, not photon time. Rig conformance (matte card at 45-65 cm) is the operator's responsibility.",
           "t_ms": ts, "rgb": rgbs, "events": events, "report": report}
    (out / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    r = report
    print(json.dumps({"saved": str(out / f"{name}.json"), "applied_props": {k: [before[k], after[k]] for k in after if before[k] != after[k]},
                      "n_steps": r["steps"]["n_steps"], "droop_median": r["steps"]["droop_median"], "onset_lag_ms": r["steps"]["onset_lag_ms_median"],
                      "fps": round(r["timing"]["fps"], 1), "interval_std_ms": round(r["timing"]["interval_std_ms"], 2),
                      "flicker": {k: r["flicker"].get(k) for k in ("status", "ratio", "peak_hz")}, "verdict": r["verdict"]["checks"],
                      "passes": r["verdict"]["passes"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
