# Human tasks

Things only a person can do (plan §2.4). Each entry: what / why / how / how long / status. The agent never records a result until the human reports it.

## Open

### H-01 — Redeem the AWS sandbox access code and share what it allows
- **Why:** blocks T1.8 (AWS inventory + E3 network) and T1.9 (E4 on EC2). Everything else proceeds locally.
- **How:** open https://tinyurl.com/hid-hackathon (redirects to AWS Workshop Studio `catalog.us-east-1.prod.workshops.aws/join`), enter the event access code, open the AWS console. Then either (a) configure the AWS CLI with the temporary credentials the console offers (`aws configure` or env vars) so `infra/scripts/inventory.sh` can run, or (b) tell the agent the region(s) shown and paste the results of the console checks listed in `infra/scripts/inventory.sh`.
- **Also record:** how long the account lives and what is wiped afterwards (ask the organizers if it is not shown).
- **Time:** ~15 min. **Status:** open.

### H-02 — Send the six organizer questions (plan §1.6)
1. Are the example figures (99.4 % liveness accuracy, 99.2 % face authentication accuracy, 0.2 % FAR, 0.6 % FRR) targets or illustrations? (Until answered we treat them as illustrative.)
2. Is FAR/FRR meant at the system level or for face matching only? (We report both, clearly labeled.)
3. Pitch format: duration, live demo vs. recorded video, Q&A length, whether judges test the kiosk hands-on, whether code is reviewed.
4. Venue: projector/screen, power, network (Wi-Fi quality, firewall on WebSockets), lighting.
5. AWS sandbox: lifetime, and does it stay live through judging?
6. Do judges bring their own spoof materials?
- **Why:** shapes pitch length, demo setup, and whether the example metrics are hard targets. **Time:** 10 min. **Status:** open. Record answers below when they arrive.

### H-03 — Hardware for E1/E2 (the go/no-go experiments)
- **Needed:** the webcam you intend to use for the demo (the laptop currently has a "USB2.0 HD UVC WebCam"; a Logitech C920/C922/Brio-class UVC camera with manual exposure/white balance is better if E1 shows the current one cannot be locked), an **external monitor ≥ 24"** facing the user (the display is the light source), a **matte white or neutral-grey card** (A4 printer paper on a grey backing is fine) and a tripod/stand for the camera.
- **Layout:** camera on top of the display; card (and later the face) 45–65 cm from the display, roughly where a face would be; no direct sunlight on the card; room lights as they will be at the demo.
- **Time:** 20 min setup. **Status:** open.

### H-04 — Run the E1 camera experiment (blocked on tooling and renderer fixes)
- **Correction from repository review:** `tools/camera_probe_native.py`, `experiments/E1_camera/README.md` and `report.md` do not exist; `/ops/camera-probe` is an explicit unimplemented route. The previous claim of a native self-run had no artifact and is withdrawn. **No E1 experiment has been conducted.**
- **Engineering prerequisites:** C1 timing/abort/cooldown correction is implemented and software-tested. Browser/native probes, synthetic step-response checks and reproducible GUI-camera instructions are owner C3 work (after C2/T1.6).
- **Then:** use the intended rig from H-03, run each capture path, record camera/OS/browser/lighting/settings and actual frame response, and export raw probe data. The engineer will provide tested exact commands when the tools exist.
- **Time:** ~30 min per camera once prepared. **Status:** open, not ready for execution. Do not treat the existing spike's reported `lock_applied` as evidence of a camera lock.

### H-05 — Consent, subjects, attack materials, and the E2 collection (plan §9.6 E2, §13.3, §13.4)
- **Before recording anyone:** sign `docs/CONSENT_FORM.md` (one per person). Pseudonymous ids `S001…`. Keep the name→id map **offline** (never in the repo).
- **Subjects:** ≥ 3 people (span of skin tones if at all possible).
- **Materials:** matte A4 laser print and glossy photo print of each subject (photos taken on a different day/device than the kiosk), 2 phones (one OLED) and 1 tablet or laptop screen, a phone video per subject (blinks + head motion), optionally flat paper masks (card stock, eye holes).
- **E2 recording sheet (≈150 sessions, ~1 h):** two lighting conditions (office overhead; dim). Per lighting: bona fide 10 per subject; `print_matte_a4` 10; `print_glossy_photo` 10; `replay_phone` 10; `screen_laptop` or `screen_tablet_lcd` 10; optional `mask_paper_flat` 5. Alternate palettes P1/P2 across sessions. Use the spike page `/ops/spike`.
- **Status:** open. Blocked on H-03/H-04 (a passing capture path) for the real run.

### H-06 — Approve gates
- G0 (lightweight) and G1 (the go/no-go for the primary architecture) need a human decision recorded in `docs/GATES.md`.

## Answers from organizers

_None yet._

## Takeover review checkpoint — owner input

### H-07 — Locate both surprise-challenge photographs
- C1 inspection: `docs/reference/` does not exist in this checkout. Only the original poster is available, now under ignored `.local/`. Please add the two surprise photographs or provide their actual paths. The engineer has used your transcription and has not claimed visual verification of either photograph.
- Needed before freezing surprise requirements; does not prevent safe tooling work. **Status:** open.

### H-08 — Architecture approvals recorded (resolved)
- Owner approved ADR-001–004, ADR-005 amendment, shared Python logic in an independent lightweight local runtime and central service, SQLite cache/outbox, signed versioned campus policies, encrypted limited identity templates and automatic audit synchronization.
- Restricted offline ALLOW is approved only under every guard, with maximum 15-minute revocation staleness (implementation refuses at age ≥900 seconds). Successful step-up still requires authorization. No elaborate gateway, microservice ecosystem or Kubernetes.
- `cryptography` and `tzdata` are approved when needed. Neither was installed or added during C1.
- ADR-005 is implemented/tested at C1; remaining architecture is scheduled, not falsely marked implemented. No repeat approval is needed for these choices; E1/E2/G1 remain evidence-gated.

### H-09 — Checkpoints, Git and available experiment time
- Per your latest instruction, stop after meaningful milestones for owner review/commits/manual verification. C1 is the current checkpoint; see `docs/CHECKPOINTS.md` for exact Git commands. The engineer never stages, commits, pushes, amends or rewrites history.
- Please confirm submission deadline and available camera/monitor/consenting-subject collection time so the experiment schedule can be realistic. No answer is assumed.
- C1 software verification is complete; no real collection is required to accept this checkpoint. Review `C1_MEASUREMENT.md` and run your own commit commands in `CHECKPOINTS.md`. Prepare camera/display/consent for owner C3 after the probe tooling is ready. The current spike includes explicit preparation overhead and makes no two-second access claim.
- **Status:** C1 ready for owner review/commit. C2/T1.6 next; real E1/E2 remain pending. Local working plan is `.local/plan.md`, deliberately ignored by Git.
