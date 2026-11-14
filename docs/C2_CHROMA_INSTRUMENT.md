# C2 — Chroma feature instrument (T1.6) — status

**Experimental measurement only.** No p_live, classifier, authentication or access decision. E1/E2 are **not** performed; the E2 go/no-go thresholds (AUC ≥ 0.95 screens, ≥ 0.90 prints, unseen people) are unchanged.

## What exists
- `backend/app/liveness/chroma_series.py`, `chroma_features.py`: per-region linear-RGB series, lag search (0–250 ms, 5 ms grid — not physical precision), segment-balanced baseline-subtracted gains, region/background/surround ratios, fit R², noise/SNR, drift, FPS/gaps, motion. Undefined measurements are `null` with explicit reasons; nothing is imputed or defaulted to nominal timing.
- `backend/app/challenge/timeline.py`: the C1 actual-transition validator, shared with ingestion.
- `backend/app/pipeline/chroma_instrument.py`: hash-verified SCRFD, one in-flight analysis (busy → 429), model missing → 503. MiniFASNet and ArcFace *serving* are NOT implemented.
- Routes (operator token): `POST /api/v1/collect/preview` (one JPEG, transient), `POST /api/v1/collect/measure` (exact issued challenge, single use, **not stored**), `POST /api/v1/collect/bundles?analyze=true` (labelled, stored).
- `/ops/spike` live panel (`LivePreview.tsx`): ~3 Hz, one request in flight, paused during capture; draws the exact processed frame with the backend's SCRFD box, landmarks and region outlines, real per-region linear-RGB means, server vs round-trip timing, and backend errors.
- `/ops/spike`: new **"Measure only — no storage"** button (no label needed) showing the raw report. Labelled "Record session" is unchanged.

## Verified
- Backend: 166 passed (incl. model + integration; new `test_measure_api.py` covers auth, forged-challenge rejection, 503 without model, single use, non-persistence; synthetic challenges now seeded). Frontend: 47 passed (+2 env-gated live). `tsc` clean.
- Real browser (fake camera): live preview returned the backend face detection (score 0.88, cold server 127 ms incl. 103 ms SCRFD; one sample, not a benchmark).
- Headless Chrome + fake camera (`tools/cdp_spike_e2e.mjs --measure`): capture → `/measure` → report returned. The fake camera is a static photo, so the report is correctly `unavailable` (no temporal variation). This tests plumbing only — **not liveness evidence**.

## Not done (next)
- Post-capture selectable-crop viewer and response plots (the raw report is shown as JSON).
- Malformed-header decoder tests; benchmarks (cold/warm inference, feature time); Docker validation; physical webcam verification by the owner.
- Known deviations: pixelwise specularity/uniformity features deferred (need defensible registration); `/measure` consumes the nonce before processing, so a busy/error response needs a new capture.
- Camera exposure/WB: unchanged browser settings do not prove physical locking.

## Manual webcam check
Run backend + `npm run dev` (see README), open `/ops/spike`, enter the operator token, Start camera, then **Measure only**. Expect `unavailable`/low-signal reasons unless the screen light actually reaches a face; that outcome is informative, not a failure.
