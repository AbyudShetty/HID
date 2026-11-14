// Live integration test: the real KioskSocket against a running backend. Skipped unless LIVE_WS_URL is set:
//   LIVE_WS_URL=ws://localhost:8000/api/v1/kiosk/ws LIVE_KIOSK_TOKEN=... npx vitest run src/net/live.test.ts
import { describe, expect, it } from "vitest";
import samples from "../../../backend/tests/fixtures/protocol_samples.json";
import type { CameraInfo, DisplayInfo } from "../types/protocol";
import { KioskSocket } from "./wsClient";

// Vitest runs in node; read env without needing @types/node.
const env = (globalThis as unknown as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const URL_ = env.LIVE_WS_URL;
const TOKEN = env.LIVE_KIOSK_TOKEN ?? "";

function until(sock: KioskSocket, pred: () => boolean, ms = 5000): Promise<void> {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const tick = () => (pred() ? resolve() : Date.now() - t0 > ms ? reject(new Error(`timeout, state=${sock.state}, err=${sock.lastError}`)) : setTimeout(tick, 25));
    tick();
  });
}

const mk = (token: string) =>
  new KioskSocket({
    url: URL_!,
    kioskId: "kiosk-live",
    kioskToken: token,
    clientVersion: "0.1.0",
    camera: () => samples.client.hello.camera as unknown as CameraInfo,
    display: () => samples.client.hello.display as unknown as DisplayInfo,
  });

describe.skipIf(!URL_)("live backend", () => {
  it("hello round trip reaches ready and reports the provisional policy", async () => {
    const s = mk(TOKEN);
    s.connect();
    await until(s, () => s.state === "ready");
    expect(s.helloAck?.server_version).toBeTruthy();
    expect(s.helloAck?.policy.provisional).toBe(true);
    s.close();
  });

  it("a wrong token ends in 'failed' and does not reconnect", async () => {
    const s = mk("definitely-wrong");
    s.connect();
    await until(s, () => s.state === "failed");
    expect(s.reconnects).toBe(0);
    s.close();
  });
});
