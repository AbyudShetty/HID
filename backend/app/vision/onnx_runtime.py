"""Shared ONNX Runtime session factory (plan §10.1): CPU provider, configurable threads, warm-up."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort


def make_session(path: Path | str, intra_op_threads: int = 0) -> ort.InferenceSession:
    """Create a CPU ``InferenceSession``. ``intra_op_threads=0`` lets ORT choose."""
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = intra_op_threads
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.log_severity_level = 3
    return ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])


def warm_up(session: ort.InferenceSession, shape: tuple[int, ...], runs: int = 2) -> None:
    """Run the model on zeros so the first real request does not pay initialisation cost."""
    name = session.get_inputs()[0].name
    x = np.zeros(shape, np.float32)
    for _ in range(runs):
        session.run(None, {name: x})
