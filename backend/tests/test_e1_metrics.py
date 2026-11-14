"""E1 metrics on synthetic camera responses with KNOWN droop, lag, rate and flicker."""
from __future__ import annotations

import numpy as np
import pytest

from app.experiments.e1 import analyze_steps, flicker, full_report, timing_stats, verdict

EVENTS = []
for k in range(5):  # neutral 2 s -> colour 2 s, five times (plan E1 procedure)
    EVENTS += [{"t_ms": 2000.0 + k * 4000, "state": "color"}, {"t_ms": 4000.0 + k * 4000, "state": "neutral"}]
T_END = 22000.0


def camera(fps=30.0, tau_ms=None, lag_ms=60.0, noise=0.002, seed=0, flick_hz=None, flick_amp=0.0, amp=(0.20, 0.10, 0.30)):
    rng = np.random.default_rng(seed)
    t = np.arange(0, T_END, 1000.0 / fps)
    x = np.tile(np.array([0.30, 0.28, 0.25]), (len(t), 1))
    for e in EVENTS:
        if e["state"] != "color":
            continue
        t_on = e["t_ms"] + lag_ms
        t_off = next(n["t_ms"] for n in EVENTS if n["state"] == "neutral" and n["t_ms"] > e["t_ms"]) + lag_ms
        m = (t >= t_on) & (t < t_off)
        decay = np.ones(m.sum()) if tau_ms is None else np.exp(-(t[m] - t_on) / tau_ms)
        x[m] += np.outer(decay, amp)
    if flick_hz:
        x += (flick_amp * np.sin(2 * np.pi * flick_hz * t / 1000.0))[:, None]
    return t, x + rng.normal(0, noise, x.shape)


def test_locked_camera_has_no_droop_and_recovers_the_response_lag():
    t, x = camera()
    r = analyze_steps(t, x, EVENTS)
    assert r["n_steps"] == 5
    assert all(abs(d) < 0.03 for d in r["droop_median"])
    assert r["onset_lag_ms_median"] == pytest.approx(60, abs=34)  # within one frame


def test_auto_exposure_decay_is_measured_as_droop():
    tau = 800.0
    t, x = camera(tau_ms=tau)
    r = analyze_steps(t, x, EVENTS)
    expected = 1 - np.exp(-1200.0 / tau)  # ~0.78
    assert all(d == pytest.approx(expected, abs=0.06) for d in r["droop_median"])
    full = full_report(t, x, EVENTS, (200.0, 1900.0))
    assert full["verdict"]["checks"]["droop_le_10pct_all_defined_channels"] is False
    assert full["verdict"]["passes"] is False


def test_droop_is_undefined_where_the_step_is_below_the_noise_floor():
    t, x = camera(amp=(0.20, 0.0005, 0.30), noise=0.004)
    r = analyze_steps(t, x, EVENTS)
    assert r["droop_median"][1] is None and r["droop_median"][0] is not None


def test_no_response_means_no_detected_steps_not_a_pass():
    t, x = camera(amp=(0.0, 0.0, 0.0))
    r = analyze_steps(t, x, EVENTS)
    assert r["n_steps"] == 0 and r["skipped"]
    v = verdict(r, timing_stats(t), flicker(t, x, 200.0, 1900.0))
    assert v["passes"] is False and v["checks"]["enough_steps"] is False


def test_short_colour_segment_cannot_support_the_late_window():
    ev = [{"t_ms": 2000.0, "state": "color"}, {"t_ms": 2900.0, "state": "neutral"}]
    t, x = camera()
    r = analyze_steps(t, x, ev)
    assert r["n_steps"] == 0 and "too short" in r["skipped"][0]["why"]


def test_timing_stats_and_the_jitter_limit():
    t, _ = camera(fps=30.0)
    s = timing_stats(t)
    assert s["fps"] == pytest.approx(30.0, abs=0.1) and s["interval_std_ms"] < 0.5
    jittery = t + np.random.default_rng(1).normal(0, 12, len(t))
    jittery = np.sort(jittery)
    assert timing_stats(jittery)["interval_std_ms"] > 8.0


def test_flicker_is_flagged_when_present_and_not_in_plain_noise():
    t, x = camera(flick_hz=10.0, flick_amp=0.01)
    bad = flicker(t, x, 200.0, 1900.0)
    assert bad["ratio"] > 2.0 and bad["peak_hz"] == pytest.approx(10.0, abs=1.0)
    clean_ratios = [flicker(*camera(seed=s), 200.0, 1900.0)["ratio"] for s in range(20)]
    assert np.median(clean_ratios) < 2.0


def test_clean_locked_camera_passes_every_check():
    t, x = camera()
    v = full_report(t, x, EVENTS, (200.0, 1900.0))["verdict"]
    assert v["passes"] is True, v


def test_invalid_inputs_are_rejected():
    t, x = camera()
    with pytest.raises(ValueError):
        analyze_steps(t[:5], x[:5], EVENTS)
    bad = t.copy()
    bad[10] = bad[9]
    with pytest.raises(ValueError, match="strictly increasing"):
        analyze_steps(bad, x, EVENTS)
    x2 = x.copy()
    x2[3, 0] = np.nan
    with pytest.raises(ValueError):
        analyze_steps(t, x2, EVENTS)


def test_e1_endpoint_requires_auth_validates_and_matches_the_library(tmp_settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    t, x = camera()
    body = {"t_ms": t.tolist(), "rgb": x.tolist(), "events": EVENTS, "neutral_window_ms": [200.0, 1900.0]}
    with TestClient(create_app(tmp_settings)) as c:
        assert c.post("/api/v1/experiments/e1/analyze", json=body).status_code == 401
        h = {"Authorization": "Bearer test-operator-token"}
        r = c.post("/api/v1/experiments/e1/analyze", json=body, headers=h)
        assert r.status_code == 200 and r.json()["verdict"]["passes"] is True
        assert r.json() == full_report(t, x, EVENTS, (200.0, 1900.0))
        assert c.post("/api/v1/experiments/e1/analyze", json={**body, "rgb": x[:-1].tolist()}, headers=h).status_code == 400
        assert c.post("/api/v1/experiments/e1/analyze", json={**body, "extra": 1}, headers=h).status_code == 422
        bad_t = t.copy()
        bad_t[5] = bad_t[4]
        assert c.post("/api/v1/experiments/e1/analyze", json={**body, "t_ms": bad_t.tolist()}, headers=h).status_code == 400


def test_probe_upload_sink_counts_bytes_and_is_bounded(tmp_settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    h = {"Authorization": "Bearer test-operator-token"}
    with TestClient(create_app(tmp_settings)) as c:
        assert c.post("/api/v1/experiments/probe/upload", content=b"x" * 10).status_code == 401
        assert c.post("/api/v1/experiments/probe/upload", content=b"x" * 1000, headers=h).json() == {"bytes": 1000}
        assert c.post("/api/v1/experiments/probe/upload", content=b"x" * (4 * 1024 * 1024 + 1), headers=h).status_code == 413
