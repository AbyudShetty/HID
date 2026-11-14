// Pure transformation of a /measure report into plot series. Missing measurements stay missing (null): never interpolated.
export interface ObservationLike {
  t_ms: number;
  file: string;
  image_size: [number, number];
  face: { box: number[]; score: number; landmarks: number[][] } | null;
  regions: Record<string, { mean_rgb: number[] | null; paths: number[][][]; pixels: number; clipped_fraction: number }>;
}
export interface MeasureReport {
  status: string;
  reasons: string[];
  warnings: string[];
  features: Record<string, number | null>;
  observations: ObservationLike[];
  emitted: number[][];
  timing: { capture_end_ms: number; idle_at_ms: number; transitions: { state: string; rgb: number[]; t_display: number }[] };
  timing_summary_ms?: Record<string, number>;
  neutral_keyframes?: string[];
}

export type Rgb = (number | null)[][]; // [channel][frame]

export interface PlotModel {
  t: number[];
  emitted: Rgb;
  regions: Record<"face_core" | "surround" | "background", Rgb>;
  transitionsMs: number[];
  lagMs: number | null;
  missing: Record<string, number>; // frames without a usable mean per region
}

const REGIONS = ["face_core", "surround", "background"] as const;

export function buildPlotModel(r: MeasureReport): PlotModel {
  const n = r.observations.length;
  if (r.emitted.length !== n) throw new Error(`emitted trace has ${r.emitted.length} samples for ${n} frames`);
  const t = r.observations.map((o) => o.t_ms);
  const emitted: Rgb = [0, 1, 2].map((c) => r.emitted.map((e) => e[c]));
  const regions = {} as PlotModel["regions"];
  const missing: Record<string, number> = {};
  for (const name of REGIONS) {
    regions[name] = [0, 1, 2].map((c) => r.observations.map((o) => o.regions[name]?.mean_rgb?.[c] ?? null));
    missing[name] = r.observations.filter((o) => !o.regions[name]?.mean_rgb).length;
  }
  const lag = r.features.lag_ms;
  return { t, emitted, regions, transitionsMs: r.timing.transitions.map((x) => x.t_display), lagMs: typeof lag === "number" ? lag : null, missing };
}

/** SVG path with gaps where values are null. Domain/range are caller-supplied so panels can share an x axis. */
export function linePath(t: number[], v: (number | null)[], x: (t: number) => number, y: (v: number) => number): string {
  let d = "";
  let pen = false;
  for (let i = 0; i < t.length; i++) {
    const val = v[i];
    if (val === null || !Number.isFinite(val)) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${x(t[i]).toFixed(1)} ${y(val).toFixed(1)}`;
    pen = true;
  }
  return d;
}

export function extent(series: Rgb[]): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of series) for (const ch of s) for (const v of ch) if (v !== null && Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  if (!Number.isFinite(lo)) return [0, 1];
  if (hi - lo < 1e-6) return [lo - 0.01, hi + 0.01];
  const pad = (hi - lo) * 0.08;
  return [lo - pad, hi + pad];
}
