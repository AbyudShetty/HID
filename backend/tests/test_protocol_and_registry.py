"""Binary framing (plan §8.1) and model integrity checks (plan §10.1)."""
from __future__ import annotations

import hashlib
import json
import struct

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.model_registry import ModelIntegrityError, assert_no_tampering, verify_models
from app.protocol import (
    MAX_HEADER_BYTES,
    MAX_IMAGE_BYTES,
    ProtocolError,
    decode_frame,
    encode_frame,
)
from app.schemas import FrameHeader

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


@pytest.fixture()
def header(samples) -> FrameHeader:
    return FrameHeader.model_validate(samples["records"]["frame_header"])


def test_frame_round_trip(header):
    got, jpeg = decode_frame(encode_frame(header, JPEG))
    assert got == header
    assert jpeg == JPEG


def test_frame_framing_layout(header):
    buf = encode_frame(header, JPEG)
    (hlen,) = struct.unpack_from("<I", buf, 0)
    assert json.loads(buf[4 : 4 + hlen])["session_id"] == header.session_id
    assert buf[4 + hlen :] == JPEG


@pytest.mark.parametrize(
    "buf",
    [b"", b"\x01\x00", struct.pack("<I", 0) + b"x", struct.pack("<I", MAX_HEADER_BYTES + 1) + b"x" * 10],
)
def test_malformed_frames_rejected(buf):
    with pytest.raises(ProtocolError):
        decode_frame(buf)


def test_header_must_be_valid_json_and_schema(header):
    bad = b"{not json}"
    with pytest.raises(ProtocolError, match="invalid frame header"):
        decode_frame(struct.pack("<I", len(bad)) + bad + JPEG)
    incomplete = json.dumps({"session_id": "x"}).encode()
    with pytest.raises(ProtocolError, match="invalid frame header"):
        decode_frame(struct.pack("<I", len(incomplete)) + incomplete + JPEG)


def test_payload_must_be_jpeg_and_bounded(header):
    raw = json.dumps(header.model_dump(mode="json", exclude_none=True)).encode()
    pre = struct.pack("<I", len(raw)) + raw
    with pytest.raises(ProtocolError, match="not a JPEG"):
        decode_frame(pre + b"PNG data")
    with pytest.raises(ProtocolError, match="no image payload"):
        decode_frame(pre)
    with pytest.raises(ProtocolError, match="too large"):
        decode_frame(pre + JPEG + b"\x00" * MAX_IMAGE_BYTES)
    with pytest.raises(ProtocolError, match="too large"):
        encode_frame(header, JPEG + b"\x00" * MAX_IMAGE_BYTES)


def _write_manifest(models_dir, entries):
    (models_dir / "manifest.json").write_text(json.dumps({"version": 1, "models": entries}), encoding="utf-8")


def test_registry_states(tmp_path):
    good = tmp_path / "good.onnx"
    good.write_bytes(b"good-model")
    unpinned = tmp_path / "unpinned.onnx"
    unpinned.write_bytes(b"x")
    _write_manifest(
        tmp_path,
        [
            {"name": "good", "file": "good.onnx", "required": True, "sha256": hashlib.sha256(b"good-model").hexdigest()},
            {"name": "gone", "file": "gone.onnx", "required": True, "sha256": "ab" * 32},
            {"name": "unpinned", "file": "unpinned.onnx", "required": False, "sha256": ""},
        ],
    )
    st = verify_models(tmp_path)
    assert [st[k].state for k in ("good", "gone", "unpinned")] == ["ok", "missing", "unpinned"]
    assert_no_tampering(st)  # missing / unpinned are not tampering


def test_registry_detects_tampering_and_app_refuses_to_start(tmp_settings):
    models = tmp_settings.models_dir
    (models / "m.onnx").write_bytes(b"original")
    _write_manifest(models, [{"name": "m", "file": "m.onnx", "required": True, "sha256": hashlib.sha256(b"original").hexdigest()}])
    with TestClient(create_app(tmp_settings)) as client:  # intact: starts fine
        assert client.get("/api/v1/health").json()["models_loaded"] == {"m": True}
    (models / "m.onnx").write_bytes(b"tampered")
    with pytest.raises(ModelIntegrityError, match="integrity check failed"):
        assert_no_tampering(verify_models(models))
    with pytest.raises(ModelIntegrityError):
        with TestClient(create_app(tmp_settings)):
            pass


def test_committed_frame_fixture_matches_encoder(header, samples):
    """kiosk/src/net/frame.test.ts decodes this same base64 frame, so both ends are proven to agree on the bytes."""
    import base64

    assert base64.b64decode(samples["records"]["frame_sample_b64"]) == encode_frame(header, JPEG)


def test_decodes_a_header_formatted_like_the_kiosk_encoder(header):
    """JS writes whole-number floats as ints ("100" not "100.0"); the server must accept that."""
    raw = json.dumps(
        {
            "session_id": "s_test0001", "kind": "crop", "seq": 17, "t_capture": 512.3,
            "crop_box": [100, 50, 400, 400], "frame_size": [1280, 720],
            "client_face_box": [220, 140, 160, 200], "capture_time_source": "captureTime",
        },
        separators=(",", ":"),
    ).encode()
    got, jpeg = decode_frame(struct.pack("<I", len(raw)) + raw + JPEG)
    assert got == header
    assert jpeg == JPEG
