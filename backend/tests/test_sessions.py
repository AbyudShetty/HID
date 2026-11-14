"""Expiry and single use of issued sessions (plan §8.1, F-04)."""
from __future__ import annotations

import pytest

from app.challenge.sequence import ChallengeConfig
from app.sessions.manager import SessionConsumed, SessionExpired, SessionManager


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture()
def rig():
    clock = Clock()
    return SessionManager(ChallengeConfig(prefetch_ttl_s=30), clock=clock), clock


def test_issue_yields_unique_ids_and_nonces(rig):
    m, _ = rig
    issued = [m.issue() for _ in range(200)]
    assert len({s.session_id for s in issued}) == 200
    assert len({s.challenge.nonce for s in issued}) == 200
    assert all(s.session_id.startswith("s_") for s in issued)


def test_consume_is_single_use(rig):
    m, _ = rig
    s = m.issue()
    assert m.consume(s.session_id).consumed is True
    with pytest.raises(SessionConsumed):
        m.consume(s.session_id)


def test_sessions_expire_after_the_ttl(rig):
    m, clock = rig
    s = m.issue()
    clock.t += 29_999
    assert m.ready_message(s).expires_in_ms == 1
    clock.t += 2
    with pytest.raises(SessionExpired):
        m.consume(s.session_id)


def test_unknown_session_is_rejected(rig):
    m, _ = rig
    with pytest.raises(SessionExpired):
        m.consume("s_0000000000000000")


def test_ready_message_carries_the_challenge_and_remaining_ttl(rig):
    m, clock = rig
    s = m.issue(palette_id="P2")
    clock.t += 5000
    msg = m.ready_message(s)
    assert msg.type == "session.ready"
    assert msg.expires_in_ms == 25_000
    assert msg.challenge.palette_id == "P2"


def test_expired_sessions_are_purged(rig):
    m, clock = rig
    for _ in range(5):
        m.issue()
    assert m.active_count() == 5
    clock.t += 31_000
    assert m.active_count() == 0
