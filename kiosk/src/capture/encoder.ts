// Thin promise wrapper over the JPEG encode worker pool.
export class JpegEncoder {
  private readonly workers: Worker[];
  private readonly pending = new Map<number, { resolve: (b: Uint8Array) => void; reject: (e: Error) => void }>();
  private nextId = 1;
  private rr = 0;

  constructor(poolSize = 2) {
    this.workers = Array.from({ length: poolSize }, () => {
      const w = new Worker(new URL("./encodeWorker.ts", import.meta.url), { type: "module" });
      w.onmessage = (ev: MessageEvent<{ id: number; buf?: ArrayBuffer; error?: string }>) => {
        const p = this.pending.get(ev.data.id);
        if (!p) return;
        this.pending.delete(ev.data.id);
        if (ev.data.error || !ev.data.buf) p.reject(new Error(ev.data.error ?? "encode failed"));
        else p.resolve(new Uint8Array(ev.data.buf));
      };
      return w;
    });
  }

  encode(bitmap: ImageBitmap, quality: number): Promise<Uint8Array> {
    const id = this.nextId++;
    const worker = this.workers[this.rr++ % this.workers.length];
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      worker.postMessage({ id, bitmap, quality }, [bitmap]);
    });
  }

  dispose(): void {
    for (const w of this.workers) w.terminate();
    this.pending.clear();
  }
}
