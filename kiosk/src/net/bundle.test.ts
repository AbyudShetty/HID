import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import { packBundle, unpackBundle, validEntryName } from "./bundle";

const fixture = Uint8Array.from(atob(samples.records.bundle_sample_b64), (c) => c.charCodeAt(0));

describe("bundle framing", () => {
  it("unpacks the bundle packed by the Python encoder", () => {
    const entries = unpackBundle(fixture.buffer);
    expect(entries.map(([n]) => n)).toEqual(samples.records.bundle_sample_names);
    expect(new TextDecoder().decode(entries[0][1])).toBe('{"k":1}');
    expect(Array.from(entries[1][1])).toEqual([0xff, 0xd8, 0xff, 0xe0, 0x61, 0x62, 0x63]);
  });

  it("re-packs byte-for-byte identically to the Python encoder", () => {
    const again = new Uint8Array(packBundle(unpackBundle(fixture.buffer)));
    expect(Array.from(again)).toEqual(Array.from(fixture));
  });

  it("rejects unsafe or duplicate entry names", () => {
    for (const bad of ["../meta.json", "/etc/passwd", "crops/../x.jpg", "crops/a/b.jpg", "other.json", "crops/x.exe"]) {
      expect(validEntryName(bad), bad).toBe(false);
      expect(() => packBundle([[bad, new Uint8Array(1)]])).toThrow(/invalid entry name/);
    }
    expect(() => packBundle([["meta.json", new Uint8Array(1)], ["meta.json", new Uint8Array(1)]])).toThrow(/duplicate/);
  });
});
