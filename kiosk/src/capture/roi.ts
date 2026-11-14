// Mean linear-RGB of a rectangular region of interest from RGBA pixels (E1 browser probe). Pure, unit-tested.
const LUT = new Float64Array(256).map((_, i) => {
  const c = i / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
});

/** `fraction` = [x, y, w, h] in 0..1 of the image. Returns the mean linear RGB, or null if the region is empty. */
export function roiMeanLinear(rgba: Uint8ClampedArray, width: number, height: number, fraction: [number, number, number, number]): [number, number, number] | null {
  const x0 = Math.max(0, Math.floor(fraction[0] * width));
  const y0 = Math.max(0, Math.floor(fraction[1] * height));
  const x1 = Math.min(width, Math.ceil((fraction[0] + fraction[2]) * width));
  const y1 = Math.min(height, Math.ceil((fraction[1] + fraction[3]) * height));
  let r = 0, g = 0, b = 0, n = 0;
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const i = (y * width + x) * 4;
      r += LUT[rgba[i]];
      g += LUT[rgba[i + 1]];
      b += LUT[rgba[i + 2]];
      n++;
    }
  }
  return n ? [r / n, g / n, b / n] : null;
}
