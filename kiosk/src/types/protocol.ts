// Mirrors backend/app/schemas.py (plan §8). Keep in sync: src/types/protocol.test.ts validates the shared
// fixtures in backend/tests/fixtures/protocol_samples.json with the guards in validate.ts.

export type Decision = "ALLOW" | "REQUEST_VERIFICATION" | "DENY";
export type DecisionLabel = "Allow" | "Request Additional Verification" | "Deny";
export type Purpose = "access" | "enroll" | "collect" | "stepup_recapture";
export type Mode = "face" | "badge";
export type LockMethod = "browser" | "prelock" | "agent" | "none";
export type SignalStatus = "ok" | "low_snr" | "low_quality" | "unavailable" | "error";
export type StepupOption = "recapture" | "pin" | "totp" | "manual_review" | "head_turn";
export type RGB = [number, number, number];
export type Box = [number, number, number, number]; // x, y, w, h

export interface ChallengeSegment {
  rgb: RGB;
  duration_ms: number;
}
export interface Challenge {
  nonce: string;
  palette_id: string;
  neutral: ChallengeSegment;
  segments: ChallengeSegment[];
  total_ms: number;
}

// --- collection label (§8.6) -------------------------------------------------------------------
export type PaiFamily = "none" | "print" | "screen_photo" | "video_replay" | "mask";
export type CaptureProcedure = "standard" | "on_the_spot_phone" | "auto_repeat_rig" | "redteam";
export type Lighting = "office" | "dim" | "backlit" | "side_lamp" | "bright";
export type SkinToneBucket = "unreported" | "light" | "medium" | "dark";

export interface CollectLabel {
  subject_id: string;
  presenter_id: string;
  class: "bona_fide" | "attack";
  enrolled: boolean | null;
  claimed_badge_id: string | null;
  capture_procedure: CaptureProcedure;
  pai_family: PaiFamily;
  pai_species: string;
  instrument_id: string | null;
  lighting: Lighting;
  distance_cm: number | null;
  glasses: boolean;
  skin_tone_bucket: SkinToneBucket;
  consent_id: string;
  operator: string;
  notes: string;
}

// --- client -> server (§8.1) ---------------------------------------------------------------------
export interface CameraInfo {
  width: number;
  height: number;
  fps: number;
  lock_method: LockMethod;
  settings: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  label: string | null;
}
export interface DisplayInfo {
  width: number;
  height: number;
  device_pixel_ratio: number;
}
export interface Hello {
  type: "hello";
  kiosk_id: string;
  kiosk_token: string;
  client_version: string;
  camera: CameraInfo;
  display: DisplayInfo;
}
export interface SessionRequest {
  type: "session.request";
  purpose: Purpose;
  mode: Mode;
  parent_session_id: string | null;
  palette_id: string | null;
}
export interface SessionStart {
  type: "session.start";
  session_id: string;
  t_lock: number;
  wall_clock_iso: string;
  claimed_badge_id: string | null;
  collect_label: CollectLabel | null;
}
export interface SegmentShown {
  type: "segment.shown";
  session_id: string;
  index: number; // -1 = neutral
  t_display: number;
}
export interface SessionEnd {
  type: "session.end";
  session_id: string;
  t_capture_end: number;
  frames_sent: { crop: number; keyframe: number };
  dropped_frames: number;
}
export interface SessionClientTiming {
  type: "session.client_timing";
  session_id: string;
  t_result_received: number;
  t_rendered: number;
  t_first_face: number | null;
}
export interface StepupVerify {
  type: "stepup.verify";
  session_id: string;
  stepup_token: string;
  method: "pin" | "totp";
  code: string;
}
export interface StepupRequestReview {
  type: "stepup.request_review";
  session_id: string;
  stepup_token: string;
}
export interface Ping {
  type: "ping";
}
export interface Pong {
  type: "pong";
}
export type ClientMessage =
  | Hello
  | SessionRequest
  | SessionStart
  | SegmentShown
  | SessionEnd
  | SessionClientTiming
  | StepupVerify
  | StepupRequestReview
  | Ping
  | Pong;

/** Header of a binary frame: [u32 LE header_len][header JSON][JPEG bytes] */
export interface FrameHeader {
  session_id: string;
  kind: "crop" | "keyframe";
  seq: number;
  t_capture: number;
  crop_box: Box;
  frame_size: [number, number];
  client_face_box?: Box | null;
  capture_time_source?: "captureTime" | "now" | null;
}

// --- server -> client ----------------------------------------------------------------------------
export interface PolicyInfo {
  version: string;
  provisional: boolean;
}
export interface CaptureConfig {
  crop_size: number;
  context_scale: number;
  crop_fps: number;
  jpeg_quality: number;
  keyframe_count: number;
  keyframe_max_width: number;
}
export interface HelloAck {
  type: "hello_ack";
  server_version: string;
  server_time_iso: string;
  capture_config: CaptureConfig;
  policy: PolicyInfo;
  kiosk_profile_version: string | null;
}
export interface SessionReady {
  type: "session.ready";
  session_id: string;
  expires_in_ms: number;
  challenge: Challenge;
}

export interface IdentitySummary {
  status: "match" | "mismatch" | "borderline" | "no_match" | "not_evaluated";
  engine: string | null;
  subject_id: string | null;
  display_name: string | null;
  similarity: number | null;
  margin: number | null;
  threshold: number | null;
  used_in_decision: boolean;
}
export interface Flow {
  capture: { status: "ok" | "low_quality"; frames_received: number; quality_reasons: string[]; duration_ms: number | null };
  liveness: { status: "live" | "uncertain" | "spoof" | "not_evaluated"; p_live: number | null; rule: string | null };
  authentication: {
    status: "match" | "borderline" | "no_match" | "mismatch" | "not_evaluated";
    similarity: number | null;
    threshold: number | null;
  };
  decision: { outcome: Decision; reason_code: string; finalize_ms: number | null };
}
export interface SignalOut {
  status: SignalStatus;
  p_live: number | null;
  raw_score: number | null;
  features: Record<string, number> | null;
  series: Record<string, unknown> | null;
  per_model: Record<string, number> | null;
  latency_ms: number | null;
  model_version: string | null;
}
export interface QualityOut {
  status: "ok" | "low_quality";
  pass: boolean;
  reasons: string[];
  metrics: Record<string, number>;
}
export interface DecisionResult {
  session_id: string;
  kiosk_id: string;
  purpose: Purpose;
  mode: Mode;
  decision: Decision;
  decision_label: DecisionLabel;
  reason_code: string;
  reason_text: string;
  liveness: { p_live: number | null; status: "ok" | "uncertain" | "spoof" | "not_evaluated"; fusion_method: "lr" | "min_provisional" | null };
  identity: IdentitySummary;
  flow: Flow;
  signals: { quality: QualityOut; chroma?: SignalOut | null; passive?: SignalOut | null; device?: SignalOut | null };
  stepup: { required: boolean; options: StepupOption[]; stepup_token: string | null; attempts_left: number };
  timings_ms: Record<string, number>;
  policy: PolicyInfo;
  versions: { server: string; models: Record<string, string> };
  created_at: string;
}
export type SessionResultMsg = DecisionResult & { type: "session.result" };
export type SessionUpdateMsg = DecisionResult & { type: "session.update" };
export interface ErrorMsg {
  type: "error";
  code: "SESSION_EXPIRED" | "BAD_TOKEN" | "PROTOCOL" | "RATE_LIMITED" | "INTERNAL";
  message: string;
  session_id: string | null;
}
export type ServerMessage = HelloAck | SessionReady | SessionResultMsg | SessionUpdateMsg | ErrorMsg | Ping | Pong;
