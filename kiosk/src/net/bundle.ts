// Session bundle upload body (ADR-001): repeated [u32 LE name_len][name utf-8][u32 LE data_len][data].
// Must stay byte-compatible with backend/app/pipeline/bundle_io.py (checked by bundle.test.ts against a Python-packed fixture).

export type BundleEntry = [name: string, data: Uint8Array];

const NAME_RE = /^(meta\.json|challenge\.json|label\.json|frames\.jsonl|keyframes\.jsonl|(crops|keyframes)\/[A-Za-z0-9_-]{1,40}\.(jpg|png))$/;

export function validEntryName(name: string): boolean {
  return NAME_RE.test(name);
}

export function packBundle(entries: BundleEntry[]): ArrayBuffer {
  const enc = new TextEncoder();
  const seen = new Set<string>();
  let total = 0;
  const named = entries.map(([name, data]) => {
    if (!validEntryName(name)) throw new Error(`invalid entry name ${name}`);
    if (seen.has(name)) throw new Error(`duplicate entry ${name}`);
    seen.add(name);
    const raw = enc.encode(name);
    total += 8 + raw.length + data.length;
    return { raw, data };
  });
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  let pos = 0;
  for (const { raw, data } of named) {
    view.setUint32(pos, raw.length, true);
    pos += 4;
    out.set(raw, pos);
    pos += raw.length;
    view.setUint32(pos, data.length, true);
    pos += 4;
    out.set(data, pos);
    pos += data.length;
  }
  return out.buffer;
}

export function unpackBundle(buf: ArrayBuffer): BundleEntry[] {
  const bytes = new Uint8Array(buf);
  const view = new DataView(buf);
  const dec = new TextDecoder();
  const out: BundleEntry[] = [];
  let pos = 0;
  while (pos < bytes.length) {
    const nameLen = view.getUint32(pos, true);
    pos += 4;
    const name = dec.decode(bytes.subarray(pos, pos + nameLen));
    pos += nameLen;
    const dataLen = view.getUint32(pos, true);
    pos += 4;
    out.push([name, bytes.slice(pos, pos + dataLen)]);
    pos += dataLen;
  }
  return out;
}
