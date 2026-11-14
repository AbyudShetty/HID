"""Structural timing/alignment acceptance, not proof of physical illumination or liveness.

Legacy bundles remain readable for provenance. New uploads require the v2 complete
timeline including neutral preparation, final neutral and the controlled UI exit.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..challenge.sequence import ChallengeConfig
from ..challenge.timeline import TimelineError, validate_timeline
from .bundle_io import BundleError

if TYPE_CHECKING:
    from .bundle_io import Bundle


def validate_measurement(bundle: Bundle, cfg: ChallengeConfig) -> None:
    try:
        validate_timeline(bundle.challenge, cfg)
    except TimelineError as exc:
        raise BundleError(str(exc)) from exc
    timing = bundle.challenge.timing
    assert timing is not None  # established by the shared validator
    times = [d.t_display for d in timing.transitions]
    if not 1 <= len(bundle.frames) <= 80 or len(bundle.keyframes) != 2:
        raise BundleError("measurement requires 1..80 crops and exactly two neutral keyframes")
    key_seqs = [f.seq for f in bundle.keyframes]
    if len(set(key_seqs)) != len(key_seqs):
        raise BundleError("duplicate keyframe seq numbers")
    if (
        len({f.file for f in bundle.frames}) != len(bundle.frames)
        or len({f.file for f in bundle.keyframes}) != 2
    ):
        raise BundleError("each frame must reference a distinct image")
    for frames in (bundle.frames, bundle.keyframes):
        previous = -1.0
        for f in frames:
            if (
                f.seq < 0
                or not math.isfinite(f.t_capture)
                or f.t_capture <= previous
                or not 0 <= f.t_capture <= timing.capture_end_ms
            ):
                raise BundleError(
                    "capture timestamps must be finite, in range and strictly increasing"
                )
            previous = f.t_capture
            if (
                f.t_callback is None
                or not math.isfinite(f.t_callback)
                or not f.t_capture <= f.t_callback <= timing.capture_end_ms
                or f.capture_time_source not in ("now", "captureTime")
            ):
                raise BundleError("capture source and valid callback timestamp are required")
            if f.capture_time_source == "now" and f.t_callback != f.t_capture:
                raise BundleError("callback-time capture must equal the callback timestamp")
    for f in bundle.keyframes:
        if not max(0, times[0] + 60) <= f.t_capture < times[1] or f.t_callback >= times[1]:
            raise BundleError("keyframe was not acquired during settled neutral illumination")
    for f in bundle.frames:
        if (
            any(not math.isfinite(v) for v in f.crop_box)
            or any(v <= 0 for v in f.frame_size)
            or any(v < 0 for v in f.crop_box[:2])
            or any(v <= 0 for v in f.crop_box[2:])
            or f.crop_box[0] + f.crop_box[2] > f.frame_size[0]
            or f.crop_box[1] + f.crop_box[3] > f.frame_size[1]
        ):
            raise BundleError("invalid crop coordinates or frame size")
