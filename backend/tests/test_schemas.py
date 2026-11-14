"""Round-trip every contract of plan §8 (T0.2). The same fixture file is validated by the kiosk (TypeScript)."""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas import (
    ClientMessage,
    CollectLabel,
    DecisionResult,
    FrameHeader,
    KioskProfile,
    ServerMessage,
    SessionMeta,
)

CLIENT = TypeAdapter(ClientMessage)
SERVER = TypeAdapter(ServerMessage)


def _dump(model) -> dict:
    return model.model_dump(mode="json", by_alias=True, exclude_unset=True)


def test_every_client_message_round_trips(samples):
    assert set(samples["client"]) == {
        "hello", "session.request", "session.start", "segment.shown", "session.end",
        "session.client_timing", "stepup.verify", "stepup.request_review", "ping", "pong",
    }
    for name, raw in samples["client"].items():
        assert _dump(CLIENT.validate_python(raw)) == raw, name


def test_every_server_message_round_trips(samples):
    for name, raw in samples["server"].items():
        assert _dump(SERVER.validate_python(raw)) == raw, name


@pytest.mark.parametrize(
    ("key", "model"),
    [("frame_header", FrameHeader), ("session_meta", SessionMeta), ("kiosk_profile", KioskProfile)],
)
def test_records_round_trip(samples, key, model):
    raw = samples["records"][key]
    assert _dump(model.model_validate(raw)) == raw


def test_collect_labels_round_trip(samples):
    for key in ("collect_label_bona_fide", "collect_label_attack"):
        raw = samples["records"][key]
        assert _dump(CollectLabel.model_validate(raw)) == raw


def test_unknown_field_is_rejected(samples):
    raw = dict(samples["client"]["hello"], surprise=1)
    with pytest.raises(ValidationError):
        CLIENT.validate_python(raw)


def test_unknown_message_type_is_rejected():
    with pytest.raises(ValidationError):
        CLIENT.validate_python({"type": "nope"})


def test_decision_result_requires_consistent_label_and_flow(samples):
    raw = dict(samples["server"]["session.result"])
    raw.pop("type")
    DecisionResult.model_validate(raw)
    with pytest.raises(ValidationError, match="decision_label"):
        DecisionResult.model_validate(dict(raw, decision_label="Allow"))
    bad_flow = dict(raw["flow"], decision={"outcome": "ALLOW", "reason_code": "OK", "finalize_ms": 1.0})
    with pytest.raises(ValidationError, match="flow.decision"):
        DecisionResult.model_validate(dict(raw, flow=bad_flow))


def test_signal_p_live_only_when_ok(samples):
    raw = dict(samples["server"]["session.result"])
    raw.pop("type")
    bad = {**raw["signals"], "passive": {"status": "ok", "p_live": None}}
    with pytest.raises(ValidationError, match="p_live must be set"):
        DecisionResult.model_validate(dict(raw, signals=bad))
    bad2 = {**raw["signals"], "passive": {"status": "unavailable", "p_live": 0.9}}
    with pytest.raises(ValidationError, match="p_live must be set"):
        DecisionResult.model_validate(dict(raw, signals=bad2))


def test_challenge_total_must_match(samples):
    raw = samples["server"]["session.ready"]
    bad = dict(raw, challenge=dict(raw["challenge"], total_ms=999))
    with pytest.raises(ValidationError, match="total_ms"):
        SERVER.validate_python(bad)


def test_label_rules(samples):
    attack = dict(samples["records"]["collect_label_attack"])
    CollectLabel.model_validate(attack)
    with pytest.raises(ValidationError, match="does not belong"):
        CollectLabel.model_validate(dict(attack, pai_species="print_matte_a4"))
    with pytest.raises(ValidationError, match="instrument_id"):
        CollectLabel.model_validate(dict(attack, instrument_id=None))
    bona = dict(samples["records"]["collect_label_bona_fide"])
    with pytest.raises(ValidationError, match="bona_fide"):
        CollectLabel.model_validate(dict(bona, pai_family="print", pai_species="print_matte_a4"))
    red = dict(attack, capture_procedure="redteam", pai_species="redteam_flashlight_print")
    CollectLabel.model_validate(red)
    with pytest.raises(ValidationError, match="redteam"):
        CollectLabel.model_validate(dict(attack, capture_procedure="redteam"))


def test_species_catalog_matches_the_shared_fixture(samples):
    """kiosk/src/ops/labels.test.ts checks the same fixture, so the spike form cannot drift from the server catalog."""
    from app.schemas import SPECIES_BY_FAMILY

    assert {k: list(v) for k, v in SPECIES_BY_FAMILY.items()} == samples["records"]["species_by_family"]
