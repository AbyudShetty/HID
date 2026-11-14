import { describe, expect, it } from "vitest";
import { buildPlotModel, extent, linePath, type MeasureReport } from "./plotModel";

const obs = (t: number, face: number[] | null) => ({
  t_ms: t, file: `crops/${t}.jpg`, image_size: [256, 256] as [number, number], face: null,
  regions: { face_core: { mean_rgb: face, paths: [], pixels: 10, clipped_fraction: 0 }, surround: { mean_rgb: [0.2, 0.2, 0.2], paths: [], pixels: 5, clipped_fraction: 0 },
             background: { mean_rgb: null, paths: [], pixels: 0, clipped_fraction: 0 } },
});
const report = (over: Partial<MeasureReport> = {}): MeasureReport => ({
  status: "ok", reasons: [], warnings: [], features: { lag_ms: 65 },
  observations: [obs(0, [0.3, 0.2, 0.1]), obs(33, null), obs(66, [0.4, 0.3, 0.2])],
  emitted: [[0.6, 0.6, 0.6], [0.1, 0.2, 1], [0.1, 0.2, 1]],
  timing: { capture_end_ms: 1200, idle_at_ms: 2200, transitions: [{ state: "challenge", rgb: [205, 205, 205], t_display: -1000 }, { state: "idle", rgb: [205, 205, 205], t_display: 2200 }] },
  ...over,
});

describe("buildPlotModel", () => {
  it("keeps missing means as null and counts them per region (never imputes)", () => {
    const m = buildPlotModel(report());
    expect(m.regions.face_core[0]).toEqual([0.3, null, 0.4]);
    expect(m.missing).toEqual({ face_core: 1, surround: 0, background: 3 });
    expect(m.emitted[2]).toEqual([0.6, 1, 1]);
    expect(m.lagMs).toBe(65);
    expect(m.transitionsMs).toEqual([-1000, 2200]);
  });
  it("reports an absent lag as null and rejects a misaligned emitted trace", () => {
    expect(buildPlotModel(report({ features: { lag_ms: null } })).lagMs).toBeNull();
    expect(() => buildPlotModel(report({ emitted: [[0, 0, 0]] }))).toThrow(/emitted trace/);
  });
});

describe("linePath / extent", () => {
  const id = (v: number) => v;
  it("breaks the line at gaps instead of bridging them", () => {
    expect(linePath([0, 1, 2, 3], [1, 2, null, 4], id, id)).toBe("M0.0 1.0L1.0 2.0M3.0 4.0");
    expect(linePath([0, 1], [null, NaN], id, id)).toBe("");
  });
  it("computes a padded extent ignoring nulls, with a safe default", () => {
    const [lo, hi] = extent([[[0.2, null], [0.4], [0.3]]]);
    expect(lo).toBeLessThan(0.2);
    expect(hi).toBeGreaterThan(0.4);
    expect(extent([[[null]]])).toEqual([0, 1]);
    const [a, b] = extent([[[0.5, 0.5]]]);
    expect(b - a).toBeGreaterThan(0);
  });
});
