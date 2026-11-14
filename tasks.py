"""Cross-platform task runner mirroring the Makefile targets (plan §18.1).

Usage:  python tasks.py test | test-models | test-integration | kiosk-test | lint | bench | up | down | all
Uses the repo venv (.venv) when present, otherwise the current interpreter.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _py() -> str:
    for cand in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if cand.exists():
            return str(cand)
    return sys.executable


def _run(cmd: list[str], cwd: Path = ROOT) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=cwd, shell=(os.name == "nt" and cmd[0] == "npm"))


TARGETS = {
    "test": lambda: _run([_py(), "-m", "pytest", "backend/tests", "-m", "not models and not integration", "-q"]),
    "test-models": lambda: _run([_py(), "-m", "pytest", "backend/tests", "-m", "models", "-q"]),
    "test-integration": lambda: _run([_py(), "-m", "pytest", "backend/tests", "-m", "integration", "-q"]),
    "kiosk-test": lambda: _run(["npm", "test"], ROOT / "kiosk"),
    "lint": lambda: _run([_py(), "-m", "ruff", "check", "backend", "eval", "tools", "experiments"]),
    "bench": lambda: _run([_py(), "tools/bench_e2e.py"]),
    "up": lambda: _run(["docker", "compose", "up", "--build", "-d"]),
    "down": lambda: _run(["docker", "compose", "down"]),
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {*TARGETS, "all"}:
        print(__doc__)
        return 2
    if sys.argv[1] == "all":
        rc = 0
        for name in ("lint", "test", "kiosk-test"):
            rc = rc or TARGETS[name]()
        return rc
    return TARGETS[sys.argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main())
