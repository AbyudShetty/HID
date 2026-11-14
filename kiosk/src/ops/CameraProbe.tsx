// E1 browser probe (plan §9.6 paths H1a/H1b): does a browser-controlled camera hold steady while the SCREEN changes colour?
// Records the mean linear RGB of a region of interest per frame and the actual times the screen changed, then asks the
// backend to apply the plan's E1 criteria (the same Python code as the native probe). No frames are stored or sent.
import { useRef, useState } from "react";
import { BrowserFrameSource } from "../capture/browserSource";
import { roiMeanLinear } from "../capture/roi";
import { apiPostJson } from "./api";

const NEUTRAL = "rgb(205,205,205)";
const COLORS = ["rgb(80,120,255)", "rgb(255,235,80)", "rgb(80,255,255)", "rgb(255,120,255)", "rgb(120,255,120)"];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function CameraProbe() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const srcRef = useRef<BrowserFrameSource | null>(null);
  const [lock, setLock] = useState<"none" | "browser">("browser");
  const [exposure, setExposure] = useState("");
  const [roi, setRoi] = useState("0.35,0.35,0.3,0.3");
  const [status, setStatus] = useState("camera off");
  const [info, setInfo] = useState<unknown>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);

  const start = async () => {
    try {
      srcRef.current?.close();
      const s = await BrowserFrameSource.open(videoRef.current!, { width: 640, height: 480, fps: 30, lock: { mode: lock, exposureTime: exposure ? Number(exposure) : undefined } });
      srcRef.current = s;
      setInfo(s.info());
      setStatus("camera on");
    } catch (e) {
      setStatus(`camera error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const run = async () => {
    const src = srcRef.current, ov = overlayRef.current, video = videoRef.current;
    if (!src || !ov || !video) return setStatus("start the camera first");
    setBusy(true);
    setResult(null);
    try {
      const frac = roi.split(",").map(Number) as [number, number, number, number];
      const cv = document.createElement("canvas");
      cv.width = 160; cv.height = 120;
      const g = cv.getContext("2d", { willReadFrequently: true })!;
      const t: number[] = [], rgb: number[][] = [], events: { t_ms: number; state: string }[] = [];
      let t0 = 0;
      let recording = true;
      const v = video as HTMLVideoElement & { requestVideoFrameCallback(cb: (n: number, m: { captureTime?: number }) => void): number };
      const loop = (now: number, meta: { captureTime?: number }) => {
        if (!recording) return;
        g.drawImage(video, 0, 0, cv.width, cv.height);
        const m = roiMeanLinear(g.getImageData(0, 0, cv.width, cv.height).data, cv.width, cv.height, frac);
        const ts = (meta.captureTime ?? now) - t0;
        if (m && ts > (t[t.length - 1] ?? -1)) { t.push(ts); rgb.push([...m]); }
        v.requestVideoFrameCallback(loop);
      };
      ov.style.display = "block";
      const apply = (state: "neutral" | "color", css: string) => {
        ov.style.background = css;
        events.push({ t_ms: performance.now() - t0, state });
      };
      t0 = performance.now();
      v.requestVideoFrameCallback(loop);
      apply("neutral", NEUTRAL);
      await sleep(2000);
      for (let k = 0; k < 5; k++) {
        apply("color", COLORS[k]);
        await sleep(2000);
        apply("neutral", NEUTRAL);
        await sleep(2000);
      }
      recording = false;
      ov.style.display = "none";
      const report = await apiPostJson<Record<string, unknown>>("/api/v1/experiments/e1/analyze", { t_ms: t, rgb, events, neutral_window_ms: [200, 1900] });
      setResult({ camera: src.info(), roi: frac, n_frames: t.length, report });
      setStatus("done");
    } catch (e) {
      ov.style.display = "none";
      setStatus(`failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const verdict = (result?.report as { verdict?: { checks: Record<string, boolean | null>; passes: boolean } } | undefined)?.verdict;
  return (
    <div className="panel">
      <h2>E1 camera probe (browser)</h2>
      <p className="hint">Point the camera at a matte white/grey card (or a face) 45-65 cm from the display and set the ROI over it. The screen shows neutral 2 s then a colour 2 s, five times. Only ROI means are analysed.</p>
      <video ref={videoRef} playsInline muted style={{ width: 320, background: "#000" }} />
      <p data-testid="probe-status">{status}</p>
      <label>lock <select value={lock} onChange={(e) => setLock(e.target.value as "none" | "browser")}><option value="browser">browser manual exposure/WB</option><option value="none">none (auto)</option></select></label>{" "}
      <label>exposureTime (blank = leave) <input value={exposure} onChange={(e) => setExposure(e.target.value)} /></label>{" "}
      <label>ROI x,y,w,h <input value={roi} onChange={(e) => setRoi(e.target.value)} /></label>{" "}
      <button data-testid="probe-start" onClick={start} disabled={busy}>Start camera</button>{" "}
      <button data-testid="probe-run" onClick={run} disabled={busy || status !== "camera on" && status !== "done"}>Run step test (~22 s)</button>
      {info !== null && <details><summary>applied camera settings (read back)</summary><pre style={{ fontSize: 11 }}>{JSON.stringify(info, null, 1)}</pre></details>}
      {verdict && (
        <div data-testid="probe-verdict">
          <h3>{verdict.passes ? "All E1 criteria met in this run" : "E1 criteria NOT met (or not measurable) in this run"}</h3>
          <table><tbody>{Object.entries(verdict.checks).map(([k, v]) => <tr key={k}><th>{k}</th><td>{v === null ? "not measurable" : String(v)}</td></tr>)}</tbody></table>
          <p className="hint">One run on an uncontrolled scene is not an E1 result. Repeat with the card, and export the JSON below into experiments/E1_camera/raw/.</p>
        </div>
      )}
      {result && <details><summary>JSON (copy into experiments/E1_camera/raw/)</summary><pre style={{ fontSize: 11, maxHeight: 260, overflow: "auto" }}>{JSON.stringify(result, null, 1)}</pre></details>}
      <div ref={overlayRef} style={{ display: "none", position: "fixed", inset: 0, zIndex: 9999 }} data-testid="probe-overlay" />
    </div>
  );
}
