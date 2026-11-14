// Post-capture view of a /measure report: actual measured response plots and a selectable captured crop with the
// backend region overlay for that exact frame. Experimental diagnostics; no liveness or access decision.
import { useEffect, useMemo, useRef, useState } from "react";
import { buildPlotModel, extent, linePath, type MeasureReport, type PlotModel, type Rgb } from "./plotModel";

const CH = ["#ef4444", "#22c55e", "#3b82f6"];
const REGION_COLORS: Record<string, string> = { forehead: "#f59e0b", nose: "#ef4444", cheek_l: "#22c55e", cheek_r: "#06b6d4", surround: "#a855f7", background: "#94a3b8" };
const W = 520, H = 130, PAD = 34;

function Panel({ title, model, series, note }: { title: string; model: PlotModel; series: Rgb; note?: string }) {
  const [lo, hi] = extent([series]);
  const t0 = model.t[0] ?? 0, t1 = model.t[model.t.length - 1] ?? 1;
  const x = (t: number) => PAD + ((t - t0) / Math.max(1, t1 - t0)) * (W - PAD - 6);
  const y = (v: number) => H - 18 - ((v - lo) / (hi - lo)) * (H - 28);
  const marks = model.transitionsMs.filter((m) => m >= t0 && m <= t1);
  return (
    <figure style={{ margin: "8px 0" }}>
      <figcaption style={{ fontSize: 12, fontWeight: 600 }}>{title}</figcaption>
      <svg width={W} height={H} role="img" aria-label={title} style={{ background: "#fff", border: "1px solid #e2e8f0" }}>
        {marks.map((m) => <line key={m} x1={x(m)} x2={x(m)} y1={4} y2={H - 18} stroke="#cbd5e1" strokeDasharray="3 3" />)}
        {series.map((ch, c) => <path key={c} d={linePath(model.t, ch, x, y)} fill="none" stroke={CH[c]} strokeWidth={1.6} />)}
        <text x={2} y={12} fontSize={10} fill="#475569">{hi.toFixed(3)}</text>
        <text x={2} y={H - 20} fontSize={10} fill="#475569">{lo.toFixed(3)}</text>
        <text x={PAD} y={H - 4} fontSize={10} fill="#475569">{t0.toFixed(0)} ms</text>
        <text x={W - 60} y={H - 4} fontSize={10} fill="#475569">{t1.toFixed(0)} ms</text>
      </svg>
      {note && <div style={{ fontSize: 11, color: "#64748b" }}>{note}</div>}
    </figure>
  );
}

function CropViewer({ report, crops }: { report: MeasureReport; crops: Map<string, Uint8Array> }) {
  const [idx, setIdx] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const obs = report.observations[Math.min(idx, report.observations.length - 1)];
  useEffect(() => {
    let cancelled = false;
    const bytes = obs && crops.get(obs.file);
    const c = canvasRef.current;
    if (!bytes || !c) return;
    createImageBitmap(new Blob([bytes as BlobPart], { type: "image/jpeg" })).then((bmp) => {
      if (cancelled) return bmp.close();
      c.width = bmp.width;
      c.height = bmp.height;
      const g = c.getContext("2d")!;
      g.drawImage(bmp, 0, 0);
      bmp.close();
      const sx = c.width / obs.image_size[0], sy = c.height / obs.image_size[1];
      g.lineWidth = 2;
      for (const [name, r] of Object.entries(obs.regions)) {
        if (name === "face_core") continue;
        g.strokeStyle = REGION_COLORS[name] ?? "#fff";
        for (const p of r.paths) {
          if (p.length < 2) continue;
          g.beginPath();
          p.forEach(([px, py], i) => (i ? g.lineTo(px * sx, py * sy) : g.moveTo(px * sx, py * sy)));
          g.closePath();
          g.stroke();
        }
      }
      if (obs.face) {
        const [x1, y1, x2, y2] = obs.face.box;
        g.strokeStyle = "#22c55e";
        g.lineWidth = 3;
        g.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy);
      }
    });
    return () => { cancelled = true; };
  }, [obs, crops]);
  if (!obs) return null;
  return (
    <div data-testid="crop-viewer">
      <label style={{ fontSize: 12 }}>captured frame {idx + 1}/{report.observations.length} · t = {obs.t_ms.toFixed(0)} ms
        <input type="range" min={0} max={report.observations.length - 1} value={idx} onChange={(e) => setIdx(Number(e.target.value))} style={{ width: 300, display: "block" }} />
      </label>
      <canvas ref={canvasRef} style={{ maxWidth: 256, background: "#000" }} />
      <div style={{ fontSize: 11, color: "#64748b" }}>
        {obs.face ? `backend face score ${obs.face.score.toFixed(2)}` : "no face detected in this frame"}. The overlay is the backend region geometry for this frame (an approximation, not skin segmentation).
      </div>
    </div>
  );
}

export function ReportViewer({ report, crops }: { report: MeasureReport; crops: Map<string, Uint8Array> }) {
  const model = useMemo(() => { try { return buildPlotModel(report); } catch { return null; } }, [report]);
  const feats = Object.entries(report.features).filter(([, v]) => v !== null) as [string, number][];
  return (
    <fieldset data-testid="report">
      <legend>Chroma measurement: experimental diagnostics, NOT a liveness or access decision (E1/E2 not performed)</legend>
      <p data-testid="report-status"><b>status: {report.status}</b>{report.reasons.length ? ` | ${report.reasons.join(", ")}` : ""}</p>
      {report.warnings.length > 0 && <p style={{ fontSize: 12, color: "#92400e" }}>warnings: {report.warnings.join(", ")}</p>}
      {model ? (
        <>
          <Panel title="Emitted illumination (actual displayed trace, linear RGB)" model={model} series={model.emitted} note="dashed = actual displayed transitions" />
          <Panel title="Measured face_core response (linear RGB mean per frame)" model={model} series={model.regions.face_core} note={`${model.missing.face_core} frame(s) without a usable value (gaps, not interpolated)${model.lagMs !== null ? ` | best-correlation lag ${model.lagMs} ms (5 ms search grid; not physical precision)` : " | no lag estimate"}`} />
          <Panel title="Measured background response" model={model} series={model.regions.background} note={`${model.missing.background} frame(s) without a usable value`} />
        </>
      ) : <p>Plots unavailable: emitted trace and frames are inconsistent.</p>}
      <CropViewer report={report} crops={crops} />
      <details open><summary>Defined measurements ({feats.length})</summary>
        <table><tbody>{feats.map(([k, v]) => <tr key={k}><th>{k}</th><td>{Number(v).toPrecision(4)}</td></tr>)}</tbody></table>
      </details>
      {report.timing_summary_ms && <p style={{ fontSize: 12 }}>backend timing (ms): {Object.entries(report.timing_summary_ms).map(([k, v]) => `${k} ${v.toFixed(0)}`).join(" | ")}</p>}
      <details><summary>raw report JSON</summary><pre style={{ maxHeight: 300, overflow: "auto", fontSize: 11 }}>{JSON.stringify({ ...report, observations: `${report.observations.length} frames (omitted)` }, null, 1)}</pre></details>
    </fieldset>
  );
}
