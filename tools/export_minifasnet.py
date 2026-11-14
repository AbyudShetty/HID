"""Export the pretrained MiniFASNet weights to ONNX and verify parity (plan §10.4, T0.4). Tooling only (needs torch).

    .venv\\Scripts\\python.exe tools\\export_minifasnet.py

Produces ``models/minifasnet_v2_2.7_80x80.onnx`` and ``models/minifasnet_v1se_4.0_80x80.onnx`` (input ``input``
1x3x80x80 float32 BGR in 0..255 — **not** divided by 255, exactly like the reference ``ToTensor`` — output ``logits`` [N,3]).
Also records PyTorch reference logits for 12 fixed crops into ``backend/tests/fixtures/minifas_parity.npz`` so the
parity test (marker ``models``) can run without torch, pins the exported hashes in ``models/manifest.json``, and writes
``experiments/E4_models/minifasnet_parity.json``.
"""
from __future__ import annotations

import json
import sys
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.minifas_src.MiniFASNet import MiniFASNetV1SE, MiniFASNetV2  # noqa: E402

MODELS = ROOT / "models"
MANIFEST = MODELS / "manifest.json"
PARITY_TOL = 1e-4
INPUT_SIZE = 80

SPECS = [
    # (manifest name, pth file, ctor, onnx file, crop scale)
    ("minifasnet_v2_onnx", "2.7_80x80_MiniFASNetV2.pth", MiniFASNetV2, "minifasnet_v2_2.7_80x80.onnx", 2.7),
    ("minifasnet_v1se_onnx", "4_0_0_80x80_MiniFASNetV1SE.pth", MiniFASNetV1SE, "minifasnet_v1se_4.0_80x80.onnx", 4.0),
]


def kernel_size(h: int, w: int) -> tuple[int, int]:
    """Reference ``utility.get_kernel``."""
    return ((h + 15) // 16, (w + 15) // 16)


def load_model(pth: Path, ctor) -> torch.nn.Module:
    model = ctor(conv6_kernel=kernel_size(INPUT_SIZE, INPUT_SIZE))
    state = torch.load(pth, map_location="cpu", weights_only=True)
    if next(iter(state)).startswith("module."):
        state = OrderedDict((k[7:], v) for k, v in state.items())
    model.load_state_dict(state)
    return model.eval()


def fixed_crops(n: int = 12, seed: int = 0) -> np.ndarray:
    """Deterministic 80x80 BGR uint8 crops cut from the three reference sample images."""
    rng = np.random.default_rng(seed)
    imgs = [cv2.imread(str(p)) for p in sorted((ROOT / "backend/tests/fixtures/minifas_samples").glob("*.jpg"))]
    if not imgs or any(i is None for i in imgs):
        raise SystemExit("reference sample images missing in backend/tests/fixtures/minifas_samples")
    crops = []
    for i in range(n):
        img = imgs[i % len(imgs)]
        side = int(rng.integers(120, 400))
        y = int(rng.integers(0, img.shape[0] - side))
        x = int(rng.integers(0, img.shape[1] - side))
        crops.append(cv2.resize(img[y : y + side, x : x + side], (INPUT_SIZE, INPUT_SIZE)))
    return np.stack(crops)


def to_batch(crops_u8: np.ndarray) -> np.ndarray:
    """uint8 NHWC BGR -> float32 NCHW, values 0..255 (the reference does NOT divide by 255)."""
    return np.ascontiguousarray(crops_u8.transpose(0, 3, 1, 2).astype(np.float32))


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_name = {m["name"]: m for m in manifest["models"]}
    crops = fixed_crops()
    batch = to_batch(crops)
    report: dict = {"torch": torch.__version__, "onnxruntime": ort.__version__, "tolerance": PARITY_TOL, "models": {}}
    fixtures: dict[str, np.ndarray] = {"crops_bgr_u8": crops}
    ok = True

    for name, pth_name, ctor, onnx_name, scale in SPECS:
        pth, onnx_path = MODELS / pth_name, MODELS / onnx_name
        if not pth.exists():
            print(f"missing {pth}; run tools/download_models.py first")
            return 2
        model = load_model(pth, ctor)
        dummy = torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE)
        torch.onnx.export(
            model,
            dummy,
            str(onnx_path),
            input_names=["input"],
            output_names=["logits"],
            dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=13,
            dynamo=False,
        )
        with torch.no_grad():
            ref = model(torch.from_numpy(batch)).numpy()
        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        out = sess.run(["logits"], {"input": batch})[0]
        diff = float(np.max(np.abs(ref - out)))
        passed = diff < PARITY_TOL
        ok &= passed
        digest = sha256(onnx_path)
        entry = by_name[name]
        entry["sha256"] = digest
        entry["size_bytes"] = onnx_path.stat().st_size
        entry["export_info"] = {
            "source_pth": pth_name,
            "source_pth_sha256": by_name[name.replace("_onnx", "_pth")]["sha256"],
            "torch": torch.__version__,
            "opset": 13,
            "preprocess": "BGR, float32, 0..255 (no /255), NCHW 1x3x80x80; real class index = 1",
            "crop_scale": scale,
        }
        fixtures[f"logits_{name}"] = ref.astype(np.float32)
        report["models"][name] = {"max_abs_logit_diff": diff, "pass": passed, "onnx_sha256": digest, "n_crops": len(crops)}
        print(f"{name}: max |torch - onnx| = {diff:.3e}  -> {'PASS' if passed else 'FAIL'}  ({onnx_path.stat().st_size / 1e6:.2f} MB)")

    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(ROOT / "backend/tests/fixtures/minifas_parity.npz", **fixtures)
    out_dir = ROOT / "experiments" / "E4_models"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "minifasnet_parity.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
