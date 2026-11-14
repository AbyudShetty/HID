"""Synthetic numerical correctness tests; NO anti-spoof efficacy claims."""
import json
from dataclasses import replace

import numpy as np
import pytest

from app.liveness.chroma_features import FeatureConfig, extract_features
from app.liveness.chroma_series import build_series, emitted
from app.vision.regions import RegionStat
from tests.synth import signal


def test_controlled_gain_lag_spatial_ratios_and_determinism():
    rec, _, series = signal()
    result = extract_features(series, rec)
    f = result["features"]
    assert result["status"] == "ok", result["reasons"]
    assert f["lag_ms"] == pytest.approx(65, abs=1000 / 30)
    assert f["sync_corr"] > .99
    assert f["gain_face"] == pytest.approx(.15, abs=.01)
    assert f["falloff_bg"] == pytest.approx(5, abs=.6)
    assert f["intra_cv"] < .05
    assert f["fit_r2"] > .98
    assert f["snr"] > 3
    assert result == extract_features(series, rec)
    assert result["classification"] == "not_implemented" and result["hardware_validated"] is False
    json.dumps(result, allow_nan=False)


def test_actual_trace_not_nominal_and_frame_boundary_sampling():
    rec, _, _ = signal()
    first = rec.displayed[1].t_display
    sampled = emitted(rec, np.array([first - .001, first, first + 50]), lag_ms=0)
    assert not np.array_equal(sampled[0], sampled[1])
    assert np.array_equal(sampled[1], sampled[2])
    assert np.array_equal(emitted(rec, np.array([first + 64]), 65)[0], sampled[0])
    # Incomplete or inconsistent actual traces must not silently fall back to issued timings.
    with pytest.raises(ValueError):
        emitted(rec.model_copy(update={"displayed": rec.displayed[:-1]}), np.array([10]))
    with pytest.raises(ValueError):
        extract_features(build_series([]), rec.model_copy(update={"timing": None}))


@pytest.mark.parametrize("times", [[1, 1], [2, 1], [-1], [float("nan")], [float("inf")]])
def test_invalid_timestamps(times):
    _, frames, _ = signal()
    with pytest.raises(ValueError):
        build_series([replace(frames[0], t_ms=t) for t in times])


def test_missing_frames_missing_regions_and_empty_are_unavailable():
    rec, frames, _ = signal()
    assert "MISSING_FRAMES" in extract_features(build_series(frames[::3]), rec)["reasons"]
    missing = [replace(f, regions={k: v for k, v in f.regions.items() if k != "nose"}) for f in frames]
    result = extract_features(build_series(missing), rec)
    assert result["status"] == "unavailable" and result["features"]["gain_nose"] is None
    empty = extract_features(build_series([]), rec)
    assert empty["status"] == "unavailable"
    json.dumps(empty, allow_nan=False)


def test_motion_multiple_faces_clipping_and_low_snr():
    rec, frames, _ = signal()
    moved = [replace(f, box=(100 + i * 3, 100, 200 + i * 3, 240)) for i, f in enumerate(frames)]
    assert "TRACK_MOTION" in extract_features(build_series(moved), rec)["reasons"]
    multi = [replace(f, significant_faces=2) for f in frames]
    assert "MULTIPLE_SIGNIFICANT_FACES" in extract_features(build_series(multi), rec)["reasons"]
    clipped = [replace(f, regions={k: replace(v, clipped_frac=.5) for k, v in f.regions.items()}) for f in frames]
    assert "CLIPPED_REGION:nose" in extract_features(build_series(clipped), rec)["reasons"]
    rec, _, series = signal(seed=8, gain=.001, noise=.01)
    assert "LOW_SNR" in extract_features(series, rec)["reasons"]
    # whatever the noise does to the lag search, a signal-free capture is never reported as usable
    for seed in range(7, 15):
        rec, _, series = signal(seed=seed, gain=.001, noise=.01)
        out = extract_features(series, rec)
        assert out["status"] != "ok" and out["reasons"]


def test_no_response_and_no_background_do_not_manufacture_scores():
    rec, frames, _ = signal(noise=0, gain=0, background_gain=0)
    r = extract_features(build_series(frames), rec)
    assert r["features"]["sync_corr"] is None and r["status"] == "unavailable"
    assert r["features"]["falloff_bg"] is None
    rec, frames, _ = signal()
    frames = [replace(f, regions={k: v for k, v in f.regions.items() if k != "background"}) for f in frames]
    r = extract_features(build_series(frames), rec)
    assert "MISSING_REFERENCE_REGION:background" in r["warnings"] and r["features"]["falloff_bg"] is None


def test_invalid_region_and_configuration():
    _, frames, _ = signal()
    with pytest.raises(ValueError):
        build_series([replace(frames[0], regions={"nose": RegionStat(np.array([2, 0, 0]), 1, 0)})])
    with pytest.raises(ValueError):
        FeatureConfig(min_frames_frac=1.1)
