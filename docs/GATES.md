# Gate reports

Template (plan Appendix C). A gate needs **human approval** before dependent work starts.

```
## Gate G<n> — <milestone> (YYYY-MM-DD)
- Criteria (copied from plan): ...
- Evidence: links to tests, reports, metrics.json, bench output
- Result per criterion: PASS / FAIL / PARTIAL with numbers
- Open issues and risks:
- Proposed outcome / next step:
- Approval: APPROVED by <name> on <date>  |  REJECTED: <reason>
```

---

## Gate G0 — Bootstrap (2026-11-14)
- Criteria (plan §19 M0): `make test` green; `docker compose up` healthy with models; kiosk hello works.
- Evidence:
  - `python tasks.py test` → 46 passed; `python tasks.py test-models` → 4 passed; `python tasks.py lint` → all checks passed.
  - `cd kiosk && npx vitest run` → 15 passed, 2 skipped (the 2 live tests are env-gated); `npx tsc --noEmit` clean; `vite build` succeeds.
  - `docker compose up --build -d` → container `healthy`; `GET /api/v1/health` → `status: ok`, all 8 manifest models `ok` (sha256-verified inside the container), `policy_provisional: true`.
  - Live TS client ↔ Python server (inside Docker): `LIVE_WS_URL=… npx vitest run src/net/live.test.ts` → 2 passed (hello → `ready` with provisional policy; wrong token → `failed`, no reconnect).
  - MiniFASNet ONNX parity: max |Δlogit| 5.4e-6 / 5.6e-6 (docs/EXPERIMENTS.md E4-0).
- Result per criterion: all PASS.
- Open issues and risks: (1) Docker Desktop was not running at session start; it was started by the agent. (2) Model hashes are trust-on-first-use (pinned from the first download). (3) Deviations awaiting review: ADR-001…004.
- Proposed outcome / next step: approve G0 and continue M1 (already in progress; M1 does not depend on any G0 decision).
- Approval: **pending human approval**

### G0 revalidation at C0 takeover review (2026-11-14)
- Current source: no Git commits exist; pre-edit source hash `0a99a29e7f07b86287efeef4967cbb3600ae284e0e64cf02e6cad962be3fba31` (113-file manifest in gitignored `data/review-20261114/`). Details: `REPOSITORY_REVIEW.md`.
- Reproduced: 102 fast tests, 14 model tests, lint; 37 frontend tests (2 skipped in ordinary run), TS/Vite build; all 8 model hashes; current-source Docker build/start and healthy response; **2 real TypeScript hello/auth tests passed against Docker** with temporary credentials.
- No integration-marked backend tests selected (exit 5). API-level tests exist in the fast suite; complete decision-flow integration does not. `/health.models_loaded` currently indicates hash verification, not inference initialization/readiness.
- Existing parity evidence is **12 crops**, not the 20 required in §10.4. Preserve this evidence; complete the additional verification without silently replacing model hashes.
- Engineering dispositions: ADR-001/003/004 accepted; ADR-002 accepted with setup amendments; ADR-005 amended/proposed. Renderer actual-timing and upload/resource-limit follow-ups must precede real illumination trials or untrusted capture.
- Bootstrap smoke criteria reproduce. This does not constitute approval or a liveness/access performance gate. **G0 approval remains pending the owner.**

## C0 — Takeover review checkpoint (2026-11-14)
- Delivered: verified repository review, ADR-001–005 decisions with consequences, `plan.md` §26 campus/offline architecture and C0–C9 execution/acceptance plan; ADR-006–009 proposals; human/manual/Git checklist.
- Boundary: documentation only. No production code, tests, model files/hashes or dependencies changed. No Git staging/commit/push/history actions.
- Owner review: edge architecture, authorization matrix, offline freshness/revocation risk and proposed crypto/time-zone dependencies. Both surprise photographs and submission/experiment schedule still needed.
- Next: C1 challenge/capture/ingress safety and T1.6 features. Do not start validated Chroma-dependent access paths before real E1/E2 evidence and G1 approval. Pure schedule/outbox work can proceed independently with synthetic inputs while experiments wait, after the checkpoint.
- Status: **ready for owner review/commit checkpoint**, not an experimental gate approval. Exact commands and manual checklist: `CHECKPOINTS.md`.
