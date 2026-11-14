"""Controlled synthetic signals only. Not a physical face/attack simulator or liveness evidence."""
import json

import numpy as np

from app.challenge.sequence import generate
from app.liveness.chroma_series import RegionFrame, build_series, emitted
from app.schemas import ChallengeRecord
from app.vision.decode import SRGB_TO_LINEAR
from app.vision.regions import ALL_REGIONS, RegionStat
from tests.bundle_factory import make_entries


def signal(seed=7, lag=65, noise=0.0005, gain=0.15, background_gain=0.03):
    challenge = generate()
    record = ChallengeRecord.model_validate(json.loads(make_entries("s_test", challenge)["challenge.json"]))
    t = np.arange(0, record.timing.capture_end_ms, 1000 / 30)
    drive = emitted(record, t, lag) - SRGB_TO_LINEAR[list(challenge.neutral.rgb)]
    rng = np.random.default_rng(seed)
    frames = []
    for i, stamp in enumerate(t):
        stats = {}
        for name in ALL_REGIONS:
            g = background_gain if name in ("background", "surround") else gain
            base = np.array([0.25, 0.20, 0.18])
            value = base + g * drive[i] + rng.normal(0, noise, 3)
            stats[name] = RegionStat(np.clip(value, 0, 1), 100, 0)
        frames.append(RegionFrame(float(stamp), stats, (100, 100, 200, 240), 1))
    return record, frames, build_series(frames)
