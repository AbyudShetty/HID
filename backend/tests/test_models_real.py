"""Tests that need the real model files in ./models (marker ``models``; plan §18.1)."""
from __future__ import annotations

import numpy as np
import onnxruntime as ort
import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.main import create_app
from app.model_registry import verify_models

pytestmark = pytest.mark.models

MODELS = REPO_ROOT / "models"
FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "minifas_parity.npz"


def test_all_required_models_present_and_pinned():
    statuses = verify_models(MODELS)
    required = {n: s for n, s in statuses.items() if s.required}
    assert required, "manifest lists no required models"
    bad = {n: s.state for n, s in required.items() if not s.ok}
    assert not bad, f"required models not ok: {bad}"


def test_health_reports_ok_with_real_models():
    settings = Settings(models_dir=MODELS, kiosk_token="k", operator_token="o", _env_file=None)
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert all(body["models_loaded"][n] for n in ("scrfd_det_10g", "arcface_w600k_r50", "minifasnet_v2_onnx", "minifasnet_v1se_onnx"))


@pytest.mark.parametrize("name", ["minifasnet_v2_onnx", "minifasnet_v1se_onnx"])
def test_minifasnet_onnx_matches_recorded_pytorch_logits(name):
    data = np.load(FIXTURE)
    crops = data["crops_bgr_u8"]  # uint8 NHWC BGR
    batch = np.ascontiguousarray(crops.transpose(0, 3, 1, 2).astype(np.float32))  # 0..255, NOT divided by 255
    entry = {s.name: s for s in verify_models(MODELS).values()}[name]
    sess = ort.InferenceSession(str(MODELS / entry.file), providers=["CPUExecutionProvider"])
    out = sess.run(["logits"], {"input": batch})[0]
    assert out.shape == (len(crops), 3)
    assert float(np.max(np.abs(out - data[f"logits_{name}"]))) < 1e-4
