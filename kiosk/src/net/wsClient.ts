// Persistent kiosk WebSocket (plan F-05, §8.1): one connection per kiosk, opened at page load and kept alive.
// hello -> hello_ack, ping/pong every 10 s, automatic reconnect with exponential backoff.
// Dependencies (WebSocket factory, timers) are injectable so the logic is unit-testable without a browser.
import type { CameraInfo, ClientMessage, DisplayInfo, HelloAck, ServerMessage } from "../types/protocol";
import { parseServerMessage } from "../types/validate";

export type SocketState = "idle" | "connecting" | "authenticating" | "ready" | "closed" | "failed";

export interface WebSocketLike {
  binaryType: string;
  readyState: number;
  send(data: string | ArrayBufferLike | ArrayBufferView): void;
  close(): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}

export interface KioskSocketOptions {
  url: string;
  kioskId: string;
  kioskToken: string;
  clientVersion: string;
  camera: () => CameraInfo;
  display: () => DisplayInfo;
  wsFactory?: (url: string) => WebSocketLike;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (h: unknown) => void;
  setIntervalFn?: (fn: () => void, ms: number) => unknown;
  clearIntervalFn?: (h: unknown) => void;
  pingIntervalMs?: number;
  backoffMs?: number[]; // delays for consecutive reconnect attempts; the last value repeats
}

export const DEFAULT_BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];
const OPEN = 1;

export class KioskSocket {
  state: SocketState = "idle";
  helloAck: HelloAck | null = null;
  lastError: string | null = null;
  reconnects = 0;

  private ws: WebSocketLike | null = null;
  private attempt = 0;
  private stopped = false;
  private reconnectTimer: unknown = null;
  private pingTimer: unknown = null;
  private readonly stateListeners = new Set<(s: SocketState) => void>();
  private readonly messageListeners = new Set<(m: ServerMessage) => void>();
  private readonly binaryListeners = new Set<(b: ArrayBuffer) => void>();
  private readonly o: Required<Pick<KioskSocketOptions, "wsFactory" | "setTimer" | "clearTimer" | "setIntervalFn" | "clearIntervalFn" | "pingIntervalMs" | "backoffMs">> &
    KioskSocketOptions;

  constructor(opts: KioskSocketOptions) {
    this.o = {
      wsFactory: (url) => new WebSocket(url) as unknown as WebSocketLike,
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
      setIntervalFn: (fn, ms) => setInterval(fn, ms),
      clearIntervalFn: (h) => clearInterval(h as ReturnType<typeof setInterval>),
      pingIntervalMs: 10_000,
      backoffMs: DEFAULT_BACKOFF_MS,
      ...opts,
    };
  }

  onState(fn: (s: SocketState) => void): () => void {
    this.stateListeners.add(fn);
    return () => this.stateListeners.delete(fn);
  }
  onMessage(fn: (m: ServerMessage) => void): () => void {
    this.messageListeners.add(fn);
    return () => this.messageListeners.delete(fn);
  }
  onBinary(fn: (b: ArrayBuffer) => void): () => void {
    this.binaryListeners.add(fn);
    return () => this.binaryListeners.delete(fn);
  }

  connect(): void {
    if (this.ws) return;
    this.stopped = false;
    this.setState("connecting");
    const ws = this.o.wsFactory(this.o.url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => {
      this.setState("authenticating");
      this.sendJson({
        type: "hello",
        kiosk_id: this.o.kioskId,
        kiosk_token: this.o.kioskToken,
        client_version: this.o.clientVersion,
        camera: this.o.camera(),
        display: this.o.display(),
      });
    };
    ws.onmessage = (ev) => this.handle(ev.data);
    ws.onerror = () => {
      this.lastError = "websocket error";
    };
    ws.onclose = () => this.handleClose(ws);
  }

  close(): void {
    this.stopped = true;
    this.stopPing();
    if (this.reconnectTimer !== null) this.o.clearTimer(this.reconnectTimer);
    this.reconnectTimer = null;
    const ws = this.ws;
    this.ws = null;
    ws?.close();
    this.setState("closed");
  }

  sendJson(msg: ClientMessage): void {
    this.requireOpen().send(JSON.stringify(msg));
  }
  sendBinary(buf: ArrayBuffer): void {
    this.requireOpen().send(buf);
  }

  /** Delay before reconnect attempt number `n` (0-based). */
  backoffFor(n: number): number {
    const d = this.o.backoffMs;
    return d[Math.min(n, d.length - 1)];
  }

  private requireOpen(): WebSocketLike {
    if (!this.ws || this.ws.readyState !== OPEN) throw new Error("socket is not open");
    return this.ws;
  }

  private handle(data: unknown): void {
    if (typeof data !== "string") {
      for (const l of this.binaryListeners) l(data as ArrayBuffer);
      return;
    }
    let msg: ServerMessage;
    try {
      msg = parseServerMessage(data);
    } catch (e) {
      this.lastError = e instanceof Error ? e.message : String(e);
      return;
    }
    if (msg.type === "hello_ack") {
      this.helloAck = msg;
      this.attempt = 0;
      this.setState("ready");
      this.startPing();
    } else if (msg.type === "ping") {
      this.sendJson({ type: "pong" });
      return;
    } else if (msg.type === "pong") {
      return;
    } else if (msg.type === "error" && msg.code === "BAD_TOKEN") {
      this.lastError = `server rejected the kiosk token: ${msg.message}`;
      this.stopped = true; // retrying with the same token cannot succeed
      this.setState("failed");
    }
    for (const l of this.messageListeners) l(msg);
  }

  private handleClose(ws: WebSocketLike): void {
    if (this.ws !== ws) return;
    this.ws = null;
    this.stopPing();
    if (this.stopped) {
      if (this.state !== "failed") this.setState("closed");
      return;
    }
    this.setState("closed");
    const delay = this.backoffFor(this.attempt++);
    this.reconnects++;
    this.reconnectTimer = this.o.setTimer(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = this.o.setIntervalFn(() => {
      if (this.ws && this.ws.readyState === OPEN) this.sendJson({ type: "ping" });
    }, this.o.pingIntervalMs);
  }
  private stopPing(): void {
    if (this.pingTimer !== null) this.o.clearIntervalFn(this.pingTimer);
    this.pingTimer = null;
  }
  private setState(s: SocketState): void {
    if (this.state === s) return;
    this.state = s;
    for (const l of this.stateListeners) l(s);
  }
}
