"""Pure, deterministic observations and display/frame alignment. No models or storage."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..challenge.timeline import validate_timeline
from ..schemas import ChallengeRecord
from ..vision.decode import SRGB_TO_LINEAR
from ..vision.regions import ALL_REGIONS, RegionStat


@dataclass(frozen=True)
class RegionFrame:
    t_ms: float
    regions: dict[str, RegionStat]
    box: tuple[float, float, float, float] | None
    significant_faces: int


@dataclass(frozen=True)
class ChromaSeries:
    t: np.ndarray
    means: dict[str, np.ndarray]  # N x 3 linearized sRGB; NaN represents missing, never imputed
    clipped: dict[str, np.ndarray]
    boxes: np.ndarray
    face_count: np.ndarray


def build_series(frames: list[RegionFrame]) -> ChromaSeries:
    t = np.array([f.t_ms for f in frames], dtype=np.float64)
    if not np.isfinite(t).all() or (t < 0).any() or (np.diff(t) <= 0).any():
        raise ValueError("frame timestamps must be finite, nonnegative and strictly increasing")
    means, clipped = {}, {}
    for name in ALL_REGIONS:
        values, clips = [], []
        for f in frames:
            stat = f.regions.get(name)
            value = None if stat is None else stat.mean_rgb
            if value is not None and (np.shape(value) != (3,) or not np.isfinite(value).all()
                                      or (np.asarray(value) < 0).any() or (np.asarray(value) > 1).any()):
                raise ValueError("region means must be finite linear RGB values in [0,1]")
            if stat is not None and (not np.isfinite(stat.clipped_frac) or not 0 <= stat.clipped_frac <= 1):
                raise ValueError("invalid clipped fraction")
            values.append([np.nan] * 3 if value is None else value)
            clips.append(np.nan if stat is None else stat.clipped_frac)
        means[name] = np.asarray(values, dtype=np.float64).reshape(-1, 3)
        clipped[name] = np.asarray(clips, dtype=np.float64)
    boxes = np.array([[np.nan] * 4 if f.box is None else f.box for f in frames], dtype=float).reshape(-1, 4)
    if any(f.box is not None and not np.isfinite(f.box).all() for f in frames):
        raise ValueError("invalid face box")
    if any(f.significant_faces < 0 for f in frames):
        raise ValueError("invalid face count")
    good = np.isfinite(boxes).all(axis=1)
    if (good & ((boxes[:, 2] <= boxes[:, 0]) | (boxes[:, 3] <= boxes[:, 1]))).any():
        raise ValueError("invalid face box")
    return ChromaSeries(t, means, clipped, boxes, np.array([f.significant_faces for f in frames]))


def emitted(record: ChallengeRecord, t: np.ndarray, lag_ms: float = 0) -> np.ndarray:
    """Sample the actual displayed trace, never nominal segment offsets."""
    validate_timeline(record)
    if not np.isfinite(lag_ms) or not 0 <= lag_ms <= 250 or not np.isfinite(t).all():
        raise ValueError("invalid alignment timestamps or lag")
    starts = np.array([d.t_display for d in record.displayed])
    shifted = t - lag_ms
    assert record.timing is not None
    if (shifted < starts[0]).any() or (t > record.timing.capture_end_ms).any():
        raise ValueError("frame is outside the recorded illumination interval")
    states = [record.challenge.neutral, *record.challenge.segments]
    rgb = SRGB_TO_LINEAR[np.array([s.rgb for s in states], dtype=np.uint8)].astype(float)
    return rgb[np.searchsorted(starts, shifted, side="right") - 1]


def steady_masks(record: ChallengeRecord, t: np.ndarray, lag_ms: float, settle_ms: float = 33) -> list[np.ndarray]:
    validate_timeline(record)
    assert record.timing is not None
    boundaries = [d.t_display for d in record.displayed[1:]] + [record.timing.capture_end_ms]
    return [(t >= a + lag_ms + settle_ms) & (t < b + lag_ms) & (t <= record.timing.capture_end_ms)
            for a, b in zip(boundaries, boundaries[1:], strict=False)]
