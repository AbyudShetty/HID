// Hand-written runtime guards for the wire contracts (no schema library: plan §7.3).
// Semantics mirror the pydantic models: required fields must be present with the right type; unknown keys are rejected.
import type { ClientMessage, ServerMessage } from "./protocol";

export type Check = (v: unknown, path: string) => string | null;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

export const str: Check = (v, p) => (typeof v === "string" ? null : `${p}: expected string`);
export const num: Check = (v, p) => (typeof v === "number" && Number.isFinite(v) ? null : `${p}: expected number`);
export const int: Check = (v, p) => (typeof v === "number" && Number.isInteger(v) ? null : `${p}: expected integer`);
export const bool: Check = (v, p) => (typeof v === "boolean" ? null : `${p}: expected boolean`);
export const anyObj: Check = (v, p) => (isObj(v) ? null : `${p}: expected object`);
export const nullable =
  (c: Check): Check =>
  (v, p) =>
    v === null ? null : c(v, p);
export const arrOf =
  (c: Check): Check =>
  (v, p) => {
    if (!Array.isArray(v)) return `${p}: expected array`;
    for (let i = 0; i < v.length; i++) {
      const e = c(v[i], `${p}[${i}]`);
      if (e) return e;
    }
    return null;
  };
export const tuple =
  (n: number, c: Check): Check =>
  (v, p) => {
    if (!Array.isArray(v) || v.length !== n) return `${p}: expected array of length ${n}`;
    for (let i = 0; i < n; i++) {
      const e = c(v[i], `${p}[${i}]`);
      if (e) return e;
    }
    return null;
  };
export const oneOf =
  (...vals: string[]): Check =>
  (v, p) =>
    typeof v === "string" && vals.includes(v) ? null : `${p}: expected one of ${vals.join("|")}`;
export const lit =
  (val: string): Check =>
  (v, p) =>
    v === val ? null : `${p}: expected literal ${val}`;
export const recordOf =
  (c: Check): Check =>
  (v, p) => {
    if (!isObj(v)) return `${p}: expected object`;
    for (const [k, x] of Object.entries(v)) {
      const e = c(x, `${p}.${k}`);
      if (e) return e;
    }
    return null;
  };

/** Object check. Keys in `required` must exist; keys in `optional` may be absent; any other key is an error. */
export const obj =
  (required: Record<string, Check>, optional: Record<string, Check> = {}): Check =>
  (v, p) => {
    if (!isObj(v)) return `${p}: expected object`;
    for (const [k, c] of Object.entries(required)) {
      if (!(k in v)) return `${p}.${k}: missing`;
      const e = c(v[k], `${p}.${k}`);
      if (e) return e;
    }
    for (const [k, x] of Object.entries(v)) {
      if (k in required) continue;
      if (k in optional) {
        const e = optional[k](x, `${p}.${k}`);
        if (e) return e;
        continue;
      }
      return `${p}.${k}: unknown field`;
    }
    return null;
  };

const rgb = tuple(3, int);
const box = tuple(4, num);
const segment = obj({ rgb, duration_ms: int });
const challenge = obj({ nonce: str, palette_id: str, neutral: segment, segments: arrOf(segment), total_ms: int });
const policyInfo = obj({ version: str, provisional: bool });
const purpose = oneOf("access", "enroll", "collect", "stepup_recapture");
const mode = oneOf("face", "badge");
const decision = oneOf("ALLOW", "REQUEST_VERIFICATION", "DENY");

export const collectLabel = obj(
  {
    subject_id: str,
    presenter_id: str,
    class: oneOf("bona_fide", "attack"),
    consent_id: str,
  },
  {
    enrolled: nullable(bool),
    claimed_badge_id: nullable(str),
    capture_procedure: oneOf("standard", "on_the_spot_phone", "auto_repeat_rig", "redteam"),
    pai_family: oneOf("none", "print", "screen_photo", "video_replay", "mask"),
    pai_species: str,
    instrument_id: nullable(str),
    lighting: oneOf("office", "dim", "backlit", "side_lamp", "bright"),
    distance_cm: nullable(int),
    glasses: bool,
    skin_tone_bucket: oneOf("unreported", "light", "medium", "dark"),
    operator: str,
    notes: str,
  },
);

const cameraInfo = obj(
  { width: int, height: int, fps: num, lock_method: oneOf("browser", "prelock", "agent", "none") },
  { settings: anyObj, capabilities: anyObj, label: nullable(str) },
);
const displayInfo = obj({ width: int, height: int }, { device_pixel_ratio: num });

export const frameHeader = obj(
  { session_id: str, kind: oneOf("crop", "keyframe"), seq: int, t_capture: num, crop_box: box, frame_size: tuple(2, int) },
  { client_face_box: nullable(box), capture_time_source: nullable(oneOf("captureTime", "now")) },
);

const flow = obj({
  capture: obj({ status: oneOf("ok", "low_quality") }, { frames_received: int, quality_reasons: arrOf(str), duration_ms: nullable(num) }),
  liveness: obj({ status: oneOf("live", "uncertain", "spoof", "not_evaluated") }, { p_live: nullable(num), rule: nullable(str) }),
  authentication: obj(
    { status: oneOf("match", "borderline", "no_match", "mismatch", "not_evaluated") },
    { similarity: nullable(num), threshold: nullable(num) },
  ),
  decision: obj({ outcome: decision, reason_code: str }, { finalize_ms: nullable(num) }),
});
const signalOut = obj(
  { status: oneOf("ok", "low_snr", "low_quality", "unavailable", "error") },
  {
    p_live: nullable(num),
    raw_score: nullable(num),
    features: nullable(recordOf(num)),
    series: nullable(anyObj),
    per_model: nullable(recordOf(num)),
    latency_ms: nullable(num),
    model_version: nullable(str),
  },
);
const decisionFields = {
  session_id: str,
  kiosk_id: str,
  purpose,
  mode,
  decision,
  decision_label: oneOf("Allow", "Request Additional Verification", "Deny"),
  reason_code: str,
  reason_text: str,
  liveness: obj({ status: oneOf("ok", "uncertain", "spoof", "not_evaluated") }, { p_live: nullable(num), fusion_method: nullable(oneOf("lr", "min_provisional")) }),
  identity: obj(
    { status: oneOf("match", "mismatch", "borderline", "no_match", "not_evaluated") },
    {
      engine: nullable(str),
      subject_id: nullable(str),
      display_name: nullable(str),
      similarity: nullable(num),
      margin: nullable(num),
      threshold: nullable(num),
      used_in_decision: bool,
    },
  ),
  flow,
  signals: obj(
    { quality: obj({ status: oneOf("ok", "low_quality"), pass: bool }, { reasons: arrOf(str), metrics: recordOf(num) }) },
    { chroma: nullable(signalOut), passive: nullable(signalOut), device: nullable(signalOut) },
  ),
  policy: policyInfo,
  versions: obj({ server: str }, { models: recordOf(str) }),
  created_at: str,
};
const decisionOptional = {
  stepup: obj(
    {},
    {
      required: bool,
      options: arrOf(oneOf("recapture", "pin", "totp", "manual_review", "head_turn")),
      stepup_token: nullable(str),
      attempts_left: int,
    },
  ),
  timings_ms: recordOf(num),
};

export const clientChecks: Record<ClientMessage["type"], Check> = {
  hello: obj({ type: lit("hello"), kiosk_id: str, kiosk_token: str, client_version: str, camera: cameraInfo, display: displayInfo }),
  "session.request": obj({ type: lit("session.request") }, { purpose, mode, parent_session_id: nullable(str), palette_id: nullable(str) }),
  "session.start": obj(
    { type: lit("session.start"), session_id: str, wall_clock_iso: str },
    { t_lock: num, claimed_badge_id: nullable(str), collect_label: nullable(collectLabel) },
  ),
  "segment.shown": obj({ type: lit("segment.shown"), session_id: str, index: int, t_display: num }),
  "session.end": obj(
    { type: lit("session.end"), session_id: str, t_capture_end: num, frames_sent: obj({}, { crop: int, keyframe: int }) },
    { dropped_frames: int },
  ),
  "session.client_timing": obj(
    { type: lit("session.client_timing"), session_id: str, t_result_received: num, t_rendered: num },
    { t_first_face: nullable(num) },
  ),
  "stepup.verify": obj({ type: lit("stepup.verify"), session_id: str, stepup_token: str, method: oneOf("pin", "totp"), code: str }),
  "stepup.request_review": obj({ type: lit("stepup.request_review"), session_id: str, stepup_token: str }),
  ping: obj({ type: lit("ping") }),
  pong: obj({ type: lit("pong") }),
};

export const serverChecks: Record<ServerMessage["type"], Check> = {
  hello_ack: obj(
    {
      type: lit("hello_ack"),
      server_version: str,
      server_time_iso: str,
      capture_config: obj({}, { crop_size: int, context_scale: num, crop_fps: int, jpeg_quality: num, keyframe_count: int, keyframe_max_width: int }),
      policy: policyInfo,
    },
    { kiosk_profile_version: nullable(str) },
  ),
  "session.ready": obj({ type: lit("session.ready"), session_id: str, expires_in_ms: int, challenge }),
  "session.result": obj({ type: lit("session.result"), ...decisionFields }, decisionOptional),
  "session.update": obj({ type: lit("session.update"), ...decisionFields }, decisionOptional),
  error: obj(
    { type: lit("error"), code: oneOf("SESSION_EXPIRED", "BAD_TOKEN", "PROTOCOL", "RATE_LIMITED", "INTERNAL"), message: str },
    { session_id: nullable(str) },
  ),
  ping: obj({ type: lit("ping") }),
  pong: obj({ type: lit("pong") }),
};

function run(checks: Record<string, Check>, v: unknown): string | null {
  if (!isObj(v) || typeof v.type !== "string") return "message must be an object with a string 'type'";
  const check = checks[v.type];
  if (!check) return `unknown message type: ${v.type}`;
  return check(v, v.type);
}

/** Returns an error string, or null if `v` is a valid client message. */
export const validateClientMessage = (v: unknown): string | null => run(clientChecks, v);
/** Returns an error string, or null if `v` is a valid server message. */
export const validateServerMessage = (v: unknown): string | null => run(serverChecks, v);
export function parseServerMessage(raw: string): ServerMessage {
  const v: unknown = JSON.parse(raw);
  const err = validateServerMessage(v);
  if (err) throw new Error(`invalid server message: ${err}`);
  return v as ServerMessage;
}
