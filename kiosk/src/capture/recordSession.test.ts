import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import { runChallenge } from "../challenge/renderer";
import { packBundle } from "../net/bundle";
import type { Challenge, CollectLabel, RGB } from "../types/protocol";
import { recordSession, type RecordParams } from "./recordSession";
import type { FrameSource, GrabRequest, Grabbed } from "./types";

const challenge = samples.server["session.ready"].challenge as unknown as Challenge; // neutral 200 + 3x330 = 1190 ms
const label = samples.records.collect_label_bona_fide as unknown as CollectLabel;
const dec = new TextDecoder();

/** One shared simulated clock: render frames at 60 Hz, camera frames at 30 Hz. */
function simulate(opts: { cameraFps?: number; t0?: number } = {}) {
  const cameraFps = opts.cameraFps ?? 30;
  const t0 = opts.t0 ?? 10_000;
  let now = t0;
  let rafCb: ((ts: number) => void) | null = null;
  let plan: ((n: number) => GrabRequest | null) | null = null;
  let onFrame: ((g: Grabbed) => void) | null = null;
  let running = false;
  const painted: { rgb: RGB; ts: number }[] = [];
  let n = 0;

  const source: FrameSource = {
    info: () => ({ width: 1280, height: 720, fps: cameraFps, lock_method: "none", settings: {}, capabilities: {}, label: "fake cam" }),
    size: () => ({ width: 1280, height: 720 }),
    start: (p, f) => {
      plan = p;
      onFrame = f;
      running = true;
    },
    stop: () => {
      running = false;
    },
  };
  const fake = (tag: number) => Promise.resolve(new Uint8Array([0xff, 0xd8, 0xff, 0xe0, tag & 255, (tag >> 8) & 255]));

  const render = (hooks: { onDisplayed?: (d: { index: number; t_display: number }) => void }) =>
    runChallenge(challenge, {
      raf: (cb) => {
        rafCb = cb;
        return 1;
      },
      setColor: (rgb) => painted.push({ rgb, ts: now }),
      onDisplayed: hooks.onDisplayed,
    });

  /** advance 1 ms at a time; deliver render/camera frames on their own cadence */
  const run = async (promise: Promise<unknown>, maxMs = 3000) => {
    let done = false;
    promise.then(() => (done = true));
    const camPeriod = 1000 / cameraFps;
    let nextRender = t0;
    let nextCam = t0 + 5; // camera phase offset
    for (let i = 0; i < maxMs && !done; i++) {
      now = t0 + i;
      if (now >= nextRender && rafCb) {
        const cb = rafCb;
        rafCb = null;
        cb(now);
        nextRender += 1000 / 60;
      }
      if (running && now >= nextCam && plan && onFrame) {
        const req = plan(now);
        if (req) {
          const g: Grabbed = { t: now, tCallback: now, source: "now", width: 1280, height: 720 };
          if (req.crop) g.crop = fake(n++);
          if (req.full) g.full = fake(1000 + n++);
          onFrame(g);
        }
        nextCam += camPeriod;
      }
      await Promise.resolve();
    }
    await promise;
  };
  return { source, render, run, getNow: () => now, painted };
}

const baseParams = (): RecordParams => ({
  challenge,
  sessionId: "s_0123456789abcdef",
  cropBox: [440, 160, 400, 400],
  faceBox: [560, 260, 160, 200],
  cropSize: 256,
  jpegQuality: 0.9,
  keyframeCount: 2,
  keyframeMaxWidth: 1280,
  keyframeSettleMs: 60,
  meta: {
    purpose: "collect",
    kiosk_id: "kiosk-test",
    client_version: "0.1.0",
    server_version: "0.1.0",
    policy_version: "2026-11-14-provisional",
    kiosk_profile_version: null,
    display: { width: 1920, height: 1080, device_pixel_ratio: 1 },
  },
  label,
});

describe("recordSession", () => {
  it("produces a complete bundle with relative timestamps, 2 settled keyframes and ~30 crops/s", async () => {
    const sim = simulate();
    const p = recordSession(baseParams(), { source: sim.source, render: sim.render, now: sim.getNow, isoNow: () => "2026-11-14T10:00:00Z" });
    await sim.run(p);
    const { entries, stats } = await p;
    const byName = new Map(entries.map(([n, d]) => [n, d]));

    expect(stats.nKeyframes).toBe(2);
    expect(stats.nCrops).toBeGreaterThanOrEqual(34);
    expect(stats.nCrops).toBeLessThanOrEqual(40);
    expect(stats.cropFps).toBeGreaterThan(27);
    expect(stats.cropFps).toBeLessThan(33);
    expect(stats.skippedSegments).toEqual([]);

    const ch = JSON.parse(dec.decode(byName.get("challenge.json")!));
    expect(ch.displayed.map((d: { index: number }) => d.index)).toEqual([-1, 0, 1, 2]);
    expect(ch.displayed[0].t_display).toBeGreaterThanOrEqual(0);
    expect(ch.displayed[0].t_display).toBeLessThan(20); // within about a frame of t_lock

    // keyframes are taken only after the neutral colour settled and before the first colour
    const kf = dec.decode(byName.get("keyframes.jsonl")!).split("\n").map((l) => JSON.parse(l));
    const neutralT = ch.displayed[0].t_display;
    for (const k of kf) {
      expect(k.t_capture).toBeGreaterThanOrEqual(neutralT + 60);
      expect(k.t_capture).toBeLessThan(neutralT + 200);
    }

    // crops: fixed box for the whole session, strictly increasing capture time, first at/after t_lock
    const frames = dec.decode(byName.get("frames.jsonl")!).split("\n").map((l) => JSON.parse(l));
    expect(frames[0].t_capture).toBeGreaterThanOrEqual(0);
    expect(new Set(frames.map((f: { crop_box: number[] }) => f.crop_box.join(","))).size).toBe(1);
    for (let i = 1; i < frames.length; i++) expect(frames[i].t_capture).toBeGreaterThan(frames[i - 1].t_capture);
    expect(frames.every((f: { file: string }) => /^crops\/\d{6}\.jpg$/.test(f.file))).toBe(true);

    const meta = JSON.parse(dec.decode(byName.get("meta.json")!));
    expect(meta).toMatchObject({ session_id: "s_0123456789abcdef", purpose: "collect", capture_time_source: "now", palette_id: "P1", crop_size: 256 });
    expect(JSON.parse(dec.decode(byName.get("label.json")!))).toEqual(label);

    // every entry name is packable (matches the server whitelist)
    expect(() => packBundle(entries)).not.toThrow();
  });

  it("stops capturing when the challenge ends", async () => {
    const sim = simulate();
    const p = recordSession(baseParams(), { source: sim.source, render: sim.render, now: sim.getNow, isoNow: () => "x" });
    await sim.run(p);
    const { stats } = await p;
    expect(stats.spanMs).toBeLessThan(challenge.total_ms + 40);
    expect(stats.spanMs).toBeGreaterThan(challenge.total_ms - 80);
  });

  it("matches the committed cross-language bundle fixture that Python validates with the real build_bundle", async () => {
    const sim = simulate();
    const p = recordSession(baseParams(), { source: sim.source, render: sim.render, now: sim.getNow, isoNow: () => "2026-11-14T10:00:00Z" });
    await sim.run(p);
    const { entries } = await p;
    const bytes = new Uint8Array(packBundle(entries));
    let bin = "";
    for (const b of bytes) bin += String.fromCharCode(b);
    const b64 = btoa(bin);
    expect(b64, "regenerate with the value printed below if the producer intentionally changed").toBe(
      (samples.records as unknown as Record<string, string>).ts_bundle_b64 ?? `MISSING ts_bundle_b64; paste: ${b64}`,
    );
  });
});
