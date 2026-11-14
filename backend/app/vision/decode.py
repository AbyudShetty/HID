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


def decode_image(data: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to an HxWx3 **BGR uint8** array. Raises :class:`DecodeError` on corrupt input."""
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise DecodeError("could not decode image")
    return img


def bgr_to_linear_rgb(img_bgr: np.ndarray) -> np.ndarray:
    """uint8 BGR image -> float32 **linear RGB** (channel order R, G, B), values 0..1."""
    return SRGB_TO_LINEAR[img_bgr[..., ::-1]]


def linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    """float linear 0..1 -> float sRGB-encoded 0..1 (exact OETF)."""
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
