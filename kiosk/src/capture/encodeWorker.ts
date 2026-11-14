// JPEG encoding off the main thread (plan §9.3) so rendering/timestamp work is not delayed by encode cost.
interface EncodeRequest {
  id: number;
  bitmap: ImageBitmap;
  quality: number;
}

const ctx = self as unknown as {
  onmessage: ((ev: MessageEvent<EncodeRequest>) => void) | null;
  postMessage: (msg: unknown, transfer?: Transferable[]) => void;
};

ctx.onmessage = async (ev) => {
  const { id, bitmap, quality } = ev.data;
  try {
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const g = canvas.getContext("2d");
    if (!g) throw new Error("no 2d context in worker");
    g.drawImage(bitmap, 0, 0);
    bitmap.close();
    const blob = await canvas.convertToBlob({ type: "image/jpeg", quality });
    const buf = await blob.arrayBuffer();
    ctx.postMessage({ id, buf }, [buf]);
  } catch (e) {
    ctx.postMessage({ id, error: e instanceof Error ? e.message : String(e) });
  }
};
