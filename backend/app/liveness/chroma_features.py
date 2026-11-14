"""Interpretable illumination measurements, NOT a trained liveness signal or decision.

RGB values are linearized encoded camera values, not calibrated scene radiance.
Undefined/ill-conditioned ratios remain None. There is deliberately no p_live.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from ..challenge.timeline import validate_timeline
from ..schemas import ChallengeRecord
from ..vision.decode import SRGB_TO_LINEAR
from ..vision.regions import ALL_REGIONS, SKIN_REGIONS
from .chroma_series import ChromaSeries, emitted, steady_masks

EPS = 1e-12  # numerical degeneracy only, not a classifier threshold


@dataclass(frozen=True)
class FeatureConfig:
    min_snr: float = 3.0
    min_frames_frac: float = 0.8
    max_motion_frac: float = 0.12
    max_clipped_frac: float = 0.05
    expected_fps: float = 30.0
    min_face_frac: float = 0.7  # plan 9.4
    max_ambient_level: float | None = None  # only set from a measured kiosk profile
    expected_lag_ms: float | None = None
    noise_floor: float | None = None

    def __post_init__(self):
        values = [self.min_snr, self.expected_fps, self.max_motion_frac, self.max_clipped_frac,
                  self.min_frames_frac, self.min_face_frac]
        if not all(np.isfinite(v) and v > 0 for v in values):
            raise ValueError("invalid measurement configuration")
        if any(v > 1 for v in (self.min_frames_frac, self.min_face_frac, self.max_clipped_frac)):
            raise ValueError("fractions must not exceed one")
        if any(v is not None and (not np.isfinite(v) or v < 0) for v in
               (self.max_ambient_level, self.expected_lag_ms, self.noise_floor)):
            raise ValueError("invalid measured camera profile")


def finite(value) -> float | None:
    return float(value) if value is not None and np.isfinite(value) else None


def ratio(a, b) -> float | None:
    return finite(a / b) if a is not None and b is not None and b > EPS else None


def correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    a, b = a.ravel(), b.ravel()
    if len(a) < 6:
        return None
    ac, bc = a - a.mean(), b - b.mean()
    den = np.linalg.norm(ac) * np.linalg.norm(bc)
    return finite(np.clip(np.dot(ac, bc) / den, -1, 1)) if den > EPS else None


def extract_features(series: ChromaSeries, record: ChallengeRecord, cfg: FeatureConfig = FeatureConfig()) -> dict:
    validate_timeline(record)
    assert record.timing is not None
    t, face = series.t, series.means["face_core"]
    if not np.isfinite(t).all() or (np.diff(t) <= 0).any() or (t < 0).any() or (t > record.timing.capture_end_ms).any():
        raise ValueError("invalid feature timestamps")
    reasons, warnings = [], ["HARDWARE_RESPONSE_UNVALIDATED", "FEATURES_NOT_A_LIVENESS_CLASSIFIER"]
    features: dict[str, float | None] = {k: None for k in
        ("sync_corr", "lag_ms", "lag_err_ms", "gain_face", "rel_gain_face", "fit_r2", "snr", "noise",
         "falloff_bg", "falloff_sur", "intra_cv", "nose_cheek", "rb_ratio", "gb_ratio", "ambient_level",
         "motion_frac", "interval_std_ms", "max_gap_ms", "fps", "neutral_drift", "max_segment_drift")}
    first_color = record.displayed[1].t_display
    valid_face = np.isfinite(face).all(axis=1)
    neutral = t < first_color
    expected_n = max(1, int(np.ceil(record.timing.capture_end_ms * cfg.expected_fps / 1000)))
    coverage = min(1.0, len(t) / expected_n)
    face_frac = float(valid_face.mean()) if len(t) else 0.0
    if coverage < cfg.min_frames_frac:
        reasons.append("MISSING_FRAMES")
    if face_frac < cfg.min_face_frac:
        reasons.append("INSUFFICIENT_FACE_COVERAGE")
    if (series.face_count > 1).any():
        reasons.append("MULTIPLE_SIGNIFICANT_FACES")
    if len(t) > 1:
        dt = np.diff(t)
        features.update(fps=finite(1000 / np.median(dt)), interval_std_ms=finite(dt.std()), max_gap_ms=finite(dt.max()))
    boxes = series.boxes[np.isfinite(series.boxes).all(axis=1)]
    if len(boxes) > 1:
        centers = (boxes[:, :2] + boxes[:, 2:]) / 2
        motion = float(np.max(np.linalg.norm(centers - np.median(centers, axis=0), axis=1)) / np.median(boxes[:, 3] - boxes[:, 1]))
        features["motion_frac"] = motion
        if motion > cfg.max_motion_frac:
            reasons.append("TRACK_MOTION")
    lag, best = None, None
    if np.count_nonzero(neutral & valid_face) >= 2:
        baseline = face[neutral & valid_face].mean(axis=0)
        delta = face - baseline
        for candidate in range(0, 251, 5):
            ref = emitted(record, t, candidate) - SRGB_TO_LINEAR[list(record.challenge.neutral.rgb)]
            corr = correlation(delta[valid_face], ref[valid_face])
            if corr is not None and (best is None or corr > best):
                lag, best = float(candidate), corr
        neutral_values = face[neutral & valid_face]
        features["neutral_drift"] = finite(np.linalg.norm(neutral_values[-1] - neutral_values[0]))
    else:
        reasons.append("INSUFFICIENT_NEUTRAL_SAMPLES")
    features.update(sync_corr=best, lag_ms=lag,
                    lag_err_ms=None if lag is None or cfg.expected_lag_ms is None else abs(lag - cfg.expected_lag_ms))
    if lag is None:
        reasons.append("NO_TEMPORAL_VARIATION")
    elif lag in (0, 250):
        warnings.append("LAG_AT_SEARCH_BOUNDARY")
    masks = steady_masks(record, t, lag) if lag is not None else [np.zeros(len(t), bool)] * 3
    neutral_rgb = SRGB_TO_LINEAR[list(record.challenge.neutral.rgb)].astype(float)
    illumination = SRGB_TO_LINEAR[np.array([s.rgb for s in record.challenge.segments])].astype(float) - neutral_rgb
    region_results = {}
    gains, relative = {}, {}
    for name in ALL_REGIONS:
        values = series.means[name]
        usable = np.isfinite(values).all(axis=1)
        counts = [int(np.count_nonzero(m & usable)) for m in masks]
        ok = np.count_nonzero(neutral & usable) >= 2 and all(n >= 2 for n in counts)
        g = np.full(3, np.nan)
        base = values[neutral & usable].mean(axis=0) if np.count_nonzero(neutral & usable) >= 2 else None
        if ok and base is not None:
            response = np.stack([values[m & usable].mean(axis=0) - base for m in masks])
            energy = np.sum(illumination ** 2, axis=0)
            np.divide(np.sum(response * illumination, axis=0), energy, out=g, where=energy > EPS)
        mean_gain = finite(g.mean())
        rel = ratio(mean_gain, finite(base.mean()) if base is not None else None)
        gains[name], relative[name] = mean_gain, rel
        features[f"gain_{name}"] = mean_gain
        features[f"rel_gain_{name}"] = rel
        region_results[name] = {"gain_rgb": [finite(x) for x in g], "gain": mean_gain, "relative_gain": rel,
                                "neutral_rgb": None if base is None else base.tolist(), "steady_samples": counts}
        clip = series.clipped[name]
        if name in SKIN_REGIONS or name == "face_core":
            if not ok:
                reasons.append(f"MISSING_REGION_OR_STEADY_WINDOW:{name}")
            if np.isfinite(clip).any() and np.nanmax(clip) > cfg.max_clipped_frac:
                reasons.append(f"CLIPPED_REGION:{name}")
        elif not ok:
            warnings.append(f"MISSING_REFERENCE_REGION:{name}")
    features.update(gain_face=gains["face_core"], rel_gain_face=relative["face_core"],
                    falloff_bg=ratio(gains["face_core"], gains["background"]),
                    falloff_sur=ratio(gains["face_core"], gains["surround"]))
    skin = [relative[n] for n in SKIN_REGIONS]
    if all(v is not None for v in skin):
        values = np.array(skin, float)
        features["intra_cv"] = ratio(float(values.std()), float(values.mean()))
        features["nose_cheek"] = ratio(relative["nose"], float(np.mean([relative["cheek_l"], relative["cheek_r"]])))
    g_face = region_results["face_core"]["gain_rgb"]
    features.update(rb_ratio=ratio(g_face[0], g_face[2]), gb_ratio=ratio(g_face[1], g_face[2]))
    bg = region_results["background"]["neutral_rgb"]
    if bg is not None:
        features["ambient_level"] = finite(np.dot(bg, [0.2126, 0.7152, 0.0722]))
        if cfg.max_ambient_level is not None and features["ambient_level"] > cfg.max_ambient_level:
            reasons.append("AMBIENT_ABOVE_MEASURED_PROFILE")
    if all(n >= 2 for n in region_results["face_core"]["steady_samples"]) and all(v is not None for v in g_face):
        base = np.array(region_results["face_core"]["neutral_rgb"])
        observed = np.concatenate([face[m & valid_face] - base for m in masks])
        predicted = np.concatenate([np.tile(illumination[k] * np.array(g_face), (np.count_nonzero(m & valid_face), 1)) for k, m in enumerate(masks)])
        sst = float(np.sum((observed - observed.mean(axis=0)) ** 2))
        features["fit_r2"] = finite(1 - np.sum((observed - predicted) ** 2) / sst) if sst > EPS else None
        noise = float(np.median([np.std(face[m & valid_face], axis=0, ddof=1) for m in masks]))
        features["noise"] = noise
        denominator = max(noise, cfg.noise_floor or 0)
        features["snr"] = ratio(float(np.sqrt(np.mean(predicted ** 2))), denominator)
        features["max_segment_drift"] = max(float(np.linalg.norm(face[m & valid_face][-1] - face[m & valid_face][0])) for m in masks)
    if features["snr"] is None:
        reasons.append("NO_RELIABLE_NOISE_ESTIMATE")
    elif features["snr"] < cfg.min_snr:
        reasons.append("LOW_SNR")
    if gains["face_core"] is not None and gains["face_core"] <= 0:
        warnings.append("NONPOSITIVE_GAIN_CAMERA_OR_ILLUMINATION_INTERFERENCE")
    unavailable = [r for r in reasons if r not in ("LOW_SNR", "AMBIENT_ABOVE_MEASURED_PROFILE")]
    return {"version": "chroma-features-v1", "status": "unavailable" if unavailable else "low_snr" if reasons else "ok",
            "features": features, "regions": region_results, "reasons": sorted(set(reasons)), "warnings": warnings,
            "quality": {"frames": len(t), "expected_frames": expected_n, "frame_fraction": coverage,
                        "face_fraction": face_frac, "lag_resolution_ms": features["fps"] and 1000 / features["fps"]},
            "configuration": asdict(cfg), "hardware_validated": False, "classification": "not_implemented"}
