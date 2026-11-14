from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import BACKEND_DIR, REPO_ROOT, Settings, load_policy

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def samples() -> dict:
    return json.loads((FIXTURES / "protocol_samples.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def policy():
    return load_policy(BACKEND_DIR / "config" / "policy.yaml")


@pytest.fixture()
def tmp_settings(tmp_path: Path) -> Settings:
    """Settings that point at throw-away dirs and carry known tokens."""
    models = tmp_path / "models"
    models.mkdir()
    (models / "manifest.json").write_text(json.dumps({"version": 1, "models": []}), encoding="utf-8")
    return Settings(
        kiosk_token="test-kiosk-token",
        operator_token="test-operator-token",
        data_dir=tmp_path / "data",
        models_dir=models,
        _env_file=None,
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
