# Architecture Decision Records

Template (plan Appendix A). Anything FINAL in plan §4.1 changes only through an **Approved** ADR.

Review convention (2026-11-14): **Accepted (engineering review)** records the decision authority delegated by the owner's takeover request. It does not mean the owner approved an experimental gate. **Amended / Proposed** entries require the named follow-up before their new behavior is adopted. Original rationale is retained below.

```
## ADR-NNN: <title>
- Date: YYYY-MM-DD · Status: Proposed | Approved (by, date) | Rejected | Superseded by ADR-MMM
- Plan reference: §x.y / decision id (F-xx / G-xx)
- Context:
- Options:
- Decision:
- Consequences:
```

---

## ADR-001: Bundle upload as one length-prefixed binary body (no multipart)
- Date: 2026-11-14 · Status: **Accepted (engineering review, Codex, 2026-11-14)**; format accepted, receiver hardening outstanding
- Plan reference: §8.2 (`POST /collect/bundles` "multipart bundle"), §7.3 (allowed dependencies), rule 2.3.8
- Context: FastAPI/Starlette can only parse `multipart/form-data` when `python-multipart` is installed. That package is **not** on the §7.3 allowed list. The plan's intent for this endpoint is only "upload a session bundle" for the M1 spike path and collect mode.
- Options: (A) add `python-multipart` (dependency ADR, small, MIT); (B) one binary body `application/x-hid-bundle` made of `[u32 name_len][name][u32 data_len][data]` entries, buildable in the browser with plain `Uint8Array`s and parseable with `struct` on the server; (C) zip in the browser (needs a zip library, so another dependency).
- Decision: **B**. Same framing style as the WebSocket binary frames (§8.1), zero new dependencies, trivially testable. Entry names are the bundle-relative paths of §8.5 (`meta.json`, `challenge.json`, `frames.jsonl`, `crops/000017.jpg`, …). The server validates names (no `..`, no absolute paths, only the allowed layout), enforces size limits, and rejects corrupt or truncated bodies with a reason.
- Consequences: the §8.2 row for `POST /collect/bundles` should read "binary bundle body (ADR-001)". Clients other than our kiosk use the same framing, documented in `backend/app/pipeline/bundle_io.py`. Switching to multipart would require coordinated receiver/client/tests, not merely a server edit.
- Review evidence: Python/TS byte fixtures, unsafe names/duplicates/truncation rejection, exact issued-challenge binding and single-use upload tests pass. No new runtime dependency is needed. Multipart and ZIP would add parsers without solving trust/size controls.
- Required hardening: cap the streamed request before allocation even without Content-Length; enforce crop/keyframe and decoded-pixel limits; reject client `result.json`/`server_timing.json`; document version negotiation and consistent 400/409/413/415 behavior. Current 48 MiB body / 8 MiB entry limits are parser limits, not a complete image resource defense. See review REV-02. Acceptance of the encoding is not security approval of an unrestricted upload endpoint.

## ADR-002: Task runner and virtual environments on the Windows dev machine
- Date: 2026-11-14 · Status: **Accepted with setup amendments (engineering review, Codex, 2026-11-14)**
- Plan reference: §7.1–7.2, §18.1
- Context: the dev laptop has no `make` and Python 3.10.0, and the camera scripts need GUI OpenCV (`opencv-python`) while the backend and serving image use `opencv-python-headless` (the two cannot share one environment).
- Decision: keep the `Makefile` (for Linux/CI/EC2) and add `tasks.py` with identical targets. `.venv` = backend + tooling (headless OpenCV); `.venv-host` = camera/GUI scripts (`tools/requirements-host.txt`). No new third-party dependencies.
- Consequences: documented in README; `make test` is equivalent to `python tasks.py test`.
- Review: both environments exist; `.venv` has `opencv-python-headless==5.0.0.93`, `.venv-host` has `opencv-python==5.0.0.93`; fast/model/lint/frontend commands work. Alternatives: install make (additional OS prerequisite), mix GUI/headless distributions (reject due to shared `cv2` namespace), or run camera tooling in Docker (unnecessary Windows device/display complexity). Keeping the small stdlib runner and Linux Makefile is justified.
- Amendments before claiming reproducible setup: add the referenced but absent host/tooling requirements manifests, record export-only dependencies, lock transitive dependencies, document explicit interpreter/working-directory use, and make `tasks.py all` run/report every requested check despite earlier failures. Do not install GUI OpenCV into the serving venv/image. `bench` remains a future target until its script exists. No packages are changed by this review.

## ADR-003: Type-definition packages for the kiosk
- Date: 2026-11-14 · Status: **Accepted (engineering review, Codex, 2026-11-14)**
- Plan reference: §7.3 (frontend dependency list), rule 2.3.8
- Context: React + TypeScript cannot type-check without `@types/react` and `@types/react-dom`. They are type-only dev dependencies, not runtime code, and are not named in §7.3 (which lists `react`, `react-dom`, `typescript`, …).
- Decision: add `@types/react@18.3.31` and `@types/react-dom@18.3.7` (dev only). Nothing else outside §7.3 was added to the kiosk. `@types/node` was deliberately **not** added: tests avoid `node:` imports.
- Consequences: none at runtime. If you prefer no `@types` packages, TypeScript would have to run without React types, which is impractical.
- Review: exact pins are dev-only in `kiosk/package.json` and lockfile; TypeScript/Vite build and 37 unit tests pass. Alternatives are hand-maintained React declarations or disabling useful type checks; neither improves maintainability. These packages provide compile-time declarations, not runtime authentication/security code.

## ADR-004: Test-tooling version pins on Python 3.10.0
- Date: 2026-11-14 · Status: **Accepted (engineering review, Codex, 2026-11-14)**
- Context: the host interpreter is CPython 3.10.0 (an early patch release). pytest 9.2.0 fails there with `AttributeError: 'NodeId' object has no attribute '_str_cache'` (a `dataclass(slots=True)` field with `init=False` is not initialised on that release).
- Decision: pin `pytest==8.4.2` (the line the machine already had) in `backend/pyproject.toml`. The Docker image (Python 3.11) does not install dev extras, so serving is unaffected.
- Consequences: upgrade Python to ≥ 3.10.12 or 3.11 if newer pytest features are wanted.
- Review evidence: host is Python 3.10.0; installed pytest is exactly 8.4.2; 102 fast and 14 model tests pass. Claude session contains the original pytest 9 failure and downgrade. The failure was not deliberately reintroduced. A later interpreter/pytest upgrade needs its own compatibility run; the original suggested newer Python versions are not claimed as newly tested fixes. Alternative now: upgrade the interpreter and all tooling, increasing takeover risk without a product benefit. Keep the documented pin and CI/container separation.

## ADR-005: Challenge distinctness rule and segment timing (replaces two numbers in plan §9.2)
- Date: 2026-11-14 · Status: **Amended / Proposed** after engineering review; color-distance rationale accepted, displayed-timing enforcement pending implementation and review; G-03 remains gated
- Plan reference: §9.2 hard constraints 1 and 3, defaults "N = 200 ms, K = 3, D = 330 ms, J = 40 ms", F-04
- Context (measured, not assumed — see the script output in docs/EXPERIMENTS.md E2-0):
  1. Constraint 3 says consecutive segments differ by ≥ 100 (of 255) in at least two channels, including neutral→first. Against the plan's own neutral (205,205,205) **every** colour of its example palette fails: the two-channel count is 0 or 1 for all six colours (e.g. (80,120,255) differs by 125/85/50). Only colours with two channels ≤ 105 could pass, which excludes yellow, cyan, magenta and the near-isoluminant P2 variant entirely (a P2 colour must have luminance ≈ 0.61, but two channels ≤ 105 cap blue at ≈ 0.18 and leave only a green).
  2. Constraint 1 counts "transitions" in any 1000 ms window. The kiosk also returns to the idle/neutral screen when the challenge ends, which is a real, visible luminance change. With K = 3 and D = 330 ms there are four changes in 990 ms (200, 530, 860, 1190 ms), exceeding 3 per second by 10 ms.
- Decision: (a) "distinct" is measured in light: **linear-RGB Euclidean distance ≥ 0.30** between consecutive states (neutral→first and colour→colour). The plan's palette scores 0.40–0.78 against the neutral and ≥ 0.32 pairwise for P2, so the *intent* (a large, measurable step) is preserved. (b) The final return to idle **counts** as a transition (stricter, safer). To satisfy it with K = 3, coloured time must be ≥ 1000 ms, so defaults become **D = 340 ms, J = 30 ms** (coloured time 930–1110 ms; the generator retries until valid; total ≤ 1300 ms cap kept). Everything else in §9.2 (neutral 200 ms, ≤ 3 changes/s, no saturated red, no repeats, `secrets` RNG, P1/P2) is unchanged.
- Consequences: `policy.yaml` `challenge:` carries `min_delta_linear: 0.30`, `segment_ms: 340`, `jitter_ms: 30`; total capture ≈ 1.22 s (+30 ms vs. plan), still ≤ 1.3 s. Because E2 decides the challenge parameters at G1, these remain defaults, not commitments. If you prefer to keep the literal plan wording, the palette must be redesigned (and P2 dropped).
- Review calculations: see `docs/EXPERIMENTS.md` E2-0 (now actually recorded). All six P1 colors fail the old two-channel rule against neutral; minimum neutral distances are 0.682612 (P1) and 0.396424 (P2), minimum pairwise distances 0.402079 / 0.322668. P2 maximum neutral-relative luminance deviation is 0.3032%. Both palettes pass 10,000 deterministic generator seeds, with accepted total durations 1,200–1,300 ms. No photometric response or medical safety was measured.
- Reproducibility: an injected RNG reproduces color orders/durations; secure nonce generation deliberately remains independent, so the seed does not reproduce a full nonce-bearing challenge. Persist the issued challenge and actual displayed timeline for replay. Production continues using `secrets`.
- Counterexample: a valid 200 + 334/333/333 ms sequence, rendered at 0/216/550/883/1200 ms, gives changes at 216/550/883/1200: **four in 984 ms**, none marked skipped. Current generator validation therefore does not establish the actual rendered-rate constraint.
- Amendment: track all actual visible state changes (neutral entry, each color, return/overlay exit, subsequent attempts); do not compress/catch up a sequence after a stall. Gate transitions against rolling history, hold a safe state on interruption and report invalid timing/unavailable evidence. Record the actual final transition, add browser-stall/abort/cooldown regression tests, verify final return contrast, and check consecutive sessions. Maintain the ≤1.3 s usable measurement target; an aborted run is not a valid challenge. If safety recovery exceeds that target, record failure rather than accelerate flashes. Planned generator checks remain useful but insufficient.
- Alternatives: redesign the palette to meet the old literal rule (still leaves runtime timing defect), or rely on nominal segment lengths (rejected by the reproduced trace). Final palette/camera/display selection remains a real E1/E2/G1 decision. Do not describe the flash constraint as a clinical safety certification.

## ADR-006: One codebase with a local edge gateway and shared Python verification
- Date: 2026-11-14 · Status: **Proposed — owner review requested, not implemented**
- Plan reference: §26.2/26.6; extends F-04/F-05/F-14 and replaces the manual-only outage story of §20.3.
- Context: a cloud-only browser loses decision capability on disconnect. Reusing the Python container locally preserves model/preprocessing/calibration parity and allows local audit durability without browser biometric storage.
- Options: (A) duplicate inference and template storage in browser; (B) manual URL/container switch; (C) persistent browser→edge connection with online upstream forwarding and the same local Python pipeline when disconnected.
- Recommendation: **C**. Separate central/edge roles, existing protocol/pipeline, local static kiosk assets. One authority per attempt; a central attempt interrupted by outage ends RV and a fresh local challenge is required. Never reuse a nonce or accept a late ALLOW after terminal timeout.
- Consequences: additional locally managed service and measured forwarding hop; local service is mandatory for SC2 demo acceptance. Local control/credential protection needs hardening. A disconnected reboot defaults to no ALLOW. Cloud remains the normal online inference authority and AWS demonstration; no models/frameworks are replaced.
- Evidence: current Python modules, worker capture/transport and Docker fallback offer reusable boundaries; no outage inference or latency measurement exists yet. Acceptance: §26.10 C6/C7/C8.

## ADR-007: Campus authorization and availability guard every final access decision
- Date: 2026-11-14 · Status: **Proposed — owner review requested, not implemented**
- Plan reference: §26.3–26.5; amends the direct identity→ALLOW rule in §11.4 and factor/manual resolution in §12.4; preserves F-01/F-02/F-03/F-15 intent.
- Options: bolt a schedule check onto UI results (reject: bypassable and misses factors), fuse schedule into liveness confidence (reject: conflates evidence), or add separate typed pure authorization and availability guards to the shared decision engine.
- Recommendation: separate pure evaluator, explicit weekly/dated schedule, scoped grants and immutable revisions; unknown/missing policy cannot permit. Apply trusted established denial vetoes before uncertainty and retain them through step-up. Successful factors rerun current authorization and execution guards.
- Consequences: extend Pydantic/TS contracts together, keep three wire outcomes and four official flow stages. New contextual system FAR/FRR need a schema-versioned companion report: ineligible schedule attempts are unauthorized; intentional closure denies are not biometric false rejections. Existing biometric definitions and E2 thresholds are unchanged pending explicit review of any metric extension.
- Security: bind campus/location/kiosk to server-owned device identity, not client fields; closure/revocation and spoof cannot be manually overridden. Data is explicitly demo data. Time tests include expiry equality, DST and final-decision policy changes.
- Acceptance: §26 decision matrix and C5/C6 test suites, with independent identity/liveness evidence.

## ADR-008: Restricted offline grants, signed snapshots and a durable metadata-only outbox
- Date: 2026-11-14 · Status: **Proposed — owner risk decision required; offline ALLOW disabled by default**
- Plan reference: §26.7/26.8; official offline requirements as transcribed by the owner, photographs pending.
- Options: cache last online ALLOW (reject: replay/stale authorization), unconditional deny/step-up on outage (safe default but limited autonomy), or a locally verified new attempt with signed scoped policies, encrypted eligible identities, trustworthy time, bounded freshness and durable audit.
- Recommendation: implement safe-default path first, then permit the restricted path only after validation and owner approval. Proposed maximum revocation staleness: **15 minutes**, bounded by earlier policy/identity/grant expiry. Disconnected restart cannot ALLOW without re-established trusted time. No offline grant after central authentication/revocation failure.
- Consequences: instant offline revocation cannot be guaranteed. Owner must accept the bounded exposure or retain no offline grants. Exact criteria and protections are §26.7. Offline PIN step-up uses an encrypted salted scrypt verifier for an already locally matched identity, explicit policy permission and persistent lockouts; it cannot bypass a missing liveness pass or expired policy.
- Audit: SQLite atomic event/outbox insert before ALLOW; no raw images/recordings/templates/feature arrays/factor secrets in the queue. At-least-once delivery, authenticated per-event ack, central idempotency/conflict checks, partial retry and quarantine, historical policy context immutable. Updated central policy produces a separate reconciliation annotation.
- Threat limits: host-admin compromise can defeat software-only key/time/rollback protections. Keys outside the database plus OS/disk access controls are a prototype boundary, not device attestation. P0 reboot-offline behavior remains fail-safe.
- Acceptance: §26.11 cache/transition/queue integration tests and real hardware local verification; C7 before C8.

## ADR-009: Cryptographic and portable time-zone dependencies
- Date: 2026-11-14 · Status: **Proposed — owner dependency approval requested; no install performed**
- Plan reference: §7.3 dependency policy; §26.4/26.7. Implements ADR-008 only if approved.
- Request: `cryptography==50.0.2` (Apache-2.0 OR BSD-3-Clause) for Ed25519 verification/signing and AES-GCM authenticated encryption; `tzdata==2026.6` (Apache-2.0) as an explicit direct time-zone data dependency.
- Observed package metadata (PyPI, 2026-11-14): cryptography requires Python ≥3.9 excluding 3.9.0/3.9.1; compatible `cp39-abi3-win_amd64` wheel 3,854,095 bytes. tzdata universal wheel 348,210 bytes. These sizes exclude crypto transitive dependencies and installed expansion; inventory and pin the complete closure before adding the packages.
- Alternatives: stdlib `hmac` shares policy-forging authority with the edge and does not provide asymmetric verification or template encryption; custom cryptography is rejected; online-only KMS cannot decrypt during an outage; fixed UTC offset fails portable IANA/DST requirements. Keep stdlib SQLite/datetime/retry logic, with no scheduler/queue framework.
- Evidence: official [Ed25519 API](https://cryptography.io/en/46.0.3/hazmat/primitives/asymmetric/ed25519/), [AEAD](https://cryptography.io/en/46.0.3/hazmat/primitives/aead/), [installation](https://cryptography.io/en/stable/installation/) and [Python 3.10 zoneinfo](https://docs.python.org/3.10/library/zoneinfo.html); published package metadata at [cryptography](https://pypi.org/pypi/cryptography/50.0.2/json) and [tzdata](https://pypi.org/pypi/tzdata/2026.6/json). API rationale uses stable versioned references, not an assertion that the new package was installed or tested. The current backend environment already has tzdata 2026.6 transitively; making it direct removes that accidental dependency.
- Consequences: small additional binary crypto runtime and required key lifecycle; signature/encryption does not establish cache freshness, trusted time or uncompromised host. Those remain independent guards.
