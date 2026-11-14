// Controlled illumination, including entry/exit. Timestamps measure DOM application on rAF,
// not physical display scan-out; E1 must measure the real camera/display response.
import type { Challenge, RGB, IlluminationTransition } from "../types/protocol";

export const TRANSITION_WINDOW_MS = 1000;
export const MAX_TRANSITIONS = 3;
export const CAPTURE_CAP_MS = 1300;

export interface PlannedSegment { index: number; rgb: RGB; startMs: number; endMs: number }
export interface DisplayedSegment { index: number; t_display: number }
export interface RenderResult {
  displayed: DisplayedSegment[];
  transitions: IlluminationTransition[];
  skipped: number[];
  status: "complete" | "aborted";
  reason: "CAPTURE_OVERRUN" | "INTERRUPTED" | null;
  tRequested: number;
  tStart: number;
  tEnd: number; // neutral restoration; safe UI exit can be later
  tIdle: number;
}

/** Page-lifetime history: callers reuse it across attempts, never reset it to skip cooldown. */
export class TransitionGuard {
  private history: number[] = [];
  private lastTime = -Infinity;
  private busy = false;
  acquire(): void {
    if (this.busy) throw new Error("illumination is already active");
    this.busy = true;
  }
  release(): void { this.busy = false; }
  change(now: number, apply: () => number | void): boolean {
    if (!Number.isFinite(now) || now < this.lastTime) throw new Error("illumination clock must be finite and monotonic");
    this.history = this.history.filter((t) => now - t < TRANSITION_WINDOW_MS);
    if (this.history.length >= MAX_TRANSITIONS) return false;
    const appliedAt = apply() ?? now;
    if (!Number.isFinite(appliedAt) || appliedAt < now) throw new Error("invalid illumination application timestamp");
    this.history.push(appliedAt);
    this.lastTime = appliedAt;
    return true;
  }
}
const pageGuard = new TransitionGuard();

export interface RenderDeps {
  raf: (cb: (ts: number) => void) => unknown;
  now: () => number; // application clock, not the possibly older rAF frame timestamp
  setColor: (rgb: RGB) => void;
  setActive?: (active: boolean) => void; // overlay entry/exit ONLY through this guard
  guard?: TransitionGuard;
  interrupted?: () => boolean;
  onDisplayed?: (d: DisplayedSegment) => void;
  onStarted?: (t: number) => void;
  onCaptureEnd?: (t: number) => void;
}

export function planSegments(challenge: Challenge): PlannedSegment[] {
  const states = [challenge.neutral, ...challenge.segments];
  let t = 0;
  return states.map((s, k) => {
    const startMs = t;
    t += s.duration_ms;
    return { index: k - 1, rgb: s.rgb, startMs, endMs: t };
  });
}

function checkChallenge(challenge: Challenge): void {
  const states = [challenge.neutral, ...challenge.segments];
  if (challenge.segments.length !== 3 || challenge.neutral.duration_ms !== 200 ||
      states.some((s) => !Number.isInteger(s.duration_ms) || s.duration_ms <= 0 ||
        s.rgb.length !== 3 || s.rgb.some((v) => !Number.isInteger(v) || v < 0 || v > 255) ||
        s.rgb[0] / (s.rgb.reduce((a, b) => a + b, 0) || 1) >= 0.6) ||
      challenge.total_ms !== states.reduce((t, s) => t + s.duration_ms, 0) || challenge.total_ms > CAPTURE_CAP_MS) {
    throw new Error("invalid challenge timing or colour");
  }
  const linear = (v: number) => v / 255 <= 0.04045 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4;
  const times = [challenge.neutral.duration_ms];
  for (const s of challenge.segments) times.push(times.at(-1)! + s.duration_ms);
  if (times.some((t) => times.filter((x) => x >= t && x < t + TRANSITION_WINDOW_MS).length > MAX_TRANSITIONS)) {
    throw new Error("nominal challenge exceeds three transitions per second");
  }
  for (let i = 1; i < states.length + 1; i++) {
    const a = states[i - 1].rgb;
    const b = states[i % states.length].rgb; // also check return to neutral
    if (Math.hypot(...a.map((v, c) => linear(v) - linear(b[c]))) < 0.30) throw new Error("challenge colours are too close");
  }
}

/**
 * Prime neutral and clear rolling history BEFORE the measurement. Preparation is explicitly
 * reported, never hidden as measured end-to-end latency. Hold issued durations from actual
 * application, with no catch-up. Abort overlong captures, then restore neutral/UI safely.
 */
export function runChallenge(challenge: Challenge, deps: RenderDeps, idle: RGB = challenge.neutral.rgb): Promise<RenderResult> {
  checkChallenge(challenge);
  const guard = deps.guard ?? pageGuard;
  guard.acquire();
  const displayed: DisplayedSegment[] = [];
  const transitions: IlluminationTransition[] = [];
  const tRequested = deps.now();
  let preparedAt: number | null = null;
  let tStart: number | null = null;
  let tEnd: number | null = null;
  let lastPaint = 0;
  let next = 0;
  let reason: RenderResult["reason"] = null;
  let restoring = false;

  return new Promise((resolve, reject) => {
    const paint = (now: number, state: "challenge" | "idle", rgb: RGB) => guard.change(now, () => {
      deps.setColor(rgb);
      deps.setActive?.(state === "challenge");
      const appliedAt = deps.now();
      transitions.push({ state, rgb, t_display: appliedAt });
      return appliedAt;
    });
    const frame = () => {
      try {
        const now = deps.now();
        if (preparedAt === null) {
          if (paint(now, "challenge", challenge.neutral.rgb)) {
            preparedAt = transitions.at(-1)!.t_display;
            const d = { index: -1, t_display: preparedAt };
            displayed.push(d);
            deps.onDisplayed?.(d);
          }
        } else if (tStart === null) {
          if (now - preparedAt >= TRANSITION_WINDOW_MS) {
            tStart = now;
            lastPaint = now;
            deps.onStarted?.(now);
          }
        } else if (tEnd === null) {
          if (deps.interrupted?.()) reason = "INTERRUPTED";
          else if (now - tStart > CAPTURE_CAP_MS) reason = "CAPTURE_OVERRUN";
          if (reason) restoring = true;
          if (!restoring) {
            const previousDuration = next === 0 ? challenge.neutral.duration_ms : challenge.segments[next - 1].duration_ms;
            if (now - lastPaint >= previousDuration) {
              if (next === challenge.segments.length) restoring = true;
              else if (paint(now, "challenge", challenge.segments[next].rgb)) {
                const d = { index: next++, t_display: transitions.at(-1)!.t_display };
                displayed.push(d);
                deps.onDisplayed?.(d);
                lastPaint = d.t_display;
              }
            }
          }
          if (restoring && paint(now, "challenge", challenge.neutral.rgb)) {
            tEnd = transitions.at(-1)!.t_display;
            if (tEnd - tStart > CAPTURE_CAP_MS && !reason) reason = "CAPTURE_OVERRUN";
            deps.onCaptureEnd?.(tEnd);
          }
        } else if (paint(now, "idle", idle)) {
          guard.release();
          resolve({ displayed, transitions, skipped: challenge.segments.map((_, i) => i).slice(next),
            status: reason ? "aborted" : "complete", reason, tRequested, tStart, tEnd, tIdle: transitions.at(-1)!.t_display });
          return;
        }
        deps.raf(frame);
      } catch (e) {
        guard.release();
        reject(e); // never force an unguarded UI change on failure
      }
    };
    deps.raf(frame);
  });
}
