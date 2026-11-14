// Crop geometry (plan §9.3): a square around the client face box, side = contextScale * max(w, h), clamped to the frame.
import type { Box } from "../types/protocol";

export interface FrameSize {
  width: number;
  height: number;
}

/**
 * Square crop box [x, y, side, side] in full-frame pixels. The square is shifted (not shrunk) to stay inside the
 * frame when possible; if the requested side exceeds the frame's short edge it is clamped to it.
 */
export function computeCropBox(face: Box, frame: FrameSize, contextScale: number): Box {
  const [fx, fy, fw, fh] = face;
  const side = Math.min(Math.round(contextScale * Math.max(fw, fh)), frame.width, frame.height);
  const cx = fx + fw / 2;
  const cy = fy + fh / 2;
  const x = Math.round(Math.min(Math.max(cx - side / 2, 0), frame.width - side));
  const y = Math.round(Math.min(Math.max(cy - side / 2, 0), frame.height - side));
  return [x, y, side, side];
}

/** A face-sized box in the middle of the frame: the explicit fallback when no face detector is available. */
export function centerFaceBox(frame: FrameSize, fraction = 0.45): Box {
  const h = Math.round(frame.height * fraction);
  const w = Math.round(h * 0.8);
  return [Math.round((frame.width - w) / 2), Math.round((frame.height - h) / 2), w, h];
}

/** Largest face by area; `null` when there are none. */
export function largestBox(boxes: Box[]): Box | null {
  let best: Box | null = null;
  for (const b of boxes) if (!best || b[2] * b[3] > best[2] * best[3]) best = b;
  return best;
}

/** Plan §9.2 / decision rule: faces smaller than `ratio` x the primary face's height are ignored. */
export function countSignificantFaces(boxes: Box[], ratio = 0.5): number {
  const primary = largestBox(boxes);
  if (!primary) return 0;
  return boxes.filter((b) => b[3] >= ratio * primary[3]).length;
}
