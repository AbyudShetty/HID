import { describe, expect, it } from "vitest";
import { centerFaceBox, computeCropBox, countSignificantFaces, largestBox } from "./crop";

const FRAME = { width: 1280, height: 720 };

describe("computeCropBox", () => {
  it("is a square of contextScale * max(w, h) centred on the face", () => {
    const [x, y, w, h] = computeCropBox([560, 260, 160, 200], FRAME, 2.0);
    expect([w, h]).toEqual([400, 400]);
    expect(x + w / 2).toBe(640);
    expect(y + h / 2).toBe(360);
  });

  it("shifts (does not shrink) to stay inside the frame", () => {
    expect(computeCropBox([0, 0, 100, 100], FRAME, 2.0)).toEqual([0, 0, 200, 200]);
    expect(computeCropBox([1180, 620, 100, 100], FRAME, 2.0)).toEqual([1080, 520, 200, 200]);
  });

  it("clamps the side to the frame's short edge", () => {
    const [x, y, w, h] = computeCropBox([300, 100, 600, 600], FRAME, 2.0);
    expect([w, h]).toEqual([720, 720]);
    expect(y).toBe(0);
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x + w).toBeLessThanOrEqual(FRAME.width);
  });

  it("always returns an in-frame box (property check)", () => {
    for (let i = 0; i < 500; i++) {
      const w = 40 + ((i * 37) % 300);
      const h = 40 + ((i * 53) % 300);
      const fx = (i * 97) % (FRAME.width - w);
      const fy = (i * 61) % (FRAME.height - h);
      const [x, y, s] = computeCropBox([fx, fy, w, h], FRAME, 2.0);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(x + s).toBeLessThanOrEqual(FRAME.width);
      expect(y + s).toBeLessThanOrEqual(FRAME.height);
    }
  });
});

describe("face boxes", () => {
  it("centerFaceBox is centred and inside the frame", () => {
    const [x, y, w, h] = centerFaceBox(FRAME);
    expect(Math.abs(x + w / 2 - 640)).toBeLessThanOrEqual(1); // integer pixels: at most 1 px of rounding
    expect(Math.abs(y + h / 2 - 360)).toBeLessThanOrEqual(1);
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x + w).toBeLessThanOrEqual(FRAME.width);
  });

  it("largestBox picks by area", () => {
    expect(largestBox([[0, 0, 10, 10], [0, 0, 30, 30], [0, 0, 20, 20]])).toEqual([0, 0, 30, 30]);
    expect(largestBox([])).toBeNull();
  });

  it("ignores faces smaller than half the primary's height (plan: judges crowd the kiosk)", () => {
    const primary: [number, number, number, number] = [0, 0, 160, 200];
    expect(countSignificantFaces([primary])).toBe(1);
    expect(countSignificantFaces([primary, [300, 0, 60, 80]])).toBe(1); // background face, 40 % of primary
    expect(countSignificantFaces([primary, [300, 0, 150, 190]])).toBe(2); // second real face
    expect(countSignificantFaces([])).toBe(0);
  });
});
