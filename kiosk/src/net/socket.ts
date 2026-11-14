// Process-wide kiosk socket (one persistent connection per page, plan F-05).
import { useSyncExternalStore } from "react";
import type { CameraInfo, DisplayInfo } from "../types/protocol";
import { KioskSocket } from "./wsClient";

export const CLIENT_VERSION = "0.1.0";
const KIOSK_ID = import.meta.env.VITE_KIOSK_ID ?? "kiosk-01";
const KIOSK_TOKEN = import.meta.env.VITE_KIOSK_TOKEN ?? "";

/** Camera details reported in hello. Until a capture module opens a camera this honestly reports "no camera". */
let cameraInfo: CameraInfo = { width: 0, height: 0, fps: 0, lock_method: "none", settings: {}, capabilities: {}, label: null };
export function setCameraInfo(info: CameraInfo): void {
  cameraInfo = info;
}

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/v1/kiosk/ws`;
}

let socket: KioskSocket | null = null;
export function getSocket(): KioskSocket {
  if (!socket) {
    socket = new KioskSocket({
      url: wsUrl(),
      kioskId: KIOSK_ID,
      kioskToken: KIOSK_TOKEN,
      clientVersion: CLIENT_VERSION,
      camera: () => cameraInfo,
      display: (): DisplayInfo => ({
        width: window.screen.width,
        height: window.screen.height,
        device_pixel_ratio: window.devicePixelRatio,
      }),
    });
  }
  return socket;
}

export function useSocket(): { socket: KioskSocket; state: KioskSocket["state"] } {
  const s = getSocket();
  const state = useSyncExternalStore(
    (cb) => s.onState(cb),
    () => s.state,
  );
  return { socket: s, state };
}
