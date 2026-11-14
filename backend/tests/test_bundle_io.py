"""Bundle framing, validation and on-disk round trip (plan §8.5, ADR-001, T1.3)."""
from __future__ import annotations

import json
import struct

import pytest

from app.challenge.sequence import ChallengeConfig, generate
from app.pipeline.bundle_io import (
    MAX_ENTRY_BYTES,
    BundleError,
    build_bundle,
    pack_bundle,
    quality_check,
    read_bundle,
    unpack_bundle,
    valid_entry_name,
    write_bundle,
)
from tests.bundle_factory import make_entries

SID = "s_0123456789abcdef"


@pytest.fixture()
def entries():
    return make_entries(SID, generate(ChallengeConfig()))


def test_wire_round_trip(entries):
    assert unpack_bundle(pack_bundle(entries)) == entries


def test_entry_name_whitelist():
    for ok in ("meta.json", "frames.jsonl", "crops/000017.jpg", "keyframes/k0.png"):
        assert valid_entry_name(ok)
    for bad in ("../meta.json", "/etc/passwd", "crops/../x.jpg", "crops/a/b.jpg", "crops/x.exe", "other.json", "crops/.jpg", ""):
        assert not valid_entry_name(bad), bad
    with pytest.raises(BundleError, match="invalid entry name"):
        pack_bundle({"../evil": b"x"})


@pytest.mark.parametrize("cut", [1, 3, 9, 40])
def test_truncated_bodies_are_rejected(entries, cut):
    blob = pack_bundle(entries)
    with pytest.raises(BundleError):
        unpack_bundle(blob[: len(blob) - cut] if cut < len(blob) else b"")


def test_hostile_framing_is_rejected():
    name = b"meta.json"
    with pytest.raises(BundleError, match="too large"):
        unpack_bundle(struct.pack("<I", len(name)) + name + struct.pack("<I", MAX_ENTRY_BYTES + 1))
    evil = b"../meta.json"
    with pytest.raises(BundleError, match="invalid entry name"):
        unpack_bundle(struct.pack("<I", len(evil)) + evil + struct.pack("<I", 0))
    dup = struct.pack("<I", len(name)) + name + struct.pack("<I", 2) + b"{}"
    with pytest.raises(BundleError, match="duplicate"):
        unpack_bundle(dup + dup)
    with pytest.raises(BundleError, match="invalid entry name"):
        unpack_bundle(struct.pack("<I", 0))


def test_build_bundle_accepts_a_valid_bundle(entries):
    b = build_bundle(entries)
    assert b.session_id == SID
    assert b.label is not None and b.label.cls == "bona_fide"
    assert len(b.frames) >= 30 and len(b.keyframes) == 2
    assert all(name.endswith(".jpg") for name in b.files)


@pytest.mark.parametrize("missing", ["meta.json", "challenge.json", "frames.jsonl", "keyframes.jsonl"])
def test_missing_required_entries(entries, missing):
    del entries[missing]
    with pytest.raises(BundleError, match="missing required entry"):
        build_bundle(entries)


def test_corrupt_or_inconsistent_bundles_are_rejected_with_a_reason(entries):
    bad = dict(entries, **{"meta.json": b"{not json"})
    with pytest.raises(BundleError, match="meta.json is not valid JSON"):
        build_bundle(bad)

    bad = dict(entries)
    del bad["crops/000003.jpg"]
    with pytest.raises(BundleError, match="referenced file .* is missing"):
        build_bundle(bad)

    bad = dict(entries, **{"crops/extra.jpg": entries["crops/000001.jpg"]})
    with pytest.raises(BundleError, match="unreferenced image"):
        build_bundle(bad)

    bad = dict(entries, **{"crops/000002.jpg": b"not a jpeg"})
    with pytest.raises(BundleError, match="not a valid JPEG"):
        build_bundle(bad)

    meta = json.loads(entries["meta.json"])
    bad = dict(entries, **{"meta.json": json.dumps(dict(meta, session_id="../x")).encode()})
    with pytest.raises(BundleError, match="invalid session_id"):
        build_bundle(bad)

    bad = dict(entries, **{"meta.json": json.dumps(dict(meta, surprise=1)).encode()})
    with pytest.raises(BundleError, match="schema validation failed"):
        build_bundle(bad)

    rows = entries["frames.jsonl"].decode().splitlines()
    swapped = json.loads(rows[5])
    swapped["t_capture"] = -50.0
    rows[5] = json.dumps(swapped)
    with pytest.raises(BundleError, match="non-decreasing"):
        build_bundle(dict(entries, **{"frames.jsonl": "\n".join(rows).encode()}))


def test_label_is_validated_when_present(entries):
    bad_label = {"subject_id": "S1", "presenter_id": "S1", "class": "attack", "pai_family": "print",
                 "pai_species": "print_matte_a4", "consent_id": "C1"}  # attack without instrument_id
    with pytest.raises(BundleError, match="schema validation failed"):
        build_bundle(dict(entries, **{"label.json": json.dumps(bad_label).encode()}))


def test_write_then_read_round_trip_and_no_overwrite(entries, tmp_path):
    bundle = build_bundle(entries)
    path = write_bundle(bundle, entries, tmp_path)
    assert (path / "meta.json").exists() and (path / "crops" / "000000.jpg").exists()
    again = read_bundle(path)
    assert again.meta == bundle.meta
    assert again.challenge == bundle.challenge
    assert [f.model_dump() for f in again.frames] == [f.model_dump() for f in bundle.frames]
    assert again.files == bundle.files
    with pytest.raises(BundleError, match="already exists"):
        write_bundle(bundle, entries, tmp_path)
    assert not list(tmp_path.glob(".*.partial"))


def test_read_bundle_rejects_non_directories(tmp_path):
    with pytest.raises(BundleError, match="not a bundle directory"):
        read_bundle(tmp_path / "nope")


def test_quality_check_flags_short_or_slow_captures():
    challenge = generate(ChallengeConfig())
    good = quality_check(build_bundle(make_entries(SID, challenge)))
    assert good.covers_challenge and not good.warnings
    assert good.crop_fps == pytest.approx(30.0, abs=1.5)

    slow = quality_check(build_bundle(make_entries(SID, challenge, n_crops=12)))
    assert any("crop rate" in w for w in slow.warnings)


def test_wire_format_matches_the_committed_cross_language_fixture(samples):
    """kiosk/src/net/bundle.test.ts unpacks and re-packs this same base64 blob byte-for-byte."""
    import base64

    entries = {"meta.json": b'{"k":1}', "crops/000000.jpg": b"\xff\xd8\xff\xe0abc", "keyframes/k0.jpg": b"\xff\xd8\xff\xe1xyz\x00\xff"}
    assert base64.b64decode(samples["records"]["bundle_sample_b64"]) == pack_bundle(entries)
    assert list(unpack_bundle(pack_bundle(entries))) == samples["records"]["bundle_sample_names"]


def test_bundle_produced_by_the_kiosk_recorder_passes_the_real_server_validation(samples):
    """The fixture is the exact output of kiosk/src/capture/recordSession.ts (simulated camera + renderer).
    The server's build_bundle must accept it, proving the TypeScript producer and Python consumer agree."""
    import base64

    from app.pipeline.bundle_io import build_bundle, quality_check, unpack_bundle

    bundle = build_bundle(unpack_bundle(base64.b64decode(samples["records"]["ts_bundle_b64"])))
    assert bundle.session_id == "s_0123456789abcdef"
    assert bundle.label is not None and bundle.label.cls == "bona_fide"
    assert len(bundle.keyframes) == 2 and len(bundle.frames) >= 34
    assert [d.index for d in bundle.challenge.displayed] == [-1, 0, 1, 2]
    assert bundle.challenge.challenge.total_ms == 1220
    from app.pipeline.measurement import validate_measurement
    validate_measurement(bundle, ChallengeConfig())
    qc = quality_check(bundle)
    assert qc.covers_challenge and qc.crop_fps is not None and 27 < qc.crop_fps < 33
    assert not qc.warnings
