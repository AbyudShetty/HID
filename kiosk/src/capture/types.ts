// Capture abstractions (plan §9.3, §20.1): the production kiosk and the spike page share these.
import type { Box, CameraInfo } from "../types/protocol";

export interface GrabRequest {
  /** Fixed square crop (full-frame pixels) resized to `size` x `size`. */
  crop?: { box: Box; size: number };
  /** The whole frame downscaled to at most `maxWidth` pixels wide. */
  full?: { maxWidth: number };
  /** JPEG quality 0..1 */
  quality: number;
}

export interface Grabbed {
  /** Capture time, performance.now() timeline. `source` says whether it came from rVFC `captureTime` or the callback `now`. */
  t: number;
  /** rVFC callback time (performance.now()); equals `t` when `source` is "now". */
  tCallback: number;
  source: "captureTime" | "now";
  width: number;
  height: number;
  /** Encoded JPEG bytes; the snapshot of the frame is taken synchronously, encoding finishes later. */
  crop?: Promise<Uint8Array>;
  full?: Promise<Uint8Array>;
}

export interface FrameSource {
  info(): CameraInfo;
  size(): { width: number; height: number };
  /**
   * Starts delivering frames. For every frame `plan(now)` is evaluated synchronously in the frame callback (so the
   * snapshot matches the frame); returning null skips the frame.
   */
  start(plan: (now: number) => GrabRequest | null, onFrame: (g: Grabbed) => void): void;
  stop(): void;
}
