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
    """

    _KIND_MAP: dict[str, str] = {
        "combat": "combat",
        "navigation": "navigation",
        "interaction": "ui",
        "dialogue": "ui",
        "system": "system",
        "explore": "navigation",
    }

    def __init__(self, cerebrum: Any) -> None:
        self._cerebrum = cerebrum

    def compile_task(self, goal: AgentGoal, spec: TaskSpec) -> Sequence[SemanticAction]:
        mission = self._cerebrum.compile_mission(goal)
        actions: list[SemanticAction] = []
        for node in mission.nodes:
            intent = node.skill_intent or node.node_type or "unknown"
            kind = "ui"
            for key, val in self._KIND_MAP.items():
                if key in intent.lower():
                    kind = val
                    break
            actions.append(SemanticAction(
                action_id=node.node_id,
                kind=kind,
                intent=intent,
                target=node.expected_state or "",
                parameters=tuple((k, str(v)) for k, v in node.parameters.items()),
                requires_physical_input=True,
            ))
        return actions

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
    from perception.genshin_screen_classifier import GenshinScreenClassifier
    from agent_kernel.adapters import VLMPerceptionProvider

    classifier = GenshinScreenClassifier()

    if dry_run:
        vlm = _DryRunVLM()
    else:
        from llm.zhipu_vlm_provider import ZhipuVLMProvider
        vlm = ZhipuVLMProvider(api_key=key)

    perception = VLMPerceptionProvider(
        screen_classifier=classifier,
        vlm_provider=vlm,
    )

    # --- Planner (Cerebrum L7-L8) ---
    from agent_kernel.cerebrum_agent import CerebrumAgentImpl
    cerebrum = CerebrumAgentImpl()
    planner = CerebrumPlannerAdapter(cerebrum)

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
        max_plan_iterations=max_plan_iterations,
        max_step_retries=max_step_retries,
        memory=memory,
    )
    agent_loop._cerebrum_interval_sec = cerebrum_interval_sec

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
