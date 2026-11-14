"""Challenge generator + safety validator (plan §9.2, F-04, T1.1)."""
from __future__ import annotations

import random
from dataclasses import replace

import pytest

from app.challenge.palettes import (
    NEUTRAL,
    P1,
    P2,
    PALETTES,
    linear_distance,
    red_fraction,
    relative_luminance,
    srgb_to_linear,
)
from app.challenge.sequence import (
    ChallengeConfig,
    ChallengeError,
    generate,
    transition_times,
    validate,
)
from app.schemas import Challenge, ChallengeSegment

CFG = ChallengeConfig()


def make(colors, durations, neutral_ms=200, palette="P1") -> Challenge:
    neutral = ChallengeSegment(rgb=NEUTRAL, duration_ms=neutral_ms)
    segs = [ChallengeSegment(rgb=c, duration_ms=d) for c, d in zip(colors, durations, strict=True)]
    return Challenge(
        nonce="x" * 22, palette_id=palette, neutral=neutral, segments=segs, total_ms=neutral_ms + sum(durations)
    )


GOOD = make([P1.colors[0], P1.colors[1], P1.colors[2]], [340, 340, 340])


def test_srgb_linearization_known_values():
    assert srgb_to_linear(0) == 0.0
    assert srgb_to_linear(255) == pytest.approx(1.0)
    assert srgb_to_linear(128) == pytest.approx(0.2158605, abs=1e-6)
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)
    assert relative_luminance((0, 0, 0)) == 0.0
    assert relative_luminance((255, 0, 0)) == pytest.approx(0.2126)


def test_palette_p2_is_near_isoluminant_with_the_neutral():
    ref = relative_luminance(NEUTRAL)
    for c in P2.colors:
        assert abs(relative_luminance(c) - ref) / ref <= 0.10, c
    # P1 is deliberately luminance-varying
    assert max(abs(relative_luminance(c) - ref) / ref for c in P1.colors) > 0.3


@pytest.mark.parametrize("palette", list(PALETTES.values()), ids=lambda p: p.id)
def test_palette_colours_are_safe_and_distinct_from_neutral(palette):
    for c in palette.colors:
        assert red_fraction(c) < 0.6, c
        assert linear_distance(palette.neutral, c) >= CFG.min_delta_linear, c


def test_good_challenge_is_valid():
    assert validate(GOOD, CFG) == []
    assert transition_times(GOOD) == [200, 540, 880, 1220]  # neutral->1, 1->2, 2->3, 3->idle


def test_validator_rejects_too_many_transitions_per_second():
    fast = make([P1.colors[0], P1.colors[1], P1.colors[2]], [300, 300, 300])  # 4 transitions inside 900 ms
    assert any("transitions within" in p for p in validate(fast, CFG))
    # the plan's own default of 330 ms would still break the rule once the return to idle is counted
    assert any("transitions within" in p for p in validate(make(GOOD.segments and [s.rgb for s in GOOD.segments], [330, 330, 330]), CFG))


def test_validator_rejects_saturated_red():
    red_palette = replace(P1, id="P1", colors=((255, 40, 40), *P1.colors))
    assert red_fraction((255, 40, 40)) >= 0.6
    PALETTES["PRED"] = red_palette  # temporary palette to exercise the colour checks
    try:
        bad = make([(255, 40, 40), P1.colors[1], P1.colors[2]], [340, 340, 340], palette="PRED")
        assert any("saturated red" in p for p in validate(bad, CFG))
    finally:
        del PALETTES["PRED"]


def test_validator_rejects_repeats_and_low_contrast():
    repeat = make([P1.colors[0], P1.colors[0], P1.colors[2]], [340, 340, 340])
    assert any("repeats the previous colour" in p for p in validate(repeat, CFG))
    near = replace(P1, colors=((205, 205, 210), *P1.colors))
    PALETTES["PNEAR"] = near
    try:
        low = make([(205, 205, 210), P1.colors[1], P1.colors[2]], [340, 340, 340], palette="PNEAR")
        assert any("too close" in p for p in validate(low, CFG))
    finally:
        del PALETTES["PNEAR"]


def test_validator_rejects_foreign_colours_total_cap_and_unknown_palette():
    foreign = make([(1, 2, 3), P1.colors[1], P1.colors[2]], [340, 340, 340])
    assert any("not in palette" in p for p in validate(foreign, CFG))
    long = make([P1.colors[0], P1.colors[1], P1.colors[2]], [420, 420, 420])
    assert any("exceeds the cap" in p for p in validate(long, CFG))
    unknown = GOOD.model_copy(update={"palette_id": "P9"})
    assert validate(unknown, CFG) == ["unknown palette 'P9'"]


@pytest.mark.parametrize("palette_id", ["P1", "P2"])
def test_generator_always_produces_valid_challenges_over_10000_seeds(palette_id):
    cfg = replace(CFG, palette_id=palette_id)
    totals = set()
    for seed in range(10_000):
        c = generate(cfg, rng=random.Random(seed))
        assert validate(c, cfg) == [], (seed, c)
        assert c.total_ms <= cfg.total_cap_ms
        assert c.total_ms <= cfg.total_cap_ms - cfg.render_reserve_ms
        totals.add(c.total_ms)
    assert len(totals) > 20  # durations really are jittered


def test_default_production_generator_uses_secure_randomness_and_unique_nonces():
    nonces = {generate(CFG).nonce for _ in range(2000)}
    assert len(nonces) == 2000
    assert all(len(n) >= 16 for n in nonces)
    # colour orders actually vary
    orders = {tuple(tuple(s.rgb) for s in generate(CFG).segments) for _ in range(300)}
    assert len(orders) > 20


def test_generator_fails_loudly_when_constraints_are_unsatisfiable():
    impossible = replace(CFG, segment_ms=200, jitter_ms=0)  # 4 transitions inside 600 ms, always
    with pytest.raises(ChallengeError, match="could not generate"):
        generate(impossible, rng=random.Random(0), max_attempts=50)


def test_from_policy_reads_the_checked_in_defaults(policy):
    cfg = ChallengeConfig.from_policy(policy.setting_section("challenge"))
    assert cfg == CFG
    assert cfg.neutral_ms == 200 and cfg.segments == 3 and cfg.total_cap_ms == 1300
    assert cfg.render_reserve_ms == 80


@pytest.mark.parametrize("change", [{"neutral_ms": 0}, {"segments": 4}, {"jitter_ms": -1},
                                   {"total_cap_ms": 1400}, {"render_reserve_ms": -1},
                                   {"max_transitions_per_s": 4}, {"min_delta_linear": 0.1},
                                   {"segment_ms": 340.5}])
def test_configuration_cannot_silently_weaken_the_measurement_contract(change):
    with pytest.raises(ValueError):
        replace(CFG, **change)


def test_seed_reproduces_segments_but_never_reuses_the_secure_nonce():
    a, b = generate(rng=random.Random(42)), generate(rng=random.Random(42))
    assert a.segments == b.segments
    assert a.nonce != b.nonce
