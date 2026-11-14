"""Structural timing/alignment acceptance, not proof of physical illumination or liveness.

Legacy bundles remain readable for provenance. New uploads require the v2 complete
timeline including neutral preparation, final neutral and the controlled UI exit.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..challenge.sequence import ChallengeConfig, validate
from .bundle_io import BundleError

if TYPE_CHECKING:
    from .bundle_io import Bundle


def validate_measurement(bundle: Bundle, cfg: ChallengeConfig) -> None:
    challenge, record = bundle.challenge.challenge, bundle.challenge
    problems = validate(challenge, cfg)
    if problems:
        raise BundleError("invalid issued challenge: " + "; ".join(problems))
    timing = record.timing
    if timing is None:
        raise BundleError("measurement timing version 2 is required for new uploads")
    if timing.capture_end_ms > cfg.total_cap_ms:
        raise BundleError("actual capture exceeds the configured measurement cap")
    displayed, changes = record.displayed, timing.transitions
    if [d.index for d in displayed] != [-1, 0, 1, 2]:
        raise BundleError("display timeline must contain every segment exactly once, in order")
    if any(not math.isfinite(d.t_display) for d in displayed):
        raise BundleError("display timestamps must be finite")
    times = [d.t_display for d in changes]
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise BundleError("transition timestamps must be strictly increasing")
    if any(sum(t0 <= t < t0 + 1000 for t in times) > 3 for t0 in times):
        raise BundleError("more than three actual transitions within 1000 ms")
    if (
        times[0] > -1000
        or timing.preparation_ms + times[0] < 0
        or times[-2] != timing.capture_end_ms
        or times[-1] != timing.idle_at_ms
    ):
        raise BundleError("invalid preparation, capture end or idle transition timestamp")
    expected_rgbs = [
        challenge.neutral.rgb,
        *(s.rgb for s in challenge.segments),
        challenge.neutral.rgb,
    ]
    if (
        [d.rgb for d in changes[:-1]] != expected_rgbs
        or any(d.state != "challenge" for d in changes[:-1])
        or changes[-1].state != "idle"
        or [d.t_display for d in displayed] != times[:4]
    ):
        raise BundleError("actual transition trace does not match the displayed challenge")
    if times[1] < challenge.neutral.duration_ms:
        raise BundleError("initial measurement neutral segment is too short")
    for i, segment in enumerate(challenge.segments):
        if times[i + 2] - times[i + 1] < segment.duration_ms:
            raise BundleError("actual colour duration is shorter than issued duration")
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
