"""JPEG decode and colour-space helpers (plan §9.3). All colour measurements use *linearized* sRGB."""
from __future__ import annotations

import cv2
import numpy as np

# Exact sRGB EOTF lookup table for 8-bit values.
_c = np.arange(256, dtype=np.float64) / 255.0
SRGB_TO_LINEAR = np.where(_c <= 0.04045, _c / 12.92, ((_c + 0.055) / 1.055) ** 2.4).astype(np.float32)
del _c


class DecodeError(ValueError):
    pass


def image_size(data: bytes) -> tuple[int, int]:
    """Read supported image dimensions before asking OpenCV to allocate pixels."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i < len(data):
            if data[i] != 255:
                break
            while i < len(data) and data[i] == 255:
                i += 1
            if i >= len(data):
                break
            marker = data[i]
            i += 1
            if marker in (0xDA, 0xD9):
                break
            if marker in (0x01, *range(0xD0, 0xD9)):
                continue
            if i + 2 > len(data):
                break
            length = int.from_bytes(data[i:i + 2], "big")
            if length < 2 or i + length > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2):
                if length < 8:
                    break
                return int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 3:i + 5], "big")
            i += length
    raise DecodeError("missing or unsupported JPEG/PNG dimensions")


def decode_image(data: bytes, *, max_side: int = 1920, max_pixels: int = 1920 * 1280) -> np.ndarray:
    """Decode JPEG/PNG bytes to an HxWx3 **BGR uint8** array. Raises :class:`DecodeError` on corrupt input."""
    w, h = image_size(data)
    if not 1 <= w <= max_side or not 1 <= h <= max_side or w * h > max_pixels:
        raise DecodeError("image dimensions exceed processing limits")
    arr = np.frombuffer(data, np.uint8)
    try:
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    except cv2.error as exc:
        raise DecodeError("could not decode image") from exc
    if img is None:
        raise DecodeError("could not decode image")
    if img.shape[:2] != (h, w):
        raise DecodeError("decoded image dimensions differ from header")
    return img


def bgr_to_linear_rgb(img_bgr: np.ndarray) -> np.ndarray:
    """uint8 BGR image -> float32 **linear RGB** (channel order R, G, B), values 0..1."""
    return SRGB_TO_LINEAR[img_bgr[..., ::-1]]


def linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    """float linear 0..1 -> float sRGB-encoded 0..1 (exact OETF)."""
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
