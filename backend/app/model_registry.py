"""Model manifest + integrity verification (plan §10.1).

``models/manifest.json`` lists every model with its file name, SHA-256, license and source. The backend
**refuses to start** when a model file is present but its hash does not match the pinned value (tampering
or a silent swap). A missing file is reported as ``missing`` (health = degraded), not as an error, so the
container can start before models are provisioned.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ModelState = Literal["ok", "missing", "hash_mismatch", "unpinned"]


class ModelIntegrityError(RuntimeError):
    """A model file does not match the SHA-256 pinned in the manifest."""


@dataclass(frozen=True)
class ModelStatus:
    name: str
    file: str
    required: bool
    state: ModelState
    sha256_expected: str | None
    sha256_actual: str | None
    license: str
    version: str

    @property
    def ok(self) -> bool:
        return self.state == "ok"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def load_manifest(models_dir: Path) -> dict:
    path = models_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"model manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_models(models_dir: Path) -> dict[str, ModelStatus]:
    """Check every manifest entry against the files in ``models_dir``."""
    manifest = load_manifest(models_dir)
    out: dict[str, ModelStatus] = {}
    for entry in manifest["models"]:
        path = models_dir / entry["file"]
        expected = entry.get("sha256") or None
        actual: str | None = None
        if not path.exists():
            state: ModelState = "missing"
        else:
            actual = sha256_file(path)
            if expected is None:
                state = "unpinned"
            elif actual != expected:
                state = "hash_mismatch"
            else:
                state = "ok"
        out[entry["name"]] = ModelStatus(
            name=entry["name"],
            file=entry["file"],
            required=bool(entry.get("required", False)),
            state=state,
            sha256_expected=expected,
            sha256_actual=actual,
            license=entry.get("license", ""),
            version=entry.get("version", ""),
        )
    return out


def assert_no_tampering(statuses: dict[str, ModelStatus]) -> None:
    bad = [s for s in statuses.values() if s.state == "hash_mismatch"]
    if bad:
        detail = "; ".join(f"{s.name} ({s.file}): expected {s.sha256_expected}, got {s.sha256_actual}" for s in bad)
        raise ModelIntegrityError(f"model integrity check failed: {detail}")
