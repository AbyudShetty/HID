# Pitch v0 (T1.11): draft, to be revised after gate G1

> Draft narrative only. **No number below is a result.** Every figure must be replaced by a measured value from `docs/RESULTS.md` (locked test) with its run id, n and confidence interval before it is spoken or shown.

## Core message
**"Is it a live person? Is it the right person? And if we are not sure, we ask instead of guessing. All inside two seconds."**

One-sentence idea (only if E2 passes; otherwise rewrite for the fallback): *The kiosk's own screen is a light we control. A real face close to the screen lights up much more than the wall behind it, and unevenly; a photo or a phone shows face and background on one flat surface, so they light up together.* Prior art (Face Flashing, NDSS 2018; AWS Rekognition Face Liveness) is credited on the slide; we claim engineering and evidence, not invention.

## Framing (official four-stage flow)
01 Capture, 02 Liveness detection, 03 Face authentication, 04 Decision (Allow / Request Additional Verification / Deny). Liveness and identity are separate stages with separate measurements: a photo of an enrolled person should show "identity: match, liveness: spoof, Deny".

## What the build can honestly say today (M1 evidence)
- A measurement instrument exists and is tested (capture, region measurements, plots), but **whether screen light separates real faces from prints and phone screens is unproven (E2 not run).**
- On the one webcam tried: frame delivery is fine at 640x480 (30 fps) but only ~10 fps at 1280x720; response delay about 55 ms; exposure/WB lock not yet confirmed (E1 inconclusive).
- Compute on a laptop: face detection and identity are affordable with the lighter models; the heavy identity model dominates the budget (E4).
- No identity matching, decision engine or kiosk screen exists yet.

## Slide outline (draft)
1. Hook: "Can you spot a spoof in two seconds?"
2. The problem as a door decision: attacks, liveness is not identity, 2 s, three outcomes.
3. Our framing: the four-stage flow with an honest "ask, don't guess" path.
4. The idea (conditional on E2) with a real measured compare view, prior art credited.
5. Live demo.
6. Results: headline cards with value, 95 percent CI, n, definition (locked test only).
7. Architecture and AWS: label every element measured vs designed.
8. Limits and roadmap (masks, injection, single rig, licensing).
9. Why HID: badge plus face, step-up, audit trail.

## Plain-language explanations
- **Liveness vs identity:** recognition says who; liveness says whether a real person is there. A photo of you passes recognition perfectly.
- **Light challenge (if it holds):** we briefly tint the screen; a real face close to it glows with that pattern much more than the wall behind it.
- **Why not blinking:** a video of you blinks too.
- **Confidence interval:** 0 failures in 50 tries means the true rate is probably below about 7 percent, not zero.
- **Locked test:** we freeze the system, record fresh test data, run once.
- **Request Additional Verification:** a guard who is unsure asks for ID; so do we (code or a person).

## Questions to send the organizers (HUMAN_TASKS H-02): not yet sent
Targets or illustrations for 99.4 / 99.2 / 0.2 / 0.6? System-level or matcher-only FAR/FRR? Pitch format and length? Venue network/projector/lighting? Sandbox lifetime? Do judges bring their own spoof materials?
