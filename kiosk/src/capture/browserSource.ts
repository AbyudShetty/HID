// Browser camera FrameSource (plan §9.3, G-01 path H1a/H1b): getUserMedia + requestVideoFrameCallback.
// "lock: browser" tries to put exposure and white balance in manual mode via applyConstraints and then READS BACK the
// settings so what actually stuck is recorded (E1 verifies on real frames, never trusting getSettings alone).
import type { CameraInfo, LockMethod } from "../types/protocol";
import { JpegEncoder } from "./encoder";
import type { FrameSource, GrabRequest, Grabbed } from "./types";

export interface BrowserCameraOptions {
  width: number;
  height: number;
  fps: number;
  deviceId?: string;
  lock: { mode: "none" | "browser"; exposureTime?: number; colorTemperature?: number };
}

interface VFMeta {
  captureTime?: number;
  presentationTime?: number;
  receiveTime?: number;
  expectedDisplayTime?: number;
  mediaTime?: number;
}
type VideoWithRVFC = HTMLVideoElement & {
  requestVideoFrameCallback(cb: (now: number, meta: VFMeta) => void): number;
  cancelVideoFrameCallback(h: number): void;
};

export class BrowserFrameSource implements FrameSource {
  private running = false;
  private handle = 0;
  readonly encoder = new JpegEncoder(2);

  private constructor(
    private readonly video: VideoWithRVFC,
    readonly stream: MediaStream,
    private readonly track: MediaStreamTrack,
    private readonly lock: LockMethod,
    readonly lockReport: { requested: Record<string, unknown> | null; applied: boolean; error: string | null },
  ) {}

  static async open(video: HTMLVideoElement, opts: BrowserCameraOptions): Promise<BrowserFrameSource> {
    if (!("requestVideoFrameCallback" in video)) throw new Error("this browser has no requestVideoFrameCallback");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        width: { ideal: opts.width },
        height: { ideal: opts.height },
        frameRate: { ideal: opts.fps },
        ...(opts.deviceId ? { deviceId: { exact: opts.deviceId } } : {}),
      },
    });
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    const track = stream.getVideoTracks()[0];
    const report = { requested: null as Record<string, unknown> | null, applied: false, error: null as string | null };
    if (opts.lock.mode === "browser") {
      const advanced: Record<string, unknown> = { exposureMode: "manual", whiteBalanceMode: "manual" };
      if (opts.lock.exposureTime !== undefined) advanced.exposureTime = opts.lock.exposureTime;
      if (opts.lock.colorTemperature !== undefined) advanced.colorTemperature = opts.lock.colorTemperature;
      report.requested = advanced;
      try {
        await track.applyConstraints({ advanced: [advanced] } as unknown as MediaTrackConstraints);
        report.applied = true;
      } catch (e) {
        report.error = e instanceof Error ? e.message : String(e);
      }
    }
    return new BrowserFrameSource(video as VideoWithRVFC, stream, track, opts.lock.mode === "browser" ? "browser" : "none", report);
  }

  info(): CameraInfo {
    const s = this.track.getSettings() as Record<string, unknown>;
    return {
      width: Number(s.width ?? this.video.videoWidth),
      height: Number(s.height ?? this.video.videoHeight),
      fps: Number(s.frameRate ?? 0),
      lock_method: this.lock,
      settings: JSON.parse(JSON.stringify({ ...s, _lock_requested: this.lockReport.requested, _lock_applied: this.lockReport.applied, _lock_error: this.lockReport.error })),
      capabilities: JSON.parse(JSON.stringify(this.track.getCapabilities?.() ?? {})),
      label: this.track.label || null,
    };
  }

  size(): { width: number; height: number } {
    return { width: this.video.videoWidth, height: this.video.videoHeight };
  }

  start(plan: (now: number) => GrabRequest | null, onFrame: (g: Grabbed) => void): void {
    this.running = true;
    const loop = (now: number, meta: VFMeta) => {
      if (!this.running) return;
      const req = plan(now);
      if (req) {
        const hasCapture = typeof meta.captureTime === "number";
        const g: Grabbed = {
          t: hasCapture ? (meta.captureTime as number) : now,
          tCallback: now,
          source: hasCapture ? "captureTime" : "now",
          width: this.video.videoWidth,
          height: this.video.videoHeight,
        };
        // The bitmap snapshot must be created synchronously inside the callback so it matches this frame.
        if (req.crop) {
          const [x, y, w, h] = req.crop.box;
          g.crop = createImageBitmap(this.video, x, y, w, h, { resizeWidth: req.crop.size, resizeHeight: req.crop.size, resizeQuality: "medium" }).then((b) =>
            this.encoder.encode(b, req.quality),
          );
        }
        if (req.full) {
          const scale = Math.min(1, req.full.maxWidth / this.video.videoWidth);
          g.full = createImageBitmap(this.video, {
            resizeWidth: Math.round(this.video.videoWidth * scale),
            resizeHeight: Math.round(this.video.videoHeight * scale),
            resizeQuality: "medium",
          }).then((b) => this.encoder.encode(b, req.quality));
        }
        onFrame(g);
      }
      this.handle = this.video.requestVideoFrameCallback(loop);
    };
    this.handle = this.video.requestVideoFrameCallback(loop);
  }

  stop(): void {
    this.running = false;
    if (this.handle) this.video.cancelVideoFrameCallback(this.handle);
  }

  /** Stop the camera and release resources. */
  close(): void {
    this.stop();
    for (const t of this.stream.getTracks()) t.stop();
    this.video.srcObject = null;
    this.encoder.dispose();
  }
}
