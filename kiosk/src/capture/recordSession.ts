// Records one challenge session into a bundle (plan §8.5, §9.3). Shared by the spike page now and the production kiosk
// later (F-14). V2 experiment times use measurement-start zero AFTER explicitly reported light preparation.
// This is not the official access t_lock metric: future access timing must include all work after face lock.
import { runChallenge, type DisplayedSegment, type RenderDeps, type RenderResult } from "../challenge/renderer";
import type { BundleEntry } from "../net/bundle";
import type { Box, Challenge, CollectLabel, DisplayInfo, MeasurementTiming, Purpose } from "../types/protocol";
import type { FrameSource, GrabRequest, Grabbed } from "./types";

export interface RecordParams {
  challenge: Challenge;
  sessionId: string;
  cropBox: Box;
  faceBox: Box | null; // null when no detector was available (center-crop fallback)
  cropSize: number; // e.g. 256
  jpegQuality: number; // 0..1
  keyframeCount: number; // e.g. 2
  keyframeMaxWidth: number; // e.g. 1280
  keyframeSettleMs: number; // wait after the neutral colour is painted before taking keyframes (plan: 60)
  meta: {
    purpose: Purpose;
    kiosk_id: string;
    client_version: string;
    server_version: string;
    policy_version: string | null;
    kiosk_profile_version: string | null;
    display: DisplayInfo;
  };
  label: CollectLabel | null;
}

export interface RecordDeps {
  source: FrameSource;
  /** Runs the challenge on screen. Defaults to the real renderer with the supplied DOM deps. */
  render: (hooks: Pick<RenderDeps, "onDisplayed" | "onStarted" | "onCaptureEnd">) => Promise<RenderResult>;
  now: () => number;
  isoNow: () => string;
}

export interface RecordedSession {
  entries: BundleEntry[];
  stats: {
    nCrops: number;
    nKeyframes: number;
    cropFps: number | null;
    skippedSegments: number[];
    captureTimeSource: "captureTime" | "now";
    tMeasurementStart: number;
    spanMs: number;
    preparationMs: number;
    captureMs: number;
    requestToIdleMs: number;
    rejectedFrames: number;
  };
}

const enc = new TextEncoder();
const json = (v: unknown) => enc.encode(JSON.stringify(v));

export async function recordSession(params: RecordParams, deps: RecordDeps): Promise<RecordedSession> {
  const { challenge } = params;
  const neutralMs = challenge.neutral.duration_ms;
  let tMeasurementStart: number | null = null;
  const grabbed: Grabbed[] = [];
  const keyframes: { g: Grabbed; k: number }[] = [];
  let neutralDisplayedAt: number | null = null;
  let lastKeyframeT = -Infinity;
  let rendering = true;
  let rejectedFrames = 0;
  let firstColourAt = Infinity;
  // Attach rejection handlers immediately, including snapshots discarded by timestamp checks.
  const encodes: Promise<unknown>[] = [];

  const plan = (now: number): GrabRequest | null => {
    if (!rendering || tMeasurementStart === null || now < tMeasurementStart) return null;
    const req: GrabRequest = { crop: { box: params.cropBox, size: params.cropSize }, quality: params.jpegQuality };
    // keyframes: only while the neutral colour is on screen and has settled (plan §3.2 #2, §9.3)
    if (
      neutralDisplayedAt !== null &&
      keyframes.length < params.keyframeCount &&
      now >= Math.max(tMeasurementStart, neutralDisplayedAt + params.keyframeSettleMs) &&
      now < Math.min(firstColourAt, tMeasurementStart + neutralMs) &&
      now - lastKeyframeT >= 30
    ) {
      req.full = { maxWidth: params.keyframeMaxWidth };
      lastKeyframeT = now;
    }
    return req;
  };

  const onFrame = (g: Grabbed) => {
    for (const p of [g.crop, g.full]) if (p) encodes.push(p.catch(() => undefined));
    if (tMeasurementStart === null || !Number.isFinite(g.t) || !Number.isFinite(g.tCallback) ||
        g.t < tMeasurementStart || g.t > g.tCallback || (grabbed.length > 0 && g.t <= grabbed[grabbed.length - 1].t)) {
      rejectedFrames++;
      return;
    }
    grabbed.push(g);
    if (g.full && neutralDisplayedAt !== null && g.t >= Math.max(tMeasurementStart, neutralDisplayedAt + params.keyframeSettleMs) &&
        g.t < Math.min(firstColourAt, tMeasurementStart + neutralMs)) keyframes.push({ g, k: keyframes.length });
  };

  deps.source.start(plan, onFrame);
  let result: RenderResult;
  try {
    result = await deps.render({
      onDisplayed: (d: DisplayedSegment) => {
        if (d.index === -1) neutralDisplayedAt = d.t_display;
        if (d.index === 0) firstColourAt = d.t_display;
      },
      onStarted: (t) => { tMeasurementStart = t; },
      onCaptureEnd: () => { rendering = false; deps.source.stop(); },
    });
  } finally {
    rendering = false;
    deps.source.stop();
    await Promise.all(encodes);
  }
  if (result.status !== "complete" || tMeasurementStart === null) throw new Error(`invalid measurement: ${result.reason ?? "not started"}`);
  if (keyframes.length !== params.keyframeCount) throw new Error("invalid measurement: insufficient neutral keyframes");
  const lock = result.tStart;

  // wait for every encode to finish
  const crops: { seq: number; t: number; tCb: number; source: Grabbed["source"]; bytes: Uint8Array }[] = [];
  let seq = 0;
  for (const g of grabbed) {
    if (g.crop) crops.push({ seq: seq++, t: g.t - lock, tCb: g.tCallback - lock, source: g.source, bytes: await g.crop });
  }
  const kfs: { k: number; t: number; tCb: number; source: Grabbed["source"]; bytes: Uint8Array }[] = [];
  for (const { g, k } of keyframes) if (g.full) kfs.push({ k, t: g.t - lock, tCb: g.tCallback - lock, source: g.source, bytes: await g.full });

  const sources = new Set(grabbed.map((g) => g.source));
  const captureTimeSource: "captureTime" | "now" = sources.size === 1 && sources.has("captureTime") ? "captureTime" : "now";
  const size = deps.source.size();
  const cam = deps.source.info();

  const entries: BundleEntry[] = [];
  entries.push([
    "meta.json",
    json({
      session_id: params.sessionId,
      purpose: params.meta.purpose,
      mode: "face",
      kiosk_id: params.meta.kiosk_id,
      created_at: deps.isoNow(),
      client_version: params.meta.client_version,
      server_version: params.meta.server_version,
      camera: {
        width: cam.width || size.width,
        height: cam.height || size.height,
        fps: cam.fps,
        lock_method: cam.lock_method,
        settings: cam.settings,
        label: cam.label,
      },
      display: params.meta.display,
      kiosk_profile_version: params.meta.kiosk_profile_version,
      policy_version: params.meta.policy_version,
      capture_time_source: captureTimeSource,
      jpeg_quality: params.jpegQuality,
      crop_size: params.cropSize,
      palette_id: challenge.palette_id,
    }),
  ]);
  entries.push([
    "challenge.json",
    json({
      challenge,
      displayed: result.displayed.map((d) => ({ index: d.index, t_display: d.t_display - lock })),
      timing: {
        version: 2,
        preparation_ms: lock - result.tRequested,
        capture_end_ms: result.tEnd - lock,
        idle_at_ms: result.tIdle - lock,
        transitions: result.transitions.map((d) => ({ ...d, t_display: d.t_display - lock })),
      } satisfies MeasurementTiming,
    }),
  ]);
  const frameRows = crops.map((c) => {
    const file = `crops/${String(c.seq).padStart(6, "0")}.jpg`;
    entries.push([file, c.bytes]);
    return { seq: c.seq, t_capture: c.t, t_callback: c.tCb, capture_time_source: c.source, crop_box: params.cropBox, frame_size: [size.width, size.height], client_face_box: params.faceBox, file };
  });
  entries.push(["frames.jsonl", enc.encode(frameRows.map((r) => JSON.stringify(r)).join("\n"))]);
  const kfRows = kfs.map((c) => {
    const file = `keyframes/k${c.k}.jpg`;
    entries.push([file, c.bytes]);
    return { seq: c.k, t_capture: c.t, t_callback: c.tCb, capture_time_source: c.source, frame_size: [size.width, size.height], file };
  });
  entries.push(["keyframes.jsonl", enc.encode(kfRows.map((r) => JSON.stringify(r)).join("\n"))]);
  if (params.label) entries.push(["label.json", json(params.label)]);

  const times = crops.map((c) => c.t);
  const spanMs = times.length > 1 ? times[times.length - 1] - times[0] : 0;
  return {
    entries,
    stats: {
      nCrops: crops.length,
      nKeyframes: kfs.length,
      cropFps: spanMs > 0 ? ((crops.length - 1) / spanMs) * 1000 : null,
      skippedSegments: result.skipped,
      captureTimeSource,
      tMeasurementStart: lock,
      spanMs,
      preparationMs: lock - result.tRequested,
      captureMs: result.tEnd - lock,
      requestToIdleMs: result.tIdle - result.tRequested,
      rejectedFrames,
    },
  };
}

/** Convenience: the real renderer bound to given DOM-ish deps. */
export function renderWith(challenge: Challenge, deps: RenderDeps, idle?: [number, number, number]) {
  return (hooks: Pick<RenderDeps, "onDisplayed" | "onStarted" | "onCaptureEnd">) => runChallenge(challenge, { ...deps, ...hooks }, idle);
}
