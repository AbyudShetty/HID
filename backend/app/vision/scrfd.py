"""SCRFD face detector (ONNX) with 5-point landmarks (plan §10.2).

Adapted from the InsightFace reference implementation (``insightface/model_zoo/scrfd.py``, MIT License,
Copyright (c) DeepInsight / InsightFace contributors). Reimplemented here so the project does not depend on the
``insightface`` package (plan §3.2 #7). The pretrained weights themselves are *non-commercial research only*.

Output tensor order of the ``det_10g`` / ``det_500m`` graphs was verified by inspecting the ONNX outputs
(9 outputs = scores[8,16,32], bbox deltas[8,16,32], keypoint deltas[8,16,32], 2 anchors per location): see
``tests/test_vision.py::test_scrfd_output_layout``.

Landmark order (InsightFace): left eye, right eye, nose tip, left mouth corner, right mouth corner, where "left"
is the *image* left (the subject's right eye).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .onnx_runtime import make_session

_STRIDES = (8, 16, 32)
_NUM_ANCHORS = 2


@dataclass(frozen=True)
class Face:
    box: tuple[float, float, float, float]  # x1, y1, x2, y2 in input-image pixels
    score: float
    kps: np.ndarray  # (5, 2) float32, input-image pixels

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def area(self) -> float:
        return self.width * self.height


def _distance2bbox(points: np.ndarray, d: np.ndarray) -> np.ndarray:
    return np.stack([points[:, 0] - d[:, 0], points[:, 1] - d[:, 1], points[:, 0] + d[:, 2], points[:, 1] + d[:, 3]], axis=-1)


def _distance2kps(points: np.ndarray, d: np.ndarray) -> np.ndarray:
    out = []
    for i in range(0, d.shape[1], 2):
        out.append(points[:, i % 2] + d[:, i])
        out.append(points[:, i % 2 + 1] + d[:, i + 1])
    return np.stack(out, axis=-1)


def _nms(dets: np.ndarray, iou_thresh: float) -> list[int]:
    x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(iou <= iou_thresh)[0] + 1]
    return keep


class Scrfd:
    """``detect(bgr, det_size)`` returns faces sorted by descending score, in input-image coordinates."""

    def __init__(self, model_path: Path | str, intra_op_threads: int = 0, score_thresh: float = 0.5, nms_thresh: float = 0.4):
        self.session = make_session(model_path, intra_op_threads)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        if len(self.output_names) != 9:
            raise ValueError(f"unexpected SCRFD output count {len(self.output_names)} (expected 9: scores/boxes/kps x 3 strides)")
        self.score_thresh = score_thresh
        self.nms_thresh = nms_thresh
        self._anchor_cache: dict[tuple[int, int, int], np.ndarray] = {}

    # -- steps kept separate for testing (plan §10.1) ---------------------------------------------
    @staticmethod
    def preprocess(bgr: np.ndarray, det_size: int) -> tuple[np.ndarray, float]:
        """Letterbox into a det_size x det_size canvas (top-left aligned) and normalise: (x-127.5)/128, BGR->RGB."""
        h, w = bgr.shape[:2]
        ratio = h / w
        if ratio > 1.0:
            new_h, new_w = det_size, int(round(det_size / ratio))
        else:
            new_w, new_h = det_size, int(round(det_size * ratio))
        scale = new_h / h
        resized = cv2.resize(bgr, (new_w, new_h))
        canvas = np.zeros((det_size, det_size, 3), np.uint8)
        canvas[:new_h, :new_w] = resized
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128.0, (det_size, det_size), (127.5, 127.5, 127.5), swapRB=True)
        return blob, scale

    def _anchors(self, h: int, w: int, stride: int) -> np.ndarray:
        key = (h, w, stride)
        if key not in self._anchor_cache:
            centers = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32) * stride
            centers = centers.reshape(-1, 2)
            self._anchor_cache[key] = np.stack([centers] * _NUM_ANCHORS, axis=1).reshape(-1, 2)
        return self._anchor_cache[key]

    def infer(self, blob: np.ndarray) -> list[np.ndarray]:
        return self.session.run(self.output_names, {self.input_name: blob})

    def postprocess(self, outs: list[np.ndarray], det_size: int, scale: float) -> list[Face]:
        fmc = len(_STRIDES)
        scores_l, boxes_l, kps_l = [], [], []
        for idx, stride in enumerate(_STRIDES):
            scores = outs[idx].reshape(-1)
            bbox_preds = outs[idx + fmc].reshape(-1, 4) * stride
            kps_preds = outs[idx + 2 * fmc].reshape(-1, 10) * stride
            g = det_size // stride
            anchors = self._anchors(g, g, stride)
            pos = np.where(scores >= self.score_thresh)[0]
            if pos.size == 0:
                continue
            scores_l.append(scores[pos])
            boxes_l.append(_distance2bbox(anchors, bbox_preds)[pos])
            kps_l.append(_distance2kps(anchors, kps_preds)[pos].reshape(-1, 5, 2))
        if not scores_l:
            return []
        scores_a = np.concatenate(scores_l)
        boxes_a = np.concatenate(boxes_l) / scale
        kps_a = np.concatenate(kps_l) / scale
        dets = np.hstack([boxes_a, scores_a[:, None]]).astype(np.float32)
        keep = _nms(dets, self.nms_thresh)
        faces = [Face(tuple(map(float, dets[i, :4])), float(dets[i, 4]), kps_a[i].astype(np.float32)) for i in keep]
        faces.sort(key=lambda f: -f.score)
        return faces

    def detect(self, bgr: np.ndarray, det_size: int = 640) -> list[Face]:
        if det_size % 32 != 0:
            raise ValueError("det_size must be a multiple of 32")
        blob, scale = self.preprocess(bgr, det_size)
        return self.postprocess(self.infer(blob), det_size, scale)
