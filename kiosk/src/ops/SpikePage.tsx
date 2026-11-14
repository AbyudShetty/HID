// M1 spike capture page (plan T1.2): records real challenge sessions with the production capture modules and uploads
// each bundle to the backend. Used to collect the E2 data. The decision is NOT shown here (collect mode hides it).
import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserFrameSource } from "../capture/browserSource";
import { centerFaceBox, computeCropBox, countSignificantFaces, largestBox } from "../capture/crop";
import { loadFaceDetector, type FramingDetector } from "../capture/faceDetector";
import { recordSession, renderWith } from "../capture/recordSession";
import { packBundle } from "../net/bundle";
import type { Box, CameraInfo } from "../types/protocol";
import { LivePreview } from "./LivePreview";
import { ApiError, getCollectChallenge, postBundle, postMeasure, type UploadResult } from "./api";
import { buildLabel, CAPTURE_PROCEDURES, DEFAULT_FORM, LIGHTINGS, SKIN_TONES, SPECIES_BY_FAMILY, type LabelForm } from "./labels";

const FORM_KEY = "hid_spike_form";
const SETTINGS_KEY = "hid_spike_settings";

interface Settings {
  countdown: number;
  palette: "" | "P1" | "P2";
  lock: "none" | "browser";
  exposureTime: string;
  colorTemperature: string;
  fullscreen: boolean;
}
const DEFAULT_SETTINGS: Settings = { countdown: 3, palette: "", lock: "none", exposureTime: "", colorTemperature: "", fullscreen: true };

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface LogRow {
  at: string;
  session_id: string;
  summary: string;
  result?: UploadResult;
  error?: string;
  stats?: { nCrops: number; nKeyframes: number; cropFps: number | null; skipped: number[]; captureTimeSource: string };
}

export function SpikePage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const boxCanvasRef = useRef<HTMLCanvasElement>(null);
  const sourceRef = useRef<BrowserFrameSource | null>(null);
  const detectorRef = useRef<FramingDetector | null>(null);
  const facesRef = useRef<{ t: number; boxes: Box[] }>({ t: 0, boxes: [] });

  const [form, setForm] = useState<LabelForm>(() => load(FORM_KEY, DEFAULT_FORM));
  const [settings, setSettings] = useState<Settings>(() => load(SETTINGS_KEY, DEFAULT_SETTINGS));
  const [camInfo, setCamInfo] = useState<CameraInfo | null>(null);
  const [camStatus, setCamStatus] = useState("camera off");
  const [detectorStatus, setDetectorStatus] = useState("not loaded");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<LogRow[]>([]);

  useEffect(() => save(FORM_KEY, form), [form]);
  useEffect(() => save(SETTINGS_KEY, settings), [settings]);

  // face detection loop for the on-screen guide and the crop box
  useEffect(() => {
    const id = setInterval(() => {
      const video = videoRef.current;
      const det = detectorRef.current;
      const canvas = boxCanvasRef.current;
      if (!video || !det || video.readyState < 2) return;
      const boxes = det.detect(video, performance.now());
      facesRef.current = { t: performance.now(), boxes };
      if (canvas) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const g = canvas.getContext("2d");
        if (g) {
          g.clearRect(0, 0, canvas.width, canvas.height);
          g.lineWidth = 3;
          g.strokeStyle = boxes.length === 1 ? "#22c55e" : "#f59e0b";
          for (const [x, y, w, h] of boxes) g.strokeRect(x, y, w, h);
        }
      }
    }, 100);
    return () => clearInterval(id);
  }, []);

  useEffect(() => () => {
    sourceRef.current?.close();
    detectorRef.current?.close();
  }, []);

  const startCamera = useCallback(async () => {
    if (!videoRef.current) return;
    setCamStatus("starting…");
    try {
      sourceRef.current?.close();
      const src = await BrowserFrameSource.open(videoRef.current, {
        width: 1280,
        height: 720,
        fps: 30,
        lock: {
          mode: settings.lock,
          exposureTime: settings.exposureTime ? Number(settings.exposureTime) : undefined,
          colorTemperature: settings.colorTemperature ? Number(settings.colorTemperature) : undefined,
        },
      });
      sourceRef.current = src;
      setCamInfo(src.info());
      setCamStatus("camera on");
      if (!detectorRef.current) {
        const r = await loadFaceDetector();
        if (r.ok) {
          detectorRef.current = r.detector;
          setDetectorStatus("MediaPipe ready");
        } else {
          setDetectorStatus(`no detector: ${r.reason}. Falling back to a fixed centre crop (recorded as client_face_box = null).`);
        }
      }
    } catch (e) {
      setCamStatus(`camera error: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [settings.lock, settings.exposureTime, settings.colorTemperature]);

  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const record = useCallback(async (measureOnly = false) => {
    const built = measureOnly ? { label: null } : buildLabel(form);
    if ("errors" in built) return setMessage(built.errors.join("; "));
    setReport(null);
    const src = sourceRef.current;
    const overlay = overlayRef.current;
    if (!src || !overlay) return setMessage("start the camera first");
    setBusy(true);
    const startedAt = new Date().toISOString();
    let sessionId = "(none)";
    try {
      if (settings.fullscreen && !document.fullscreenElement) {
        try {
          await document.documentElement.requestFullscreen(); // needs the click's user gesture, so do it first
        } catch {
          /* not fatal: the overlay still covers the viewport */
        }
      }
      for (let i = settings.countdown; i > 0; i--) {
        setMessage(`Recording in ${i}… hold still, face the screen`);
        await sleep(1000);
      }
      setMessage("recording…");
      const ch = await getCollectChallenge(settings.palette || undefined);
      sessionId = ch.session_id;
      const frame = src.size();
      let faceBox: Box | null = null;
      if (detectorRef.current) {
        const { t, boxes } = facesRef.current;
        if (performance.now() - t > 500 || countSignificantFaces(boxes) === 0) throw new Error("no face detected: position the face in view and retry");
        if (countSignificantFaces(boxes) > 1) throw new Error("more than one face in frame");
        faceBox = largestBox(boxes);
      }
      const crop = computeCropBox(faceBox ?? centerFaceBox(frame), frame, ch.capture_config.context_scale);
      const rec = await recordSession(
        {
          challenge: ch.challenge,
          sessionId: ch.session_id,
          cropBox: crop,
          faceBox,
          cropSize: ch.capture_config.crop_size,
          jpegQuality: ch.capture_config.jpeg_quality,
          keyframeCount: ch.capture_config.keyframe_count,
          keyframeMaxWidth: ch.capture_config.keyframe_max_width,
          keyframeSettleMs: 60,
          meta: {
            purpose: "collect",
            kiosk_id: import.meta.env.VITE_KIOSK_ID ?? "kiosk-01",
            client_version: "0.1.0",
            server_version: ch.server_version,
            policy_version: ch.policy_version,
            kiosk_profile_version: null,
            display: { width: window.screen.width, height: window.screen.height, device_pixel_ratio: window.devicePixelRatio },
          },
          label: built.label,
        },
        {
          source: src,
          render: renderWith(ch.challenge, {
            raf: (cb) => requestAnimationFrame(cb),
            now: () => performance.now(),
            interrupted: () => document.hidden,
            setActive: (active) => { overlay.style.display = active ? "block" : "none"; },
            setColor: (rgb) => {
              overlay.style.background = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
            },
          }),
          now: () => performance.now(),
          isoNow: () => new Date().toISOString(),
        },
      );
      if (measureOnly) {
        const rep = await postMeasure(packBundle(rec.entries));
        setReport(rep);
        setMessage(`measured (nothing stored); prep ${Math.round(rec.stats.preparationMs)} ms; capture ${Math.round(rec.stats.captureMs)} ms`);
        return;
      }
      if (!built.label) throw new Error("label required");
      const result = await postBundle(packBundle(rec.entries));
      const stats = { nCrops: rec.stats.nCrops, nKeyframes: rec.stats.nKeyframes, cropFps: rec.stats.cropFps, skipped: rec.stats.skippedSegments, captureTimeSource: rec.stats.captureTimeSource };
      setLog((l) => [{ at: startedAt, session_id: sessionId, summary: `${built.label!.class}${built.label!.pai_species !== "none" ? ` / ${built.label!.pai_species}` : ""}`, result, stats }, ...l]);
      const timing = `prep ${Math.round(rec.stats.preparationMs)} ms; capture ${Math.round(rec.stats.captureMs)} ms; request→idle ${Math.round(rec.stats.requestToIdleMs)} ms`;
      setMessage(result.qc.warnings.length ? `uploaded with warnings: ${result.qc.warnings.join("; ")}; ${timing}` : `uploaded OK; ${timing}`);
    } catch (e) {
      const msg = e instanceof ApiError || e instanceof Error ? e.message : String(e);
      setLog((l) => [{ at: startedAt, session_id: sessionId, summary: "FAILED", error: msg }, ...l]);
      setMessage(`failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }, [form, settings]);

  const set = <K extends keyof LabelForm>(k: K, v: LabelForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const setS = <K extends keyof Settings>(k: K, v: Settings[K]) => setSettings((s) => ({ ...s, [k]: v }));

  return (
    <div className="panel spike">
      <h2>Spike capture (E1/E2 data collection)</h2>
      <p className="hint">
        Records the real challenge with the production capture modules and uploads the bundle. Requires the operator token (header). The decision is hidden. Everyone recorded must have signed a consent
        form (docs/CONSENT_FORM.md).
      </p>

      <div className="row">
        <div>
          <div className="videobox">
            <video ref={videoRef} playsInline muted data-testid="preview" />
            <canvas ref={boxCanvasRef} className="boxes" />
          </div>
          <p data-testid="camera-status">{camStatus}</p>
          <p className="hint">{detectorStatus}</p>
          {camInfo && (
            <details>
              <summary>
                {camInfo.label ?? "camera"} — {camInfo.width}x{camInfo.height} @ {camInfo.fps || "?"} fps, lock: {camInfo.lock_method}
              </summary>
              <pre>{JSON.stringify({ settings: camInfo.settings, capabilities: camInfo.capabilities }, null, 1)}</pre>
            </details>
          )}
        </div>

        <fieldset>
          <legend>Camera</legend>
          <label>Lock method
            <select value={settings.lock} onChange={(e) => setS("lock", e.target.value as Settings["lock"])}>
              <option value="none">none (auto exposure / WB)</option>
              <option value="browser">browser constraints (manual)</option>
            </select>
          </label>
          <label>exposureTime (browser units, blank = leave)
            <input value={settings.exposureTime} onChange={(e) => setS("exposureTime", e.target.value)} />
          </label>
          <label>colorTemperature K (blank = leave)
            <input value={settings.colorTemperature} onChange={(e) => setS("colorTemperature", e.target.value)} />
          </label>
          <button data-testid="start-camera" onClick={startCamera} disabled={busy}>Start / restart camera</button>
        </fieldset>
      </div>

      <LivePreview video={camStatus === "camera on" ? videoRef.current : null} active={camStatus === "camera on" && !busy} />

      <fieldset>
        <legend>Label (plan §8.6)</legend>
        <div className="grid">
          <label>subject_id<input value={form.subject_id} onChange={(e) => set("subject_id", e.target.value)} /></label>
          <label>presenter_id<input value={form.presenter_id} onChange={(e) => set("presenter_id", e.target.value)} /></label>
          <label>consent_id<input value={form.consent_id} onChange={(e) => set("consent_id", e.target.value)} /></label>
          <label>operator<input value={form.operator} onChange={(e) => set("operator", e.target.value)} /></label>
          <label>class
            <select value={form.cls} onChange={(e) => {
              const cls = e.target.value as LabelForm["cls"];
              setForm((f) => ({ ...f, cls, pai_family: cls === "bona_fide" ? "none" : f.pai_family === "none" ? "print" : f.pai_family, pai_species: cls === "bona_fide" ? "none" : f.pai_species === "none" ? SPECIES_BY_FAMILY.print[0] : f.pai_species }));
            }}>
              <option value="bona_fide">bona fide</option>
              <option value="attack">attack</option>
            </select>
          </label>
          {form.cls === "bona_fide" ? (
            <label>enrolled? <input type="checkbox" checked={form.enrolled} onChange={(e) => set("enrolled", e.target.checked)} /></label>
          ) : (
            <>
              <label>family
                <select value={form.pai_family} onChange={(e) => {
                  const fam = e.target.value as keyof typeof SPECIES_BY_FAMILY;
                  setForm((f) => ({ ...f, pai_family: fam, pai_species: SPECIES_BY_FAMILY[fam][0] }));
                }}>
                  {Object.keys(SPECIES_BY_FAMILY).map((f) => <option key={f}>{f}</option>)}
                </select>
              </label>
              <label>species
                {form.capture_procedure === "redteam" ? (
                  <input value={form.pai_species} onChange={(e) => set("pai_species", e.target.value)} placeholder="redteam_<description>" />
                ) : (
                  <select value={form.pai_species} onChange={(e) => set("pai_species", e.target.value)}>
                    {(SPECIES_BY_FAMILY[form.pai_family as keyof typeof SPECIES_BY_FAMILY] ?? []).map((s) => <option key={s}>{s}</option>)}
                  </select>
                )}
              </label>
              <label>instrument_id<input value={form.instrument_id} onChange={(e) => set("instrument_id", e.target.value)} placeholder="e.g. phone_pixel7_A" /></label>
            </>
          )}
          <label>procedure
            <select value={form.capture_procedure} onChange={(e) => set("capture_procedure", e.target.value as LabelForm["capture_procedure"])}>
              {CAPTURE_PROCEDURES.map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
          <label>lighting
            <select value={form.lighting} onChange={(e) => set("lighting", e.target.value as LabelForm["lighting"])}>{LIGHTINGS.map((l) => <option key={l}>{l}</option>)}</select>
          </label>
          <label>distance_cm<input value={form.distance_cm} onChange={(e) => set("distance_cm", e.target.value)} /></label>
          <label>glasses <input type="checkbox" checked={form.glasses} onChange={(e) => set("glasses", e.target.checked)} /></label>
          <label>skin tone (optional)
            <select value={form.skin_tone_bucket} onChange={(e) => set("skin_tone_bucket", e.target.value as LabelForm["skin_tone_bucket"])}>{SKIN_TONES.map((s) => <option key={s}>{s}</option>)}</select>
          </label>
          <label>notes<input value={form.notes} onChange={(e) => set("notes", e.target.value)} /></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Recording</legend>
        <label>palette
          <select value={settings.palette} onChange={(e) => setS("palette", e.target.value as Settings["palette"])}>
            <option value="">server default</option><option>P1</option><option>P2</option>
          </select>
        </label>
        <label>countdown s<input type="number" min={0} max={10} value={settings.countdown} onChange={(e) => setS("countdown", Number(e.target.value))} /></label>
        <label>fullscreen <input type="checkbox" checked={settings.fullscreen} onChange={(e) => setS("fullscreen", e.target.checked)} /></label>
        <button data-testid="record" onClick={() => record(false)} disabled={busy}>{busy ? "recording…" : "Record session (labelled, stored)"}</button>
        <button data-testid="measure" onClick={() => record(true)} disabled={busy}>Measure only — no storage</button>
        <p data-testid="status-message">{message}</p>
      </fieldset>

      {report && (
        <fieldset data-testid="report">
          <legend>Chroma measurement (experimental — NOT a liveness or access decision; E1/E2 not yet performed)</legend>
          <pre style={{ maxHeight: 360, overflow: "auto", fontSize: 12 }}>{JSON.stringify(report, null, 1)}</pre>
        </fieldset>
      )}
      <h3>This page's recordings ({log.filter((r) => r.result).length} uploaded)</h3>
      <table data-testid="log">
        <thead><tr><th>time</th><th>session</th><th>label</th><th>crops</th><th>fps</th><th>kf</th><th>result</th></tr></thead>
        <tbody>
          {log.map((r) => (
            <tr key={r.session_id + r.at}>
              <td>{r.at.slice(11, 19)}</td><td>{r.session_id}</td><td>{r.summary}</td>
              <td>{r.stats?.nCrops ?? "—"}</td><td>{r.stats?.cropFps?.toFixed(1) ?? "—"}</td><td>{r.stats?.nKeyframes ?? "—"}</td>
              <td>{r.error ? `ERROR ${r.error}` : r.result?.qc.warnings.length ? `warn: ${r.result.qc.warnings.join("; ")}` : "ok"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div ref={overlayRef} className="challenge-overlay" data-testid="overlay">
        <span>Hold still</span>
      </div>
    </div>
  );
}
