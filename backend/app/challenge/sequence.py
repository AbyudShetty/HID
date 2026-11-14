"""Server-issued light challenge: generator + safety validator (plan §9.2, F-04).

A challenge is a neutral reference segment followed by K colour segments. The hard constraints (checked by
:func:`validate`; :func:`generate` retries until they hold):

1. at most ``max_transitions_per_s`` state changes inside ANY 1000 ms window — counting neutral->first AND the final
   return to the idle/neutral screen, which is a real luminance change the user sees (photosensitivity safety);
2. no saturated red: ``R/(R+G+B) < 0.6`` for every colour;
3. consecutive states are clearly distinct *in measured light*: linear-RGB distance >= ``min_delta_linear``
   (applies to neutral->first and every colour->colour step). See ADR-005 for why this replaces the plan's literal
   "differ by >= 100/255 in two channels" wording (that rule rejects every colour of the plan's own example palette);
4. no two consecutive segments use the same colour;
5. total duration <= ``total_cap_ms`` and every segment has a positive duration.

Randomness: colours, jitter and the nonce come from ``secrets.SystemRandom`` / ``secrets.token_urlsafe`` (plan rule 2.3.3).
A caller may inject another ``random.Random`` *only for tests* (to run the generator over thousands of seeds).
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass

from ..schemas import Challenge, ChallengeSegment
from .palettes import PALETTES, Palette, linear_distance, red_fraction

WINDOW_MS = 1000


@dataclass(frozen=True)
class ChallengeConfig:
    neutral_ms: int = 200
    segments: int = 3
    segment_ms: int = 340
    jitter_ms: int = 30
    total_cap_ms: int = 1300
    palette_id: str = "P1"
    max_transitions_per_s: int = 3
    min_delta_linear: float = 0.30
    prefetch_ttl_s: int = 30
    render_reserve_ms: int = (
        80  # leave room for rAF quantization inside the unchanged 1300 ms actual cap
    )

    def __post_init__(self) -> None:
        integers = (
            self.neutral_ms,
            self.segments,
            self.segment_ms,
            self.jitter_ms,
            self.total_cap_ms,
            self.prefetch_ttl_s,
            self.render_reserve_ms,
        )
        if any(type(v) is not int for v in integers):
            raise ValueError("challenge timing/count values must be integers")
        if (
            self.neutral_ms != 200
            or self.segments != 3
            or self.segment_ms <= self.jitter_ms
            or self.jitter_ms < 0
            or self.total_cap_ms > 1300
            or self.render_reserve_ms < 0
            or self.total_cap_ms - self.render_reserve_ms < 1200
            or self.prefetch_ttl_s <= 0
            or self.max_transitions_per_s != 3
            or self.min_delta_linear != 0.30
        ):
            raise ValueError("challenge configuration violates the measurement/safety contract")

    @classmethod
    def from_policy(cls, settings: dict) -> ChallengeConfig:
        """Build from ``policy.structural['challenge']`` (backend/config/policy.yaml)."""
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in settings.items() if k in known})


class ChallengeError(RuntimeError):
    """Raised when no valid challenge could be generated (a configuration problem, not randomness)."""


def transition_times(challenge: Challenge) -> list[int]:
    """Times (ms from challenge start) of every visible state change, including the final return to idle."""
    t = challenge.neutral.duration_ms
    times = [t]  # neutral -> first colour
    for seg in challenge.segments:
        t += seg.duration_ms
        times.append(t)  # colour k -> next colour, and the last one -> idle/neutral
    return times


def validate(challenge: Challenge, cfg: ChallengeConfig | None = None) -> list[str]:
    """Return human-readable violations of the hard constraints (empty list = valid)."""
    cfg = cfg or ChallengeConfig()
    problems: list[str] = []
    palette = PALETTES.get(challenge.palette_id)
    if palette is None:
        return [f"unknown palette {challenge.palette_id!r}"]

    states = [challenge.neutral, *challenge.segments]
    if len(challenge.segments) != cfg.segments or challenge.neutral.duration_ms != cfg.neutral_ms:
        problems.append("challenge must have the configured neutral duration and segment count")
    if any(s.duration_ms <= 0 for s in states):
        problems.append("every segment needs a positive duration")
    if challenge.total_ms > cfg.total_cap_ms:
        problems.append(f"total {challenge.total_ms} ms exceeds the cap {cfg.total_cap_ms} ms")
    if any(
        not cfg.segment_ms - cfg.jitter_ms <= s.duration_ms <= cfg.segment_ms + cfg.jitter_ms
        for s in challenge.segments
    ):
        problems.append("segment duration is outside configured jitter bounds")
    if tuple(challenge.neutral.rgb) != palette.neutral:
        problems.append("neutral segment colour is not the palette neutral")

    # 1. flash-rate safety over any 1 s window
    times = transition_times(challenge)
    for i, t0 in enumerate(times):
        in_window = sum(1 for t in times[i:] if t < t0 + WINDOW_MS)
        if in_window > cfg.max_transitions_per_s:
            problems.append(
                f"{in_window} transitions within {WINDOW_MS} ms starting at {t0} ms (max {cfg.max_transitions_per_s})"
            )
            break

    for k, seg in enumerate(challenge.segments):
        rgb = tuple(seg.rgb)
        if rgb not in palette.colors:
            problems.append(f"segment {k} colour {rgb} is not in palette {palette.id}")
        # 2. no saturated red
        if red_fraction(rgb) >= 0.6:  # type: ignore[arg-type]
            problems.append(f"segment {k} colour {rgb} is saturated red (R/(R+G+B) >= 0.6)")
        # 4. no immediate repeats
        prev = states[k]  # states[0] is neutral, so segment k's predecessor is states[k]
        if tuple(prev.rgb) == rgb:
            problems.append(f"segment {k} repeats the previous colour {rgb}")
        # 3. distinct in measured light
        elif linear_distance(tuple(prev.rgb), rgb) < cfg.min_delta_linear:  # type: ignore[arg-type]
            problems.append(
                f"segment {k} is too close to its predecessor in linear RGB (< {cfg.min_delta_linear})"
            )
    if (
        challenge.segments
        and linear_distance(tuple(challenge.segments[-1].rgb), palette.neutral)
        < cfg.min_delta_linear
    ):
        problems.append("final return to neutral is too close in linear RGB")
    return problems


def _build(palette: Palette, cfg: ChallengeConfig, rng: random.Random) -> Challenge:
    colors: list[tuple[int, int, int]] = []
    prev = palette.neutral
    for _ in range(cfg.segments):
        choices = [c for c in palette.colors if c != prev]
        prev = rng.choice(choices)
        colors.append(prev)
    segments = [
        ChallengeSegment(
            rgb=c, duration_ms=cfg.segment_ms + rng.randint(-cfg.jitter_ms, cfg.jitter_ms)
        )
        for c in colors
    ]
    neutral = ChallengeSegment(rgb=palette.neutral, duration_ms=cfg.neutral_ms)
    return Challenge(
        nonce=secrets.token_urlsafe(16),
        palette_id=palette.id,
        neutral=neutral,
        segments=segments,
        total_ms=neutral.duration_ms + sum(s.duration_ms for s in segments),
    )


def generate(
    cfg: ChallengeConfig | None = None, rng: random.Random | None = None, max_attempts: int = 1000
) -> Challenge:
    """Generate a valid challenge. ``rng`` is for tests only; production uses ``secrets.SystemRandom``."""
    cfg = cfg or ChallengeConfig()
    rng = rng or secrets.SystemRandom()
    palette = PALETTES.get(cfg.palette_id)
    if palette is None:
        raise ChallengeError(f"unknown palette {cfg.palette_id!r}")
    for _ in range(max_attempts):
        challenge = _build(palette, cfg, rng)
        if challenge.total_ms <= cfg.total_cap_ms - cfg.render_reserve_ms and not validate(
            challenge, cfg
        ):
            return challenge
    raise ChallengeError(
        f"could not generate a valid challenge in {max_attempts} attempts for {cfg}; "
        "the durations/palette cannot satisfy the safety constraints"
    )
