# Owner checkpoints and Git commands

The owner performs all Git writes. The engineer never stages, commits, pushes, amends, resets, cleans or rewrites history. Stop after each meaningful milestone for review, manual verification where needed, and a separate owner commit.

## C1 — Measurement-path repair: ready for review and commit

Read [C1 implementation/evidence/limitations](C1_MEASUREMENT.md), [approved ADRs](DECISIONS.md) and [metadata-only browser evidence](../experiments/C1_measurement/browser_checks.json). C0 was committed by the owner as `63668f9`; the working plan and original poster are now private under ignored `.local/`. Do not move or stage them.

C1 acceptance: 136 fast backend tests, 14 model tests, one measurement-upload integration test, 47 frontend unit tests, two separate live TS↔Docker tests; lint, frontend build, Docker health/eight model hashes passed. The original timing regression is fixed. The first browser run retained a local proxy timeout (9/10 accepted); repeat and final timestamp runs each passed 10/10. An injected 1400 ms stall aborted without uploading a bundle. These checks use a simulated camera and establish no real liveness result.

Manual review now:

1. Review the new illumination preparation and safe-release overhead. The spike's complete request-to-idle is about 2.5 s; capture-only timing is not an access-decision performance claim.
2. Review v2 trace/schema and timestamp checks, plus preserved legacy provenance. Exact issued-challenge binding and single use still apply.
3. No physical data collection is required for this software checkpoint. Real exposure/WB/illumination verification waits for owner C3's tested probes and consented rig/data.
4. Supply the two surprise photographs: `docs/reference/` was still absent during C1. The local plan records this source gap. Also confirm submission deadline and available hardware/subjects when possible.

If manually using the updated spike, rebuild your own configured backend first (`docker compose up --build -d`), then start the kiosk. The pre-existing owner container was preserved during testing and may still contain the older bundle schema. No real participant recording is needed for this checkpoint.

Run from the repository after reviewing the diff. The source/test fixture changes contain controlled synthetic data; the published browser JSON contains metadata only. Raw browser bundles/logs remain ignored in `data/`. No credentials, real participant data, weights or private plan should be staged.

```powershell
Set-Location -LiteralPath 'C:\ABYUD\HACKATHONS\HID'
git status --short --branch
git diff --check
git add backend kiosk/src tools/cdp_spike_e2e.mjs docs experiments/C1_measurement README.md
git diff --cached --stat
git diff --cached --name-only
# After reviewing the staged paths and content:
git commit -m "C1: repair challenge rendering and validate measurement timing"
```

Do not run `git add .` or force-add `.local/`, `data/`, `.env`, private keys or model weights. If other work has appeared since this checkpoint, inspect it and stage the exact C1 files only. No push is requested.

## Approved next checkpoints (owner sequence)

| Stop | Deliverable | Owner/manual action |
|---|---|---|
| C1 — current | Measurement generation/rendering, frame alignment, trace acceptance, ADR-005 evidence | Review and commit; no physical experiment approval inferred |
| C2 | T1.6 Chroma series/features and synthetic quality/alignment tests | Review definitions/tests and commit; no liveness confidence fabricated |
| C3 | E1 browser/native probes, E2 participant/device-aware analysis, AWS inventory and measurement tools | Set up rig, consent/collect real data, provide sandbox access; approve G1 only on evidence |
| C4 | Campus authorization, signed versioned policy, schedule administrator/demo UI | Test windows, weekdays/weekends, holidays, step-up and policy updates; separate commit |
| C5 | Lightweight independent local runtime, strict freshness/cache guards, SQLite outbox and sync | Cut central network/process, restart offline, test spoof/unknown/stale refusal, restore and verify duplicate/partial sync |
| C6 | Full access-flow integration, benchmarks, calibration/locked evidence and judge-ready demo | Real hardware/attack verification and rehearsals; owner freeze/tag/commit actions |

Architecture/dependency choices in ADR-006–009 are already approved; do not ask for the same approval again. Restricted offline ALLOW still requires every approved guard and verified data less than 900 seconds old. Actual E1/E2 results, empirical gates, and later cloud provisioning remain separate from permission to implement.
