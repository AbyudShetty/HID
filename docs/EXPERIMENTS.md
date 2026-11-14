# Experiment log

Entry template (plan Appendix B). Every measurement is logged here with provenance. "Not measured yet" is a valid state.

```
## E<id>-<n>: <title> (YYYY-MM-DD)
- Hypothesis:
- Setup: hardware, software versions, config hash, git commit
- Data: bundles/manifest path, n per class
- Procedure:
- Results: tables with n and CIs; plots path
- Conclusion: (supports / refutes / inconclusive)
- Decision proposed: ADR-NNN (if any)
```

---

## E4-0: MiniFASNet ONNX export parity (2026-11-14)
- Hypothesis: the pretrained MiniFASNet V2 (scale 2.7) and V1SE (scale 4.0) weights export to ONNX with logits identical to PyTorch (plan §10.4 tolerance: max |Δ| < 1e-4).
- Setup: Windows 11, CPython 3.10.0, torch 2.14.1+cpu, onnxruntime 1.23.2, legacy TorchScript exporter, opset 13, dynamic batch axis. Weights from `minivision-ai/Silent-Face-Anti-Spoofing@master` (sha256 pinned in `models/manifest.json`).
- Data: 12 deterministic 80×80 BGR crops cut from the three repository sample images (`backend/tests/fixtures/minifas_samples/`). Fixture `minifas_parity.npz` stores inputs + PyTorch logits.
- Procedure: `.venv\Scripts\python tools\export_minifasnet.py`.
- Results (n = 12 crops): V2 max |Δlogit| = 5.364e-06; V1SE max |Δlogit| = 5.603e-06; both PASS. Raw output: `experiments/E4_models/minifasnet_parity.json`.
- Facts read from the reference source (not assumed): input is the **BGR** image as float **0..255 without division by 255** (`ToTensor` has `div(255)` commented out); real class = **index 1** (`label == 1` → "Real Face"); crop = `CropImage._get_new_box` (scale clamped by image bounds, shift-and-clip); model names encode scale/size (`2.7_80x80_…`, `4_0_0_80x80_…` = 4.0).
- Note: the reference detects the face with a RetinaFace Caffe model; we use SCRFD, whose box convention differs slightly. Effect on p_live is to be measured in M2 (T2.2), not assumed to be zero.
- Conclusion: supports. This is a numerical-equivalence result only; it says nothing about liveness accuracy.
- Decision proposed: none.

## E2-0: Palette and renderer engineering checks — NOT the real E2 experiment (2026-11-14)
- Purpose: verify ADR-005 against actual palette/generator/renderer code. This missing ADR evidence is now recorded. **No face, camera, reflected light, physical display output, liveness classification or real attack was measured.** E1 and E2 remain unperformed.
- Provenance: pre-review uncommitted source aggregate SHA-256 `0a99a29e7f07b86287efeef4967cbb3600ae284e0e64cf02e6cad962be3fba31`; Python 3.10.0; Node 25.2.0; code in `backend/app/challenge/{palettes,sequence}.py`, `kiosk/src/challenge/renderer.ts` and their existing tests. Git commit: none exists. Data: deterministic RGB values and synthetic rAF timestamps only; no dataset split.
- Procedure: calculate the exact sRGB EOTF, neutral/color and pairwise Euclidean distances, neutral-relative luminance deviations and red fractions; run `generate(ChallengeConfig(palette_id=p), rng=random.Random(seed))` for seeds 0–9999 for each palette; validate every result. Invoke the actual TypeScript renderer after type-only transpilation with injected rAF and color setter.

| Computed property | P1 | P2 |
|---|---|---|
| Minimum linear-RGB distance to neutral | 0.682612 | 0.396424 |
| Minimum pairwise color distance | 0.402079 | 0.322668 |
| Maximum relative luminance deviation from neutral | 63.3766% | 0.3032% |
| Maximum R/(R+G+B) | 0.500000 | 0.449102 |
| Colors satisfying original two-channel ≥100 difference from neutral | 0/6 | 0/6 |
| Nominal generator validity | 10,000/10,000 | 10,000/10,000 |
| Accepted total duration range across these seeds | 1,200–1,300 ms | 1,200–1,300 ms |

- RNG reproducibility: two runs with injected seed 42 reproduce segments/durations; secure nonces differ by design. Replay must store the complete issued challenge, not just a seed. These loops check implementation invariants, not statistical liveness performance or flash safety certification.
- Renderer counterexample (actual `runChallenge`, synthetic timing): P1 neutral 200 ms, then its first three colors for 334/333/333 ms; total 1,200 ms. Python `validate()` returns no violations. rAF callbacks at **0, 216, 550, 883, 1200 ms** paint neutral/color0/color1/color2/neutral. `skipped=[]`. Actual changes at 216/550/883/1200 fit **four transitions in 984 ms**. This violates the intended three-in-any-1000-ms rule despite a valid nominal challenge. The original existing renderer tests use a legacy 330 ms fixture; they do not establish the new constraint.
- Conclusion: supports the palette-distance amendment and nominal generator invariants; **refutes the assertion that nominal timing validation alone enforces displayed timing**. Amend ADR-005; fix rolling actual-timestamp safety, interruption, final return and inter-attempt transitions before real E1/E2. Do not claim Chroma feasibility or detector accuracy from these results.

## C1-1: Measurement-path repair software verification (2026-11-14)
- Question: does the corrected capture path enforce its application-timestamp contract and reject invalid data, without claiming physical liveness?
- Provenance: base commit `63668f9` plus uncommitted C1 changes. Final runtime source hashes and per-run metadata: `experiments/C1_measurement/browser_checks.json`. Windows, Chrome headless with a looping reference-face fake camera, Node 25.2.0, Python 3.10 host / 3.11 Docker. Model hashes unchanged. Dataset split: none; **synthetic/software checks only**.
- Changes tested: nominal 1200–1220 ms generation with 80 ms rendering reserve; actual 1300 ms capture cap; guarded neutral entry/colors/final neutral/UI exit; explicit preparation; actual style-application completion times; no catch-up; neutral keyframe/sensor timing checks; exact-issued-challenge and single-use upload.
- Results: original four-transition/984 ms regression reproduced failing, then fixed. Final suites: 136 fast backend, 14 model, 1 measurement-upload integration, 47 frontend unit plus 2 separate live TS↔Docker tests; lint/build/health/hash checks passed.
- Real-browser software checks: initial run 9/10 accepted, with one Vite upstream `ETIMEDOUT` on challenge issuance and no backend request; repeat 10/10; final application-completion-timestamp run 10/10. Injected 1400 ms main-thread stall aborted with `CAPTURE_OVERRUN`, no upload. First failure retained. Intermediate and final runs are labeled separately in the metadata.
- Across all three iterations: 29 accepted captures, two neutral keyframes each; all stored traces pass final server validation. Capture range 1208.4–1236.0 ms; full request-to-idle 2528.7–2586.3 ms, including preparation/release. This is **not** the official access-decision metric and does not satisfy/claim the two-second target.
- Conclusion: supports the C1 software invariants and invalid-capture rejection. Actual optical timing, camera exposure/WB stability, reflected-light features/separability and liveness/identity accuracy remain unmeasured. E1/E2 thresholds stay unchanged; no real E1/E2 result or G1 outcome follows from this check.
- Human follow-up: owner review/commit, then C2/T1.6; real rig/consent/data after C3 probe preparation. Details and limitations: `docs/C1_MEASUREMENT.md`.

## E4-1: C2 instrument compute timings (2026-11-14)
- Hypothesis: per-crop work (SCRFD + regions) fits the plan §9.6 E4 budget of ≤ 20 ms p95.
- Setup: `tools/bench_chroma.py --runs 60`; Windows 11, i7-13620H (16 threads), CPython 3.10.0, onnxruntime CPU, SCRFD `det_10g` with 2 intra-op threads; one Apache-2.0 reference face photo; no GPU. Compute only, not decision latency.
- Results (n = 60 each): SCRFD load 60 ms; first call 134 ms; 640 px preview with outlines p50 121 ms / p95 132 ms; 320 px captured-crop observation p50 30.6 ms / p95 41.9 ms; feature extraction on a 36-frame synthetic series p50 3.8 ms. Raw: `experiments/E4_models/chroma_bench.json`.
- Conclusion: **refutes** the ≤ 20 ms per-crop budget on this machine/config. Serial analysis of 36 crops ≈ 1.1 s, so analysing after capture would not fit a 2 s decision together with ≥ 1.2 s capture; work must overlap capture (M3 streaming) and/or use a lighter detector (`det_500m`) or more threads. Not yet tried; E4 on the real target instance is still pending.
- Decision proposed: none yet; revisit at G1 with E4 on EC2 and the det_500m variant.
- Follow-up (same machine, single reference crop, n = 60, detector only at 320 px, regions excluded): `det_10g` 2 threads p50 27.2 / p95 28.6 ms; 4 threads p50 14.9 / p95 19.1 ms; `det_500m` 2 threads p50 3.0 / p95 3.6 ms; 4 threads p50 2.2 / p95 2.7 ms. So 4 threads brings `det_10g` inside the 20 ms budget on this laptop, and `det_500m` is ~9x faster but scored 0.72 vs 0.76 on this one image. Whether `det_500m` is accurate enough for region placement and identity alignment is **not tested** (needs LFW/kiosk data; decision G-06 stays open). Ad-hoc measurement, not saved as an artifact.

## E1-1: camera control, laptop webcam self-run (2026-11-14) - INCONCLUSIVE
- Full write-up: `experiments/E1_camera/report.md`. Rig deviates from the plan (no card, laptop display, uncontrolled ROI).
- Solid: the camera is YUY2-only; 1280x720 delivers ~10 fps, 640x480 delivers 30.5-30.7 fps (interval std 3.4-3.6 ms); response delay ~55 ms; manual WB settable, exposure control not confirmed by read-back.
- Not solid: 3 manual-mode runs gave 5 / 1 / 4 detected steps and droop from -4 % to +34 % depending on the run; one run met every criterion, two did not. Auto mode: 7.5 fps, no detectable step.
- Conclusion: refutes the 1280x720@30 assumption for this camera; does not decide G-01. Needs the card rig (HUMAN_TASKS H-03/H-04).

## E3-0: network probe tool check (2026-11-14) - tool validation only
- `tools/net_probe.py` against a local backend (`experiments/E3_network/localhost_toolcheck.json`): RTT p50 0.54 ms, uplink ~2.5 Gbit/s. **These say nothing about a real network.**
- Real measurement: JPEG frame sizes from the reference crop: 256 px q0.9 = 14,787 B (3.55 Mbit/s at 30 fps), 256 px q0.8 = 10,246 B (2.46 Mbit/s), 192 px q0.8 = 7,111 B (1.71 Mbit/s). Content-dependent (one reference photo).
- E3 proper (RTT/uplink to a candidate AWS region) is blocked on the sandbox access code (H-01).

## E4-2: model latency matrix on this laptop (2026-11-14)
- `tools/bench_models.py --runs 60 --warmup 10`; full table in `experiments/E4_models/report.md`. i7-13620H, 16 threads, ORT CPU, one reference image, compute only.
- p95 highlights (1 / 2 / 4 threads): det_10g@640 212 / 216 / 120 ms; det_10g@256 90 / 41 / 20 ms; det_500m@640 52 / 24 / 14 ms; det_500m@256 12 / 3 / 3 ms; ArcFace R50 404 / 197 / 152 ms (p50 at 4 threads 104 ms); ArcFace MBF 20 / 13 / 7 ms; MiniFASNet V2 and V1SE 2-6 ms.
- Against plan budgets: per-crop (det@256 + regions, <= 20 ms): det_10g meets it only at 4 threads before regions are added; det_500m meets it at any thread count. Keyframe work (det@640 + R50 + 2x MiniFASNet, <= 300 ms): ~277 ms p95 at 4 threads (barely), ~419 ms at 2 threads (fails); with det_500m + MBF it is ~40 ms.
- Conclusion: the identity model (R50) is the latency driver, not liveness. Accuracy of the lighter det_500m / MBF is NOT measured (LFW check pending, G-06 open). P1 models (YOLOX-tiny, DINOv2) not measured. EC2 instance types not measured (H-01).
