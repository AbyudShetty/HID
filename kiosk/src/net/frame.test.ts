import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import type { FrameHeader } from "../types/protocol";
import { decodeFrame, encodeFrame, MAX_IMAGE_BYTES } from "./frame";

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, ...new Array(64).fill(0), 0xff, 0xd9]);
const header = samples.records.frame_header as unknown as FrameHeader;

describe("binary frame framing", () => {
  it("round-trips", () => {
    const got = decodeFrame(encodeFrame(header, JPEG));
    expect(got.header).toEqual(header);
    expect(Array.from(got.jpeg)).toEqual(Array.from(JPEG));
  });

  it("decodes a frame produced by the Python encoder (records.frame_sample_b64)", () => {
    const pyBytes = Uint8Array.from(atob(samples.records.frame_sample_b64), (c) => c.charCodeAt(0));
    const decoded = decodeFrame(pyBytes.buffer);
    expect(decoded.header).toEqual(header);
    expect(Array.from(decoded.jpeg)).toEqual(Array.from(JPEG));
  });

  it("rejects malformed frames", () => {
    expect(() => decodeFrame(new ArrayBuffer(2))).toThrow(/length prefix/);
    const good = new Uint8Array(encodeFrame(header, JPEG));
    expect(() => decodeFrame(good.slice(0, 10).buffer)).toThrow(/truncated/);
    const notJpeg = new Uint8Array(encodeFrame(header, JPEG));
    notJpeg[notJpeg.length - JPEG.length] = 0x00;
    expect(() => decodeFrame(notJpeg.buffer)).toThrow(/not a JPEG/);
  });

  it("enforces size limits when encoding", () => {
    expect(() => encodeFrame(header, new Uint8Array(MAX_IMAGE_BYTES + 1))).toThrow(/too large/);
  });
});
