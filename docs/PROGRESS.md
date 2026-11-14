# Progress

> Source of truth for *what to build* is `plan.md`. This file tracks *what is done*. Update it on every task (plan §2.2).

## Environment log

| Date | Item | Value |
|---|---|---|
| 2026-11-14 | OS | Windows 11 Home (10.0.26300), 16 logical cores (i7-13620H), 15.6 GB RAM |
| 2026-11-14 | GPU | NVIDIA GeForce RTX 4050 Laptop (not used: serving is CPU-only, plan F-06) |
| 2026-11-14 | Host Python | 3.10.0 (`C:\Program Files\Python310`); repo venvs: `.venv` (backend + tooling, headless OpenCV), `.venv-host` (camera scripts, GUI OpenCV) |
| 2026-11-14 | Node / npm | v25.2.0 / 11.19.0 |
| 2026-11-14 | Docker | CLI 29.5.3 installed; **daemon not running at session start** (see blockers) |
| 2026-11-14 | `make` | not installed; use `python tasks.py <target>` (Makefile kept in sync) |
| 2026-11-14 | Camera | "USB2.0 HD UVC WebCam" (1 device) |
| 2026-11-14 | AWS CLI / sandbox access | CLI not installed; **sandbox access code not yet provided** (HUMAN task H-01) |
| 2026-11-14 | Git | repo initialised; `origin` = https://github.com/AbyudShetty/HID.git ; **no commits made by the agent** (human handles all commits/pushes) |

## Current milestone / task

M1: **owner C1 measurement repair complete; stop for owner review/commit**. Next: C2 / T1.6 features. Architecture/dependencies approved by owner; E1/E2/G1 remain unperformed/unapproved. Working plan updated in owner-ignored `.local/plan.md`. See `C1_MEASUREMENT.md` and `CHECKPOINTS.md`.

## In progress

_(see the session log at the bottom of this file)_

## Master checklist (plan §22)

```
M0 Bootstrap
[x] T0.1 Repo + docs skeleton        [x] T0.2 Backend skeleton        [x] T0.3 Kiosk skeleton
[x] T0.4 Models download/verify/export
[ ] G0 approved   (report in docs/GATES.md, awaiting human approval)
M1 Risk spikes
[x] T1.1 Challenge generator         [x] T1.2 Capture modules + spike page   [x] T1.3 Bundle I/O
[ ] T1.4 E1 camera                   [ ] T1.5 SCRFD + regions                [ ] T1.6 Chroma features
[ ] T1.7 E2 chroma feasibility [HUMAN data]   [ ] T1.8 AWS inventory + E3   [ ] T1.9 E4 models
[ ] T1.10 G1 report   [ ] T1.11 Pitch v0 + organizer questions sent
[ ] G1 approved — outcome: ________
M2 Core offline
[ ] T2.1 Quality  [ ] T2.2 MiniFASNet  [ ] T2.3 ArcFace + LFW  [ ] T2.4 Chroma signal
[ ] T2.5 Decision engine  [ ] T2.6 Orchestrator + replay  [ ] T2.7 Eval toolkit  [ ] T2.8 Calibration scripts
[ ] G2 approved
M3 Online E2E
[ ] T3.1 Sessions  [ ] T3.2 WS server  [ ] T3.3 Online orchestrator  [ ] T3.4 Kiosk state machine
[ ] T3.5 Storage + audit  [ ] T3.6 Gallery + enrollment backend  [ ] T3.7 bench_e2e
[ ] G3 approved — p95 local: ____ ms
M4 Dev data + calibration
[ ] T4.1 Collect UI  [ ] T4.2 Materials/consent [HUMAN]  [ ] T4.3 Dev R1 [HUMAN]
[ ] T4.4 Manifest/splits  [ ] T4.5 Liveness calibration  [ ] T4.6 Identity calibration  [ ] T4.7 Dev report (headline + rigorous)
[ ] T4.8 Results story v1  [ ] T4.9 Auto-repeat rig (P1)
[ ] G4 approved
M5 Step-up + hardening
[ ] T5.1 Step-up backend  [ ] T5.2 Step-up screens  [ ] T5.3 Enrollment UX  [ ] T5.4 Rate limit
[ ] T5.5 Hardening  [ ] T5.6 Manual review  [ ] T5.7 Scenarios S1–S18
[ ] G5 approved
M6 AWS
[ ] T6.1 Image  [ ] T6.2 CloudFormation  [ ] T6.3 Deploy + bench  [ ] T6.4 Redeploy drill + edge
[ ] T6.5 AWS storage (P0 if allowed)  [ ] T6.6 Concurrency bench + SCALABILITY.md
[ ] G6 approved — p95 AWS: ____ ms, ladder rung: __, K kiosks/instance: __
M7 UI
[ ] T7.1 Evidence + Light Response + compare  [ ] T7.2 Judge dashboard  [ ] T7.3 Calibrate  [ ] T7.4 Polish
[ ] T7.5 UI acceptance  [ ] T7.6 Usability test [HUMAN]  [ ] T7.7 Presenter mode
[ ] G7 approved
M8 P1 (each: keep/drop ADR), in order
[ ] T8.1 Device detector  [ ] T8.5 Rekognition identity engine  [ ] T8.3 Head-turn  [ ] T8.4 Breakdowns  [ ] T8.2 DINOv2
M9 Freeze + test
[ ] T9.1 Red team  [ ] T9.2 Freeze (tag freeze-v1)  [ ] T9.3 Test collection [HUMAN]
[ ] T9.4 Lock + run once  [ ] T9.5 Claims list  [ ] T9.6 Slides v1 + Q&A drill #1
[ ] G9 approved
M10 Demo
[ ] T10.1 Demo script  [ ] T10.2 Model card + threat model  [ ] T10.3 Kiosk setup + venue calibration
[ ] T10.4 Backup video [HUMAN]  [ ] T10.5 Rehearsals x3 incl. mock judging [HUMAN]  [ ] T10.6 Slides final
[ ] T10.7 Q&A drill #2
[ ] G10 approved
```

## Blockers

| Date | Symptom | Attempts | Options | Asked human on |
|---|---|---|---|---|

## Latency history

| Date | Milestone | p50 | p95 | Environment |
|---|---|---|---|---|

## Session log

### 2026-11-14 — M0 bootstrap (agent)
- T0.1: repo initialised (`git init`, `origin` added; no commits made). Tree per plan §6, `.gitignore`, `Makefile` + `tasks.py`, docs skeleton. `make` is absent on this machine → ADR-002.
- T0.2: FastAPI app factory + lifespan, `GET /api/v1/health`, policy loader enforcing the §11.3 source rules, `schemas.py` with every §8 contract, `protocol.py` (binary frames), model registry (sha256, refuses to start on mismatch), auth (constant-time, fail-closed), `GET /config`, Dockerfile + compose. 46 fast tests.
- T0.3: Vite + React 18 + TS kiosk skeleton; protocol types + hand-written validators checked against the *same* JSON fixtures as pydantic; persistent WS client (hello/ping/backoff, injectable for tests); provisional-threshold banner driven by the server's `hello_ack`; unbuilt routes render "Not implemented". 15 Vitest tests + 2 live tests.
- T0.4: models downloaded + sha256 pinned (trust-on-first-use, see manifest note); MiniFASNet V2 + V1SE exported to ONNX, torch↔ONNX max |Δlogit| 5.4e-6 / 5.6e-6 (tolerance 1e-4); reference preprocessing read from source (BGR, **no /255**, real class = index 1).
- Deviations needing human review: ADR-001 (bundle upload is one binary body, not multipart, to avoid `python-multipart`), ADR-002 (task runner/venvs), ADR-003 (type-only npm packages). pytest pinned to 8.4.2 because pytest 9.2.0 crashes on Python 3.10.0 (dataclass slots bug).

### 2026-11-14 — C0 takeover review (Codex)
- Read the original plan in full, project documents/ADRs, implementation/tests/configuration, model/export files and Claude project-session history. Remote correct; `main` has no commits; existing files preserved. Only original poster accessible; both surprise photographs still needed. Source snapshot hash is recorded in `REPOSITORY_REVIEW.md`.
- Revalidated: 102 fast backend tests; 14 model tests; lint; 37 frontend tests (2 live skipped in ordinary run); TS/Vite build; all eight model hashes. Rebuilt current Docker source, healthy/provisional; separate real TS↔Docker hello/auth run: 2 passed. No `integration`-marked tests exist yet (collection exits 5); no full access flow is claimed.
- T1.1/1.2/1.3 checklist now reflects the implemented baseline reported by Claude. C1 follow-ups remain mandatory: actual rendered transition constraint, streamed upload limits and validation. T1.5 code/model tests pass; its five-bundle region-overlay manual evidence is missing, so full task acceptance remains open.
- Calculated palette/generator properties for both palettes over 10,000 seeds each. Reproduced four actual renderer transitions in 984 ms for a nominally valid challenge. Recorded E2-0 as deterministic/synthetic engineering checks, **not a real E2 experiment**. No thresholds/models changed. Reproduced source-only policy NaN acceptance in memory.
- ADR-001/003/004 accepted in engineering review; ADR-002 accepted with reproducibility amendments; ADR-005 amended/proposed because displayed timing is not enforced. Original rationale retained. New ADR-006–009 are proposed, not owner-approved.
- Updated plan §26 maps campus schedules, local fail-safe verification, signed cache, metadata audit/sync, interfaces/APIs, decision matrix, security limits, experiments/dependencies and C0–C9 acceptance checkpoints. No new library, model or framework installed.
- Corrected H-04's unsupported claim that E1 probes/report already existed. E1/E2 have not run; AWS sandbox/network and runtime model-latency evidence remain absent. `RESULTS.md` remains empty of accuracy claims.
- Owner requested stops for commits/manual verification: C0 is the next stop. Next recommended implementation is C1 (measurement foundations and T1.6), followed by tested E1 tooling and physical verification. Use the exact commands/checklist in `CHECKPOINTS.md`; no Git writes performed.
- Final checkpoint checks: source-snapshot comparison confirms all production/test/model/dependency files unchanged; only seven existing documentation files changed and two review/checkpoint documents added. Explicit local Markdown links and code fences validate; nothing is staged; secret/data/model/venv ignore rules checked. Stopped only the Docker backend created by this review (exit 0), leaving the tested image available.

### 2026-11-14 — Owner C1 measurement repair
- Start: clean working tree on owner commit `63668f9`, remote correct. The plan and original poster are now owner-private in ignored `.local/`; updated the plan there without moving/staging it. `docs/reference/` and both surprise photographs are still absent.
- Owner approved ADR-001–004, ADR-005 amendment, a lightweight independent local runtime using the shared Python engine, signed policies, SQLite cache/outbox, encrypted limited templates, strict 15-minute freshness conjunction and crypto/time-zone dependencies when needed. ADR statuses and the owner's C1–C6 sequence are recorded; no new library installed.
- Original renderer regression reproduced red (four transitions in 984 ms) then repaired. Nominal generation now reserves 80 ms inside the unchanged 1300 ms actual cap. Shared page history guards preparation entry/colors/final neutral/UI release. Hold durations from actual style application; no catch-up; stalls/interruption invalidate and restore safely. Preparation is logged separately, not excluded from any future official access-latency claim.
- V2 measurement traces and per-frame sensor/callback sources added. Recorder filters invalid/pre-lock/duplicate/future timestamps and refuses insufficient neutral keyframes. Server checks complete timing/rate/alignment while preserving exact-issued challenge and single use. Streaming body cap and rejection of client-written result/timing metadata added. Legacy fixture retained and current TS↔Python producer fixture migrated explicitly.
- Final tests: **136 fast backend**, **14 model**, **1 measurement-upload integration**, **47 frontend unit** (2 live skipped normally), **2 separate live TS↔final Docker tests** passed. Ruff, TS/Vite build, Compose config, Docker build/health/eight model hashes, and Git whitespace checks passed. Initial lint failures were corrected; no tests removed/weakened to pass.
- Browser evidence: initial simulated-camera run **9/10 accepted**, one Vite→isolated-Docker `ETIMEDOUT` on challenge request (no backend request). Repeat **10/10**; final application-completion-timestamp run **10/10**. A separate 1400 ms main-thread stall safely aborted with no upload. All 29 accepted traces revalidated server-side, each with two neutral keyframes. Capture 1208.4–1236.0 ms; request-to-idle 2528.7–2586.3 ms across iterations. **No physical liveness/identity/2 s access evidence**. First failure retained in the report.
- Published metadata-only evidence: `experiments/C1_measurement/browser_checks.json`; full explanation/limitations: `docs/C1_MEASUREMENT.md`. No real biometric dataset, raw camera material, weights or credentials included. The pre-existing owner Docker stack was untouched; review used an isolated container/port and temporary tokens.
- Stop at C1. C2/T1.6 and E1/E2 software/physical work are not marked done. Human follow-up: owner review/commit; provide surprise photographs and timing/rig/consenting-subject availability. No Git writes performed.
