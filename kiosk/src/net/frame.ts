// Binary WebSocket frame: [u32 little-endian header_len][header JSON utf-8][JPEG bytes]  (plan §8.1).
// Limits match backend/app/protocol.py (plan §16.1).
import type { FrameHeader } from "../types/protocol";

export const MAX_HEADER_BYTES = 2048;
export const MAX_IMAGE_BYTES = 400 * 1024;

export function encodeFrame(header: FrameHeader, jpeg: Uint8Array): ArrayBuffer {
  // JSON.stringify drops undefined; the backend (exclude_none) omits nulls, so do the same for byte parity.
  const clean = Object.fromEntries(Object.entries(header).filter(([, v]) => v !== null && v !== undefined));
  const raw = new TextEncoder().encode(JSON.stringify(clean));
  if (raw.length > MAX_HEADER_BYTES) throw new Error(`header too large: ${raw.length} > ${MAX_HEADER_BYTES}`);
  if (jpeg.length > MAX_IMAGE_BYTES) throw new Error(`image too large: ${jpeg.length} > ${MAX_IMAGE_BYTES}`);
  const out = new Uint8Array(4 + raw.length + jpeg.length);
  new DataView(out.buffer).setUint32(0, raw.length, true);
  out.set(raw, 4);
  out.set(jpeg, 4 + raw.length);
  return out.buffer;
}

export function decodeFrame(buf: ArrayBuffer): { header: FrameHeader; jpeg: Uint8Array } {
  if (buf.byteLength < 4) throw new Error("frame shorter than the 4-byte length prefix");
  const hlen = new DataView(buf).getUint32(0, true);
  if (hlen === 0 || hlen > MAX_HEADER_BYTES) throw new Error(`invalid header length ${hlen}`);
  if (buf.byteLength < 4 + hlen) throw new Error("frame truncated inside the header");
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen))) as FrameHeader;
  const jpeg = new Uint8Array(buf, 4 + hlen);
  if (jpeg.length === 0) throw new Error("frame has no image payload");
  if (jpeg.length > MAX_IMAGE_BYTES) throw new Error(`image too large: ${jpeg.length} > ${MAX_IMAGE_BYTES}`);
  if (!(jpeg[0] === 0xff && jpeg[1] === 0xd8 && jpeg[2] === 0xff)) throw new Error("payload is not a JPEG");
  return { header, jpeg };
}
