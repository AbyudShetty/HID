"""FastAPI application factory (plan §6, T0.2). Models are loaded once in the lifespan."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import rest_collect, rest_experiments, rest_ops, ws_kiosk
from .challenge.sequence import ChallengeConfig
from .config import Policy, Settings, load_policy
from .model_registry import assert_no_tampering, verify_models
from .pipeline.chroma_instrument import ChromaInstrument
from .schemas import HealthResponse
from .sessions.manager import SessionManager


def create_app(settings: Settings | None = None, policy: Policy | None = None) -> FastAPI:
    settings = settings or Settings()
    policy = policy or load_policy(settings.policy_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        statuses = verify_models(settings.models_dir)
        assert_no_tampering(statuses)  # raises ModelIntegrityError: refuse to start (plan §10.1)
        app.state.model_status = statuses
        app.state.chroma_instrument = ChromaInstrument(settings, statuses, policy)
        yield

    app = FastAPI(title="HID liveness kiosk backend", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.policy = policy
    app.state.sessions = SessionManager(ChallengeConfig.from_policy(policy.setting_section("challenge")))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(ws_kiosk.router)
    app.include_router(rest_ops.router)
    app.include_router(rest_collect.router)
    app.include_router(rest_experiments.router)

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        statuses = getattr(app.state, "model_status", None) or verify_models(settings.models_dir)
        required_ok = all(s.ok for s in statuses.values() if s.required)
        return HealthResponse(
            status="ok" if required_ok else "degraded",
            models_loaded={name: s.ok for name, s in statuses.items()},
            models={
                name: {"state": s.state, "file": s.file, "required": s.required, "sha256": s.sha256_actual}
                for name, s in statuses.items()
            },
            storage=settings.storage_backend,
            policy_version=policy.version,
            policy_provisional=policy.provisional,
        )

    return app


def get_app() -> FastAPI:
    """Factory for ``uvicorn app.main:get_app --factory``."""
    return create_app()
