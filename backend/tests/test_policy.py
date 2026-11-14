"""Policy loader integrity rules (plan §11.3, T0.2)."""
from __future__ import annotations

import copy

import pytest
import yaml

from app.config import BACKEND_DIR, PolicyError, load_policy, parse_policy


@pytest.fixture()
def raw() -> dict:
    with open(BACKEND_DIR / "config" / "policy.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_real_policy_loads_and_is_provisional(policy):
    assert policy.status == "provisional"
    assert policy.provisional is True
    assert policy.value("fusion.tau_allow") == 0.90
    assert policy.source("quality.secondary_face_ratio") == "final"
    assert policy.required_signals == ("chroma", "passive")
    assert policy.fusion_method == "min_provisional"


def test_identity_thresholds_are_uncalibrated_nulls(policy):
    for key in ("tau_match_1to1", "tau_reject_1to1", "tau_match_1toN", "tau_reject_1toN"):
        assert policy.value(f"identity.{key}") is None
        assert policy.source(f"identity.{key}") == "uncalibrated"


def test_leaf_without_source_is_rejected(raw):
    raw["chroma"]["min_snr"] = 3.0  # bare scalar, no {value, source}
    with pytest.raises(PolicyError, match="exactly 'value' and 'source'"):
        parse_policy(raw)


def test_leaf_missing_source_key_is_rejected(raw):
    raw["chroma"]["min_snr"] = {"value": 3.0}
    with pytest.raises(PolicyError, match="exactly 'value' and 'source'"):
        parse_policy(raw)


def test_unknown_source_is_rejected(raw):
    raw["chroma"]["min_snr"] = {"value": 3.0, "source": "guessed"}
    with pytest.raises(PolicyError, match="invalid source"):
        parse_policy(raw)


def test_value_null_iff_uncalibrated(raw):
    raw["identity"]["tau_match_1to1"] = {"value": 0.4, "source": "uncalibrated"}
    with pytest.raises(PolicyError, match="null if and only if"):
        parse_policy(raw)
    raw2 = yaml.safe_load(open(BACKEND_DIR / "config" / "policy.yaml", encoding="utf-8"))
    raw2["identity"]["tau_match_1to1"] = {"value": None, "source": "provisional"}
    with pytest.raises(PolicyError, match="null if and only if"):
        parse_policy(raw2)


def test_calibrated_status_requires_every_leaf_final_or_calibrated(raw):
    raw["status"] = "calibrated"
    with pytest.raises(PolicyError, match="requires every threshold"):
        parse_policy(raw)


def test_fully_calibrated_policy_is_not_provisional(raw):
    raw = copy.deepcopy(raw)
    for section in ("quality", "chroma", "passive", "fusion", "identity"):
        for key, entry in raw[section].items():
            if isinstance(entry, dict):
                entry["source"] = "final" if section == "quality" and key == "secondary_face_ratio" else "calibrated:run_0001"
                if entry["value"] is None:
                    entry["value"] = 0.5
    raw["status"] = "calibrated"
    policy = parse_policy(raw)
    assert policy.provisional is False


def test_preliminary_source_keeps_policy_provisional(raw):
    raw["identity"]["tau_match_1to1"] = {"value": 0.4, "source": "preliminary:lfw"}
    policy = parse_policy(raw)
    assert policy.provisional is True
    assert policy.source("identity.tau_match_1to1") == "preliminary:lfw"


def test_bad_status_and_architecture_rejected(raw):
    raw["status"] = "maybe"
    with pytest.raises(PolicyError, match="status"):
        parse_policy(raw)
    raw2 = yaml.safe_load(open(BACKEND_DIR / "config" / "policy.yaml", encoding="utf-8"))
    raw2["architecture"] = "secondary"
    with pytest.raises(PolicyError, match="architecture"):
        parse_policy(raw2)


def test_missing_section_rejected(raw):
    del raw["timing"]
    with pytest.raises(PolicyError, match="missing key: timing"):
        parse_policy(raw)


def test_to_public_exposes_sources(policy):
    public = policy.to_public()
    assert public["provisional"] is True
    assert public["thresholds"]["fusion.tau_allow"] == {"value": 0.9, "source": "provisional"}
    assert public["settings"]["timing"]["client_watchdog_ms"] == 1950


def test_load_policy_from_path():
    assert load_policy(BACKEND_DIR / "config" / "policy.yaml").version
