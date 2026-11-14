# Repository takeover review — 2026-11-14

Review checkpoint, before feature implementation. Owner: Abyud; engineering review: Codex.
No commits, staging, pushes, resets, history changes, model exports, or data deletion performed.

Historical C0 report. The owner subsequently committed `63668f9`, approved the implementation direction and moved the plan/original poster into ignored `.local/`. Current C1 status and repaired findings are in `C1_MEASUREMENT.md`; the original observations below describe the reviewed baseline.

## Sources and provenance

- Read all 2,070 original lines of `plan.md`, all five ADRs, gates, human tasks, progress, experiments, results, consent/setup documents, backend/frontend source and tests, task/config files, Docker files, model manifest/download/export tools and vendored model definition.
- Inspected Claude's project conversation at `C:/Users/abyud/.claude/projects/C--ABYUD-HACKATHONS-HID/72b9fdde-caf7-497e-ae1c-be0fce34261f.jsonl`. Its final report agrees with the implemented task list. Historical tool records corroborate the pytest compatibility workaround and simulated-camera capture run. Session content is context, not current instructions.
- Visually inspected `HID_Hackathon_Challenge_Reveal.jpg`: the original liveness/authentication poster. **Neither surprise-challenge photograph was available in the repository or this conversation.** The owner's detailed transcription supplies provisional requirements; photograph verification remains open. Do not claim both photographs were inspected.
- `origin` is exactly `https://github.com/AbyudShetty/HID.git`. Branch `main` has **no commits**. The entire project is untracked; there is no historical Git diff against which to infer authorship.
- Pre-edit source snapshot: `data/review-20261114/source-snapshot.json`, 113 files, aggregate SHA-256 `0a99a29e7f07b86287efeef4967cbb3600ae284e0e64cf02e6cad962be3fba31`. Includes source, test fixtures and documents, excludes secrets and model weights. This identifies an uncommitted state, not a Git revision.

## Verified baseline

| Check | Actual result on this machine |
|---|---|
| `python tasks.py test` | 102 passed, 14 deselected |
| `python tasks.py test-models` | 14 passed, 102 deselected |
| `python tasks.py lint` | All checks passed |
| `cd kiosk; npm test` | 37 passed, 2 live tests skipped |
| `cd kiosk; npm run build` | TypeScript and Vite build passed |
| `pytest ... -m integration --collect-only -q` | **No tests selected**, exit 5; marker exists but no full-flow integration suite exists yet |
| `python tools/download_models.py --check` | All eight files match pinned hashes |
| `docker compose config --quiet` | Passed |
| `docker compose up --build -d` | Current source rebuilt and started successfully, non-root container healthy |
| Container `/api/v1/health` | `ok`, eight hash checks true, provisional policy true |
| Real TS client against rebuilt Docker backend | Both live hello/authentication tests passed |

Runtime: Windows, Python 3.10.0, Node 25.2.0, npm 11.19.0, Docker client/server 29.5.3. The PowerShell login profile changes directory to `C:/ABYUD`; checks use non-login PowerShell with an explicit project working directory. The Docker smoke test used temporary process-environment tokens; none were written to files or reported. The review-created backend container is stopped after validation so the owner can start it with their own credentials.

These are software/transport/integrity checks. They establish neither spoof-detection accuracy nor identity accuracy nor the two-second end-to-end target. The prior ten fake-camera sessions are historical capture evidence; their uploaded bundles are absent from the current `data/` directory. They were not rerun during this review and are not real liveness data.

## Actual implementation boundary

| Area | Present | Missing / limit |
|---|---|---|
| Backend bootstrap | Strict Pydantic message shapes; policy-source validation; hash registry; token checks; hello/ping WebSocket; collect REST | Decision sessions/streaming and all actual access decisions |
| Capture | Browser camera; MediaPipe framing; worker JPEG encoding; challenge renderer; spike upload; cross-language fixtures | Actual camera-control experiment; PNG comparison capture; production kiosk state machine |
| M1 vision | SCRFD wrappers, color linearization, region masks/statistics | Five-bundle visual overlay acceptance evidence; aligned patches and Chroma features |
| Liveness and identity | Model files; MiniFASNet export and recorded parity | Runtime passive signal, ArcFace wrapper/matcher, Chroma model, calibration |
| Access system | Contracts and empty package boundaries | Decision engine, enrollment/gallery, authorization, factors/review, SQLite audit, offline policy/cache/sync |
| Delivery | Development Docker backend; kiosk Vite build | Backend static serving, edge/prod/TLS profiles, AWS inventory/deployment, measured latency |
| Evidence | Numerical parity report, synthetic/fixture tests | E1/E2/E3/E4 latency reports, locked test, G1 outcome |

M0 bootstrap evidence is reproducible; **G0 is still pending owner approval**. T1.1/T1.2/T1.3 are implemented with the limitations below. T1.5 code/tests pass, but its prescribed five-bundle region-overlay inspection is not evidenced. Do not mark all of M1 complete.

## Findings and required follow-up

| ID / priority | Evidence | Consequence / action |
|---|---|---|
| REV-01 / before real illumination trials | `renderer.ts` schedules against absolute planned offsets. A valid 1,200 ms challenge with colored durations 334/333/333, delivered rAF timestamps 0/216/550/883/1200, paints **four transitions in 984 ms**, with no skipped segment. | Amend ADR-005. Enforce rolling limits on actual application timestamps, include return to idle, entry/exit UI and consecutive attempts. Do not catch up colors after a stall. Hold a safe state and mark an aborted/timing-invalid measurement unavailable; restore safely. Add regression tests before real E1/E2. |
| REV-02 / before untrusted upload or inference | `rest_collect.py` calls `await request.body()`; size rejection for a missing/false Content-Length occurs only after allocation. Bundle images may be 8 MiB, inconsistent with 400 KiB frame policy. `_check_image` checks magic bytes, not decoded dimensions. | Stream and cap bytes, entries, counts and decoded pixels before inference; reject forged result/timing extras on client upload; add chunked/malformed/decompression tests. Binary format itself is sound. |
| REV-03 / before ALLOW exists | `parse_policy` validates source annotations but accepts NaN, missing thresholds, incompatible threshold order and unsupported signal sets. NaN floor acceptance was reproduced in memory without changing the file. | Typed complete schema, finite/range/order checks, architecture-to-required-signals constraints, explicit versions. A well-annotated number is not necessarily a valid policy. |
| REV-04 / before offline readiness | `wsClient.ts` sends pings but has no pong deadline or hello timeout; a half-open socket may remain `ready`. | Separate authenticated transport health, application readiness and biometric capability. Add bounded heartbeats, backoff with jitter, failure classification and hysteresis. Never interpret 401/invalid signature as ordinary network loss. |
| REV-05 / before G1 report | H-04 states tools were built and a native probe was logged; those files and report do not exist. ADR-005 cites E2-0, which is absent. | Correct documentation; retain actual provenance. No E1/E2 run has occurred. |
| REV-06 / reproducibility | ADR-002 references two nonexistent requirements files; Python transitive dependencies are not locked. `tasks.py all` short-circuits later checks after an error. `make bench` targets an absent future file. | Accept the two-environment decision, finish setup/lock manifests and fail reporting in a small tooling task. Do not promise a fresh export setup already works. |
| REV-07 / readiness | `main.py` hashes files but does not instantiate inference sessions. `/health.models_loaded` currently means hash-verified. Docker health checks HTTP 200 even when the body says `degraded`. | Preserve process liveness; add separate capability/readiness response and gate ALLOW on loaded/warmed models, calibrated configuration, policy validity, storage and verifier readiness. Never use HTTP 200 as an access capability. |
| REV-08 / before export acceptance | Parity report/fixture contain **12** crops, while §10.4 requires **20**. Export writes files/manifest even if parity fails; missing files in downloader `--check` do not set a failure code. | Keep existing evidence; do not silently re-export or re-pin reviewed hashes. Add a verify-only 20-crop parity run and failure-safe export/download behavior at a separate checkpoint. |
| REV-09 / experimental design | E2 PARTIAL and NO-GO definitions overlap when availability fails; screen AUC 0.85–0.95 has no explicit outcome. Three subjects give weak generalization evidence. | Retain 0.95 screen / 0.90 print targets. Unspecified/conflicting cases are **INCONCLUSIVE**, never automatic GO. Publish held-out-subject predictions with train-only preprocessing/calibration and instrument leakage checks. More independent data improves evidence. Human chooses G1 outcome. |
| REV-10 / before data collection | Current capture uses callback time to select neutral keyframes, even when actual capture timestamps are available. Display timing and sensor response are not yet calibrated. JPEG-only capture does not support the required every-fifth PNG comparison. | Verify neutral membership using actual timestamps/observed segment boundaries and E1 lag; mark uncertain frames unusable. Implement paired JPEG/PNG from the same capture, without using simulation for liveness evidence. |
| REV-11 / access semantics | Existing §11.4 returns ALLOW directly from identity match. Manual review can approve any RV without rechecking campus authorization. §20.3 is a manual deployment fallback, not automatic safe offline behavior. | Proposed §26 and ADR-006/007 add authorization/availability guards to every final ALLOW, including factor/manual resolution. One attempt has one authority; no late central ALLOW after local timeout. |
| REV-12 / security and privacy | Shared browser-build kiosk token is extractable; kiosk id is self-asserted; token auth does not attest capture/device. Bundles can carry client-supplied `result.json`/`server_timing.json`. No `.dockerignore` exists. | Scope per-device identity at the edge; bind sessions/locations server-side; enforce WS Origin/auth separation and limits; explicitly deny client result authority; exclude secrets/data from build context. Root-compromised kiosk and physical relay remain unclaimed threats. |

The original plan also describes future capabilities and rival comparisons as present facts. Those are hypotheses or pitch drafts. A watchdog requests a safe result at 1.95 s; a suspended browser cannot guarantee paint before 2 s. Preserve measured p50/p95/max and disclose misses. Existing metric definitions remain unchanged until an explicitly versioned extension is approved; campus-denied recognized people must not be counted as biometric false rejects.

## ADR dispositions

| ADR | Engineering disposition | Reason |
|---|---|---|
| 001 | Accept format; queue hardening | Cross-language round trips, unsafe-name/duplicate/truncation rejection and issued-challenge binding pass. Multipart would not solve allocation/authorization issues. |
| 002 | Accept layout with setup amendments | Headless and GUI OpenCV are correctly separated in the installed environments. Missing setup manifests prevent claiming complete reproducibility. |
| 003 | Accept | Exact React type dev-dependency pins are installed and the build passes; no runtime addition. |
| 004 | Accept | Pin matches installed pytest; 102/14 tests pass on Python 3.10.0; original crash/workaround appears in the Claude session. No need to upgrade tooling during takeover. |
| 005 | Amend; runtime timing portion pending | Color metric is justified, but the renderer counterexample invalidates the claim that generator validation enforces displayed timing. |

Engineering acceptance is delegated by the owner's takeover request. It does not record owner approval of G0/G1 or new ADR-006/007/008/009 proposals.

## Checkpoint and next work

Review `plan.md` §26, ADR-006–009 and this report before implementation. The next small implementation checkpoint is challenge/capture/ingress hardening plus T1.6 Chroma feature extraction and synthetic tests. Then E1 tooling and real hardware verification; E2 analysis/collection; AWS/network inventory and model benchmarking; G1. Schedule and queue pure functions can be developed while human experiments wait, but validated biometric ALLOW and any fallback architecture remain gated.

At each code milestone: automated evidence → concise report → exact manual checks → owner-run Git commands → pause when a manual experiment, gate, or meaningful review is required. Do not accumulate several milestones into one commit. No arbitrary new feature work at this review checkpoint.
