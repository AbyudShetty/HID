"""Settings (environment) and the decision-policy loader (plan §11.3).

The policy loader enforces the integrity rules of plan §11.3:
  * every threshold leaf is a mapping with exactly ``value`` and ``source``;
  * ``source`` is one of final | provisional | preliminary:<origin> | calibrated:<run_id> | uncalibrated;
  * ``uncalibrated`` <=> ``value is None``;
  * ``status: calibrated`` is allowed only when every leaf is ``final`` or ``calibrated:*``.
A policy is *provisional* unless it is calibrated; the flag propagates to every DecisionResult (rule 2.3.4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

_SOURCE_RE = re.compile(r"^(final|provisional|uncalibrated|preliminary:[\w.\-]+|calibrated:[\w.\-]+)$")

# Sections whose entries are thresholds (every dict entry must be a {value, source} leaf).
_THRESHOLD_SECTIONS = ("quality", "chroma", "passive", "fusion", "identity")
# Bare (non-leaf) keys allowed inside threshold sections.
_BARE_ALLOWED = {"fusion": {"method"}}
# Structural sections: plain values, not thresholds.
_STRUCTURAL_SECTIONS = ("stepup", "rate_limit", "timing", "challenge")
_VALID_STATUS = {"provisional", "calibrated"}
_VALID_ARCH = {"primary", "primary_partial", "fallback_f2"}


class PolicyError(ValueError):
    """The policy file violates the integrity rules of plan §11.3."""


class Settings(BaseSettings):
    """Process configuration from the environment / .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    kiosk_token: str = ""
    operator_token: str = ""
    storage_backend: str = "local"
    data_dir: Path = REPO_ROOT / "data"
    models_dir: Path = REPO_ROOT / "models"
    aws_region: str = ""
    audit_save_frames: bool = False
    cors_origins: str = "http://localhost:5173"
    policy_path: Path = BACKEND_DIR / "config" / "policy.yaml"
    kiosk_profile_dir: Path = BACKEND_DIR / "config" / "kiosk_profiles"
    kiosk_dist_dir: Path | None = None  # built kiosk static files (served by the backend in production)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@dataclass(frozen=True)
class Leaf:
    value: Any
    source: str

    @property
    def provisional(self) -> bool:
        return self.source in ("provisional", "uncalibrated") or self.source.startswith("preliminary:")


@dataclass(frozen=True)
class Policy:
    version: str
    status: str
    architecture: str
    required_signals: tuple[str, ...]
    leaves: dict[str, Leaf]  # dotted path -> leaf, e.g. "chroma.min_snr"
    fusion_method: str
    structural: dict[str, dict[str, Any]] = field(default_factory=dict)

    # -- access ---------------------------------------------------------------------------------
    def value(self, path: str) -> Any:
        """Threshold value (may be ``None`` for an uncalibrated threshold)."""
        return self.leaves[path].value

    def source(self, path: str) -> str:
        return self.leaves[path].source

    def setting(self, section: str, key: str) -> Any:
        return self.structural[section][key]

    def setting_section(self, section: str) -> dict[str, Any]:
        return dict(self.structural[section])

    @property
    def provisional(self) -> bool:
        """True unless the policy is fully calibrated (plan rule 2.3.4)."""
        if self.status != "calibrated":
            return True
        return any(leaf.provisional for leaf in self.leaves.values())

    def to_public(self) -> dict[str, Any]:
        """Policy with ``source`` per threshold, for ``GET /config`` and the operator banner."""
        return {
            "version": self.version,
            "status": self.status,
            "architecture": self.architecture,
            "provisional": self.provisional,
            "required_signals": list(self.required_signals),
            "fusion_method": self.fusion_method,
            "thresholds": {p: {"value": leaf.value, "source": leaf.source} for p, leaf in self.leaves.items()},
            "settings": self.structural,
        }


def parse_policy(raw: dict[str, Any]) -> Policy:
    """Validate and build a :class:`Policy` from parsed YAML. Raises :class:`PolicyError`."""
    if not isinstance(raw, dict):
        raise PolicyError("policy must be a mapping")
    for key in ("version", "status", "architecture", "required_signals", *_THRESHOLD_SECTIONS, *_STRUCTURAL_SECTIONS):
        if key not in raw:
            raise PolicyError(f"missing key: {key}")
    if raw["status"] not in _VALID_STATUS:
        raise PolicyError(f"status must be one of {sorted(_VALID_STATUS)}, got {raw['status']!r}")
    if raw["architecture"] not in _VALID_ARCH:
        raise PolicyError(f"architecture must be one of {sorted(_VALID_ARCH)}, got {raw['architecture']!r}")
    if not isinstance(raw["required_signals"], list) or not raw["required_signals"]:
        raise PolicyError("required_signals must be a non-empty list")

    leaves: dict[str, Leaf] = {}
    fusion_method = None
    for section in _THRESHOLD_SECTIONS:
        body = raw[section]
        if not isinstance(body, dict):
            raise PolicyError(f"{section} must be a mapping")
        for key, entry in body.items():
            path = f"{section}.{key}"
            if key in _BARE_ALLOWED.get(section, set()):
                if section == "fusion" and key == "method":
                    if entry not in ("min_provisional", "lr"):
                        raise PolicyError(f"fusion.method must be min_provisional|lr, got {entry!r}")
                    fusion_method = entry
                continue
            if not isinstance(entry, dict) or set(entry) != {"value", "source"}:
                raise PolicyError(f"{path}: a threshold must be a mapping with exactly 'value' and 'source'")
            source = entry["source"]
            if not isinstance(source, str) or not _SOURCE_RE.match(source):
                raise PolicyError(f"{path}: invalid source {source!r}")
            value = entry["value"]
            if (source == "uncalibrated") != (value is None):
                raise PolicyError(f"{path}: value must be null if and only if source is 'uncalibrated'")
            leaves[path] = Leaf(value=value, source=source)
    if fusion_method is None:
        raise PolicyError("fusion.method is required")

    if raw["status"] == "calibrated":
        bad = [p for p, leaf in leaves.items() if not (leaf.source == "final" or leaf.source.startswith("calibrated:"))]
        if bad:
            raise PolicyError(f"status 'calibrated' requires every threshold to be final or calibrated:*; offending: {bad}")

    structural = {}
    for section in _STRUCTURAL_SECTIONS:
        body = raw[section]
        if not isinstance(body, dict):
            raise PolicyError(f"{section} must be a mapping")
        structural[section] = dict(body)

    return Policy(
        version=str(raw["version"]),
        status=raw["status"],
        architecture=raw["architecture"],
        required_signals=tuple(raw["required_signals"]),
        leaves=leaves,
        fusion_method=fusion_method,
        structural=structural,
    )


def load_policy(path: Path | str) -> Policy:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return parse_policy(raw)


def get_settings() -> Settings:
    return Settings()


__all__ = [
    "BACKEND_DIR",
    "REPO_ROOT",
    "Leaf",
    "Policy",
    "PolicyError",
    "Settings",
    "get_settings",
    "load_policy",
    "parse_policy",
]
