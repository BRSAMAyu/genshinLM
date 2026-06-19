from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from execution.verifier_base import VerifierResult


JsonDict = dict[str, Any]


@dataclass(slots=True)
class FocusState:
    focused: bool
    window_title: str | None = None
    process_name: str | None = None


@dataclass(slots=True)
class UIStateEstimate:
    frame_id: int
    timestamp: float
    state: str
    confidence: float
    payload: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class Observation:
    frame_id: int
    t_capture: float
    t_processed: float
    latency_ms: float
    viewport_size: tuple[int, int]
    target_track: TargetTrack | None
    obstacle_field: ObstacleField | None
    ui_state: UIStateEstimate | None
    visual_triggers: dict[str, bool]
    os_focus: FocusState
    image: Any = None  # np.ndarray | None — raw frame for VLM/UI adapters
    stale: bool = False
    extensions: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class TargetCandidate:
    frame_id: int
    class_id: str
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    center_px: tuple[float, float]
    area_px: float
    aspect_ratio: float
    appearance_signature: JsonDict | None = None
    depth_hint: float | None = None
    source: str = "detector"


@dataclass(slots=True)
class TargetTrack:
    track_id: str
    class_id: str
    state: str
    bbox_xyxy: tuple[float, float, float, float] | None
    smoothed_center_px: tuple[float, float] | None
    velocity_px_s: tuple[float, float]
    confidence: float
    identity_confidence: float
    missing_duration_ms: float
    bearing_deg: float | None
    pitch_deg: float | None
    estimated_range: float | None
    last_seen_frame_id: int
    appearance_signature: JsonDict | None = None


@dataclass(slots=True)
class ObstacleField:
    frame_id: int
    timestamp: float
    sectors: dict[str, float]
    confidence: float
    source: str


@dataclass(slots=True)
class CameraModel:
    viewport_width: int = 1280
    viewport_height: int = 720
    # Default FOV for Genshin Impact (75-80° typical, 16:9 approximation ~78°)
    horizontal_fov_deg: float = 78.0
    vertical_fov_deg: float | None = None
    sensitivity_yaw: float = 1.0
    sensitivity_pitch: float = 1.0
    invert_y: bool = False


@dataclass(slots=True)
class CameraControlError:
    yaw_error_deg: float
    pitch_error_deg: float
    angular_distance_deg: float
    target_confidence: float
    stale: bool


@dataclass(slots=True)
class CameraIntent:
    yaw_delta: float
    pitch_delta: float
    duration_ms: int
    confidence: float
    reason: str


@dataclass(slots=True)
class MovementIntent:
    move_forward: float
    move_right: float
    jump: bool = False
    dash: bool = False
    duration_ms: int = 150
    reason: str = ""


@dataclass(slots=True)
class InputLease:
    lease_id: str
    owner: str
    priority: int
    key_states: dict[str, str]
    mouse_delta: tuple[float, float] | None
    created_at: float
    expires_at: float
    reason: str
    # Optional atomic actions for human-complete computer-use coverage.
    # Examples:
    # {"type":"left_click"}, {"type":"mouse_scroll","delta":-1},
    # {"type":"type_text","text":"hello"}, {"type":"execute_combo","keys":["ctrl","c"]}.
    actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ProgressState:
    timestamp: float
    ewma_progress: float
    progress_slope_2s: float
    visibility_ratio_1s: float
    oscillation_score: float
    frustration: float
    trend: str
    active_interrupt: Interrupt | None = None


@dataclass(slots=True)
class SkillResult:
    skill_name: str
    status: str
    failure_code: str | None
    started_at: float
    finished_at: float
    payload: JsonDict = field(default_factory=dict)
    verifier_result: VerifierResult | None = None
    claim_id: str = ""
    claim_status: str = ""


# ---------------------------------------------------------------------------
# Spatial substrate (sensor-agnostic localization)
#
# These three types form the seam between sensors and the pose belief:
#   LocalizationReading  — raw per-frame measurements from a LocalizationProvider
#   MotionCommand        — the body-frame motion the executor actually commanded
#   PoseEstimate         — the fused belief consumed by every plane via StateBus
#
# The fusion engine (`perception.pose_fusion.PoseFusion`) is game-agnostic. A
# minimap is just one source of readings; a game without a minimap supplies the
# same readings from visual odometry / VLM landmark fixes, and falls back to
# dead-reckoning from MotionCommand when no measurement is available.
#
# Conventions (documented once, relied on everywhere):
#   - position is 2D ground-plane (x=east/+X, y=north/+Y) in *world units*.
#     Each provider converts its sensor frame (e.g. minimap pixels) into these
#     units; the fusion engine never assumes pixels.
#   - heading_deg is clockwise from north: 0=+Y, 90=+X, range [0, 360).
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LocalizationReading:
    """Raw localization measurements from one frame, before fusion.

    Every measurement is optional — a provider supplies whatever it could read
    this frame and leaves the rest ``None``. Displacement fields are *incremental*
    world-frame deltas since the previous reading (e.g. minimap optical flow,
    already rotated into world frame and scaled to world units).
    """

    timestamp: float
    frame_id: int
    heading_deg: float | None = None
    heading_confidence: float = 0.0
    flow_dx: float | None = None
    flow_dy: float | None = None
    flow_confidence: float = 0.0
    absolute_position: tuple[float, float] | None = None
    absolute_confidence: float = 0.0
    minimap_visible: bool = True
    source: str = "unknown"
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class MotionCommand:
    """Body-frame motion the executor commanded this step (dead-reckoning input).

    ``forward``/``right`` are normalized analog axes in [-1, 1] mirroring
    :class:`MovementIntent`. ``speed_world_units_per_sec`` is the calibrated
    nominal walking speed; ``yaw_rate_deg_per_sec`` integrates camera turning.
    """

    timestamp: float
    forward: float = 0.0
    right: float = 0.0
    speed_world_units_per_sec: float = 0.0
    yaw_rate_deg_per_sec: float = 0.0
    is_moving: bool = False


@dataclass(slots=True)
class PoseEstimate:
    """Fused belief about where the agent is and which way it faces.

    ``confidence`` is the overall trust [0, 1]. ``position_uncertainty`` grows
    (in world units) while dead-reckoning and shrinks on an absolute fix —
    consumers compare it against a threshold to decide whether to trust the pose
    or hand off to last-mile visual reacquisition. ``has_absolute_fix`` is False
    while the position is purely relative/dead-reckoned.
    """

    frame_id: int
    timestamp: float
    position: tuple[float, float]
    heading_deg: float
    velocity: tuple[float, float] = (0.0, 0.0)
    confidence: float = 0.0
    position_uncertainty: float = 0.0
    heading_uncertainty_deg: float = 0.0
    has_absolute_fix: bool = False
    source: str = "init"
