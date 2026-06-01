"""Protocols (interfaces) for the AgentKernel framework.

Each protocol defines the contract that adapters must implement.
Uses Python's typing.Protocol for structural subtyping — no inheritance required.

Layer mapping (from AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md §3):
  L0   InputLeaseManager     — 100Hz physical safety, lease management
  L1-2 SpinalReflexAgent     — 50Hz combat reflex, threat evaluation
  L3-4 BrainstemNavigator    — 10-20Hz PID navigation, stuck detection
  L3-4 DialogueController    — 3-5Hz smart dialogue skip + branch intercept
  L5-6 CerebellumController  — 2-5Hz DesktopTree, OCR, route compilation
  L7-8 CerebrumAgent         — 0.1-0.2Hz mission compilation, failure diagnosis
  L9   CompanionAgent        — on-demand user interaction, override handling

Plus cross-cutting protocols:
  PerceptionProvider         — frame → semantic observation
  Planner                    — observation + goal → action plan
  ExecutionProvider          — action primitive → step result
  SuccessChecker             — observation + criteria → verified?
  MemoryStore                — experience recording and recall
  SkillRecipeLookup          — skill ID → SkillRecipe resolution
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_kernel.types import (
    ActionPlan,
    ActionPrimitive,
    AgentGoal,
    CapsulePatchProposal,
    CombatCommand,
    Experience,
    MissionGraph,
    MissionNode,
    PhysicalReceipt,
    RepairPatch,
    RouteSegment,
    RuntimeOverride,
    SceneGraph,
    SemanticObservation,
    SkillRecipe,
    StateDeltaClaim,
    StepResult,
    TaskSpec,
    ThreatSignal,
)


# ===========================================================================
# L0: Physical Safety Layer (100Hz)
# ===========================================================================

@runtime_checkable
class InputLeaseManager(Protocol):
    """L0: Control physical input with absolute safety.

    Manages lease-based input control with human-first intercept.
    When a physical user intervenes, all leases are instantly released.
    """

    def acquire_lease(self, owner: str, duration_sec: float, priority: int) -> str | None:
        """Acquire an input lease. Returns lease_id or None if denied."""
        ...

    def release_lease(self, lease_id: str) -> bool:
        """Release a specific lease."""
        ...

    def verify_window_focus(self) -> bool:
        """Check that the target window still has focus."""
        ...

    def detect_human_intervention(self) -> bool:
        """Detect physical mouse/keyboard activity from a human user."""
        ...

    def emergency_release_all(self) -> None:
        """Force-release all active leases immediately."""
        ...


# ===========================================================================
# L1-L2: Spinal Reflex Layer (50Hz)
# ===========================================================================

@runtime_checkable
class SpinalReflexAgent(Protocol):
    """L1-L2: High-frequency combat reflex engine.

    Evaluates threats and generates combat commands at 50Hz.
    Uses lightweight YOLO detection + combo state machine.
    """

    def evaluate_threats(self, latest_frame: object) -> list[ThreatSignal]:
        """Evaluate current frame for threats. Returns threat signals."""
        ...

    def tick_combat_reflex(
        self,
        threats: list[ThreatSignal],
        current_combo_step: int,
    ) -> CombatCommand | None:
        """Generate a combat command based on current threats and combo state."""
        ...


# ===========================================================================
# L3-L4: Brainstem Layer (10-20Hz)
# ===========================================================================

@runtime_checkable
class BrainstemNavigator(Protocol):
    """L3-L4: PID navigation controller with stuck detection.

    Handles heading servo, movement execution, and automatic unstuck routines.
    """

    def update_heading_servo(
        self,
        current_yaw: float,
        target_segment: RouteSegment,
    ) -> None:
        """Update the heading servo to face the next route segment."""
        ...

    def detect_stuck_state(
        self,
        current_pos: tuple[float, float, float],
        elapsed_sec: float,
    ) -> bool:
        """Detect if the agent is stuck (no meaningful position change)."""
        ...

    def execute_unstuck_routine(self, method: str = "jump") -> None:
        """Execute an unstuck routine (jump, dash_back, teleport_fallback)."""
        ...


@runtime_checkable
class DialogueController(Protocol):
    """L3-L4: Smart dialogue skip with branch interception.

    When in dialogue mode, skips through text at 3-5Hz.
    When a branch choice appears, pauses and delegates selection.
    """

    def tick_dialogue_skip(self, scene_graph: SceneGraph) -> None:
        """Process one dialogue skip tick. Handles text advancement."""
        ...

    def is_option_present(self, scene_graph: SceneGraph) -> bool:
        """Check if a dialogue branch choice is currently on screen."""
        ...

    def select_best_option(
        self,
        scene_graph: SceneGraph,
        option_registry: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Select the best dialogue option from available choices.

        Uses option_registry for known options, falls back to VLM for unknown.
        """
        ...


# ===========================================================================
# L5-L6: Cerebellum Layer (2-5Hz)
# ===========================================================================

@runtime_checkable
class CerebellumController(Protocol):
    """L5-L6: DesktopTree construction, OCR, and route compilation.

    Builds structured UI trees from raw frames using template anchoring
    and geometric clustering. Compiles navigation routes.
    """

    def locate_ui_panel_roi(
        self,
        frame: object,
        panel_template_id: str,
    ) -> tuple[float, float, float, float] | None:
        """Locate a UI panel ROI using template matching."""
        ...

    def parse_desktop_tree(
        self,
        frame: object,
        active_roi: tuple[float, float, float, float] | None = None,
    ) -> SceneGraph:
        """Parse a frame into a structured SceneGraph (UI tree)."""
        ...

    def compile_route(
        self,
        current_pos: tuple[float, float, float],
        destination: tuple[float, float, float],
    ) -> list[RouteSegment]:
        """Compile a navigation route from current position to destination.

        Returns a list of route segment dicts.
        """
        ...

    def commit_yaml_patch(
        self,
        capsule_id: str,
        patch_data: dict[str, Any],
    ) -> bool:
        """Write a permanent YAML patch to a capsule's config."""
        ...


# ===========================================================================
# L7-L8: Cerebrum Agent (0.1-0.2Hz, cloud-first)
# ===========================================================================

@runtime_checkable
class CerebrumAgent(Protocol):
    """L7-L8: Cloud-hosted strategic brain.

    Handles mission compilation, failure diagnosis, visual puzzle solving,
    and replanning. Cloud-first but must support offline fallback.
    """

    def compile_mission(self, goal: AgentGoal) -> MissionGraph:
        """Compile a goal into a MissionGraph (plan DAG)."""
        ...

    def diagnose_failure(
        self,
        failed_node: MissionNode,
        screenshot: object,
        error_trace: str,
    ) -> RepairPatch:
        """Diagnose why a mission node failed. Returns a repair patch."""
        ...

    def solve_visual_puzzle(
        self,
        puzzle_image: object,
        scene_description: str,
    ) -> tuple[str, ...]:
        """Solve a visual puzzle using multi-modal reasoning.

        Returns a tuple of action descriptions to execute.
        """
        ...


# ===========================================================================
# L9: Companion Agent (on-demand)
# ===========================================================================

@runtime_checkable
class CompanionAgent(Protocol):
    """L9: User-facing dialogue companion.

    Handles natural language interaction, state explanation,
    runtime override injection, and YAML patch proposals.
    """

    def handle_user_message(
        self,
        message: str,
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle a user message and return a response.

        Response includes display_message, technical_action, and optional
        patch_draft.
        """
        ...

    def propose_override(
        self,
        user_text: str,
        current_state: dict[str, Any],
    ) -> RuntimeOverride | None:
        """Parse user text into a RuntimeOverride proposal."""
        ...

    def propose_capsule_patch(
        self,
        override: RuntimeOverride,
        session_outcome: str,
    ) -> CapsulePatchProposal | None:
        """Propose making a runtime override permanent as a Capsule YAML patch."""
        ...

    def explain_current_state(self, state: dict[str, Any]) -> str:
        """Generate a human-readable explanation of the current agent state."""
        ...


# ===========================================================================
# Cross-cutting Protocols
# ===========================================================================

@runtime_checkable
class PerceptionProvider(Protocol):
    """Transform raw frames into semantic understanding."""

    def observe(self, frame: object) -> SemanticObservation:
        """Produce a semantic observation from a raw frame."""
        ...

    def describe_scene(self, frame: object, prompt: str) -> str:
        """Get a natural language description of the scene."""
        ...

    def locate_element(
        self, frame: object, description: str,
    ) -> object | None:
        """Find an element matching a natural language description."""
        ...


@runtime_checkable
class Planner(Protocol):
    """Generate action plans from observations and goals."""

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
class SuccessChecker(Protocol):
    """Check whether a goal has been achieved."""

    def check(
        self, observation: SemanticObservation, criteria: str,
    ) -> tuple[bool, float]:
        """Return (achieved, confidence)."""
        ...


@runtime_checkable
class ExecutionProvider(Protocol):
    """Execute action primitives via physical input."""

    def execute(self, primitive: ActionPrimitive) -> StepResult:
        """Execute a single primitive and return the result."""
        ...

    def locate_and_click(self, description: str) -> StepResult:
        """Locate an element by description and click it."""
        ...

    def press_key(self, key: str, reason: str = "") -> StepResult:
        """Press a keyboard key."""
        ...


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
class SkillRecipeLookup(Protocol):
    """Resolve skill IDs to SkillRecipe instances."""

    def lookup(self, skill_id: str) -> SkillRecipe | None:
        """Look up a SkillRecipe by ID."""
        ...

    def find_applicable(
        self,
        context: str,
        goal: AgentGoal,
    ) -> list[SkillRecipe]:
        """Find all skills applicable to the given context and goal."""
        ...


@runtime_checkable
class ClaimAdjudicator(Protocol):
    """Verify state delta claims against observation evidence."""

    def adjudicate(self, claim: StateDeltaClaim) -> StateDeltaClaim:
        """Verify a claim and return it with verified=True/False and confidence."""
        ...


# ===========================================================================
# Game Capsule Protocol (§6 in SPARKLE_AGENT_KERNEL_DESIGN.md)
# ===========================================================================

@runtime_checkable
class GameCapsule(Protocol):
    """Protocol for game-specific capsule integration.

    Each game must implement this protocol to plug into the Kernel.
    The Kernel never imports game-specific code; it only uses this interface.
    """

    @property
    def game_id(self) -> str:
        """Unique identifier for this game capsule (e.g., 'genshin', 'hsr')."""
        ...

    def screen_vocabulary(self) -> tuple[str, ...]:
        """Return known screen state names for this game."""
        ...

    def action_vocabulary(self) -> tuple[str, ...]:
        """Return known action types for this game."""
        ...

    def skill_library(self) -> dict[str, SkillRecipe]:
        """Return all skills provided by this capsule."""
        ...

    def risk_policy(self) -> dict[str, str]:
        """Return risk level mappings for this game's actions."""
        ...
