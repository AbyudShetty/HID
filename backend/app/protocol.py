"""Binary WebSocket frame framing (plan §8.1): ``[u32 little-endian header_len][header JSON utf-8][JPEG bytes]``.

Size limits follow plan §16.1 (header <= 2 kB, image <= 400 kB) and are enforced *before* decoding images.
"""
from __future__ import annotations

import json
import struct

from pydantic import ValidationError

from .schemas import FrameHeader

MAX_HEADER_BYTES = 2048
MAX_IMAGE_BYTES = 400 * 1024
_JPEG_SOI = b"\xff\xd8\xff"


class ProtocolError(ValueError):
    """A frame violates the wire protocol."""


def encode_frame(header: FrameHeader, jpeg: bytes) -> bytes:
    raw = json.dumps(header.model_dump(mode="json", exclude_none=True), separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_HEADER_BYTES:
        raise ProtocolError(f"header too large: {len(raw)} > {MAX_HEADER_BYTES}")
    if len(jpeg) > MAX_IMAGE_BYTES:
        raise ProtocolError(f"image too large: {len(jpeg)} > {MAX_IMAGE_BYTES}")
    return struct.pack("<I", len(raw)) + raw + jpeg


def decode_frame(buf: bytes) -> tuple[FrameHeader, bytes]:
    if len(buf) < 4:
        raise ProtocolError("frame shorter than the 4-byte length prefix")
    (hlen,) = struct.unpack_from("<I", buf, 0)
    if hlen == 0 or hlen > MAX_HEADER_BYTES:
        raise ProtocolError(f"invalid header length {hlen}")
    if len(buf) < 4 + hlen:
        raise ProtocolError("frame truncated inside the header")
    try:
        header = FrameHeader.model_validate(json.loads(buf[4 : 4 + hlen].decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ProtocolError(f"invalid frame header: {exc}") from exc
    jpeg = bytes(buf[4 + hlen :])
    if not jpeg:
        raise ProtocolError("frame has no image payload")
    if len(jpeg) > MAX_IMAGE_BYTES:
        raise ProtocolError(f"image too large: {len(jpeg)} > {MAX_IMAGE_BYTES}")
    if not jpeg.startswith(_JPEG_SOI):
        raise ProtocolError("payload is not a JPEG")
    return header, jpeg
