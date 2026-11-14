// Challenge renderer (plan §9.3): paints the server-issued colour sequence and records, for each segment, the
// requestAnimationFrame timestamp of the frame in which its colour was first applied (t_display).
// Pure logic with injected rAF / colour setter so it is unit-testable; the DOM wiring lives in the spike/kiosk pages.
import type { Challenge, RGB } from "../types/protocol";

export interface PlannedSegment {
  index: number; // -1 = neutral
  rgb: RGB;
  startMs: number;
  endMs: number;
}

export interface DisplayedSegment {
  index: number;
  t_display: number; // rAF timestamp (performance.now() timeline) of the frame that applied this colour
}

export interface RenderResult {
  displayed: DisplayedSegment[];
  skipped: number[]; // segments whose whole window passed between two frames (never painted)
  tStart: number; // rAF timestamp of the frame that painted the neutral segment
  tEnd: number; // rAF timestamp of the frame that restored the idle colour
}

export interface RenderDeps {
  raf: (cb: (ts: number) => void) => unknown;
  setColor: (rgb: RGB) => void;
  /** Called synchronously, in the frame that painted a segment (before the next rAF). */
  onDisplayed?: (d: DisplayedSegment) => void;
}

export function planSegments(challenge: Challenge): PlannedSegment[] {
  const out: PlannedSegment[] = [];
  let t = 0;
  out.push({ index: -1, rgb: challenge.neutral.rgb, startMs: t, endMs: t + challenge.neutral.duration_ms });
  t += challenge.neutral.duration_ms;
  challenge.segments.forEach((s, i) => {
    out.push({ index: i, rgb: s.rgb, startMs: t, endMs: t + s.duration_ms });
    t += s.duration_ms;
  });
  return out;
}

/**
 * Runs the challenge to completion. `idle` is applied when it ends (the plan's neutral/idle screen).
 * Frame callbacks are driven by `deps.raf`; elapsed time is measured from the first frame (which paints the neutral).
 */
export function runChallenge(challenge: Challenge, deps: RenderDeps, idle: RGB = challenge.neutral.rgb): Promise<RenderResult> {
  const plan = planSegments(challenge);
  const total = challenge.total_ms;
  const displayed: DisplayedSegment[] = [];
  const skipped: number[] = [];
  let tStart: number | null = null;
  let next = 0; // next planned segment to paint

  return new Promise((resolve) => {
    const frame = (ts: number) => {
      if (tStart === null) tStart = ts;
      const elapsed = ts - tStart;
      if (elapsed >= total) {
        // any segment never painted before the end was skipped
        for (; next < plan.length; next++) skipped.push(plan[next].index);
        deps.setColor(idle);
        resolve({ displayed, skipped, tStart, tEnd: ts });
        return;
      }
      // paint the segment whose window contains `elapsed`; segments whose whole window passed between frames were skipped
      if (next < plan.length && plan[next].startMs <= elapsed) {
        let target = next;
        while (target + 1 < plan.length && plan[target + 1].startMs <= elapsed) target++;
        for (let k = next; k < target; k++) skipped.push(plan[k].index);
        deps.setColor(plan[target].rgb);
        const d = { index: plan[target].index, t_display: ts };
        displayed.push(d);
        deps.onDisplayed?.(d);
        next = target + 1;
      }
      deps.raf(frame);
    };
    deps.raf(frame);
  });
}
