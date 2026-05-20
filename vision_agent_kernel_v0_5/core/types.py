from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.events import Interrupt


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
    horizontal_fov_deg: float = 90.0
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
