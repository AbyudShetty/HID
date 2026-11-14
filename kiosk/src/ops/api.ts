// Operator REST client (plan §8.2). The operator token lives in sessionStorage only.
const KEY = "hid_operator_token";

export function getOperatorToken(): string {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}
export function setOperatorToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    /* storage unavailable: the token is simply not remembered */
  }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function check(res: Response): Promise<unknown> {
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = typeof body === "object" && body !== null && "detail" in body ? String((body as { detail: unknown }).detail) : String(body ?? res.statusText);
    throw new ApiError(res.status, `${res.status}: ${detail}`);
  }
  return body;
}

const auth = () => ({ Authorization: `Bearer ${getOperatorToken()}` });

export async function apiGet<T>(path: string): Promise<T> {
  return (await check(await fetch(path, { headers: auth() }))) as T;
}

export interface CollectChallenge {
  type: "session.ready";
  session_id: string;
  expires_in_ms: number;
  challenge: import("../types/protocol").Challenge;
  server_version: string;
  policy_version: string;
  capture_config: { crop_size: number; context_scale: number; crop_fps: number; jpeg_quality: number; keyframe_count: number; keyframe_max_width: number };
}

export const getCollectChallenge = (palette?: "P1" | "P2") =>
  apiGet<CollectChallenge>(`/api/v1/collect/challenge${palette ? `?palette_id=${palette}` : ""}`);

export interface UploadResult {
  session_id: string;
  stored: string;
  qc: { n_crops: number; n_keyframes: number; crop_fps: number | null; capture_span_ms: number | null; covers_challenge: boolean; warnings: string[] };
}

export async function postBundle(body: ArrayBuffer): Promise<UploadResult> {
  return (await check(await fetch("/api/v1/collect/bundles", { method: "POST", headers: { ...auth(), "Content-Type": "application/x-hid-bundle" }, body }))) as UploadResult;
}

/** Measure-only: analysed in memory by the backend, nothing is stored. */
export async function postMeasure(body: ArrayBuffer): Promise<Record<string, unknown>> {
  return (await check(await fetch("/api/v1/collect/measure", { method: "POST", headers: { ...auth(), "Content-Type": "application/x-hid-bundle" }, body }))) as Record<string, unknown>;
}

export interface PreviewResult {
  image_size: [number, number];
  face: { box: number[]; score: number; landmarks: number[][] } | null;
  significant_faces: number;
  regions: Record<string, { mean_rgb: number[] | null; pixels: number; clipped_fraction: number; paths: number[][][] }>;
  timings_ms: Record<string, number>;
  model_load_ms?: number;
  model?: string;
}

export async function postPreview(jpeg: Blob): Promise<PreviewResult> {
  return (await check(await fetch("/api/v1/collect/preview", { method: "POST", headers: { ...auth(), "Content-Type": "image/jpeg" }, body: jpeg }))) as PreviewResult;
}

export async function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  return (await check(await fetch(path, { method: "POST", headers: { ...auth(), "Content-Type": "application/json" }, body: JSON.stringify(body) }))) as T;
}
