"""Core data types for the AgentKernel framework.

All types are frozen dataclasses with slots=True, following project conventions.
No dependencies on any game-specific code.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Perception types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ActionableElement:
    """A clickable/interactable element detected on screen."""
    element_type: str          # "button", "slot", "character_card", "menu_item", "text_input"
    label: str                 # "升级", "确认", "钟离", "C"
    bbox: tuple[float, float, float, float]  # Normalised (x1, y1, x2, y2)
    confidence: float = 0.0
    state: str = "enabled"     # "enabled", "disabled", "selected", "hidden"


@dataclass(frozen=True, slots=True)
class SemanticObservation:
    """VLM/OCR enriched observation of the current screen."""
    timestamp: float
    scene_description: str     # "角色详情页，当前角色是钟离，等级80/90"
    actionable_elements: tuple[ActionableElement, ...] = ()
    screen_state: str = ""     # "character_detail", "world_hud", "dialog"
    raw_ocr_text: str = ""
    vlm_confidence: float = 0.0
    frame_hash: str = ""       # dedup key


# ---------------------------------------------------------------------------
# Planning types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AgentGoal:
    """What the agent is trying to achieve."""
    goal_id: str
    description: str          # "将钟离从80级升到90级"
    success_criteria: str     # VLM-checkable: "角色等级显示90"
    priority: int = 50
    parent_goal_id: str = ""


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """One step in an action plan."""
    step_id: str
    description: str          # "点击升级按钮"
    target_description: str   # VLM locator: "显示'升级'文字的按钮"
    expected_outcome: str     # "出现材料确认弹窗"
    fallback: str = ""        # "如果按钮灰化，检查是否需要突破"


@dataclass(frozen=True, slots=True)
class ActionPlan:
    """An LLM-generated plan to achieve a goal."""
    plan_id: str
    goal_id: str
    steps: tuple[PlannedStep, ...] = ()
    confidence: float = 0.0
    requires_confirmation: bool = False  # dangerous actions need human OK


# ---------------------------------------------------------------------------
# Execution types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ActionPrimitive:
    """A low-level execution primitive."""
    primitive_type: str  # "click", "type", "key_press", "scroll", "wait", "drag", "hold"
    target: str          # VLM description or normalised "nx,ny" coords
    params: tuple[tuple[str, str], ...] = ()  # key-value pairs
    reason: str = ""


@dataclass(frozen=True, slots=True)
class StepResult:
    """Outcome of executing a single step."""
    step_id: str
    success: bool
    observation_after: SemanticObservation | None = None
    error: str = ""
    duration_sec: float = 0.0


# ---------------------------------------------------------------------------
# Memory types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Experience:
    """A recorded experience for future reference."""
    goal_description: str
    scene_description: str
    action_taken: str
    outcome: str              # "success", "failed", "partial"
    failure_reason: str = ""
    duration_sec: float = 0.0
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Scene understanding types (§5.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SceneObject:
    """A named object detected in the current scene."""
    object_id: str
    kind: str                  # npc, enemy, button, waypoint, item, door, puzzle_part
    label: str
    bbox_norm: tuple[float, float, float, float] | None
    spatial_hint: str = ""      # left, near, above, behind, far, unknown
    confidence: float = 0.0
    source: str = "unknown"     # ocr, template, vlm, heuristic


@dataclass(frozen=True, slots=True)
class Affordance:
    """An action that can be performed on a scene object."""
    affordance_id: str
    verb: str                   # talk, attack, open, select, teleport, follow, inspect
    target_object_id: str
    preconditions: tuple[str, ...] = ()
    expected_delta: str = ""
    risk_level: str = "low"


@dataclass(frozen=True, slots=True)
class SceneGraph:
    """Structured representation of the current game scene."""
    timestamp: float
    scene_state: str
    objects: tuple[SceneObject, ...] = ()
    affordances: tuple[Affordance, ...] = ()
    frame_id: int = 0
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Skill recipe types (§8.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SkillStep:
    """One step inside a skill recipe."""
    step_id: str
    intent: str
    target_query: str           # natural language or structured query
    expected_delta: str = ""
    locator_policy: str = "affordance_then_vlm"
    retry_policy: str = "resample_relocate_replan"


@dataclass(frozen=True, slots=True)
class SkillRecipe:
    """A reusable, verifiable skill definition."""
    skill_id: str
    title: str
    goal_template: str
    applicable_context: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    steps: tuple[SkillStep, ...] = ()
    verifiers: tuple[str, ...] = ()
    recovery_policies: tuple[str, ...] = ()
    risk_level: str = "low"
    version: str = "1.0"


# ---------------------------------------------------------------------------
# Task specification
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Top-level task specification submitted by the operator or planner."""
    task_id: str
    objective: str              # mainline_progress, character_level_up, etc.
    dialog_policy: str = ""     # progress_main_story, skip_all, etc.
    resource_policy: str = ""   # no_rare_consumables, etc.
    uncertainty_policy: str = ""  # ask_user_after_120s, etc.
    execution_mode: str = "dry_run"  # dry_run, safe_window, console
    priority: int = 50
    parent_task_id: str = ""


# ---------------------------------------------------------------------------
# Runtime override & capsule patch types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RuntimeOverride:
    """A runtime parameter override requested by user or system."""
    override_id: str
    target_parameter: str
    new_value: str
    reason: str = ""
    source: str = "user"        # user, auto, system
    scope: str = "session"      # session, permanent
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class CapsulePatchProposal:
    """A proposed edit to a YAML skill capsule."""
    proposal_id: str
    capsule_id: str
    yaml_path: str
    patch_data: tuple[tuple[str, str], ...] = ()  # key-value pairs
    reason: str = ""
    verified: bool = False
    user_confirmed: bool = False


# ---------------------------------------------------------------------------
# Operator command types (§10)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OperatorCommand:
    """A parsed command from the human operator."""
    command_id: str
    user_text: str
    parsed_intent: str          # set_goal, adjust_policy, explain, confirm, abort
    parameters: tuple[tuple[str, str], ...] = ()
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Claim & evidence types (§5.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ClaimEvidence:
    """Evidence backing a state claim."""
    claim_id: str
    evidence_type: str          # ocr_text, screenshot_hash, vlm_description, state_change
    value: str
    confidence: float = 0.0
    source: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class StateDeltaClaim:
    """A claim that the game state has transitioned as expected."""
    claim_id: str
    expected_state: str
    observed_state: str
    evidence: tuple[ClaimEvidence, ...] = ()
    verified: bool = False
    confidence: float = 0.0
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GoalResult:
    """Final result of pursuing a goal."""
    goal_id: str
    achieved: bool
    steps_total: int = 0
    steps_succeeded: int = 0
    total_duration_sec: float = 0.0
    experiences: tuple[Experience, ...] = ()
    error: str = ""


# ---------------------------------------------------------------------------
# Execution contract types (ADR §4, 总纲 §5.6)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ActionContract:
    """Contract wrapping a semantic action with safety and execution policy.

    This is the core execution unit — every physical action must flow through
    an ActionContract. Referenced in 总纲 §1.1, §5.6, §13.1.
    """
    action_id: str
    semantic_action: ActionPrimitive
    safety_policy: tuple[tuple[str, str], ...] = ()  # key-value safety constraints
    timeout_ms: int = 5000
    risk_level: str = "low"       # low, medium, high, critical
    requires_confirmation: bool = False
    lease_id: str = ""


@dataclass(frozen=True, slots=True)
class PhysicalReceipt:
    """Receipt from physical action execution.

    Proves that an action was submitted, accepted, and either executed
    or failed. Part of the Claim chain (总纲 §5.4).
    """
    action_id: str
    success: bool
    reason: str = ""
    execution_latency_ms: float = 0.0
    focus_maintained: bool = True
    is_verified: bool = False
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# ADR structured types (from AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md §4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ThreatSignal:
    """A detected threat from the combat reflex layer (L1-L2)."""
    threat_type: str        # "projectile", "telegraph_aoe", "boss_animation_charge", "low_hp"
    severity: float         # 0.0 ~ 1.0
    direction_degrees: float = 0.0
    time_to_impact_ms: int = 0
    source: str = "unknown"


@dataclass(frozen=True, slots=True)
class CombatCommand:
    """A combat reflex command (L1-L2)."""
    reflex_action: str      # "dodge", "dash", "cast_skill_e", "cast_burst_q", "combo_normal_attack", "switch_character", "heal_emergency"
    target_character_index: int = 1
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RouteSegment:
    """A single segment of a navigation route (L3-L4)."""
    segment_id: int
    target_position: tuple[float, float, float]  # (x, y, z) in game world
    movement_type: str = "run"  # "run", "glide", "climb", "swim"
    speed_factor: float = 1.0


@dataclass(frozen=True, slots=True)
class MissionNode:
    """A node in the mission graph (L7-L8)."""
    node_id: str
    skill_intent: str
    preconditions: tuple[str, ...] = ()
    expected_state: str = ""
    risk_level: str = "low"


@dataclass(frozen=True, slots=True)
class MissionGraph:
    """A directed acyclic graph of mission nodes (L7-L8)."""
    graph_id: str
    nodes: tuple[MissionNode, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()  # (from_id, to_id) pairs
    current_node_index: int = 0


@dataclass(frozen=True, slots=True)
class RepairPatch:
    """A repair/replan suggestion from the CerebrumAgent (L7-L8)."""
    replan_required: bool = False
    inject_skills: tuple[str, ...] = ()
    runtime_overrides: tuple[tuple[str, str], ...] = ()  # key-value overrides
    explanation: str = ""
