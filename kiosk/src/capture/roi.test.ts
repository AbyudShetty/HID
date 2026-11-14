import { describe, expect, it } from "vitest";
import { roiMeanLinear } from "./roi";

function image(w: number, h: number, fill: (x: number, y: number) => [number, number, number]) {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const [r, g, b] = fill(x, y); d.set([r, g, b, 255], (y * w + x) * 4); }
  return d;
}

describe("roiMeanLinear", () => {
  it("linearises sRGB (128 -> 0.2158605) and ignores pixels outside the ROI", () => {
    const img = image(10, 10, (x) => (x < 5 ? [128, 128, 128] : [255, 0, 0]));
    const m = roiMeanLinear(img, 10, 10, [0, 0, 0.5, 1])!;
    expect(m[0]).toBeCloseTo(0.2158605, 6);
    expect(m[2]).toBeCloseTo(0.2158605, 6);
    expect(roiMeanLinear(img, 10, 10, [0.5, 0, 0.5, 1])).toEqual([1, 0, 0]);
  });
  it("averages in linear light, not in sRGB", () => {
    const img = image(2, 1, (x) => (x === 0 ? [0, 0, 0] : [255, 255, 255]));
    expect(roiMeanLinear(img, 2, 1, [0, 0, 1, 1])![0]).toBeCloseTo(0.5, 9); // sRGB average would give 0.2158
  });
  it("returns null for an empty region and clamps to the image", () => {
    const img = image(4, 4, () => [10, 10, 10]);
    expect(roiMeanLinear(img, 4, 4, [0.5, 0.5, 0, 0])).toBeNull();
    expect(roiMeanLinear(img, 4, 4, [0.5, 0.5, 2, 2])).not.toBeNull();
  });
});
