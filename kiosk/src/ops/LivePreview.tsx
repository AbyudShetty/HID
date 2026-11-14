// Engineering instrument: the exact frame sent to the backend, with the backend's real SCRFD box, landmarks and region
// outlines. Nothing here is estimated client-side. ~3 Hz, one request in flight, paused during capture.
import { useEffect, useRef, useState } from "react";
import { postPreview, type PreviewResult } from "./api";

const COLORS: Record<string, string> = { forehead: "#f59e0b", nose: "#ef4444", cheek_l: "#22c55e", cheek_r: "#06b6d4", surround: "#a855f7", background: "#94a3b8" };

export function LivePreview({ video, active }: { video: HTMLVideoElement | null; active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [res, setRes] = useState<PreviewResult | null>(null);
  const [rtt, setRtt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!video || !active) return;
    let stopped = false;
    let inFlight = false;
    const grab = document.createElement("canvas");
    const tick = async () => {
      if (stopped || inFlight || video.readyState < 2 || !video.videoWidth) return;
      inFlight = true;
      try {
        const w = Math.min(640, video.videoWidth);
        grab.width = w;
        grab.height = Math.round((video.videoHeight * w) / video.videoWidth);
        grab.getContext("2d")!.drawImage(video, 0, 0, grab.width, grab.height);
        const blob: Blob = await new Promise((r, j) => grab.toBlob((b) => (b ? r(b) : j(new Error("encode failed"))), "image/jpeg", 0.8));
        const t0 = performance.now();
        const out = await postPreview(blob);
        const trip = performance.now() - t0;
        if (stopped) return;
        // draw the exact processed frame, then the server's overlays on top
        const c = canvasRef.current;
        if (c) {
          c.width = grab.width;
          c.height = grab.height;
          const g = c.getContext("2d")!;
          g.drawImage(grab, 0, 0);
          const [iw, ih] = out.image_size;
          const sx = c.width / iw, sy = c.height / ih;
          g.lineWidth = 2;
          for (const [name, r] of Object.entries(out.regions)) {
            g.strokeStyle = COLORS[name] ?? "#fff";
            for (const path of r.paths) {
              if (path.length < 2) continue;
              g.beginPath();
              path.forEach(([x, y], i) => (i ? g.lineTo(x * sx, y * sy) : g.moveTo(x * sx, y * sy)));
              g.closePath();
              g.stroke();
            }
          }
          if (out.face) {
            const [x1, y1, x2, y2] = out.face.box;
            g.strokeStyle = "#22c55e";
            g.lineWidth = 3;
            g.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy);
            g.fillStyle = "#fff";
            for (const [x, y] of out.face.landmarks) g.fillRect(x * sx - 2, y * sy - 2, 4, 4);
          }
        }
        setRes(out);
        setRtt(trip);
        setError(null);
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : String(e));
      } finally {
        inFlight = false;
      }
    };
    const id = setInterval(tick, 350);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [video, active]);

  return (
    <fieldset data-testid="live-preview">
      <legend>Live backend measurement (SCRFD + regions; experimental, not a liveness decision)</legend>
      {error && <p style={{ color: "#b91c1c" }} data-testid="preview-error">Backend preview error: {error}</p>}
      {!active && <p className="hint">paused (capture running or camera off)</p>}
      <canvas ref={canvasRef} data-testid="preview-canvas" style={{ maxWidth: 480, background: "#000" }} />
      {res && (
        <>
          <p data-testid="preview-summary">
            {res.face ? `face score ${res.face.score.toFixed(2)}, ${res.significant_faces} significant face(s)` : "no face detected by the backend"} · server {res.timings_ms.total.toFixed(0)} ms
            (SCRFD {res.timings_ms.scrfd_inference.toFixed(0)} ms, regions {res.timings_ms.regions.toFixed(0)} ms) · round trip {rtt?.toFixed(0)} ms
            {res.model_load_ms && res.model_load_ms > 50 ? ` · model load ${res.model_load_ms.toFixed(0)} ms (cold)` : ""}
          </p>
          <table>
            <thead><tr><th>region</th><th>linear RGB mean</th><th>pixels</th><th>clipped</th></tr></thead>
            <tbody>
              {Object.entries(res.regions).filter(([n]) => n !== "face_core").map(([n, r]) => (
                <tr key={n}><td style={{ color: COLORS[n] }}>{n}</td><td>{r.mean_rgb ? r.mean_rgb.map((v) => v.toFixed(3)).join(", ") : "—"}</td><td>{r.pixels}</td><td>{(r.clipped_fraction * 100).toFixed(0)}%</td></tr>
              ))}
            </tbody>
          </table>
          <p className="hint">Region geometry is an approximation of skin areas, not semantic segmentation. Means are linearised sRGB over non-clipped pixels.</p>
        </>
      )}
    </fieldset>
  );
}
