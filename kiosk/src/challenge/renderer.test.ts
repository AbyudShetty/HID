import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import type { Challenge, RGB } from "../types/protocol";
import { planSegments, runChallenge, TransitionGuard, type RenderDeps } from "./renderer";

const challenge: Challenge = { ...samples.server["session.ready"].challenge as unknown as Challenge,
  segments: samples.server["session.ready"].challenge.segments.map((s) => ({ ...s, rgb: s.rgb as RGB, duration_ms: 340 })), total_ms: 1220 };
const frames = (from: number, to: number, period = 1000 / 60) => {
  const out: number[] = [];
  for (let t = from; t <= to; t += period) out.push(t);
  return out;
};
function rig(frameTimes: number[], guard = new TransitionGuard(), rafOffset = 0) {
  const painted: { rgb: RGB; ts: number }[] = [];
  const active: { active: boolean; ts: number }[] = [];
  let cb: ((ts: number) => void) | null = null;
  let current = frameTimes[0] ?? 0;
  const deps: RenderDeps = {
    raf: (fn) => { cb = fn; }, now: () => current, guard,
    setColor: (rgb) => painted.push({ rgb, ts: current }),
    setActive: (a) => active.push({ active: a, ts: current }),
  };
  const drain = () => {
    for (const t of frameTimes) {
      if (!cb) break;
      const fn = cb; cb = null; current = t; fn(t - rafOffset);
    }
  };
  return { deps, painted, active, drain };
}
function safe(times: number[]) {
  for (const t of times) expect(times.filter((x) => x >= t && x < t + 1000).length).toBeLessThanOrEqual(3);
}

describe("planSegments", () => {
  it("lays the neutral then each colour end to end", () => {
    const p = planSegments(challenge);
    expect(p.map((s) => s.index)).toEqual([-1, 0, 1, 2]);
    expect(p[0]).toMatchObject({ startMs: 0, endMs: 200 });
    expect(p.at(-1)?.endMs).toBe(challenge.total_ms);
  });
});
describe("runChallenge", () => {
  it("regression: never compresses four visible changes into 984 ms after a delayed first colour", async () => {
    const c = { ...challenge, total_ms: 1200, segments: challenge.segments.map((s, i) => ({ ...s, duration_ms: i === 0 ? 334 : 333 })) };
    // Shift the original failing callbacks by the separately reported neutral preparation.
    const r = rig([0, 1000, 1216, 1550, 1883, 2200, ...frames(2217, 4500)]);
    const p = runChallenge(c, r.deps); r.drain(); const result = await p;
    safe(result.transitions.map((d) => d.t_display));
    expect(result.tEnd - result.displayed[1].t_display).toBeGreaterThanOrEqual(1000);
    expect(result.displayed[1].t_display).toBe(1216);
  });
  it("holds every issued duration from actual application and records entry, final neutral and UI exit", async () => {
    const r = rig(frames(5000, 9500));
    const p = runChallenge(challenge, r.deps); r.drain(); const result = await p;
    expect(result.status).toBe("complete"); expect(result.skipped).toEqual([]);
    expect(result.tStart - result.tRequested).toBeGreaterThanOrEqual(1000);
    expect(result.displayed.map((d) => d.index)).toEqual([-1, 0, 1, 2]);
    const colour = result.displayed.slice(1);
    expect(colour[0].t_display - result.tStart).toBeGreaterThanOrEqual(200);
    colour.forEach((d, i) => expect((colour[i + 1]?.t_display ?? result.tEnd) - d.t_display).toBeGreaterThanOrEqual(challenge.segments[i].duration_ms));
    expect(result.tEnd - result.tStart).toBeLessThanOrEqual(1300);
    expect(result.transitions.map((d) => d.rgb)).toEqual([challenge.neutral.rgb, ...challenge.segments.map((s) => s.rgb), challenge.neutral.rgb, challenge.neutral.rgb]);
    expect(result.transitions.at(-1)?.state).toBe("idle");
    expect(r.active.at(-1)?.active).toBe(false);
    safe(result.transitions.map((d) => d.t_display));
  });
  it("applies a caller idle colour through the same guard", async () => {
    const r = rig(frames(0, 4500)); const p = runChallenge(challenge, r.deps, [10, 20, 30]);
    r.drain(); const result = await p;
    expect(r.painted.at(-1)?.rgb).toEqual([10, 20, 30]); safe(result.transitions.map((d) => d.t_display));
  });
  it("does not catch up missed segments after a long stall; aborts overlong capture", async () => {
    const r = rig([0, 1000, 1200, 2600, ...frames(2617, 4500)]);
    const p = runChallenge(challenge, r.deps); r.drain(); const result = await p;
    expect(result.status).toBe("aborted"); expect(result.reason).toBe("CAPTURE_OVERRUN");
    expect(result.skipped).toEqual([1, 2]); expect(result.displayed.map((d) => d.index)).toEqual([-1, 0]);
    expect(result.transitions.at(-2)?.rgb).toEqual(challenge.neutral.rgb);
    safe(result.transitions.map((d) => d.t_display));
  });
  it("does not paint a measurement segment twice", async () => {
    const r = rig(frames(0, 4500)); const p = runChallenge(challenge, r.deps); r.drain();
    expect((await p).displayed).toHaveLength(4);
  });
  it("uses application time even when the rAF timestamp is older", async () => {
    const r = rig(frames(1000, 5500), new TransitionGuard(), 50);
    const p = runChallenge(challenge, r.deps); r.drain(); const result = await p;
    expect(result.displayed[0].t_display).toBe(1000);
    expect(result.transitions.map((d) => d.t_display)).toEqual(r.painted.map((d) => d.ts));
  });
  it("keeps page-lifetime transition history across successive attempts", async () => {
    const guard = new TransitionGuard();
    const a = rig(frames(0, 4500), guard); const pa = runChallenge(challenge, a.deps); a.drain(); const ra = await pa;
    const b = rig(frames(ra.tIdle + 1, ra.tIdle + 5000), guard); const pb = runChallenge(challenge, b.deps); b.drain(); const rb = await pb;
    safe([...ra.transitions, ...rb.transitions].map((d) => d.t_display));
    expect(rb.tStart - rb.tRequested).toBeGreaterThanOrEqual(1000);
  });
  it("aborts interrupted measurements and restores the surface safely", async () => {
    const r = rig(frames(0, 4500));
    r.deps.interrupted = () => r.painted.length >= 3;
    const p = runChallenge(challenge, r.deps); r.drain(); const result = await p;
    expect(result.status).toBe("aborted"); expect(result.reason).toBe("INTERRUPTED"); safe(result.transitions.map((d) => d.t_display));
  });
  it("rejects malformed durations, unsafe colours and invalid return-to-neutral contrast before painting", () => {
    const r = rig([]);
    for (const c of [ { ...challenge, total_ms: NaN }, { ...challenge, segments: [] },
      { ...challenge, total_ms: 1190, segments: challenge.segments.map((s) => ({ ...s, duration_ms: 330 })) },
      { ...challenge, segments: challenge.segments.map((s) => ({ ...s, rgb: [255, 0, 0] as RGB })) },
      { ...challenge, segments: challenge.segments.map((s, i) => i === 2 ? { ...s, rgb: challenge.neutral.rgb } : s) } ]) {
      expect(() => runChallenge(c, r.deps)).toThrow();
    }
    expect(r.painted).toEqual([]);
  });
});
describe("TransitionGuard", () => {
  it("uses completion time when applying a style itself takes time", () => {
    const g = new TransitionGuard();
    expect(g.change(0, () => 100)).toBe(true);
    expect(g.change(300, () => 400)).toBe(true);
    expect(g.change(600, () => 700)).toBe(true);
    expect(g.change(1000, () => 1000)).toBe(false);
    expect(g.change(1100, () => 1100)).toBe(true);
  });
  it("enforces the half-open 1000 ms boundary and rejects bad clocks/concurrent renderers", () => {
    const g = new TransitionGuard(); const apply = () => undefined;
    g.acquire(); expect(() => g.acquire()).toThrow(/already active/); g.release();
    expect(g.change(0, apply)).toBe(true); expect(g.change(300, apply)).toBe(true); expect(g.change(600, apply)).toBe(true);
    expect(g.change(999, apply)).toBe(false); expect(g.change(1000, apply)).toBe(true);
    expect(() => g.change(999, apply)).toThrow(/monotonic/); expect(() => g.change(NaN, apply)).toThrow(/finite/);
  });
});
