"""Pure C1 timeline validation, shared by ingestion and Chroma alignment."""
from __future__ import annotations

import math

from ..schemas import ChallengeRecord
from .sequence import ChallengeConfig, validate


class TimelineError(ValueError):
    pass


def validate_timeline(record: ChallengeRecord, cfg: ChallengeConfig | None = None) -> None:
    cfg = cfg or ChallengeConfig()
    challenge = record.challenge
    problems = validate(challenge, cfg)
    if problems:
        raise TimelineError("invalid issued challenge: " + "; ".join(problems))
    timing = record.timing
    if timing is None:
        raise TimelineError("measurement timing version 2 is required for new uploads")
    if timing.capture_end_ms > cfg.total_cap_ms:
        raise TimelineError("actual capture exceeds the configured measurement cap")
    displayed, changes = record.displayed, timing.transitions
    if [d.index for d in displayed] != [-1, 0, 1, 2]:
        raise TimelineError("display timeline must contain every segment exactly once, in order")
    if any(not math.isfinite(d.t_display) for d in displayed):
        raise TimelineError("display timestamps must be finite")
    times = [d.t_display for d in changes]
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise TimelineError("transition timestamps must be strictly increasing")
    if any(sum(t0 <= t < t0 + 1000 for t in times) > 3 for t0 in times):
        raise TimelineError("more than three actual transitions within 1000 ms")
    if (
        times[0] > -1000
        or timing.preparation_ms + times[0] < 0
        or times[-2] != timing.capture_end_ms
        or times[-1] != timing.idle_at_ms
    ):
        raise TimelineError("invalid preparation, capture end or idle transition timestamp")
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
        raise TimelineError("actual transition trace does not match the displayed challenge")
    if times[1] < challenge.neutral.duration_ms:
        raise TimelineError("initial measurement neutral segment is too short")
    for i, segment in enumerate(challenge.segments):
        if times[i + 2] - times[i + 1] < segment.duration_ms:
            raise TimelineError("actual colour duration is shorter than issued duration")
