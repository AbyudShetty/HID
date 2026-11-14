"""Face region masks and per-region linear-RGB means for the chroma signal (plan §9.3).

Geometry (``d`` = inter-ocular distance, ``m`` = eye midpoint; axis-aligned in crop coordinates):
  forehead   rectangle centred at m - (0, 0.55 d), size 1.0 d x 0.35 d
  nose       disc, radius 0.18 d, centred halfway between m and the nose tip
  cheek_l/r  discs, radius 0.22 d, centred at the midpoint of the same-side eye and mouth corner, shifted outward 0.15 d
  face_core  union of the four (skin only: eyes and mouth excluded)
  surround   inside 1.6x the SCRFD face box and outside 1.25x of it (hair, ears, neck, near background)
  background the top-left / top-right corner squares (side 0.2 x crop) outside 1.6x the face box
The four skin regions are made mutually exclusive in the order nose, forehead, cheek_l, cheek_r.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .decode import SRGB_TO_LINEAR
from .scrfd import Face

SKIN_REGIONS = ("forehead", "nose", "cheek_l", "cheek_r")
ALL_REGIONS = (*SKIN_REGIONS, "face_core", "surround", "background")
CLIP_THRESHOLD = 250  # a pixel with any sRGB channel >= this is excluded from means (clipped highlight)


@dataclass(frozen=True)
class RegionGeometry:
    forehead_dy: float = 0.55
    forehead_w: float = 1.0
    forehead_h: float = 0.35
    nose_r: float = 0.18
    cheek_r: float = 0.22
    cheek_out: float = 0.15
    surround_inner: float = 1.25
    surround_outer: float = 1.6
    corner_frac: float = 0.2


def _disc(shape: tuple[int, int], cx: float, cy: float, r: float) -> np.ndarray:
    h, w = shape
    yy, xx = np.ogrid[:h, :w]
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r


def _rect(shape: tuple[int, int], cx: float, cy: float, rw: float, rh: float) -> np.ndarray:
    h, w = shape
    yy, xx = np.ogrid[:h, :w]
    return (np.abs(xx - cx) <= rw / 2) & (np.abs(yy - cy) <= rh / 2)


def _scaled_box_mask(shape: tuple[int, int], box: tuple[float, float, float, float], factor: float) -> np.ndarray:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    return _rect(shape, cx, cy, (x2 - x1) * factor, (y2 - y1) * factor)


def region_masks(shape: tuple[int, int], face: Face, geom: RegionGeometry = RegionGeometry()) -> dict[str, np.ndarray]:
    """Boolean masks (``shape`` = (H, W) of the crop) for every region in :data:`ALL_REGIONS`."""
    le, re, nose, lm, rm = (face.kps[i].astype(float) for i in range(5))
    d = float(np.linalg.norm(re - le))
    mid = (le + re) / 2
    out: dict[str, np.ndarray] = {}

    taken = np.zeros(shape, bool)
    nose_c = (mid + nose) / 2
    out["nose"] = _disc(shape, nose_c[0], nose_c[1], geom.nose_r * d)
    taken |= out["nose"]
    fore = _rect(shape, mid[0], mid[1] - geom.forehead_dy * d, geom.forehead_w * d, geom.forehead_h * d)
    out["forehead"] = fore & ~taken
    taken |= out["forehead"]
    cl = (le + lm) / 2 + np.array([-geom.cheek_out * d, 0.0])
    cr = (re + rm) / 2 + np.array([geom.cheek_out * d, 0.0])
    out["cheek_l"] = _disc(shape, cl[0], cl[1], geom.cheek_r * d) & ~taken
    taken |= out["cheek_l"]
    out["cheek_r"] = _disc(shape, cr[0], cr[1], geom.cheek_r * d) & ~taken
    out["face_core"] = out["forehead"] | out["nose"] | out["cheek_l"] | out["cheek_r"]

    outer = _scaled_box_mask(shape, face.box, geom.surround_outer)
    inner = _scaled_box_mask(shape, face.box, geom.surround_inner)
    out["surround"] = outer & ~inner

    h, w = shape
    side = int(round(geom.corner_frac * min(h, w)))
    corners = np.zeros(shape, bool)
    corners[:side, :side] = True
    corners[:side, w - side :] = True
    out["background"] = corners & ~outer
    return out


@dataclass(frozen=True)
class RegionStat:
    mean_rgb: np.ndarray | None  # linear RGB (3,), None when no usable pixel
    n_pixels: int
    clipped_frac: float


def region_stats(img_bgr: np.ndarray, masks: dict[str, np.ndarray]) -> dict[str, RegionStat]:
    """Per-region mean of **linearized** RGB over non-clipped pixels, plus the clipped fraction."""
    lin = SRGB_TO_LINEAR[img_bgr[..., ::-1]]  # (H, W, 3) linear RGB
    clipped = (img_bgr >= CLIP_THRESHOLD).any(axis=2)
    stats: dict[str, RegionStat] = {}
    for name, m in masks.items():
        n = int(m.sum())
        if n == 0:
            stats[name] = RegionStat(None, 0, 0.0)
            continue
        usable = m & ~clipped
        nu = int(usable.sum())
        stats[name] = RegionStat(lin[usable].mean(axis=0) if nu else None, nu, 1.0 - nu / n)
    return stats
