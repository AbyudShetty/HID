"""Bounded operator instrument. Images are transient unless explicitly collected.

The ASGI routes run this CPU work in a thread. One lock per runtime prevents an
unbounded inference backlog. No embeddings, classification or access decisions.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from time import perf_counter

import cv2
import numpy as np

from ..liveness.chroma_features import FeatureConfig, extract_features
from ..liveness.chroma_series import RegionFrame, build_series, emitted
from ..model_registry import sha256_file
from ..vision.decode import DecodeError, decode_image
from ..vision.regions import region_masks, region_stats
from ..vision.scrfd import Scrfd
from .measurement import validate_measurement


class InstrumentBusy(RuntimeError):
    pass


class InstrumentUnavailable(RuntimeError):
    pass


def ms(start: float) -> float:
    return (perf_counter() - start) * 1000


class ChromaInstrument:
    def __init__(self, settings, statuses, policy):
        self.settings, self.statuses, self.policy = settings, statuses, policy
        self.detector = None
        self.lock = threading.Lock()

    @contextmanager
    def acquired(self):
        if not self.lock.acquire(blocking=False):
            raise InstrumentBusy("vision instrument busy; retry after current processing completes")
        try:
            yield
        finally:
            self.lock.release()

    def admit(self) -> None:
        """Cheap pre-flight used before a one-time challenge is consumed: not busy, model loadable."""
        if self.lock.locked():
            raise InstrumentBusy("vision instrument busy; retry after current processing completes")
        self.load()

    def load(self):
        if self.detector is not None:
            return
        status = self.statuses.get("scrfd_det_10g")
        if status is None or not status.ok:
            raise InstrumentUnavailable("SCRFD det_10g missing or unverified; provision pinned models")
        path = self.settings.models_dir / status.file
        if sha256_file(path) != status.sha256_expected:
            raise InstrumentUnavailable("SCRFD integrity verification failed before loading")
        try:
            self.detector = Scrfd(path, intra_op_threads=2)
        except Exception as exc:
            raise InstrumentUnavailable("SCRFD initialization failed; inspect server log/model runtime") from exc

    def observe(self, data: bytes, *, crop: bool, outlines: bool = True) -> tuple[dict, dict, object]:
        started = perf_counter()
        image = decode_image(data, max_side=512 if crop else 1280, max_pixels=512 ** 2 if crop else 1280 ** 2)
        td = ms(started)
        h, w = image.shape[:2]
        start = perf_counter()
        blob, scale = self.detector.preprocess(image, 320 if crop else 640)
        tp = ms(start)
        start = perf_counter()
        outputs = self.detector.infer(blob)
        ti = ms(start)
        start = perf_counter()
        faces = self.detector.postprocess(outputs, 320 if crop else 640, scale)
        significant = []
        if faces:
            primary = max(faces, key=lambda f: f.area)
            significant = [f for f in faces if f.area >= primary.area * self.policy.value("quality.secondary_face_ratio")]
        face = max(significant, key=lambda f: f.area) if significant else None
        tpost = ms(start)
        start = perf_counter()
        masks = region_masks((h, w), face) if face is not None else {}
        stats = region_stats(image, masks)
        regions = {}
        for name, stat in stats.items():
            paths = []
            if outlines:
                contours, _ = cv2.findContours(masks[name].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                paths = [cv2.approxPolyDP(c, 1, True).reshape(-1, 2).tolist() for c in contours]
            regions[name] = {"mean_rgb": None if stat.mean_rgb is None else stat.mean_rgb.tolist(),
                             "pixels": stat.n_pixels, "clipped_fraction": stat.clipped_frac, "paths": paths}
        tr = ms(start)
        return {"image_size": [w, h], "face": None if face is None else {"box": face.box, "score": face.score, "landmarks": face.kps.tolist()},
                "significant_faces": len(significant), "regions": regions,
                "timings_ms": {"decode": td, "preprocess": tp, "scrfd_inference": ti, "postprocess": tpost,
                               "regions": tr, "total": ms(started)}}, stats, face

    def preview(self, data: bytes) -> dict:
        with self.acquired():
            start = perf_counter()
            self.load()
            load_ms = ms(start)
            report, _, _ = self.observe(data, crop=False)
            report.update(model="scrfd_det_10g", model_load_ms=load_ms, experimental=True,
                          passive={"status": "not_implemented", "reason": "MiniFASNet exports verified; serving wrapper not implemented"})
            return report

    def analyze(self, bundle, entries, challenge_config) -> dict:
        validate_measurement(bundle, challenge_config)
        with self.acquired():
            started = perf_counter()
            self.load()
            load_ms = ms(started)
            observations, frames = [], []
            for row in bundle.frames:
                try:
                    item, stats, face = self.observe(entries[row.file], crop=True)
                except DecodeError as exc:
                    raise DecodeError(f"{row.file}: {exc}") from exc
                x, y, cw, ch = row.crop_box
                w, h = item["image_size"]
                native = None if face is None else (x + face.box[0] * cw / w, y + face.box[1] * ch / h,
                                                    x + face.box[2] * cw / w, y + face.box[3] * ch / h)
                frames.append(RegionFrame(row.t_capture, stats, native, item["significant_faces"]))
                item.update(seq=row.seq, file=row.file, t_ms=row.t_capture,
                            callback_delay_ms=row.t_callback - row.t_capture, capture_time_source=row.capture_time_source)
                observations.append(item)
            start = perf_counter()
            series = build_series(frames)
            p = self.policy
            cfg = FeatureConfig(min_snr=p.value("chroma.min_snr"), min_frames_frac=p.value("quality.min_frames_frac"),
                                max_motion_frac=p.value("quality.max_motion_frac"), max_clipped_frac=p.value("quality.max_clipped_frac"))
            result = extract_features(series, bundle.challenge, cfg)
            feature_ms = ms(start)
            result["warnings"].extend(["EXPOSURE_AND_WHITE_BALANCE_NOT_PHYSICALLY_VALIDATED", "NO_CAMERA_PROFILE_CALIBRATION"])
            end_settings = bundle.meta.camera_settings_end
            changed = [k for k in ("exposureMode", "exposureTime", "whiteBalanceMode", "colorTemperature")
                       if end_settings is not None and bundle.meta.camera.settings.get(k) != end_settings.get(k)]
            if changed:
                result["status"] = "unavailable"
                result["reasons"].append("CAMERA_SETTINGS_CHANGED:" + ",".join(changed))
            result.update(session_id=bundle.session_id, observations=observations,
                          emitted=emitted(bundle.challenge, series.t).tolist(),
                          displayed=[d.model_dump(mode="json") for d in bundle.challenge.displayed],
                          timing=bundle.challenge.timing.model_dump(mode="json"),
                          neutral_keyframes=[k.file for k in bundle.keyframes],
                          passive={"status": "not_implemented"}, identity={"status": "not_implemented"},
                          timing_summary_ms={"model_load": load_ms, "feature_extraction": feature_ms,
                                             "frames_total": sum(o["timings_ms"]["total"] for o in observations),
                                             "backend_total": ms(started)},
                          provenance={"detector": "scrfd_det_10g", "sha256": self.statuses.get("scrfd_det_10g").sha256_actual,
                                      "crop_detector_size": 320, "threads": 2, "policy_version": p.version,
                                      "thresholds_provisional": p.provisional, "settle_ms": 33})
            return result
