import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import type { CameraInfo, DisplayInfo } from "../types/protocol";
import { KioskSocket, type WebSocketLike } from "./wsClient";

class FakeWS implements WebSocketLike {
  binaryType = "blob";
  readyState = 0;
  sent: unknown[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  send(d: unknown) {
    this.sent.push(d);
  }
  close() {
    this.readyState = 3;
    this.onclose?.({});
  }
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  recv(msg: unknown) {
    this.onmessage?.({ data: typeof msg === "string" ? msg : JSON.stringify(msg) });
  }
  drop() {
    this.readyState = 3;
    this.onclose?.({});
  }
}

function rig() {
  const sockets: FakeWS[] = [];
  const timers: { fn: () => void; ms: number; cancelled: boolean }[] = [];
  const intervals: { fn: () => void; ms: number; cancelled: boolean }[] = [];
  const client = new KioskSocket({
    url: "ws://test/api/v1/kiosk/ws",
    kioskId: "kiosk-01",
    kioskToken: "tok",
    clientVersion: "0.1.0",
    camera: () => samples.client.hello.camera as unknown as CameraInfo,
    display: () => samples.client.hello.display as unknown as DisplayInfo,
    wsFactory: () => {
      const w = new FakeWS();
      sockets.push(w);
      return w;
    },
    setTimer: (fn, ms) => {
      const t = { fn, ms, cancelled: false };
      timers.push(t);
      return t;
    },
    clearTimer: (h) => {
      (h as { cancelled: boolean }).cancelled = true;
    },
    setIntervalFn: (fn, ms) => {
      const t = { fn, ms, cancelled: false };
      intervals.push(t);
      return t;
    },
    clearIntervalFn: (h) => {
      (h as { cancelled: boolean }).cancelled = true;
    },
  });
  return { client, sockets, timers, intervals };
}

const helloAck = samples.server.hello_ack;

describe("KioskSocket", () => {
  it("sends hello on open and becomes ready on hello_ack", () => {
    const { client, sockets } = rig();
    client.connect();
    expect(client.state).toBe("connecting");
    expect(sockets[0].binaryType).toBe("arraybuffer");
    sockets[0].open();
    expect(client.state).toBe("authenticating");
    const hello = JSON.parse(sockets[0].sent[0] as string);
    expect(hello).toMatchObject({ type: "hello", kiosk_id: "kiosk-01", kiosk_token: "tok", client_version: "0.1.0" });
    sockets[0].recv(helloAck);
    expect(client.state).toBe("ready");
    expect(client.helloAck?.policy.provisional).toBe(true);
  });

  it("answers ping with pong and pings every 10 s once ready", () => {
    const { client, sockets, intervals } = rig();
    client.connect();
    sockets[0].open();
    sockets[0].recv(helloAck);
    expect(intervals).toHaveLength(1);
    expect(intervals[0].ms).toBe(10_000);
    sockets[0].recv({ type: "ping" });
    expect(JSON.parse(sockets[0].sent.at(-1) as string)).toEqual({ type: "pong" });
    intervals[0].fn();
    expect(JSON.parse(sockets[0].sent.at(-1) as string)).toEqual({ type: "ping" });
  });

  it("reconnects with exponential backoff, resetting after a successful hello", () => {
    const { client, sockets, timers } = rig();
    client.connect();
    sockets[0].open();
    sockets[0].drop();
    expect(client.state).toBe("closed");
    expect(timers.map((t) => t.ms)).toEqual([1000]);
    timers[0].fn();
    expect(sockets).toHaveLength(2);
    sockets[1].drop(); // never opened: second failure
    expect(timers.map((t) => t.ms)).toEqual([1000, 2000]);
    timers[1].fn();
    sockets[2].open();
    sockets[2].recv(helloAck); // success resets the backoff
    sockets[2].drop();
    expect(timers.at(-1)?.ms).toBe(1000);
    expect(client.backoffFor(99)).toBe(15000);
  });

  it("does not reconnect after BAD_TOKEN or an explicit close", () => {
    const a = rig();
    a.client.connect();
    a.sockets[0].open();
    a.sockets[0].recv({ type: "error", code: "BAD_TOKEN", message: "no", session_id: null });
    expect(a.client.state).toBe("failed");
    a.sockets[0].drop();
    expect(a.timers).toHaveLength(0);
    expect(a.client.state).toBe("failed");

    const b = rig();
    b.client.connect();
    b.sockets[0].open();
    b.client.close();
    expect(b.timers).toHaveLength(0);
    expect(b.client.state).toBe("closed");
  });

  it("ignores invalid server messages but records the error", () => {
    const { client, sockets } = rig();
    client.connect();
    sockets[0].open();
    sockets[0].recv({ type: "hello_ack", nonsense: true });
    expect(client.state).toBe("authenticating");
    expect(client.lastError).toMatch(/invalid server message/);
  });

  it("refuses to send while not open", () => {
    const { client } = rig();
    expect(() => client.sendJson({ type: "ping" })).toThrow(/not open/);
  });
});
