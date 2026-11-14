"""Challenge palettes (plan §9.2) and colour-science helpers. Pure functions, no randomness.

``P1`` is the plan's luminance-varying palette (stronger signal). ``P2`` is the near-isoluminant variant derived from
P1 *offline* (hue preserved; luminance matched to the neutral within ±10 %; actual deviation < 0.5 %):
  * a colour brighter than the neutral is scaled down in linear light;
  * a colour darker than the neutral is blended towards white in linear light until its relative luminance matches.
The derived integers are stored below so the palette is reproducible and reviewable; ``tests/test_challenge.py``
re-checks the ±10 % luminance property. Which palette stays is decided at gate G1 from experiment E2 (G-03).
"""
from __future__ import annotations

from dataclasses import dataclass

RGB8 = tuple[int, int, int]

NEUTRAL: RGB8 = (205, 205, 205)


def srgb_to_linear(c8: int) -> float:
    """Exact sRGB EOTF for one 8-bit channel."""
    c = c8 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_rgb(rgb: RGB8) -> tuple[float, float, float]:
    return (srgb_to_linear(rgb[0]), srgb_to_linear(rgb[1]), srgb_to_linear(rgb[2]))


def relative_luminance(rgb: RGB8) -> float:
    """WCAG relative luminance (Rec. 709 weights on linear RGB)."""
    r, g, b = linear_rgb(rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def linear_distance(a: RGB8, b: RGB8) -> float:
    """Euclidean distance between two colours in linear RGB (0 = identical, ~1.7 = black vs. white)."""
    la, lb = linear_rgb(a), linear_rgb(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb, strict=True)) ** 0.5


def red_fraction(rgb: RGB8) -> float:
    """R / (R + G + B). The plan rejects colours with a fraction >= 0.6 as 'saturated red' (stricter than WCAG's 0.8)."""
    total = sum(rgb)
    return rgb[0] / total if total else 0.0


@dataclass(frozen=True)
class Palette:
    id: str
    neutral: RGB8
    colors: tuple[RGB8, ...]


P1 = Palette(
    id="P1",
    neutral=NEUTRAL,
    colors=((80, 120, 255), (255, 235, 80), (80, 255, 255), (255, 120, 255), (120, 255, 120), (255, 175, 80)),
)

P2 = Palette(
    id="P2",
    neutral=NEUTRAL,
    colors=((194, 202, 255), (225, 207, 69), (70, 226, 226), (255, 180, 255), (108, 230, 108), (255, 193, 136)),
)

PALETTES: dict[str, Palette] = {P1.id: P1, P2.id: P2}
