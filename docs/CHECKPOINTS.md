# Owner checkpoints and Git commands

The owner runs all Git writes. The engineer never stages, commits, pushes, amends, resets, cleans or rewrites history. Stop after meaningful, tested milestones for review and any required manual verification. Do not collect several milestones into one giant change.

## C0 — Review and architecture draft, ready for owner review

Read [repository review](REPOSITORY_REVIEW.md), [plan §26](../plan.md#26-campus-access-and-safe-offline-operation--v12-review-draft), [ADR dispositions and proposals](DECISIONS.md), and [human tasks](HUMAN_TASKS.md). The important choices are the local edge gateway, separate campus authorization, the proposed offline freshness bound, and two direct dependencies. Proposed architecture is not yet implemented or approved. No new feature code/tests/dependencies were changed during review.

Evidence: 102 fast backend + 14 model tests; lint; 37 frontend unit tests; TS/Vite build; all eight model hashes; current-source Docker build/healthy probe; two real TS↔Docker hello/auth tests. The integration marker selects no tests: complete access-flow integration remains to build. E1/E2 remain unperformed. Full details/known defects are in the review.

Manual review now:

1. Confirm the architectural/risk choices in plan §26.12 and ADR-006–009. Approving a documentation checkpoint is distinct from approving offline grants or G0/G1.
2. Supply both surprise photographs or their local paths, plus submission deadline and available real-rig/subject collection time.
3. Optional smoke check after setting your own backend/kiosk tokens: `/ops` should connect and show provisional thresholds; `/kiosk` should honestly report it is unimplemented. No ALLOW or accuracy claim is expected. The review-created Docker backend was stopped after testing; start your own stack with `docker compose up --build -d`, then `cd kiosk` and `npm run dev`.
4. Real color/camera trials wait until C1 fixes the actual-render timing defect. No need to repeat automatic baseline tests manually just to approve the review.

There is no existing Git commit, so the first owner commit needs to capture the inherited implementation as well as the review. A docs-only initial commit would leave the described code absent from a fresh checkout. These commands explicitly include source/fixtures and only the model manifest; ignored raw data, weights, virtual environments and secrets remain excluded. Review the staged names yourself before committing.

```powershell
Set-Location -LiteralPath 'C:\ABYUD\HACKATHONS\HID'
git status --short --branch
git add .env.example .gitignore HID_Hackathon_Challenge_Reveal.jpg Makefile README.md backend docker-compose.yml docs experiments infra kiosk models/manifest.json plan.md ruff.toml tasks.py tools
git diff --cached --stat
git diff --cached --name-only
# After reviewing the staged paths and content:
git commit -m "Bootstrap HID capture and vision; document campus and offline architecture review"
```

Do not add `.env`, private keys, `data/`, raw participant material or model weights. The reference image/NPZ test fixtures under `backend/tests/fixtures` are inherited public-source test artifacts with attribution, not new participant recordings. No push is requested here. If any other actor has made a first commit before you run this, inspect status/diff and choose the corresponding smaller staging set instead of assuming this is still an initial commit.

## Subsequent stops

| Stop | Engineer delivers | Owner/manual action before dependent work |
|---|---|---|
| C1 | Renderer/capture/ingress hardening and T1.6 feature extraction; focused/full test evidence; exact staging list | Review small code milestone and run commit; inspect safe real-display behavior before experiments |
| C2 | Tested E1 browser/native probes and exact hardware commands | Set up rig and run real probes; record raw evidence and capture-path decision |
| C3/C4/G1 | E2 LOSO analysis, real data results; AWS/network/model timing evidence; G1 report | Consent/collect data; sandbox credentials; approve GO/PARTIAL/FALLBACK/INCONCLUSIVE explicitly |
| C5/C6 | Pure schedule/decision/outbox then integrated online campus flow | Test permitted/closed/factor-required schedule and policy update with labeled data; separate commits |
| C7 | Safe offline state/queue/sync without grants | Cut network mid-attempt, restart offline, restore; verify no late grants and no duplicate events |
| C8 | Restricted local verification and offline factor | Approve freshness risk; verify with real enrolled people/attacks and stale/tampered cache; enable only after evidence |
| C9 | Calibrated system, locked results, AWS/local demo and rehearsals | Owner freezes/tags/commits; real demo rehearsal; judge acceptance |

Each stop gets its own concrete commands and evidence when ready; the table does not approve future changes, cloud provisioning or gates. If an experiment or required check fails, report the failure and revise the milestone rather than committing a misleading completion claim.
