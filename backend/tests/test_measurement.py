"""Synthetic timing/alignment regressions only. Not camera or liveness evidence."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.api import rest_collect
from app.challenge.sequence import ChallengeConfig, generate
from app.main import create_app
from app.pipeline.bundle_io import BundleError, build_bundle, pack_bundle, unpack_bundle
from app.pipeline.measurement import validate_measurement
from app.schemas import Challenge
from tests.bundle_factory import make_entries

AUTH = {"Authorization": "Bearer test-operator-token", "Content-Type": "application/x-hid-bundle"}


def check(entries):
    validate_measurement(build_bundle(entries), ChallengeConfig())


@pytest.fixture()
def entries():
    return make_entries("s_0123456789abcdef", generate())


def edit_record(entries, mutation):
    r = json.loads(entries["challenge.json"])
    mutation(r)
    entries["challenge.json"] = json.dumps(r).encode()
    return entries


def test_valid_synthetic_measurement_and_actual_recorder_fixture(samples, entries):
    check(entries)
    check(unpack_bundle(base64.b64decode(samples["records"]["ts_bundle_b64"])))


def test_legacy_bundles_remain_readable_but_not_acceptable_as_new_measurements(samples):
    old = build_bundle(unpack_bundle(base64.b64decode(samples["records"]["ts_bundle_v1_b64"])))
    assert old.challenge.challenge.total_ms == 1190
    assert old.challenge.timing is None
    # Its old 330 ms issued timing is invalid too; neither condition is grandfathered into acceptance.
    with pytest.raises(BundleError):
        validate_measurement(old, ChallengeConfig())


def test_reproduced_four_actual_changes_in_984_ms_are_rejected(entries):
    r = json.loads(entries["challenge.json"])
    r["challenge"]["total_ms"] = 1200
    for i, s in enumerate(r["challenge"]["segments"]):
        s["duration_ms"] = 334 if i == 0 else 333
    times = [-1000, 216, 550, 883, 1200, 2200]
    for i, d in enumerate(r["timing"]["transitions"]):
        d["t_display"] = times[i]
    for i, d in enumerate(r["displayed"]):
        d["t_display"] = times[i]
    r["timing"].update(capture_end_ms=1200, idle_at_ms=2200)
    entries["challenge.json"] = json.dumps(r).encode()
    with pytest.raises(BundleError, match="three actual transitions"):
        check(entries)


@pytest.mark.parametrize(
    "bad",
    [
        "missing_timing",
        "missing_segment",
        "duplicate_segment",
        "nan_display",
        "idle_too_soon",
        "wrong_colour",
        "wrong_end",
        "short_neutral",
        "short_colour",
    ],
)
def test_invalid_display_traces_rejected(entries, bad):
    def mutate(r):
        if bad == "missing_timing":
            r.pop("timing")
        elif bad == "missing_segment":
            r["displayed"].pop()
        elif bad == "duplicate_segment":
            r["displayed"][2]["index"] = 0
        elif bad == "nan_display":
            r["displayed"][1]["t_display"] = float("nan")
        elif bad == "idle_too_soon":
            r["timing"]["idle_at_ms"] = r["timing"]["capture_end_ms"] + 1
            r["timing"]["transitions"][-1]["t_display"] = r["timing"]["idle_at_ms"]
        elif bad == "wrong_colour":
            r["timing"]["transitions"][2]["rgb"] = [1, 2, 3]
        elif bad == "wrong_end":
            r["timing"]["capture_end_ms"] -= 1
        elif bad == "short_neutral":
            r["displayed"][1]["t_display"] = 199
            r["timing"]["transitions"][1]["t_display"] = 199
        elif bad == "short_colour":
            r["displayed"][2]["t_display"] -= 1
            r["timing"]["transitions"][2]["t_display"] -= 1

    with pytest.raises(BundleError):
        check(edit_record(entries, mutate))


@pytest.mark.parametrize(
    "bad",
    [
        "coloured_keyframe",
        "future_sensor",
        "negative_sensor",
        "nan_sensor",
        "missing_source",
        "wrong_now",
        "duplicate_time",
        "duplicate_key_seq",
        "crop_bounds",
    ],
)
def test_invalid_frame_alignment_rejected(entries, bad):
    name = (
        "keyframes.jsonl" if bad in ("coloured_keyframe", "duplicate_key_seq") else "frames.jsonl"
    )
    rows = [json.loads(line) for line in entries[name].splitlines()]
    if bad == "coloured_keyframe":
        rows[0].update(t_capture=210, t_callback=210)
    elif bad == "future_sensor":
        rows[0]["t_capture"] = rows[0]["t_callback"] + 1
    elif bad == "negative_sensor":
        rows[0]["t_capture"] = -1
    elif bad == "nan_sensor":
        rows[0]["t_capture"] = float("nan")
    elif bad == "missing_source":
        rows[0].pop("capture_time_source")
    elif bad == "wrong_now":
        rows[0]["t_callback"] += 1
    elif bad == "duplicate_time":
        rows[1]["t_capture"] = rows[0]["t_capture"]
    elif bad == "duplicate_key_seq":
        rows[1]["seq"] = rows[0]["seq"]
    elif bad == "crop_bounds":
        rows[0]["crop_box"][2] = 2000
    entries[name] = b"\n".join(json.dumps(r).encode() for r in rows)
    with pytest.raises(BundleError):
        check(entries)


def test_valid_sensor_timestamp_lag_with_settled_neutral(entries):
    rows = [json.loads(line) for line in entries["keyframes.jsonl"].splitlines()]
    for r in rows:
        r.update(capture_time_source="captureTime", t_capture=r["t_callback"] - 80)
    entries["keyframes.jsonl"] = b"\n".join(json.dumps(r).encode() for r in rows)
    check(entries)


def test_chunked_upload_limit_is_enforced_without_content_length(tmp_settings, monkeypatch):
    monkeypatch.setattr(rest_collect, "MAX_BUNDLE_BYTES", 100)
    with TestClient(create_app(tmp_settings)) as client:
        response = client.post(
            "/api/v1/collect/bundles", headers=AUTH, content=iter([b"x" * 60, b"y" * 60])
        )
    assert response.status_code == 413
    assert not (tmp_settings.data_dir / "sessions").exists()


@pytest.mark.integration
def test_measurement_upload_flow_exact_issued_challenge_and_single_use(tmp_settings):
    with TestClient(create_app(tmp_settings)) as client:
        ready = client.get("/api/v1/collect/challenge", headers=AUTH).json()
        entries = make_entries(ready["session_id"], Challenge.model_validate(ready["challenge"]))
        response = client.post(
            "/api/v1/collect/bundles", headers=AUTH, content=pack_bundle(entries)
        )
        assert response.status_code == 200, response.text
        assert response.json()["qc"]["n_keyframes"] == 2
        assert (
            client.post(
                "/api/v1/collect/bundles", headers=AUTH, content=pack_bundle(entries)
            ).status_code
            == 409
        )


@pytest.mark.parametrize("extra", ["result.json", "server_timing.json"])
def test_client_cannot_inject_server_results(tmp_settings, entries, extra):
    entries[extra] = b"{}"
    with TestClient(create_app(tmp_settings)) as client:
        r = client.post("/api/v1/collect/bundles", headers=AUTH, content=pack_bundle(entries))
    assert r.status_code == 400 and "client cannot supply" in r.text
