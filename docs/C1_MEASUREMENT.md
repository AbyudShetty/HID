# C1 — Measurement-path repair (2026-11-14)

Implementation checkpoint on base commit `63668f9`, with uncommitted C1 changes. C1 is complete as a software measurement-path milestone. **No real E1/E2 experiment, liveness accuracy, identity accuracy or two-second access decision is claimed.** Stop here for owner review/commit; next is C2 / T1.6 feature extraction.

## Implemented and why

- Reproduced the original failure with a failing regression: a nominally valid 200 + 334/333/333 ms challenge applied at 0/216/550/883/1200 produces four changes within 984 ms. The test now passes with guarded actual application timing.
- The generator retains neutral 200 ms, three 340±30 ms colors, secure nonce/randomness and linear-RGB separation ≥0.30. It reserves 80 ms for rendering, producing nominal totals **1200–1220 ms**; the actual capture cap remains **1300 ms**. Configuration cannot silently raise the transition rate/cap or lower separation. Final return contrast is validated too.
- A page-lifetime transition guard covers entry into the neutral surface, all colors, final neutral and exit to the ordinary UI. It permits at most three controlled changes in every half-open `[t,t+1000)` window. Completion timestamps include style-application work; stale rAF timestamps do not compress the recorded interval. History survives successive attempts; overlapping renderers are rejected.
- Hold every issued duration from its actual application. Never skip/catch up to a later color after a stall. Overrun or visibility interruption invalidates the capture; the renderer then restores neutral and releases the UI through the same guard. Invalid measurements are not uploaded as valid data.
- Neutral entry is followed by at least one second of explicit preparation before the measurement starts. This clears recent entry/idle history without squeezing extra changes into the short measurement. Preparation, capture and request-to-idle overhead are reported individually on the spike page and in the bundle. Safe UI release can occur after capture ends.
- Start camera sampling only when the prepared measurement starts, while keeping the camera itself open. Filter non-finite, future, duplicate and pre-measurement sensor frames. Select two full-frame keyframes only from settled neutral; retain sensor/callback timestamps and their source per frame. Insufficient neutral keyframes fail the recording, rather than falling back to colored identity inputs. Encoding rejections are observed even for discarded snapshots.
- New uploads require a v2 complete transition trace. The server independently checks order/uniqueness, finite times, rate, issued minimum durations, preparation/end/idle boundaries, frame order/range/source, neutral keyframes, crop coordinates and counts. It still checks the **exact issued challenge including nonce** and enforces single use. It bounds request bytes while streaming and rejects client-written server results/timing.
- Old bundles remain readable for provenance. Preserve the original synthetic TS fixture as `ts_bundle_v1_b64`; replace the current producer fixture with v2 output and verify it in both languages. An old trace is not grandfathered into new-measurement acceptance.

## Timing contract

```text
ordinary UI
  → guarded neutral entry (recorded at a negative measurement-relative time)
  → at least 1000 ms preparation/cooldown
measurement start = 0
  → neutral measurement interval ≥200 ms
  → three issued colors, each held for its full duration from actual application
  → guarded final neutral, capture end ≤1300 ms
  → guarded ordinary-UI release (can be later than capture end)
```

`challenge.json.timing` is `{version:2, preparation_ms, capture_end_ms, idle_at_ms, transitions:[{state,rgb,t_display}]}`. `displayed` still holds neutral index -1 and color indices 0–2. Neutral's timestamp records its **actual earlier entry**, not an invented paint at measurement start. Full-frame and crop records carry `t_capture`, `t_callback`, and `capture_time_source` (`captureTime` or `now`). RGB on the idle-release event is the overlay color at release; the revealed UI is not a uniform emitted-color stimulus. Feature extraction ends at capture end.

These experiment-relative times **do not redefine official access `t_lock` or decision time**. Future access must count all work after the original face lock, including any preparation incurred then. The production kiosk should prepare a neutral idle surface before lock if it can do so safely. The current spike measures a longer request-to-idle cycle; do not claim its capture-only duration satisfies the two-second application requirement.

Application timestamps record rAF-driven DOM changes, not physical display scan-out, camera exposure midpoint or verified exposure/WB stability. With callback-time fallback, actual sensor timing remains unknown; the long neutral preparation reduces contamination risk but does not establish hardware alignment. E1 must verify actual frames and lag. Three controlled changes per second is an implementation constraint, not a clinical safety certification.

## Actual verification

Changed-file inventory:

| Area | Files |
|---|---|
| Backend | `app/challenge/sequence.py`, `app/pipeline/measurement.py` (new), `app/api/rest_collect.py`, `app/schemas.py`, `config/policy.yaml` |
| Backend tests | `tests/bundle_factory.py`, `test_bundle_io.py`, `test_challenge.py`, `test_measurement.py` (new), `fixtures/protocol_samples.json` |
| Kiosk | `src/challenge/renderer.ts` and tests; `src/capture/recordSession.ts` and tests; `src/ops/SpikePage.tsx`; `src/types/protocol.ts` |
| Browser tooling | `tools/cdp_spike_e2e.mjs` |
| Documentation | `README.md`; `docs/C1_MEASUREMENT.md` (new), `CHECKPOINTS.md`, `DECISIONS.md`, `EXPERIMENTS.md`, `GATES.md`, `HUMAN_TASKS.md`, `PROGRESS.md`, `REPOSITORY_REVIEW.md` |
| Evidence | `experiments/C1_measurement/browser_checks.json` (new, metadata only) |
| Owner-private plan | `.local/plan.md` updated in place, ignored and excluded from commit commands |

Dependencies, model weights/hashes, Docker configuration and Git history are unchanged.

| Check | Result |
|---|---|
| Fast backend suite | **136 passed**, 15 deselected |
| Model suite | **14 passed**, 137 deselected |
| Measurement-upload integration suite | **1 passed**, 150 deselected |
| Frontend unit suite | **47 passed**, 2 live tests skipped |
| Separate real TS↔final Docker hello/auth suite | **2 passed** |
| Ruff / TypeScript / Vite build | Passed |
| Compose config, final-source Docker build, `/health`, eight pinned model hashes | Passed |
| Two palette generator loops | 10,000 seeds per palette; all nominal invariants and rendering reserve pass |
| First headless simulated-camera run | **9/10 accepted**; one challenge request failed via Vite upstream `ETIMEDOUT` on the isolated Docker port, with no matching backend request |
| Repeat run | **10/10 accepted** |
| Final application-completion-timestamp run | **10/10 accepted** |
| Injected 1400 ms browser main-thread stall | Aborted with `CAPTURE_OVERRUN`; **no bundle uploaded** |

The first failing run is retained, not removed from the evidence. Across the three browser iterations, 29 captures were accepted with two neutral keyframes each. Recorded capture range: **1208.4–1236.0 ms**. Full request-to-idle range: **2528.7–2586.3 ms**, including preparation and safe release. Those ranges span intermediate/final C1 iterations, are software timing observations on one machine, and are **not** liveness or access-decision performance results. Final-source success is separately identified in the artifact.

Evidence: [metadata-only browser checks](../experiments/C1_measurement/browser_checks.json); raw browser logs and synthetic bundles are under ignored `data/review-20261114/`. No raw frames, real participant data, credentials or model weights are in the published report. The simulated camera uses the inherited public-source reference face, not a live subject.

Tests cover the original compression, half-open rate boundary, actual application clock, delayed style application, safe custom idle return, repeated attempts, interruption/stall, nominal validation, sensor lag/pre-lock filtering, insufficient neutral keyframes, current/legacy fixtures, invalid traces/frames, missing/NaN timestamps, exact-issued challenge, single use, client result injection and chunked oversize upload. Existing model/protocol tests remain intact; fixture expectations changed only for the documented version migration. Lint initially identified formatting/import/strict-zip issues; these were corrected and the final lint run passed.

## Scope and remaining human work

- T1.6 features are **not implemented yet**; neither E1 nor E2 has run. No exposure/WB or reflected-light separability assertion is made. The unseen-person AUC targets stay ≥0.95 screens / ≥0.90 prints.
- A full end-to-end **access** integration test remains C6 work. The new integration test covers issued challenge → synthetic capture bundle → validation/storage → replay rejection only.
- Image magic-byte validation is not a complete decoded-pixel/decompression defense; that C0 finding remains before untrusted inference. General biometric-policy numeric completeness, heartbeat/readiness and worker lifecycle hardening remain separate work. No required ALLOW guard is treated as implemented by C1.
- ADR-001–004 and the ADR-005 amendment are owner-approved. The lightweight independent local runtime, campus/offline guards and crypto/time-zone dependencies are approved but not implemented here; no new dependency installed.
- This checkout keeps the plan and original poster in ignored `.local/`. The plan is updated there in place. `docs/reference/` and the two surprise photographs are still absent; provide those files/paths before requirements freeze. Submission deadline and real camera/display/consenting-subject availability remain useful inputs.
- No real collection is required to accept this C1 software checkpoint. Prepare the rig/consent for C3's tested E1/E2 tooling. The known local proxy timeout remains a development transport reliability observation; it did not produce an accepted invalid measurement.

The pre-existing owner Docker stack was left untouched. Testing used a separate `hid-c1-review` container/port and temporary credentials; only review-created processes are stopped afterward. No Git writes performed.

For manual use of the updated spike, rebuild the owner stack with its own configured tokens (`docker compose up --build -d`) before starting the kiosk. An older running image cannot accept the new v2 measurement contract. This rebuild was deliberately not applied to the pre-existing owner container during isolated verification.
