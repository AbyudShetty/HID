"""Decoder bounds: oversized/malformed headers are rejected before OpenCV allocates pixels."""
from __future__ import annotations

import struct
import zlib

import cv2
import numpy as np
import pytest

from app.vision.decode import DecodeError, decode_image, image_size


def png(w: int, h: int, real_pixels: bool = False) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00" * (w * 3) for _ in range(h)) if real_pixels else zlib.compress(b"")
    idat = zlib.compress(raw) if real_pixels else raw
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def test_valid_images_round_trip_and_report_size():
    ok, buf = cv2.imencode(".jpg", np.full((40, 60, 3), 90, np.uint8))
    assert image_size(buf.tobytes()) == (60, 40)
    assert decode_image(buf.tobytes()).shape == (40, 60, 3)
    assert image_size(png(8, 4, True)) == (8, 4)


def test_oversized_png_header_is_rejected_without_decoding():
    bomb = png(60000, 60000)  # tiny file claiming 3.6 gigapixels
    assert len(bomb) < 200
    with pytest.raises(DecodeError, match="exceed"):
        decode_image(bomb)


def test_per_call_limits_apply():
    ok, buf = cv2.imencode(".jpg", np.zeros((300, 300, 3), np.uint8))
    with pytest.raises(DecodeError, match="exceed"):
        decode_image(buf.tobytes(), max_side=256, max_pixels=256 * 256)
    assert decode_image(buf.tobytes(), max_side=512, max_pixels=512 * 512).shape[:2] == (300, 300)


@pytest.mark.parametrize("data", [b"", b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF89a....", b"\xff\xd8\xff\xe0" + b"\x00" * 10])
def test_truncated_or_unsupported_data_is_rejected(data):
    with pytest.raises(DecodeError):
        decode_image(data)


def test_truncated_jpeg_body_is_rejected():
    ok, buf = cv2.imencode(".jpg", np.random.default_rng(0).integers(0, 255, (64, 64, 3), dtype=np.uint8))
    with pytest.raises(DecodeError):
        decode_image(buf.tobytes()[:60])
