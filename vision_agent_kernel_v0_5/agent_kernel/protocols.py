"""Protocols (interfaces) for the Sparkle Agent Kernel core neurology.

Each protocol defines the strict contract that game capsules and drivers must
implement. Uses Python's typing.Protocol for structural subtyping.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Dict, Any, Sequence
from uuid import UUID

from agent_kernel.types import (
    ActionContract,
    ActionPlan,
    ActionPrimitive,
    AgentGoal,
    CapsulePatchProposal,
    DesktopTree,
    Experience,
    GoalResult,
    PhysicalReceipt,
    RuntimeOverride,
    SemanticAction,
    SemanticObservation,
    StateDeltaClaim,
    StepResult,
    TaskSpec,
    WorldStateGraph,
    SceneGraph,
    SkillRecipe,
    ThreatSignal,
    MissionNode,
    MissionGraph,
    RouteSegment,
    ObservationClaim,
    RepairPatch,
)

# ===========================================================================
# 1. Core General Protocols (Legacy & Multi-Game Capsule)
# ===========================================================================

@runtime_checkable
class GameCapsule(Protocol):
    """Encapsulation of a single game's specs, UI vocabularies and routes."""
    @property
    def game_id(self) -> str: ...
    
    def screen_vocabulary(self) -> dict[str, Any]: ...
    def action_vocabulary(self) -> dict[str, Any]: ...
    def world_knowledge(self) -> dict[str, Any]: ...
    def verifier_bundle(self) -> dict[str, Any]: ...
    def skill_library(self) -> dict[str, Any]: ...


@runtime_checkable
class MemoryStore(Protocol):
    """Record and recall experiences."""

    def record(self, experience: Experience) -> None:
        """Store an experience."""
        ...

    def recall(self, situation: str, limit: int = 5) -> list[Experience]:
        """Retrieve relevant past experiences."""
        ...

    def recall_failures(self, goal_type: str) -> list[Experience]:
        """Retrieve failed experiences for a goal type."""
        ...


@runtime_checkable
class Planner(Protocol):
    """Generate action plans from observations and goals (Legacy compatibility)."""

    def plan(
        self,
        observation: SemanticObservation,
        goal: AgentGoal,
        memory: object,
    ) -> ActionPlan:
        """Generate a plan to achieve the goal given current observation."""
        ...

    def replan(
        self,
        observation: SemanticObservation,
        goal: AgentGoal,
        failure: StepResult,
        memory: object,
    ) -> ActionPlan:
        """Re-plan after a step failure."""
        ...


@runtime_checkable
class SkillRecipeLookup(Protocol):
    """Repository mapping skill intent strings to generalized recipes."""
    def lookup(self, capability: str) -> SkillRecipe: ...
    def lookup_recipe(self, skill_id: str) -> dict[str, Any]: ...


# ===========================================================================
# 2. Perception Protocols (L3-L6)
# ===========================================================================

@runtime_checkable
class PerceptionProvider(Protocol):
    """Cortex Fusion: Transforms raw capture frame into full SemanticObservation."""

    def observe(self, frame: object, frame_id: int) -> SemanticObservation:
        """Produce a full observation (2D DesktopTree + 3D WorldStateGraph)."""
        ...

    def parse_desktop_tree(
        self, frame: object, active_roi: tuple[float, float, float, float] | None = None
    ) -> DesktopTree:
        """Locate containers using templates, run local OCR, and cluster nodes."""
        ...

    def build_world_state(self, frame: object) -> WorldStateGraph:
        """Analyze 3D terrain, waypoints, targets, landmarks, and obstacles."""
        ...


# ===========================================================================
# 3. Planning & Verification Protocols (L7-L8)
# ===========================================================================

@runtime_checkable
class CerebrumPlanner(Protocol):
    """Cerebrum: Low-frequency, Cloud-First strategic planner and replanner."""

    def compile_task(self, goal: AgentGoal, spec: TaskSpec) -> Sequence[SemanticAction]:
        """Generate high-level strategic actions to achieve a goal."""
        ...

    def replan_on_failure(
        self,
        failed_action: SemanticAction,
        observation: SemanticObservation,
        error_msg: str,
    ) -> Sequence[SemanticAction]:
        """Determine strategic recovery route or request human intervention."""
        ...


@runtime_checkable
class SuccessChecker(Protocol):
    """Adjudicates claims and verifies if a goal has been reached."""

    def adjudicate_delta(
        self, pre_obs: SemanticObservation, post_obs: SemanticObservation, criteria: str
    ) -> StateDeltaClaim:
        """Check post-action observation claims to verify expected state shifts."""
        ...

    def check(
        self, observation: SemanticObservation, criteria: str,
    ) -> tuple[bool, float]:
        """Return (achieved, confidence)."""
        ...


@runtime_checkable
class ClaimAdjudicator(Protocol):
    """L8 Fact Verification: Core facts adjudication."""
    def adjudicate(
        self,
        claim: StateDeltaClaim,
        observations: list[ObservationClaim],
        *,
        dependency_health: float = 1.0,
        drift_penalty: float = 1.0,
        sample_sufficiency: float = 1.0,
    ) -> Any: ...


# ===========================================================================
# 4. Execution Protocols (L0-L2)
# ===========================================================================

@runtime_checkable
class ExecutionProvider(Protocol):
    """Execution Runtime: The unique and secure gatekeeper to physical keyboard/mouse."""

    def execute(self, primitive: ActionPrimitive) -> StepResult:
        """Execute a single primitive and return the result."""
        ...

    def locate_and_click(self, description: str) -> StepResult:
        """Locate an element by description and click it."""
        ...

    def press_key(self, key: str, reason: str = "") -> StepResult:
        """Press a keyboard key."""
        ...

    def execute_contract(self, contract: ActionContract) -> PhysicalReceipt:
        """Execute a validated contract under active safety leases."""
        ...

    def emergency_halt(self) -> None:
        """Immediately release all active keys, cancel physical inputs, and clear queues."""
        ...


# ===========================================================================
# 5. Low-level Controller Protocols (L0-L5)
# ===========================================================================

@runtime_checkable
class InputLeaseManager(Protocol):
    """L0 物理安全层：控制物理键鼠的绝对控制权与安全截断"""
    def acquire_lease(self, owner: str, duration_sec: float, priority: int) -> UUID | str | None: ...
    def release_lease(self, lease_id: UUID | str) -> bool: ...
    def verify_window_focus(self) -> bool: ...
    def detect_human_intervention(self) -> bool: ...
    def emergency_release_all(self) -> None: ...


@runtime_checkable
class SpinalReflexAgent(Protocol):
    """L1-L2 脊髓层：实时战斗反射与连招状态机"""
    def evaluate_threats(self, latest_frame: Any) -> list[ThreatSignal]: ...
    def tick_combat_reflex(self, threats: Sequence[ThreatSignal], current_combo_step: int) -> Any: ...


@runtime_checkable
class BrainstemNavigator(Protocol):
    """L3-L4 脑干层：物理 PID 导航与自动避卡"""
    def update_heading_servo(self, current_yaw: float, target_segment: RouteSegment) -> None: ...
    def detect_stuck_state(self, current_pos: tuple[float, float, float], elapsed_sec: float) -> bool: ...
    def execute_unstuck_routine(self, method: str) -> None: ...


@runtime_checkable
class DialogueController(Protocol):
    """L3-L4 脑干层：智能对话跳过与选项拦截选择"""
    def tick_dialogue_skip(self, tree: SceneGraph) -> None: ...
    def tick(self, scene_graph: SceneGraph) -> None: ...
    def is_option_present(self, tree: SceneGraph) -> bool: ...
    def select_best_option(self, tree: SceneGraph, option_registry: dict[str, Any] | None = None) -> Any: ...


@runtime_checkable
class CerebellumController(Protocol):
    """L5-L6 小脑层：动态 UI 树解析、锚点对齐与路线编译"""
    def locate_ui_panel_roi(self, frame: Any, panel_template_id: str) -> tuple[float, float, float, float] | None: ...
    def parse_desktop_tree(self, frame: Any, active_roi: tuple[float, float, float, float] | None = None) -> SceneGraph: ...
    def align_ui_anchor(self, tree: SceneGraph, target_label: str, active_overrides: dict[str, Any] | None = None) -> Any: ...
    def compile_route(self, current_pos: tuple[float, float, float], destination: tuple[float, float, float]) -> Sequence[RouteSegment]: ...
    def commit_yaml_patch(self, capsule_id: str, patch_data: dict[str, Any]) -> bool: ...


@runtime_checkable
class CerebrumAgent(Protocol):
    """L8 大脑层：高级战略规划与复杂故障诊断"""
    def compile_mission(self, goal: AgentGoal) -> MissionGraph: ...
    def diagnose_failure(self, failed_node: MissionNode, screenshot: Any, error_trace: str) -> RepairPatch: ...
    def solve_visual_puzzle(self, puzzle_image: Any, scene_description: str) -> tuple[str, ...]: ...


# ===========================================================================
# 6. Companion Interaction Protocols (L9)
# ===========================================================================

@runtime_checkable
class CompanionAgent(Protocol):
    """Companion: High-level natural language companion dialogue interface."""

    def parse_override(self, user_command: str, tree: DesktopTree) -> RuntimeOverride:
        """Parse natural language command into a safe policy RuntimeOverride patch."""
        ...

    def propose_capsule_patch(
        self, capsule_id: str, successful_override: RuntimeOverride
    ) -> CapsulePatchProposal:
        """Generate schema-validated Capsule patch with displayable diff."""
        ...
