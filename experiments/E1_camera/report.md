# E1: camera control. Report (laptop webcam, self-run; NOT the specified rig)

**Verdict: inconclusive. E1 is not established and the capture path (G-01) is not decided.** What was measured is real; what it supports is limited.

## Setup (what was and was not controlled)
- Camera: "USB2.0 HD UVC WebCam" (built-in/USB), Windows 11, OpenCV 5.0.0 DirectShow. Display: the laptop's own screen (plan wants an external monitor facing the user).
- **No matte white/grey card.** The ROI (central 30 percent x 30 percent of the frame) saw whatever was in front of the camera, uncontrolled and possibly moving. This is the main reason step response was inconsistent.
- Protocol: neutral 2 s, then colour 2 s, five times (plan P1 colours), steps 2 s apart. Only ROI means were stored (`experiments/E1_camera/raw/*.json`, gitignored); no frames were saved. Event times are when the window update returned, not photon time.
- Metrics and pass criteria: `backend/app/experiments/e1.py` (unit-tested on synthetic known droop/lag/flicker). The same code backs the browser probe.

## Findings that are solid (frame delivery)
| Finding | Evidence |
|---|---|
| The webcam offers only uncompressed YUY2; an MJPG request is ignored | read back FOURCC = YUY2 after requesting MJPG |
| **1280x720 is capped at ~10 fps** (USB2 bandwidth); **640x480 gives 30.7 fps** | bare capture test, 60 frames each; probe runs: 9.9 / 10.1 fps at 720p |
| At 640x480 with manual exposure/WB: 30.5-30.6 fps, interval std 3.4-3.6 ms | 3 runs |
| Display-to-camera response delay about 55-56 ms | median onset lag 54.6 / 55.5 / 55.9 ms (3 runs); includes display, camera exposure/readout and our timestamp slack |
| In auto mode the frame rate collapsed to 7.5 fps and no screen-light step was detectable | 1 run (auto exposure/WB at 640x480) |
| Manual white balance can be set through DirectShow (auto_wb 1 to 0, temperature 4600 to 4500 read back) | property read-back; **exposure/auto-exposure read back as -6 / -1 both before and after, so exposure control was NOT confirmed** |

Consequence: the plan's 1280x720 @ 30 fps assumption is false for this camera. 640x480 is enough for ROI means and 256 px crops, but the capture config (G-04) and any kiosk camera choice must account for it. A UVC camera with MJPG (e.g. C920 class) is the likely fix; not tested.

## Findings that are NOT solid (step response and droop)
Three manual-mode runs at 640x480 (exposure -6, WB 4500):
| Run | steps detected | median droop (R, G, B) | flicker ratio (peak Hz) | all criteria |
|---|---|---|---|---|
| 1 | 5 | -1.2 %, -4.2 %, -0.6 % | 1.91 (0.6 Hz) | met |
| 2 | 1 | undefined, undefined, -5.1 % | 2.06 (8.1 Hz) | not met (too few steps; flicker ratio over 2.0) |
| 3 | 4 | +6.0 %, -1.9 %, **+33.8 %** | 1.70 (0.6 Hz) | not met (blue droop 34 %) |

Run 1 alone would look like a pass; runs 2-3 show it is not repeatable on an uncontrolled scene. A 34 percent droop in one channel could be auto-adaptation, subject movement or scene change; the data cannot separate them. Passing or failing here says little about the camera until the card rig is used.

## What this does and does not decide
- Does support: manual control (at least white balance) is reachable from native code; frame rate/jitter are fine at 640x480; the response delay is about 55 ms.
- Does not establish: that exposure can be locked (read-back never changed); that droop is within 10 percent on a controlled target; whether the browser path (H1a) works at all (the browser probe page `/ops/camera-probe` is built and typechecked but has not been run on a real camera).

## To finish E1 (human, about 30 minutes; docs/HUMAN_TASKS.md H-03/H-04)
1. External monitor facing the user, matte white/grey card 45-65 cm away, room lights as at the demo, camera on 640x480.
2. Native: `.venv-host\Scripts\python tools\camera_probe_native.py --mode manual --exposure -6 --wb 4500 --name rig_manual_1` (repeat at least 5 times; also `--mode auto` once for contrast; try other exposure values).
3. Browser: `/ops/camera-probe` on the kiosk display (lock = browser, then none), export the JSON.
4. Pass per the plan: droop <= 10 percent on all channels with a detectable step, fps >= 25, interval std <= 8 ms, no flicker peak above the 2x ratio, repeatable across runs.

Decision proposed: none yet (G-01 stays at its default, native agent, until the rig result exists).
