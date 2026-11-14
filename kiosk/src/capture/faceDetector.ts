// Client-side face framing with MediaPipe (plan F-07): used ONLY for the on-screen guide and the crop box, never for decisions.
import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";
import type { Box } from "../types/protocol";

const WASM_BASE = "/mediapipe/wasm";
const MODEL_URL = "/mediapipe/blaze_face_short_range.tflite";

export interface FramingDetector {
  detect(video: HTMLVideoElement, timestampMs: number): Box[];
  close(): void;
}

export type DetectorLoad = { ok: true; detector: FramingDetector } | { ok: false; reason: string };

/** Loads MediaPipe from locally served assets (run `npm run assets` once). Returns a reason instead of throwing. */
export async function loadFaceDetector(): Promise<DetectorLoad> {
  try {
    const head = await fetch(MODEL_URL, { method: "HEAD" });
    const ct = head.headers.get("content-type") ?? "";
    if (!head.ok || ct.includes("text/html")) {
      return { ok: false, reason: `MediaPipe assets not found at ${MODEL_URL} (run "npm run assets" in kiosk/)` };
    }
    const fileset = await FilesetResolver.forVisionTasks(WASM_BASE);
    const detector = await FaceDetector.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL_URL },
      runningMode: "VIDEO",
      minDetectionConfidence: 0.5,
    });
    return {
      ok: true,
      detector: {
        detect(video, ts) {
          const res = detector.detectForVideo(video, ts);
          return res.detections.flatMap((d) => {
            const b = d.boundingBox;
            return b ? [[b.originX, b.originY, b.width, b.height] as Box] : [];
          });
        },
        close: () => detector.close(),
      },
    };
  } catch (e) {
    return { ok: false, reason: e instanceof Error ? e.message : String(e) };
  }
}
