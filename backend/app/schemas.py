"""Canonical data contracts (plan §8). The kiosk mirrors these in ``kiosk/src/types/protocol.ts``.

Conventions: snake_case JSON; client times are ms from ``performance.now()`` relative to ``t_lock``;
server times are monotonic ms internally and ISO-8601 UTC in stored records.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------------------------------
# Base + shared enums
# --------------------------------------------------------------------------------------------------


class Strict(BaseModel):
    """Inbound/stored contracts reject unknown fields so protocol drift is caught early."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


Decision = Literal["ALLOW", "REQUEST_VERIFICATION", "DENY"]
DecisionLabel = Literal["Allow", "Request Additional Verification", "Deny"]
Purpose = Literal["access", "enroll", "collect", "stepup_recapture"]
Mode = Literal["face", "badge"]
LockMethod = Literal["browser", "prelock", "agent", "none"]
SignalStatusOut = Literal["ok", "low_snr", "low_quality", "unavailable", "error"]
StepupOption = Literal["recapture", "pin", "totp", "manual_review", "head_turn"]

Byte = Annotated[int, Field(ge=0, le=255)]
RGB = tuple[Byte, Byte, Byte]

DECISION_LABELS: dict[str, str] = {
    "ALLOW": "Allow",
    "REQUEST_VERIFICATION": "Request Additional Verification",
    "DENY": "Deny",
}

# --------------------------------------------------------------------------------------------------
# Challenge (plan §8.1, §9.2)
# --------------------------------------------------------------------------------------------------


class ChallengeSegment(Strict):
    rgb: RGB
    duration_ms: int = Field(gt=0)


class Challenge(Strict):
    nonce: str = Field(min_length=16)
    palette_id: str
    neutral: ChallengeSegment
    segments: list[ChallengeSegment] = Field(min_length=1)
    total_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def _total_matches(self) -> Challenge:
        expected = self.neutral.duration_ms + sum(s.duration_ms for s in self.segments)
        if expected != self.total_ms:
            raise ValueError(f"total_ms {self.total_ms} != neutral + segments {expected}")
        return self


# --------------------------------------------------------------------------------------------------
# Collection label (plan §8.6)
# --------------------------------------------------------------------------------------------------

PaiFamily = Literal["none", "print", "screen_photo", "video_replay", "mask"]
SPECIES_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "print": ("print_matte_a4", "print_glossy_photo", "print_cutout_eyes", "print_curved"),
    "screen_photo": ("screen_phone_oled", "screen_tablet_lcd", "screen_laptop"),
    "video_replay": ("replay_phone", "replay_tablet", "replay_monitor"),
    "mask": ("mask_paper_flat", "mask_paper_curved", "mask_rigid_3d"),
}
ALL_SPECIES: tuple[str, ...] = tuple(s for group in SPECIES_BY_FAMILY.values() for s in group)
CaptureProcedure = Literal["standard", "on_the_spot_phone", "auto_repeat_rig", "redteam"]
Lighting = Literal["office", "dim", "backlit", "side_lamp", "bright"]
SkinToneBucket = Literal["unreported", "light", "medium", "dark"]


class CollectLabel(Strict):
    subject_id: str  # pseudonymous; for attacks = the subject depicted
    presenter_id: str  # who held the instrument (attacks) or same as subject (bona fide)
    cls: Literal["bona_fide", "attack"] = Field(alias="class")
    enrolled: bool | None = None  # bona fide only
    claimed_badge_id: str | None = None
    capture_procedure: CaptureProcedure = "standard"
    pai_family: PaiFamily = "none"
    pai_species: str = "none"
    instrument_id: str | None = None
    lighting: Lighting = "office"
    distance_cm: int | None = Field(default=None, ge=10, le=300)
    glasses: bool = False
    skin_tone_bucket: SkinToneBucket = "unreported"
    consent_id: str = Field(min_length=1)
    operator: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> CollectLabel:
        if self.cls == "bona_fide":
            if self.pai_family != "none" or self.pai_species != "none":
                raise ValueError("bona_fide labels must have pai_family='none' and pai_species='none'")
            if self.instrument_id is not None:
                raise ValueError("bona_fide labels must not carry an instrument_id")
        else:
            if self.pai_family == "none" or self.pai_species == "none":
                raise ValueError("attack labels need a pai_family and a pai_species")
            if self.capture_procedure == "redteam":
                if not self.pai_species.startswith("redteam_"):
                    raise ValueError("redteam sessions use pai_species='redteam_<description>'")
            elif self.pai_species not in SPECIES_BY_FAMILY.get(self.pai_family, ()):
                raise ValueError(f"pai_species {self.pai_species!r} does not belong to family {self.pai_family!r}")
            if self.instrument_id is None:
                raise ValueError("attack labels need an instrument_id (a specific device/print)")
        return self


# --------------------------------------------------------------------------------------------------
# WebSocket protocol (plan §8.1) — client -> server
# --------------------------------------------------------------------------------------------------


class CameraInfo(Strict):
    width: int
    height: int
    fps: float
    lock_method: LockMethod
    settings: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None  # device label; used by the virtual-camera allowlist (plan §16.1)


class DisplayInfo(Strict):
    width: int
    height: int
    device_pixel_ratio: float = 1.0


class Hello(Strict):
    type: Literal["hello"] = "hello"
    kiosk_id: str
    kiosk_token: str
    client_version: str
    camera: CameraInfo
    display: DisplayInfo


class SessionRequest(Strict):
    type: Literal["session.request"] = "session.request"
    purpose: Purpose = "access"
    mode: Mode = "face"
    parent_session_id: str | None = None
    palette_id: str | None = None  # E2 only: force palette P1/P2 for a collect session


class SessionStart(Strict):
    type: Literal["session.start"] = "session.start"
    session_id: str
    t_lock: float = 0.0
    wall_clock_iso: str
    claimed_badge_id: str | None = None
    collect_label: CollectLabel | None = None


class SegmentShown(Strict):
    type: Literal["segment.shown"] = "segment.shown"
    session_id: str
    index: int  # -1 = the neutral segment
    t_display: float


class FramesSent(Strict):
    crop: int = 0
    keyframe: int = 0


class SessionEnd(Strict):
    type: Literal["session.end"] = "session.end"
    session_id: str
    t_capture_end: float
    frames_sent: FramesSent
    dropped_frames: int = 0


class SessionClientTiming(Strict):
    type: Literal["session.client_timing"] = "session.client_timing"
    session_id: str
    t_result_received: float
    t_rendered: float
    t_first_face: float | None = None


class StepupVerify(Strict):
    type: Literal["stepup.verify"] = "stepup.verify"
    session_id: str
    stepup_token: str
    method: Literal["pin", "totp"]
    code: str


class StepupRequestReview(Strict):
    type: Literal["stepup.request_review"] = "stepup.request_review"
    session_id: str
    stepup_token: str


class Ping(Strict):
    type: Literal["ping"] = "ping"


class Pong(Strict):
    type: Literal["pong"] = "pong"


ClientMessage = Annotated[
    Hello
    | SessionRequest
    | SessionStart
    | SegmentShown
    | SessionEnd
    | SessionClientTiming
    | StepupVerify
    | StepupRequestReview
    | Ping
    | Pong,
    Field(discriminator="type"),
]

BoxXYWH = tuple[float, float, float, float]


class FrameHeader(Strict):
    """Header of a binary WebSocket frame: ``[u32 LE header_len][header JSON][JPEG bytes]``."""

    session_id: str
    kind: Literal["crop", "keyframe"]
    seq: int = Field(ge=0)
    t_capture: float
    crop_box: BoxXYWH  # in full-frame pixels; for keyframes: [0, 0, W, H]
    frame_size: tuple[int, int]
    client_face_box: BoxXYWH | None = None
    capture_time_source: Literal["captureTime", "now"] | None = None


# --------------------------------------------------------------------------------------------------
# Decision result (plan §8.3)
# --------------------------------------------------------------------------------------------------


class LivenessSummary(Strict):
    p_live: float | None = None
    status: Literal["ok", "uncertain", "spoof", "not_evaluated"]
    fusion_method: Literal["lr", "min_provisional"] | None = None


class IdentitySummary(Strict):
    status: Literal["match", "mismatch", "borderline", "no_match", "not_evaluated"]
    engine: str | None = None
    subject_id: str | None = None
    display_name: str | None = None
    similarity: float | None = None
    margin: float | None = None
    threshold: float | None = None
    used_in_decision: bool = False  # false when liveness already decided (identity is still computed)


class FlowCapture(Strict):
    status: Literal["ok", "low_quality"]
    frames_received: int = 0
    quality_reasons: list[str] = Field(default_factory=list)
    duration_ms: float | None = None


class FlowLiveness(Strict):
    status: Literal["live", "uncertain", "spoof", "not_evaluated"]
    p_live: float | None = None
    rule: str | None = None  # R3_QUALITY ... R9_PASS


class FlowAuthentication(Strict):
    status: Literal["match", "borderline", "no_match", "mismatch", "not_evaluated"]
    similarity: float | None = None
    threshold: float | None = None


class FlowDecision(Strict):
    outcome: Decision
    reason_code: str
    finalize_ms: float | None = None


class Flow(Strict):
    """The four official prototype stages (plan §5.6, F-15). Values are copied, never invented."""

    capture: FlowCapture
    liveness: FlowLiveness
    authentication: FlowAuthentication
    decision: FlowDecision


class QualityOut(Strict):
    status: Literal["ok", "low_quality"]
    passed: bool = Field(alias="pass")
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class SignalOut(Strict):
    status: SignalStatusOut
    p_live: float | None = None
    raw_score: float | None = None
    features: dict[str, float] | None = None
    series: dict[str, Any] | None = None  # chroma plots: t, emitted, face, surround, background
    per_model: dict[str, float] | None = None  # passive: per MiniFASNet model
    latency_ms: float | None = None
    model_version: str | None = None

    @model_validator(mode="after")
    def _p_live_only_when_ok(self) -> SignalOut:
        # plan §8.4: p_live is None <=> status != ok
        if (self.p_live is None) != (self.status != "ok"):
            raise ValueError("p_live must be set if and only if status == 'ok'")
        return self


class Signals(Strict):
    quality: QualityOut
    chroma: SignalOut | None = None
    passive: SignalOut | None = None
    device: SignalOut | None = None


class StepupInfo(Strict):
    required: bool = False
    options: list[StepupOption] = Field(default_factory=list)
    stepup_token: str | None = None
    attempts_left: int = 0


class PolicyInfo(Strict):
    version: str
    provisional: bool


class Versions(Strict):
    server: str
    models: dict[str, str] = Field(default_factory=dict)


class DecisionResult(Strict):
    session_id: str
    kiosk_id: str
    purpose: Purpose
    mode: Mode
    decision: Decision
    decision_label: DecisionLabel
    reason_code: str
    reason_text: str  # short, kiosk-safe text
    liveness: LivenessSummary
    identity: IdentitySummary
    flow: Flow
    signals: Signals
    stepup: StepupInfo = Field(default_factory=StepupInfo)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    policy: PolicyInfo
    versions: Versions
    created_at: str

    @model_validator(mode="after")
    def _label_matches(self) -> DecisionResult:
        if DECISION_LABELS[self.decision] != self.decision_label:
            raise ValueError("decision_label does not match decision")
        if self.flow.decision.outcome != self.decision or self.flow.decision.reason_code != self.reason_code:
            raise ValueError("flow.decision is inconsistent with decision/reason_code")
        return self


# --------------------------------------------------------------------------------------------------
# WebSocket protocol — server -> client
# --------------------------------------------------------------------------------------------------


class CaptureConfig(Strict):
    crop_size: int = 256
    context_scale: float = 2.0
    crop_fps: int = 30
    jpeg_quality: float = 0.9
    keyframe_count: int = 2
    keyframe_max_width: int = 1280


class HelloAck(Strict):
    type: Literal["hello_ack"] = "hello_ack"
    server_version: str
    server_time_iso: str
    capture_config: CaptureConfig
    policy: PolicyInfo
    kiosk_profile_version: str | None = None


class SessionReady(Strict):
    type: Literal["session.ready"] = "session.ready"
    session_id: str
    expires_in_ms: int
    challenge: Challenge


class SessionResultMsg(DecisionResult):
    type: Literal["session.result"] = "session.result"


class SessionUpdateMsg(DecisionResult):
    type: Literal["session.update"] = "session.update"


ErrorCode = Literal["SESSION_EXPIRED", "BAD_TOKEN", "PROTOCOL", "RATE_LIMITED", "INTERNAL"]


class ErrorMsg(Strict):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str
    session_id: str | None = None


ServerMessage = Annotated[
    HelloAck | SessionReady | SessionResultMsg | SessionUpdateMsg | ErrorMsg | Ping | Pong,
    Field(discriminator="type"),
]

# --------------------------------------------------------------------------------------------------
# Session bundle records (plan §8.5)
# --------------------------------------------------------------------------------------------------


class BundleCamera(Strict):
    width: int
    height: int
    fps: float
    lock_method: LockMethod
    settings: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None


class SessionMeta(Strict):
    session_id: str
    purpose: Purpose
    mode: Mode
    kiosk_id: str
    created_at: str
    client_version: str
    server_version: str
    camera: BundleCamera
    display: DisplayInfo
    kiosk_profile_version: str | None = None
    policy_version: str | None = None
    capture_time_source: Literal["captureTime", "now"] | None = None
    jpeg_quality: float | None = None
    crop_size: int | None = None
    palette_id: str | None = None


class DisplayedSegment(Strict):
    index: int  # -1 = neutral
    t_display: float


class IlluminationTransition(Strict):
    state: Literal["challenge", "idle"]
    rgb: RGB
    t_display: float = Field(allow_inf_nan=False)


class MeasurementTiming(Strict):
    version: Literal[2]
    preparation_ms: float = Field(ge=1000, allow_inf_nan=False)
    capture_end_ms: float = Field(gt=0, le=1300, allow_inf_nan=False)
    idle_at_ms: float = Field(gt=0, allow_inf_nan=False)
    transitions: list[IlluminationTransition] = Field(min_length=6, max_length=6)


class ChallengeRecord(Strict):
    challenge: Challenge
    displayed: list[DisplayedSegment] = Field(default_factory=list)
    timing: MeasurementTiming | None = None  # legacy bundles are readable, not accepted as new measurements


class FrameRecord(Strict):
    seq: int
    t_capture: float
    t_callback: float | None = None  # rVFC callback time, when different from t_capture (diagnostics for E1/E2)
    capture_time_source: Literal["captureTime", "now"] | None = None
    crop_box: BoxXYWH
    frame_size: tuple[int, int]
    client_face_box: BoxXYWH | None = None
    file: str  # crops/000017.jpg


class KeyframeRecord(Strict):
    seq: int
    t_capture: float
    t_callback: float | None = None
    capture_time_source: Literal["captureTime", "now"] | None = None
    frame_size: tuple[int, int] | None = None
    file: str  # keyframes/k0.jpg


# --------------------------------------------------------------------------------------------------
# Kiosk profile (plan §8.7) and attempt record (plan §8.8)
# --------------------------------------------------------------------------------------------------


class ProfileCamera(Strict):
    model: str = ""
    lock_method: LockMethod = "none"
    exposure: str | float | None = None
    white_balance_k: int | None = None
    powerline_hz: Literal[50, 60] | None = None


class ProfileDisplay(Strict):
    model: str = ""
    brightness_pct: int = 100
    adaptive_brightness_disabled: bool = False


class ProfileGeometry(Strict):
    face_distance_cm: tuple[int, int] = (40, 70)


class ProfileChroma(Strict):
    expected_lag_ms: float
    lag_tolerance_ms: float = 60.0
    noise_floor: float
    max_ambient_level: float = 0.55


class KioskProfile(Strict):
    kiosk_id: str
    version: str
    camera: ProfileCamera = Field(default_factory=ProfileCamera)
    display: ProfileDisplay = Field(default_factory=ProfileDisplay)
    geometry: ProfileGeometry = Field(default_factory=ProfileGeometry)
    chroma: ProfileChroma
    calibrated_at: str
    calibrated_by: str


class AttemptRecord(Strict):
    """Audit record (no images, no embeddings)."""

    session_id: str
    kiosk_id: str
    created_at: str
    purpose: Purpose
    mode: Mode
    decision: Decision
    reason_code: str
    p_live: float | None = None
    signal_status: dict[str, str] = Field(default_factory=dict)
    signal_p_live: dict[str, float | None] = Field(default_factory=dict)
    identity_status: str = "not_evaluated"
    identity_similarity: float | None = None
    identity_subject_id: str | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    client_decision_time_ms: float | None = None
    policy_version: str
    model_versions: dict[str, str] = Field(default_factory=dict)
    parent_session_id: str | None = None


# --------------------------------------------------------------------------------------------------
# REST models (plan §8.2)
# --------------------------------------------------------------------------------------------------


class HealthResponse(Strict):
    status: Literal["ok", "degraded"]
    models_loaded: dict[str, bool]
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)
    storage: str
    policy_version: str
    policy_provisional: bool


class SubjectCreate(Strict):
    display_name: str = Field(min_length=1)
    badge_id: str = Field(min_length=1)
    consent_id: str = Field(min_length=1)
    pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    enable_totp: bool = False


class SubjectCreated(Strict):
    subject_id: str
    totp_uri: str | None = None


class CaptureAttach(Strict):
    session_id: str
    liveness_attested_by: str | None = None


class CaptureResult(Strict):
    accepted: bool
    reason: str | None = None
    consistency: float | None = None


class FinalizeResult(Strict):
    template_ready: bool
    n_captures: int
    warnings: list[str] = Field(default_factory=list)


class ReviewAction(Strict):
    action: Literal["approve", "deny"]
    operator_note: str = ""
