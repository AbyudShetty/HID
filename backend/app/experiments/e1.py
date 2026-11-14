"""E1 camera-control metrics (plan §9.6): does a step in screen colour produce a response that holds steady?

Pure numpy. Used by the native probe (tools/camera_probe_native.py), the browser probe (via
POST /api/v1/experiments/e1/analyze) and the unit tests, so there is ONE implementation.

Input: a region-of-interest mean per frame (linear RGB of a matte card or face) plus the actual times the screen
changed. Definitions (ours; the plan gives the pass numbers, not the estimator):
  baseline   mean over `baseline_ms` before the step
  onset      first frame at/after the step whose |delta| reaches 50 % of the step's plateau (so onset - t_on is the
             display-to-camera response delay seen in this data, not a nominal value)
  A          mean delta over the `window_ms` starting at onset
  A_late     the same window starting `late_after_ms` after onset
  droop      (A - A_late) / A per channel, only where |A| >= amp_floor x baseline noise; else None (undefined)
Auto exposure / white balance that adapts to the step shows up as droop.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PASS = {"max_droop": 0.10, "min_fps": 25.0, "max_interval_std_ms": 8.0, "max_flicker_ratio": 2.0, "min_steps": 3}


@dataclass(frozen=True)
class StepConfig:
    baseline_ms: float = 300.0
    window_ms: float = 100.0
    late_after_ms: float = 1200.0
    amp_floor: float = 5.0  # |A| must exceed this many baseline-noise sigmas
    plateau_from_ms: float = 500.0


def _mean_window(t: np.ndarray, x: np.ndarray, lo: float, hi: float) -> np.ndarray | None:
    m = (t >= lo) & (t < hi)
    return x[m].mean(axis=0) if m.sum() >= 2 else None


def analyze_steps(t_ms, rgb, events, cfg: StepConfig = StepConfig()) -> dict:
    """events: [{"t_ms": float, "state": "color" | "neutral"}] in the same clock as t_ms (actual application times)."""
    t = np.asarray(t_ms, float)
    x = np.asarray(rgb, float)
    if t.ndim != 1 or x.shape != (len(t), 3) or len(t) < 10:
        raise ValueError("need >= 10 frames of RGB with matching timestamps")
    if not np.isfinite(t).all() or not np.isfinite(x).all() or (np.diff(t) <= 0).any():
        raise ValueError("timestamps must be finite and strictly increasing; RGB finite")
    ev = sorted(events, key=lambda e: e["t_ms"])
    steps, skipped = [], []
    for i, e in enumerate(ev):
        if e["state"] != "color":
            continue
        t_on = float(e["t_ms"])
        t_off = next((float(n["t_ms"]) for n in ev[i + 1:] if n["state"] == "neutral"), None)
        if t_off is None:
            skipped.append({"t_on": t_on, "why": "no following neutral event"})
            continue
        base_sel = (t >= t_on - cfg.baseline_ms) & (t < t_on)
        if base_sel.sum() < 3:
            skipped.append({"t_on": t_on, "why": "baseline has < 3 frames"})
            continue
        baseline = x[base_sel].mean(axis=0)
        noise = np.maximum(x[base_sel].std(axis=0, ddof=1), 1e-9)
        plateau = _mean_window(t, x, t_on + cfg.plateau_from_ms, t_off)
        if plateau is None:
            skipped.append({"t_on": t_on, "why": "no plateau frames"})
            continue
        pmag = float(np.linalg.norm(plateau - baseline))
        after = np.where(t >= t_on)[0]
        reach = [j for j in after if np.linalg.norm(x[j] - baseline) >= 0.5 * pmag]
        if pmag < cfg.amp_floor * float(np.linalg.norm(noise)) or not reach:  # plateau must stand out of the noise
            skipped.append({"t_on": t_on, "why": "no detectable response"})
            continue
        onset = float(t[reach[0]])
        a = _mean_window(t, x, onset, onset + cfg.window_ms)
        late = _mean_window(t, x, onset + cfg.late_after_ms, onset + cfg.late_after_ms + cfg.window_ms)
        if a is None or late is None or onset + cfg.late_after_ms + cfg.window_ms > t_off:
            skipped.append({"t_on": t_on, "why": "colour segment too short for the late window"})
            continue
        A, Al = a - baseline, late - baseline
        droop = [float((A[c] - Al[c]) / A[c]) if abs(A[c]) >= cfg.amp_floor * noise[c] else None for c in range(3)]
        steps.append({"t_on": t_on, "onset_lag_ms": onset - t_on, "amplitude": A.tolist(), "late_amplitude": Al.tolist(),
                      "noise": noise.tolist(), "droop": droop})
    med = []
    for c in range(3):
        vals = [s["droop"][c] for s in steps if s["droop"][c] is not None]
        med.append(float(np.median(vals)) if vals else None)
    return {"steps": steps, "skipped": skipped, "n_steps": len(steps), "droop_median": med,
            "onset_lag_ms_median": float(np.median([s["onset_lag_ms"] for s in steps])) if steps else None}


def timing_stats(t_ms) -> dict:
    t = np.asarray(t_ms, float)
    d = np.diff(t)
    return {"n_frames": int(len(t)), "fps": float((len(t) - 1) / ((t[-1] - t[0]) / 1000.0)), "interval_mean_ms": float(d.mean()),
            "interval_std_ms": float(d.std()), "max_gap_ms": float(d.max())}


def flicker(t_ms, rgb, lo_ms: float, hi_ms: float) -> dict:
    """Spectrum of the neutral interval's luminance. ratio = strongest non-DC bin / 95th percentile of the others."""
    t = np.asarray(t_ms, float)
    x = np.asarray(rgb, float)
    m = (t >= lo_ms) & (t < hi_ms)
    if m.sum() < 24:
        return {"status": "unavailable", "reason": "neutral interval has < 24 frames", "ratio": None, "peak_hz": None}
    y = x[m].sum(axis=1)
    tt = t[m]
    fs = (len(tt) - 1) / ((tt[-1] - tt[0]) / 1000.0)
    y = y - np.polyval(np.polyfit(tt, y, 1), tt)
    amp = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    freqs = np.fft.rfftfreq(len(y), 1.0 / fs)
    amp, freqs = amp[1:], freqs[1:]  # drop DC
    k = int(np.argmax(amp))
    floor = float(np.percentile(np.delete(amp, k), 95)) or 1e-12
    return {"status": "ok", "ratio": float(amp[k] / floor), "peak_hz": float(freqs[k]), "sample_rate_hz": float(fs),
            "note": "mains flicker aliases at the camera rate: 100 Hz -> 10 Hz and 120 Hz -> 0 Hz when sampled at 30 fps"}


def verdict(steps: dict, timing: dict, fl: dict) -> dict:
    """Apply the plan's E1 pass criteria. Each check is True/False/None (None = not measurable here)."""
    droops = [d for d in steps["droop_median"] if d is not None]
    checks = {
        "enough_steps": steps["n_steps"] >= PASS["min_steps"],
        "droop_le_10pct_all_defined_channels": (max(abs(d) for d in droops) <= PASS["max_droop"]) if droops and steps["n_steps"] >= PASS["min_steps"] else None,
        "fps_ge_25": timing["fps"] >= PASS["min_fps"],
        "interval_std_le_8ms": timing["interval_std_ms"] <= PASS["max_interval_std_ms"],
        "no_flicker_peak_gt_2x": None if fl["status"] != "ok" else fl["ratio"] <= PASS["max_flicker_ratio"],
    }
    known = [v for v in checks.values() if v is not None]
    return {"checks": checks, "passes": bool(known) and all(known) and None not in checks.values(),
            "criteria": PASS, "note": "passes=True requires every check measurable and true"}


def full_report(t_ms, rgb, events, neutral_window_ms: tuple[float, float], cfg: StepConfig = StepConfig()) -> dict:
    steps = analyze_steps(t_ms, rgb, events, cfg)
    timing = timing_stats(t_ms)
    fl = flicker(t_ms, rgb, *neutral_window_ms)
    return {"steps": steps, "timing": timing, "flicker": fl, "verdict": verdict(steps, timing, fl)}
