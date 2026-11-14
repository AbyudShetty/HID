# HID Face Liveness + Authentication Kiosk

A prototype targeting an access decision **within 2 seconds**, combining physical liveness (screen-light "Chroma-Challenge" + passive texture), identity and campus authorization, with safe offline behavior. Intended outcomes: **Allow / Request Additional Verification / Deny**. Built for the HID Hackathon 2026; AWS deployment remains planned and permission-dependent.

The owner's working plan is `.local/plan.md` (private/ignored in the current layout). Public implementation progress lives in `docs/PROGRESS.md`; approved decisions in `docs/DECISIONS.md`; measurements in `docs/EXPERIMENTS.md`; gate reports in `docs/GATES.md`.

> Status: Milestones M0–M1 (bootstrap + risk experiments) in progress. The screen-light approach is **unproven until experiment E2 passes** (see `docs/EXPERIMENTS.md`). No accuracy numbers are claimed anywhere in this repository without provenance.

Current checkpoint: [C1 measurement repair](docs/C1_MEASUREMENT.md), [approved architecture decisions](docs/DECISIONS.md), [owner checkpoints and Git commands](docs/CHECKPOINTS.md). The renderer timing defect is repaired with regression and simulated-camera browser evidence. Chroma features, actual access decisions and campus/offline features remain to implement. E1/E2 remain unperformed; architecture approval is not empirical validation.

## Quick start (Windows dev machine)

```powershell
# one-time
python -m venv .venv ; .venv\Scripts\python -m pip install -e backend[dev]      # backend + tests
python tools\download_models.py                                                # SCRFD / ArcFace / MiniFASNet (sha256-verified)
.venv\Scripts\python tools\export_minifasnet.py                                # needs torch (tooling): ONNX export + parity check
cd kiosk ; npm install ; cd ..

# run
$env:KIOSK_TOKEN="dev-kiosk"; $env:OPERATOR_TOKEN="dev-operator"
.venv\Scripts\python -m uvicorn app.main:get_app --factory --app-dir backend --port 8000   # or: docker compose up --build
cd kiosk ; npm run dev                                                                      # http://localhost:5173/ops
```

Set `VITE_KIOSK_TOKEN` (see `kiosk/.env.example`) so the kiosk can authenticate its WebSocket.

The export command is an explicit model-writing operation, not a routine smoke check: existing exported weights and manifest hashes are already present on the original machine and must not be casually regenerated/re-pinned. For verification use `.venv\Scripts\python tools\download_models.py --check` and `python tasks.py test-models`. Fresh host/export setup manifests still need completion (ADR-002); the quick start above is not yet a fully locked environment recipe.

## Tests (`make` targets, or `python tasks.py <target>` where `make` is missing)

| Target | What |
|---|---|
| `test` | fast backend unit tests (no model files) |
| `test-models` | tests needing the real models in `./models` |
| `test-integration` | in-process end-to-end tests |
| `kiosk-test` | Vitest (`cd kiosk && npm test`) |
| `lint` | ruff |
| `bench` | end-to-end latency bench (from M3) |

Live client/server check (real TypeScript client vs. a running backend):
`cd kiosk && LIVE_WS_URL=ws://127.0.0.1:8000/api/v1/kiosk/ws LIVE_KIOSK_TOKEN=<token> npx vitest run src/net/live.test.ts`

## Layout

See plan §6. Key folders: `backend/` (FastAPI, vision, liveness, identity, decision), `kiosk/` (React kiosk + operator UI), `eval/` (metrics, splits, locked test), `tools/` (model download/export, benchmarks, camera probes), `experiments/` (E1–E4), `infra/` (Docker, CloudFormation), `docs/`.

## Rules worth knowing

- Models and data are never committed (`models/*.onnx`, `data/`, `.env` are gitignored). `models/manifest.json` pins SHA-256 hashes; the backend refuses to start on a mismatch.
- Every threshold in `backend/config/policy.yaml` carries a `source`. While any is provisional/uncalibrated the operator UI shows **PROVISIONAL THRESHOLDS** and identity can never ALLOW until its thresholds are calibrated.
- Model licenses: InsightFace weights are non-commercial research only; MiniFASNet is Apache-2.0. See `models/manifest.json`.
