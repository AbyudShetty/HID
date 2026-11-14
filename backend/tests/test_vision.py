"""Vision core: decode/linearization, region masks, SCRFD (plan §18.2 Vision, T1.5)."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.config import REPO_ROOT
from app.vision.decode import (
    SRGB_TO_LINEAR,
    DecodeError,
    bgr_to_linear_rgb,
    decode_image,
    linear_to_srgb,
)
from app.vision.regions import ALL_REGIONS, SKIN_REGIONS, region_masks, region_stats
from app.vision.scrfd import Face, Scrfd

SAMPLES = REPO_ROOT / "backend" / "tests" / "fixtures" / "minifas_samples"
MODELS = REPO_ROOT / "models"


# ---------------------------------------------------------------- decode / colour space (no models)
def test_srgb_lut_known_values():
    assert SRGB_TO_LINEAR[0] == 0.0
    assert SRGB_TO_LINEAR[255] == pytest.approx(1.0)
    assert SRGB_TO_LINEAR[128] == pytest.approx(0.2158605, abs=1e-6)
    assert SRGB_TO_LINEAR[10] == pytest.approx(10 / 255 / 12.92, abs=1e-6)  # linear toe


def test_bgr_to_linear_rgb_swaps_channels():
    px = np.array([[[0, 0, 255]]], np.uint8)  # pure red in BGR
    assert bgr_to_linear_rgb(px)[0, 0].tolist() == [1.0, 0.0, 0.0]


def test_linear_to_srgb_inverts_the_lut():
    for v in (0, 1, 10, 50, 128, 200, 255):
        assert linear_to_srgb(SRGB_TO_LINEAR[v]) * 255 == pytest.approx(v, abs=1e-3)


def test_decode_image_round_trip_and_errors():
    img = np.full((8, 8, 3), (10, 120, 240), np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    assert np.array_equal(decode_image(buf.tobytes()), img)
    with pytest.raises(DecodeError):
        decode_image(b"definitely not an image")


# ---------------------------------------------------------------- region masks (synthetic faces, no models)
def synthetic_face(size: int = 256, scale: float = 1.0) -> tuple[Face, tuple[int, int]]:
    c = size / 2
    d = 60 * scale
    kps = np.array(
        [[c - d / 2, c - 0.2 * d], [c + d / 2, c - 0.2 * d], [c, c + 0.15 * d], [c - 0.4 * d, c + 0.55 * d], [c + 0.4 * d, c + 0.55 * d]],
        np.float32,
    )
    box = (c - 0.9 * d, c - 1.0 * d, c + 0.9 * d, c + 1.3 * d)
    return Face(box, 0.99, kps), (size, size)


def test_masks_are_inside_the_crop_and_skin_regions_are_exclusive():
    face, shape = synthetic_face()
    m = region_masks(shape, face)
    assert set(m) == set(ALL_REGIONS)
    assert all(v.shape == shape and v.dtype == bool for v in m.values())
    for i, a in enumerate(SKIN_REGIONS):
        assert m[a].any(), a
        for b in SKIN_REGIONS[i + 1 :]:
            assert not (m[a] & m[b]).any(), (a, b)
    assert np.array_equal(m["face_core"], m["forehead"] | m["nose"] | m["cheek_l"] | m["cheek_r"])


def test_skin_surround_and_background_are_disjoint():
    face, shape = synthetic_face()
    m = region_masks(shape, face)
    assert not (m["face_core"] & m["surround"]).any()
    assert not (m["face_core"] & m["background"]).any()
    assert not (m["surround"] & m["background"]).any()
    assert m["surround"].any() and m["background"].any()


def test_background_is_only_the_top_corners():
    face, shape = synthetic_face()
    bg = region_masks(shape, face)["background"]
    ys, xs = np.nonzero(bg)
    assert ys.max() < 0.2 * shape[0] + 1
    assert (xs < 0.2 * shape[1] + 1).any() and (xs > shape[1] - 0.2 * shape[1] - 2).any()


def test_regions_scale_with_the_inter_ocular_distance():
    small, shape = synthetic_face(scale=0.7)
    big, _ = synthetic_face(scale=1.3)
    ms, mb = region_masks(shape, small), region_masks(shape, big)
    assert mb["face_core"].sum() > 2.0 * ms["face_core"].sum()


def test_region_stats_mean_clipping_and_empty():
    face, shape = synthetic_face()
    m = region_masks(shape, face)
    img = np.full((*shape, 3), (40, 90, 160), np.uint8)  # BGR
    st = region_stats(img, m)
    expect = SRGB_TO_LINEAR[[160, 90, 40]]  # linear RGB
    for name in ("face_core", "nose", "surround"):
        assert st[name].mean_rgb == pytest.approx(expect, rel=1e-3)
        assert st[name].clipped_frac == 0.0

    img2 = img.copy()
    ys, xs = np.nonzero(m["nose"])
    half = len(ys) // 2
    img2[ys[:half], xs[:half]] = 255  # clip half of the nose pixels
    st2 = region_stats(img2, m)
    assert st2["nose"].clipped_frac == pytest.approx(half / len(ys), abs=1e-6)
    assert st2["nose"].mean_rgb == pytest.approx(expect, rel=1e-3)  # clipped pixels are excluded, not averaged in

    img3 = img.copy()
    img3[m["nose"]] = 255
    assert region_stats(img3, m)["nose"].mean_rgb is None  # nothing usable

    empty = {"x": np.zeros(shape, bool)}
    assert region_stats(img, empty)["x"] == region_stats(img, empty)["x"]
    assert region_stats(img, empty)["x"].n_pixels == 0


# ---------------------------------------------------------------- SCRFD (needs models)
@pytest.fixture(scope="module")
def det():
    return Scrfd(MODELS / "det_10g.onnx")


def load(name: str) -> np.ndarray:
    img = cv2.imread(str(SAMPLES / f"{name}.jpg"))
    assert img is not None
    return img


@pytest.mark.models
def test_scrfd_output_layout(det):
    """9 outputs = scores/boxes/kps for strides 8/16/32 with 2 anchors per location (plan §10.2)."""
    for size in (256, 640):
        blob, _ = det.preprocess(np.zeros((480, 640, 3), np.uint8), size)
        assert blob.shape == (1, 3, size, size)
        outs = det.infer(blob)
        assert len(outs) == 9
        for k, stride in enumerate((8, 16, 32)):
            n = 2 * (size // stride) ** 2
            assert outs[k].shape == (n, 1)
            assert outs[k + 3].shape == (n, 4)
            assert outs[k + 6].shape == (n, 10)


@pytest.mark.models
@pytest.mark.parametrize("name", ["image_T1", "image_F1", "image_F2"])
@pytest.mark.parametrize("size", [640, 256])
def test_scrfd_finds_the_face_with_plausible_landmarks(det, name, size):
    faces = det.detect(load(name), size)
    assert len(faces) == 1
    f = faces[0]
    assert f.score > 0.6
    le, re, nose, lm, rm = f.kps
    assert le[0] < re[0]  # image-left eye first
    tol = 0.3 * (re[0] - le[0])  # tolerate non-frontal faces (printed/screen samples are slightly turned)
    assert le[0] - tol < nose[0] < re[0] + tol
    assert max(le[1], re[1]) < nose[1] < min(lm[1], rm[1])  # eyes above nose above mouth
    assert lm[0] < rm[0]
    x1, y1, x2, y2 = f.box
    assert all(x1 <= x <= x2 and y1 <= y <= y2 for x, y in f.kps)  # landmarks inside the box


@pytest.mark.models
def test_scrfd_boxes_agree_between_detection_sizes(det):
    img = load("image_T1")
    a, b = det.detect(img, 640)[0], det.detect(img, 256)[0]
    ix = max(0.0, min(a.box[2], b.box[2]) - max(a.box[0], b.box[0]))
    iy = max(0.0, min(a.box[3], b.box[3]) - max(a.box[1], b.box[1]))
    iou = ix * iy / (a.area + b.area - ix * iy)
    assert iou > 0.85


@pytest.mark.models
def test_scrfd_returns_nothing_on_blank_images(det):
    assert det.detect(np.zeros((480, 640, 3), np.uint8), 640) == []
    assert det.detect(np.full((480, 640, 3), 127, np.uint8), 256) == []
    noise = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    assert det.detect(noise, 640) == []


@pytest.mark.models
def test_scrfd_rejects_bad_det_size(det):
    with pytest.raises(ValueError, match="multiple of 32"):
        det.detect(load("image_T1"), 250)
