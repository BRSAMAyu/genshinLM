"""Live Genshin Impact AgentLoop factory.

Wires all production components (DxcamCapture, ZhipuVLM, SafeWindowBackend,
GenshinScreenClassifier, etc.) into the AgentLoop L0-L9 neurological runtime.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Sequence

from agent_kernel.types import (
    ActionContract,
    AgentGoal,
    PhysicalReceipt,
    SemanticAction,
    SemanticObservation,
    StateDeltaClaim,
    StepResult,
    TaskSpec,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter: CerebrumAgentImpl → CerebrumPlanner protocol
# ---------------------------------------------------------------------------

class CerebrumPlannerAdapter:
    """Adapts CerebrumAgentImpl to CerebrumPlanner protocol.

    Exposes compile_task / replan_on_failure (not plan/replan),
    so AgentLoop uses the neurological (non-legacy) code path.

    When a precompiled MissionGraphV4 is provided, compile_task() converts
    its nodes directly to SemanticActions (bypassing cerebrum.compile_mission).
    """

    _KIND_MAP: dict[str, str] = {
        "combat": "combat",
        "navigation": "navigation",
        "interaction": "ui",
        "dialogue": "ui",
        "system": "system",
        "explore": "navigation",
        "quest": "navigation",
        "loot": "ui",
        "unknown": "navigation",
    }

    def __init__(self, cerebrum: Any, precompiled_graph: Any | None = None) -> None:
        self._cerebrum = cerebrum
        self._precompiled_graph = precompiled_graph

    def compile_task(self, goal: AgentGoal, spec: TaskSpec) -> Sequence[SemanticAction]:
        if self._precompiled_graph is not None:
            return self._compile_from_graph(self._precompiled_graph)
        mission = self._cerebrum.compile_mission(goal)
        actions: list[SemanticAction] = []
        for node in mission.nodes:
            intent = node.skill_intent or node.node_type or "unknown"
            kind = self._infer_kind(intent)
            actions.append(SemanticAction(
                action_id=node.node_id,
                kind=kind,
                intent=intent,
                target=node.expected_state or "",
                parameters=tuple((k, str(v)) for k, v in node.parameters.items()),
                requires_physical_input=True,
            ))
        return actions

    def _compile_from_graph(self, graph: Any) -> Sequence[SemanticAction]:
        """Convert precompiled MissionGraphV4 nodes to SemanticAction sequence."""
        order = graph.topological_order()
        if not order:
            order = list(graph.node_ids)
        actions: list[SemanticAction] = []
        for node_id in order:
            node = graph.get_node(node_id)
            if node is None:
                continue
            semantic = str(node.metadata.get("semantic_action", node.node_type))
            target = str(node.metadata.get("target", ""))
            kind = self._infer_kind(semantic)
            actions.append(SemanticAction(
                action_id=node.node_id,
                kind=kind,
                intent=semantic,
                target=target,
                parameters=tuple(
                    (str(k), str(v)) for k, v in node.metadata.get("parameters", {}).items()
                ),
                requires_physical_input=node.node_type not in ("system",),
            ))
        return actions

    @classmethod
    def _infer_kind(cls, intent: str) -> str:
        lower = intent.lower()
        for key, val in cls._KIND_MAP.items():
            if key in lower:
                return val
        return "ui"

    def replan_on_failure(
        self,
        failed_action: SemanticAction,
        observation: SemanticObservation,
        error_msg: str,
    ) -> Sequence[SemanticAction]:
        from agent_kernel.types import MissionNode, RepairPatch
        failed_node = MissionNode(
            node_id=failed_action.action_id,
            skill_intent=failed_action.intent,
        )
        patch: RepairPatch = self._cerebrum.diagnose_failure(failed_node, None, error_msg)
        if patch.replan_required:
            return [SemanticAction(
                action_id=f"replan_{uuid.uuid4().hex[:8]}",
                kind="system",
                intent="replan_requested",
                reason=patch.explanation,
                requires_physical_input=False,
            )]
        return []


# ---------------------------------------------------------------------------
# Adapter: GenshinActionExecutor → ExecutionProvider protocol
# ---------------------------------------------------------------------------

class ActionExecutorAdapter:
    """Adapts GenshinActionExecutor to the ExecutionProvider protocol.

    Delegates to the 40+ action handlers in GenshinActionExecutor._ACTION_MAP
    while providing the contract-based execution path that AgentLoop expects.
    """

    def __init__(self, executor: Any) -> None:
        self._executor = executor

    def execute_contract(self, contract: ActionContract) -> PhysicalReceipt:
        sa = contract.semantic_action
        context: dict[str, Any] = {}
        for k, v in sa.parameters:
            context[k] = v
        try:
            success = self._executor.execute_semantic(sa.intent, sa.target, context)
        except Exception as exc:
            log.warning("[ActionAdapter] execute_semantic failed: %s", exc)
            success = False
        now = time.perf_counter()
        return PhysicalReceipt(
            receipt_id=uuid.uuid4(),
            lease_id=uuid.uuid4(),
            issued_at=now,
            expires_at=now + 0.25,
            action_type="click",
            execution_latency_ms=0.0,
            focus_maintained=bool(success),
            action_id=sa.action_id,
            status="verified" if success else "failed",
            submitted_at=now,
            lease_accepted=True,
            focus_ok=bool(success),
            duration_ms=0.0,
        )

    def execute(self, primitive: Any) -> StepResult:
        try:
            success = self._executor.execute_semantic(
                primitive.primitive_type, primitive.target, {},
            )
        except Exception:
            success = False
        return StepResult(
            step_id=primitive.target or str(uuid.uuid4()),
            success=bool(success),
        )

    def locate_and_click(self, description: str) -> StepResult:
        try:
            success = self._executor.execute_semantic("click_button", description, {})
        except Exception:
            success = False
        return StepResult(step_id=description, success=bool(success))

    def press_key(self, key: str, reason: str = "") -> StepResult:
        try:
            success = self._executor.execute_semantic(key, reason, {})
        except Exception:
            success = False
        return StepResult(step_id=key, success=bool(success))

    def emergency_halt(self) -> None:
        try:
            self._executor._backend.release_all(reason="emergency_halt")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Human intervention detector for InputLeaseManager
# ---------------------------------------------------------------------------

def _make_human_detector(backend: Any) -> Callable[[], bool]:
    """Create a callable that detects human intervention via focus loss."""
    last_focused = True

    def detect() -> bool:
        nonlocal last_focused
        try:
            current = backend.is_target_focused()
        except Exception:
            current = False
        intervened = last_focused and not current
        last_focused = current
        return intervened

    return detect


# ---------------------------------------------------------------------------
# Main factory
# ---------------------------------------------------------------------------

def create_live_genshin_loop(
    goal: str,
    window_title: str,
    *,
    api_key: str | None = None,
    max_plan_iterations: int = 20,
    max_step_retries: int = 2,
    cerebrum_interval_sec: float = 5.0,
    capture_fps: float = 15.0,
    pixels_per_degree: float = 8.0,
    dry_run: bool = False,
    precompiled_graph: Any | None = None,
) -> tuple[Any, Any, Any]:
    """Wire all live components into an AgentLoop for Genshin gameplay.

    Returns (agent_loop, capturer, backend) — caller must start/stop capturer
    and call backend.release_all() when done.
    """
    import os
    from core.local_secret_store import get_secret

    os.environ.setdefault("AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW", "1")
    key = api_key or get_secret("ZHIPU_API_KEY") or ""

    # --- Screen capture ---
    from core.timebase import Timebase
    timebase = Timebase()

    if dry_run:
        capturer = _DryRunCapturer()
        backend = _DryRunBackend()
    else:
        from perception.dxcam_capture import DxcamCapturer, CaptureConfig
        capturer = DxcamCapturer(CaptureConfig(target_fps=capture_fps), timebase=timebase)
        from execution.safe_window_backend import SafeWindowInputBackend
        backend = SafeWindowInputBackend(
            target_window_title=window_title,
            pixels_per_degree=pixels_per_degree,
        )

    frame_counter = [0]

    def capture_frame() -> Any:
        packet = capturer.get_latest_frame()
        if packet is None:
            return None
        return packet.image

    # --- Perception ---
    from capsules.detector_resolver import get_screen_classifier, get_combat_detector
    from agent_kernel.adapters import VLMPerceptionProvider

    classifier = get_screen_classifier()

    if dry_run:
        vlm = _DryRunVLM()
    else:
        from llm.zhipu_vlm_provider import ZhipuVLMProvider
        vlm = ZhipuVLMProvider(api_key=key)

    perception = VLMPerceptionProvider(
        screen_classifier=classifier,
        vlm_provider=vlm,
    )

    # Wire combat detector to perception pipeline (if not dry-run)
    if not dry_run:
        try:
            _combat_detector = get_combat_detector()
            if _combat_detector is not None:
                # Register with perception pipeline's fusion runtime if available
                if hasattr(perception, '_fusion') and perception._fusion is not None:
                    perception._fusion.set_combat_detector(_combat_detector.detect)
        except Exception as exc:
            log.debug("[LiveFactory] Combat detector wiring skipped: %s", exc)

    # --- Planner (Cerebrum L7-L8) ---
    from agent_kernel.cerebrum_agent import CerebrumAgentImpl
    cerebrum = CerebrumAgentImpl()
    planner = CerebrumPlannerAdapter(cerebrum, precompiled_graph=precompiled_graph)

    # --- Executor ---
    if dry_run:
        executor = ActionExecutorAdapter(_DryRunActionExecutor())
    else:
        from agent.genshin_game_agent import GenshinActionExecutor
        genshin_executor = GenshinActionExecutor(backend)
        executor = ActionExecutorAdapter(genshin_executor)

    # --- Success checker ---
    from agent_kernel.adapters import VLMSuccessChecker
    checker = VLMSuccessChecker(vlm_provider=vlm, threshold=0.7)

    # --- Companion (L9) ---
    from agent_kernel.operator_agent import SimpleOperatorAgent
    companion = SimpleOperatorAgent(
        task_keywords={
            "每日委托": "daily", "每日": "daily", "主线": "mainline",
            "探索": "explore", "传送": "teleport", "升级": "upgrade",
            "战斗": "combat", "对话": "dialogue", "收集": "collect",
            "daily": "daily", "commission": "daily", "quest": "mainline",
            "explore": "explore", "teleport": "teleport", "fight": "combat",
        },
    )

    # --- Lease manager (L0) ---
    from agent_kernel.input_lease_manager import InputLeaseManagerImpl
    lease_manager = InputLeaseManagerImpl(
        focus_checker=backend,
        human_detector=_make_human_detector(backend),
    )

    # --- Combat agent (L1-L2) ---
    from agent_kernel.spinal_reflex_agent import SpinalReflexAgentImpl
    combat_agent = SpinalReflexAgentImpl()

    # --- Dialogue controller (L3-L4) ---
    from agent_kernel.dialogue_controller import DialogueController, OptionRegistry
    option_registry = OptionRegistry(entries={
        "每日委托": "select", "Daily Commissions": "select",
        "领取奖励": "select", "Claim Reward": "select",
        "确认": "select", "Confirm": "select",
    })
    dialogue_controller = DialogueController(option_registry=option_registry)

    # --- Embodied runtime (L3-L6 fast-path) ---
    from agent_kernel.embodied_runtime import DailyCommissionDryRunRuntime
    embodied_runtime = DailyCommissionDryRunRuntime()

    # --- Memory ---
    from agent_kernel.memory import FileMemoryStore
    memory = FileMemoryStore(path="logs/experiences.jsonl")

    # --- Unknown scene handler (autonomous exploration) ---
    from agent_kernel.unknown_scene_handler import UnknownSceneHandler
    unknown_handler = UnknownSceneHandler(max_probe_attempts=6, confidence_threshold=0.45)

    # --- Meta-learning bridge (exploration→BAGEL→skill chain) ---
    from bagel.fig_schema import FalsifiableInterventionGraph
    from bagel.belief_proposer import BeliefProposer
    from learning.decision_memory import DecisionMemory
    from learning.meta_learning_bridge import MetaLearningBridge
    from learning.parameterized_skill_induction import ParameterizedSkillInductor

    fig = FalsifiableInterventionGraph()
    decision_memory = DecisionMemory(db_path="data/decision_memory.db")
    belief_proposer = BeliefProposer(fig=fig, decision_memory=decision_memory)
    skill_inductor = ParameterizedSkillInductor()
    meta_bridge = MetaLearningBridge(
        fig=fig,
        decision_memory=decision_memory,
        belief_proposer=belief_proposer,
        skill_inductor=skill_inductor,
    )

    # Wire UnknownSceneHandler → MetaLearningBridge (gap 4 closure)
    unknown_handler.set_meta_learning_bridge(meta_bridge)

    # --- Gated self-modification ("Claude Code inside", human-approved) ---
    # The coordinator synthesizes + sandbox-validates + PROPOSES patches; nothing
    # is applied without an explicit human approve() (gate is structural). The
    # loop ticks HotReloadManager to swap in approved modules. Defensive: failure
    # to build this layer must never block loop construction.
    hot_reload_manager = None
    self_mod_coordinator = None
    try:
        from runtime.hot_reload_manager import HotReloadManager
        from learning.self_modification_coordinator import SelfModificationCoordinator
        from app_service.coding_agent import CodingAgent
        hot_reload_manager = HotReloadManager()
        self_mod_coordinator = SelfModificationCoordinator(
            coding_agent=CodingAgent(llm=None),  # LLM wiring is a follow-up slice
            hot_reload_manager=hot_reload_manager,
        )
        log.info("[LiveFactory] Gated self-modification coordinator wired.")
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("[LiveFactory] Self-modification wiring skipped: %s", exc)

    # --- Pose substrate (spatial localization → StateBus.latest_pose) ---
    # Pure perception: publishes a fused PoseEstimate each cycle; drives no
    # input, so it is safe in dry-run and live alike. Defensive: a failure to
    # build the pose layer must never block loop construction.
    from core.state_bus import StateBus
    state_bus_core = StateBus()
    pose_wiring = None
    try:
        from perception.live_pose_wiring import wire_genshin_pose
        pose_wiring = wire_genshin_pose(state_bus_core, profile="genshin_1920x1080")
        log.info("[LiveFactory] Pose substrate wired (publishes StateBus.latest_pose).")
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("[LiveFactory] Pose substrate wiring skipped: %s", exc)

    # --- Assemble AgentLoop ---
    from agent_kernel.loop import AgentLoop
    agent_loop = AgentLoop(
        perception=perception,
        planner=planner,
        executor=executor,
        checker=checker,
        companion=companion,
        capture_frame=capture_frame,
        lease_manager=lease_manager,
        combat_agent=combat_agent,
        dialogue_controller=dialogue_controller,
        embodied_runtime=embodied_runtime,
        pose_wiring=pose_wiring,
        max_plan_iterations=max_plan_iterations,
        max_step_retries=max_step_retries,
        memory=memory,
    )
    agent_loop._cerebrum_interval_sec = cerebrum_interval_sec
    agent_loop._unknown_scene_handler = unknown_handler
    agent_loop._meta_learning_bridge = meta_bridge
    # Expose the real StateBus so navigation/recovery consumers can read pose.
    agent_loop._state_bus_core = state_bus_core
    # Expose the gated self-modification machinery on the loop.
    agent_loop._hot_reload_manager = hot_reload_manager
    agent_loop._self_mod_coordinator = self_mod_coordinator

    log.info(
        "[LiveFactory] AgentLoop assembled: goal='%s' window='%s' dry_run=%s",
        goal, window_title, dry_run,
    )
    return agent_loop, capturer, backend


# ---------------------------------------------------------------------------
# Dry-run stubs for testing without real hardware
# ---------------------------------------------------------------------------

class _DryRunCapturer:
    """Mimics DxcamCapturer interface for dry-run mode."""
    def start(self) -> None:
        pass
    def stop(self) -> None:
        pass
    def get_latest_frame(self) -> Any:
        import numpy as np
        from perception.capture_base import FramePacket
        return FramePacket(
            image=np.zeros((1080, 1920, 3), dtype=np.uint8),
            frame_id=0,
            timestamp=time.perf_counter(),
            source_size=(1920, 1080),
        )


class _DryRunBackend:
    """Mimics SafeWindowInputBackend for dry-run mode."""
    def is_target_focused(self) -> bool:
        return True
    def release_all(self, reason: str = "") -> None:
        pass
    def key_down(self, key: str, reason: str = "") -> None:
        pass
    def key_up(self, key: str, reason: str = "") -> None:
        pass
    def left_click(self, reason: str = "") -> None:
        pass
    def mouse_move(self, dx: float, dy: float, reason: str = "") -> None:
        pass


class _DryRunVLM:
    """Mimics ZhipuVLMProvider for dry-run mode."""
    def describe_image(self, image: Any, prompt: str) -> Any:
        return _DryRunResult(description="overworld", confidence=0.8)
    def ground_ui(self, image: Any, description: str) -> Any:
        return _DryRunResult(candidates=[])


class _DryRunResult:
    def __init__(self, description: str = "", confidence: float = 0.0, candidates: list | None = None) -> None:
        self.description = description
        self.confidence = confidence
        self.candidates = candidates or []


class _DryRunActionExecutor:
    """Mimics GenshinActionExecutor for dry-run mode."""
    def __init__(self) -> None:
        self._backend = _DryRunBackend()
    def execute_semantic(self, intent: str, target: str, context: dict) -> bool:
        log.info("[DryRun] execute_semantic(intent='%s', target='%s')", intent, target)
        return True
