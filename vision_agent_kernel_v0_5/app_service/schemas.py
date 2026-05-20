from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RuntimeHealthSummary(BaseModel):
    healthy: bool = True
    input_worker_alive: bool = False
    telemetry_ok: bool = True
    release_all_called: bool = True
    updated_at: float = 0.0


class AgentStateSummary(BaseModel):
    mode: Literal["STOPPED", "RUNNING", "PAUSED", "EMERGENCY_STOPPED"]
    current_node: str
    current_skill: str | None = None
    target_state: str
    progress: float = Field(ge=0.0)
    frustration: float = Field(ge=0.0)
    input_backend: str
    focus_status: str
    active_interrupt: dict[str, Any] | None = None
    runtime_health: RuntimeHealthSummary
    input_released: bool
    telemetry_ok: bool
    latest_run_id: str | None = None
    updated_at: float


class CommandResult(BaseModel):
    ok: bool
    state: AgentStateSummary


class HealthResponse(BaseModel):
    status: str
    service: str = "vision-agent-local-service"


class ConfigResponse(BaseModel):
    input_backend: str
    default_mode: str
    safe_window_required_for_real_input: bool
    f9_emergency_stop: bool
    service: dict[str, Any]


class LatestRunResponse(BaseModel):
    run_id: str | None = None
    run_dir: str | None = None
    report_path: str | None = None
    report_markdown: str | None = None
    health_report: dict[str, Any] | None = None


class DiagnosticsResponse(BaseModel):
    ok: bool
    report_path: str
    checks: list[dict[str, Any]]


class WindowRectSummary(BaseModel):
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int


class WindowSummary(BaseModel):
    title: str
    pid: int
    handle: int
    rect: WindowRectSummary
    focused: bool
    visible: bool


class WindowListResponse(BaseModel):
    windows: list[WindowSummary]
    selected_handle: int | None = None


class WindowSelectRequest(BaseModel):
    title: str | None = None
    handle: int | None = None


class WindowSelectResponse(BaseModel):
    ok: bool
    window: WindowSummary


RoiMode = Literal["relative", "anchor"]
AnchorName = Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]


class RoiDefinitionModel(BaseModel):
    mode: RoiMode
    x: float | None = Field(default=None, ge=0.0, le=1.0)
    y: float | None = Field(default=None, ge=0.0, le=1.0)
    w: float | None = Field(default=None, ge=0.0, le=1.0)
    h: float | None = Field(default=None, ge=0.0, le=1.0)
    anchor: AnchorName | None = None
    offset_x_px: int | None = None
    offset_y_px: int | None = None
    width_px: int | None = None
    height_px: int | None = None


class CalibrationProfileModel(BaseModel):
    profile_id: str
    window_title: str
    source_resolution: tuple[int, int]
    normalized_resolution: tuple[int, int] = (1280, 720)
    rois: dict[str, RoiDefinitionModel]
    created_at: str | None = None


class CalibrationProfileSaveRequest(BaseModel):
    profile: CalibrationProfileModel
    activate: bool = True


class CalibrationProfilesResponse(BaseModel):
    active_profile_id: str | None = None
    profiles: list[dict[str, Any]]


class CalibrationTestRequest(BaseModel):
    profile_id: str | None = None


class CalibrationTestResponse(BaseModel):
    ok: bool
    profile_id: str | None = None
    message: str | None = None
    errors: list[str] = []


class ModelStatusResponse(BaseModel):
    detector_backend: str
    model_path: str | None = None
    model_exists: bool
    ultralytics_available: bool
    tracker: str
    tracker_available: bool
    device: str
    half: bool


class ModelLoadRequest(BaseModel):
    model_path: str | None = None


class ModelCommandResponse(BaseModel):
    ok: bool
    message: str
    model_path: str | None = None


class ModelBenchmarkResponse(BaseModel):
    ok: bool
    capture_fps: float
    detector_latency_ms: float | None = None
    tracker_latency_ms: float | None = None
    message: str


class SkillStepModel(BaseModel):
    step_id: str
    type: str
    label: str = ""
    delay_ms: int = 0
    timeout_ms: int = 1000
    interruptible: bool = True
    params: dict[str, Any] = {}


class SkillDefinitionModel(BaseModel):
    skill_id: str
    name: str
    type: Literal["ui", "navigation", "combat", "recovery", "verification"] = "ui"
    version: int = 1
    metadata: dict[str, Any] = {}
    environment_profile: str = "default_1920x1080"
    preconditions: list[str] = []
    steps: list[SkillStepModel]
    visual_triggers: dict[str, dict[str, Any]] = {}
    success_criteria: list[str] = []
    failure_policy: dict[str, Any] = {"max_retries": 1}
    cleanup: list[dict[str, Any]] = []
    safety: dict[str, Any] = {
        "dry_run_default": True,
        "interruptible": True,
        "require_focus": True,
        "max_duration_ms": 5000,
    }
    archived: bool = False
    updated_at: float | None = None


class SkillListResponse(BaseModel):
    skills: list[dict[str, Any]]


class SkillRecordCommandResponse(BaseModel):
    ok: bool
    session: dict[str, Any] | None = None
    draft: dict[str, Any] | None = None
    message: str


class SkillRecordStartRequest(BaseModel):
    backend: Literal["mock", "test-window", "global-hook"] = "mock"


class SkillRecordEventRequest(BaseModel):
    event_type: Literal[
        "key_down",
        "key_up",
        "mouse_move",
        "mouse_click",
        "wait",
        "visual_snapshot_summary",
        "active_window",
        "marker",
    ]
    timestamp: float | None = None
    payload: dict[str, Any] = {}
    target_state: str | None = None
    focus_state: str | None = None
    roi_profile: str | None = None
    observation_frame_id: int | None = None
    visual_triggers: dict[str, bool] = {}
    marker: str | None = None
    visual_trigger_marker: str | None = None


class SkillRecordMarkerRequest(BaseModel):
    marker: str = "user_marker"


class SkillRecordSaveRequest(BaseModel):
    skill_id: str | None = None
    name: str | None = None


class SkillValidationResponse(BaseModel):
    ok: bool
    errors: list[str] = []


class SkillDryRunResponse(BaseModel):
    ok: bool
    result: dict[str, Any]


class SkillReplayRequest(BaseModel):
    mode: Literal["dry-run", "safe-window"] = "dry-run"
    confirm: bool = False


class SkillReplayResponse(BaseModel):
    ok: bool
    result: dict[str, Any]


class SkillVersionsResponse(BaseModel):
    skill_id: str
    versions: list[str]


class PersonaProfileModel(BaseModel):
    persona_id: str
    name: str
    style: str
    tone: str
    avatar_asset: str
    voice_config: dict[str, Any] = {}
    event_templates: dict[str, str] = {}
    safety_style: str = "friendly_safe"
    technical_detail_level: str = "medium"
    emotion_map: dict[str, str] = {}


class PersonaEventRequest(BaseModel):
    event_code: str
    payload: dict[str, Any] = {}
    persona_id: str = "default_companion"


class PersonaEventResponse(BaseModel):
    persona_id: str
    event_code: str
    message: str
    overlay_state: str
    emotion: str = "normal"


class PlannerRequest(BaseModel):
    goal: str
    provider: str = "mock"
    persona_id: str = "default_companion"


class PlannerResponse(BaseModel):
    ok: bool
    provider: str
    task_spec: dict[str, Any]
    skill_chain: list[str]
    risks: list[str]
    validation: dict[str, Any]
    usage: dict[str, Any] = {}
    provider_error: str | None = None


class KnowledgeResolveResponse(BaseModel):
    ok: bool
    resource: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class RouteRankResponse(BaseModel):
    ok: bool
    routes: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class MissionPlanRequest(BaseModel):
    goal: str


class MissionPlanResponse(BaseModel):
    ok: bool
    mission: dict[str, Any]
    validation: dict[str, Any]


class FailureExplanationRequest(BaseModel):
    summary: dict[str, Any]
    provider: str = "mock"


class FailureExplanationResponse(BaseModel):
    user_friendly_summary: str
    technical_summary: str
    suggested_next_steps: list[str]
    possible_skill_patch: dict[str, Any]
    provider: str | None = None
    provider_error: str | None = None


class CombatPlaybookRequest(BaseModel):
    goal: str
    team_profile: str = "default_team"
    provider: str = "mock"


class CombatPlaybookResponse(BaseModel):
    ok: bool
    playbook: dict[str, Any]
    validation: dict[str, Any]


class DangerEventRequest(BaseModel):
    signals: dict[str, float]
    context_priority: float = 0.0


class DangerEventResponse(BaseModel):
    danger_score: float
    level: str
    components: dict[str, float] = Field(default_factory=dict)
    dominant_signal: str | None = None
    interrupt: dict[str, Any] | None = None
    dodge: dict[str, Any] | None = None
    dodge_policy: dict[str, Any] = Field(default_factory=dict)
    companion_message: str | None = None


class ProductChecklistItemModel(BaseModel):
    key: str
    label: str
    ok: bool
    detail: str


class ProductChecklistResponse(BaseModel):
    ok: bool
    items: list[ProductChecklistItemModel]
    profile: str
    skill: str


class ProductRunE2ERequest(BaseModel):
    mode: Literal["dry-run", "safe-window"] = "dry-run"
    seconds: float = 20.0
    profile: str | None = None
    skill: str | None = None
    task: str = "complete product demo"
    use_mock_llm: bool = True
    chaos: Literal["none", "mild"] = "none"
    confirm: bool = False


class ProductRunE2EResponse(BaseModel):
    ok: bool
    run_id: str
    run_dir: str
    report_path: str
    checklist: list[ProductChecklistItemModel]
    selected_profile: str
    selected_skill: str
    planner_provider: str
    task_validation: dict[str, Any]
    execution_mode: str
    safety_events: list[str]
    release_all_called: bool
    companion_summary: str
    confirm_required: bool = False
    error: str | None = None


class ProductLatestReportResponse(BaseModel):
    run_id: str | None = None
    report_path: str | None = None
    report_markdown: str | None = None


class ShowcaseRunRequest(BaseModel):
    mode: Literal["dry-run", "safe-window"] = "dry-run"
    seconds: float = 30.0
    persona: str = "default_companion"
    provider: Literal["mock", "glm", "minimax"] = "mock"
    target_window_title: str = "vision_agent_kernel_v0_5 pseudo3d_scene"


class ShowcaseRunResponse(BaseModel):
    ok: bool
    run_id: str | None = None
    report_path: str | None = None
    report_markdown: str | None = None
    stdout: str = ""
    stderr: str = ""


class ShowcaseLatestReportResponse(BaseModel):
    run_id: str | None = None
    report_path: str | None = None
    report_markdown: str | None = None
