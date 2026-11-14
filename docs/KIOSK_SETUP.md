# Kiosk setup checklist (plan §21.2)

Status: **draft from the plan; updated with what E1 teaches us.** Nothing below has been verified on the real kiosk rig yet.

## Hardware and placement
- [ ] External monitor ≥ 24" at **100 % brightness**, facing the user. The display is the light source for the challenge.
- [ ] Webcam on top of the display; face distance 45–65 cm.
- [ ] Laptop plugged into mains power.
- [ ] Neutral, non-reflective background; **no window behind the user**; venue lighting as at the demo.
- [ ] Second screen for the operator view.

## Windows settings (any of these distorts the emitted light)
- [ ] Night light OFF
- [ ] "Change brightness based on content" (Intel/AMD power saving) OFF
- [ ] HDR OFF
- [ ] Battery saver OFF; power mode "Best performance"
- [ ] Notifications / Focus assist ON (no pop-ups during capture); sleep OFF
- [ ] Display color profile unchanged between calibration and demo

## Browser
- [ ] Chrome in kiosk mode: `chrome.exe --kiosk --use-fake-ui-for-media-stream=false http://localhost:5173/kiosk` (camera permission pre-granted for the kiosk origin)
- [ ] Camera lock method per decision G-01 (pending E1): browser constraints / pre-lock / native agent
- [ ] Power-line frequency set for the venue (50 Hz / 60 Hz); record it in the kiosk profile

## Calibration (morning of the demo)
- [ ] `/ops/calibrate` (lag, noise floor, ambient) green — page arrives in M7
- [ ] 10 genuine attempts by the team; check the RV rate
- [ ] Policy thresholds and models are **frozen**; only the kiosk profile may change
