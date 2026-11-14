"""Session issuing: single-use, expiring challenge sessions (plan §8.1, F-04).

Core semantics needed by the M1 spike/collect path and extended in T3.1 (prefetch pool, buffers, deadlines):
a session carries a server-generated challenge with a nonce; it expires ``ttl_s`` after issue and can be consumed
exactly once. Unknown, expired or already-consumed sessions are rejected.
"""
from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace

from ..challenge.sequence import ChallengeConfig, generate
from ..schemas import Challenge, Mode, Purpose, SessionReady
from ..timing import now_ms


class SessionError(Exception):
    """Base class; ``code`` maps to the wire ``error`` codes of plan §8.1."""

    code = "PROTOCOL"


class SessionExpired(SessionError):
    code = "SESSION_EXPIRED"


class SessionConsumed(SessionError):
    code = "PROTOCOL"


@dataclass(frozen=True)
class IssuedSession:
    session_id: str
    challenge: Challenge
    purpose: Purpose
    mode: Mode
    parent_session_id: str | None
    issued_at_ms: float
    expires_at_ms: float
    consumed: bool = False


class SessionManager:
    def __init__(self, cfg: ChallengeConfig, clock: Callable[[], float] = now_ms) -> None:
        self.cfg = cfg
        self._clock = clock
        self._sessions: dict[str, IssuedSession] = {}
        self._lock = threading.Lock()

    @property
    def ttl_ms(self) -> float:
        return self.cfg.prefetch_ttl_s * 1000.0

    def issue(
        self,
        purpose: Purpose = "access",
        mode: Mode = "face",
        parent_session_id: str | None = None,
        palette_id: str | None = None,
    ) -> IssuedSession:
        cfg = replace(self.cfg, palette_id=palette_id) if palette_id else self.cfg
        now = self._clock()
        session = IssuedSession(
            session_id="s_" + secrets.token_hex(8),
            challenge=generate(cfg),
            purpose=purpose,
            mode=mode,
            parent_session_id=parent_session_id,
            issued_at_ms=now,
            expires_at_ms=now + self.ttl_ms,
        )
        with self._lock:
            self._purge_locked(now)
            self._sessions[session.session_id] = session
        return session

    def consume(self, session_id: str) -> IssuedSession:
        """Mark the session used. Raises :class:`SessionExpired` (unknown/expired) or :class:`SessionConsumed`."""
        now = self._clock()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.expires_at_ms <= now:
                self._sessions.pop(session_id, None)
                raise SessionExpired(f"session {session_id!r} is unknown or expired")
            if session.consumed:
                raise SessionConsumed(f"session {session_id!r} was already used")
            used = replace(session, consumed=True)
            self._sessions[session_id] = used
            return used

    def ready_message(self, session: IssuedSession) -> SessionReady:
        remaining = max(0, int(session.expires_at_ms - self._clock()))
        return SessionReady(session_id=session.session_id, expires_in_ms=remaining, challenge=session.challenge)

    def active_count(self) -> int:
        now = self._clock()
        with self._lock:
            self._purge_locked(now)
            return sum(1 for s in self._sessions.values() if not s.consumed)

    def _purge_locked(self, now: float) -> None:
        stale = [sid for sid, s in self._sessions.items() if s.expires_at_ms <= now]
        for sid in stale:
            del self._sessions[sid]
