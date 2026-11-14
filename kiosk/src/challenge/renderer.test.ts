import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import type { Challenge, RGB } from "../types/protocol";
import { planSegments, runChallenge } from "./renderer";

const challenge = samples.server["session.ready"].challenge as unknown as Challenge; // 200 + 3*330 = 1190 ms

/** Deterministic rAF: call `step()` to deliver the next frame at the given timestamp. */
function rig(frameTimes: number[]) {
  const painted: { rgb: RGB; ts: number }[] = [];
  let cb: ((ts: number) => void) | null = null;
  let i = 0;
  let current = 0;
  const deps = {
    raf: (fn: (ts: number) => void) => {
      cb = fn;
      return 1;
    },
    setColor: (rgb: RGB) => painted.push({ rgb, ts: current }),
  };
  const drain = () => {
    while (cb && i < frameTimes.length) {
      const fn = cb;
      cb = null;
      current = frameTimes[i++];
      fn(current);
    }
  };
  return { deps, painted, drain };
}

const frames60 = (from: number, to: number) => {
  const out: number[] = [];
  for (let t = from; t <= to; t += 1000 / 60) out.push(t);
  return out;
};

describe("planSegments", () => {
  it("lays the neutral then each colour end to end", () => {
    const plan = planSegments(challenge);
    expect(plan.map((p) => p.index)).toEqual([-1, 0, 1, 2]);
    expect(plan[0]).toMatchObject({ startMs: 0, endMs: 200 });
    expect(plan[1].startMs).toBe(200);
    expect(plan.at(-1)?.endMs).toBe(challenge.total_ms);
  });
});

describe("runChallenge", () => {
  it("paints each segment on the first frame at or after its start and records that frame's timestamp", async () => {
    const t0 = 5000;
    const { deps, painted, drain } = rig(frames60(t0, t0 + 1400));
    const p = runChallenge(challenge, deps);
    drain();
    const res = await p;

    expect(res.tStart).toBe(t0);
    expect(res.skipped).toEqual([]);
    expect(res.displayed.map((d) => d.index)).toEqual([-1, 0, 1, 2]);
    const plan = planSegments(challenge);
    res.displayed.forEach((d, k) => {
      const lateBy = d.t_display - t0 - plan[k].startMs;
      expect(lateBy).toBeGreaterThanOrEqual(0);
      expect(lateBy).toBeLessThan(1000 / 60 + 1e-6); // at most one frame late
    });
    // neutral, 3 colours, then the idle colour restored at the end
    expect(painted.map((x) => x.rgb)).toEqual([
      challenge.neutral.rgb,
      ...challenge.segments.map((s) => s.rgb),
      challenge.neutral.rgb,
    ]);
    expect(res.tEnd - t0).toBeGreaterThanOrEqual(challenge.total_ms);
    expect(res.tEnd - t0).toBeLessThan(challenge.total_ms + 1000 / 60 + 1e-6);
  });

  it("applies the idle colour passed by the caller at the end", async () => {
    const { deps, painted, drain } = rig(frames60(0, 1300));
    const p = runChallenge(challenge, deps, [10, 20, 30]);
    drain();
    await p;
    expect(painted.at(-1)?.rgb).toEqual([10, 20, 30]);
  });

  it("reports segments that fell between two frames as skipped and never claims they were displayed", async () => {
    // a 400 ms stall swallows the window of segment 0 (200..530) entirely? no: stall from 100 -> 560 skips segment 0 only
    const times = [0, 16, 33, 50, 100, 560, 576, 592, ...frames60(600, 1300)];
    const { deps, drain } = rig(times);
    const p = runChallenge(challenge, deps);
    drain();
    const res = await p;
    expect(res.skipped).toEqual([0]);
    expect(res.displayed.map((d) => d.index)).toEqual([-1, 1, 2]);
  });

  it("does not paint the same segment twice", async () => {
    const { deps, painted, drain } = rig(frames60(0, 1400));
    const p = runChallenge(challenge, deps);
    drain();
    await p;
    expect(painted).toHaveLength(5);
  });
});
