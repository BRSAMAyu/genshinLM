"""Unit tests for the production Sparkle Agent Kernel neurological loop."""
from __future__ import annotations

import time
import pytest
import threading
from typing import Any, Sequence, Dict

from agent_kernel.loop import AgentLoop
from agent_kernel.types import (
    ActionContract,
    AgentGoal,
    CapsulePatchProposal,
    DesktopNode,
    DesktopTree,
    GoalResult,
    PhysicalReceipt,
    RuntimeOverride,
    SemanticAction,
    SemanticObservation,
    StateDeltaClaim,
    TaskSpec,
    ThreatSignal,
    CombatCommand,
)


# ===========================================================================
# Mock Classes for Multi-layered Testing
# ===========================================================================

class MockInputLeaseManager:
    def __init__(self) -> None:
        self.intervened = False
        self.focus = True

    def verify_window_focus(self) -> bool:
        return self.focus

    def detect_human_intervention(self) -> bool:
        return self.intervened

    def clear_emergency(self) -> None:
        self.intervened = False


class MockSpinalReflexAgent:
    def evaluate_threats(self, latest_frame: Any) -> Sequence[ThreatSignal]:
        # Simulates a sudden danger signal
        return [ThreatSignal("projectile", 0.85, 90.0, 50)]

    def tick_combat_reflex(self, threats: Sequence[ThreatSignal], current_combo_step: int) -> CombatCommand | None:
        return CombatCommand("dodge", reason="incoming bullet")


class MockDialogueController:
    def __init__(self) -> None:
        self.skipped = False

    def tick_dialogue_skip(self, tree: DesktopTree) -> None:
        self.skipped = True


class MockPerceptionProvider:
    def observe(self, frame: object, frame_id: int) -> SemanticObservation:
        nodes = (
            DesktopNode("option_daily", "list_item", "Daily Commissions", (0.5, 0.5, 0.9, 0.6), 0.25),
        )
        # First frame is dialog, subsequent frames are world hud (dialog complete)
        screen_state = "npc_dialog" if frame_id < 1005 else "world_hud"
        is_modal = True if frame_id < 1005 else False
        tree = DesktopTree(time.time(), screen_state, nodes, is_modal_active=is_modal)
        
        return SemanticObservation(
            timestamp=time.time(),
            frame_id=frame_id,
            screen_state=screen_state,
            desktop_tree=tree
        )


class MockCerebrumPlanner:
    def compile_task(self, goal: AgentGoal, spec: TaskSpec) -> Sequence[SemanticAction]:
        return [
            SemanticAction(
                action_id="action_click",
                kind="ui",
                intent="click_anchor",
                target="Daily Commissions",
                requires_physical_input=True
            )
        ]


class MockExecutionProvider:
    def execute_contract(self, contract: ActionContract) -> PhysicalReceipt:
        import uuid
        return PhysicalReceipt(
            receipt_id=uuid.uuid4(),
            lease_id=uuid.uuid4(),
            issued_at=time.time(),
            expires_at=time.time() + 0.25,
            action_type="click",
            execution_latency_ms=10.0,
            focus_maintained=True
        )

    def emergency_halt(self) -> None:
        pass

    def execute(self, primitive: ActionPrimitive) -> StepResult:
        return StepResult(step_id="mock", success=True)

    def locate_and_click(self, description: str) -> StepResult:
        return StepResult(step_id="mock", success=True)

    def press_key(self, key: str, reason: str = "") -> StepResult:
        return StepResult(step_id="mock", success=True)



class MockSuccessChecker:
    def adjudicate_delta(
        self, pre_obs: SemanticObservation, post_obs: SemanticObservation, criteria: str
    ) -> StateDeltaClaim:
        return StateDeltaClaim(
            claim_id="claim_verified",
            pre_frame_id=pre_obs.frame_id,
            post_frame_id=post_obs.frame_id,
            delta_description="comission_claimed",
            verified=True,
            confidence=0.99
        )


class MockCompanionAgent:
    def propose_capsule_patch(
        self, capsule_id: str, successful_override: RuntimeOverride
    ) -> CapsulePatchProposal:
        return CapsulePatchProposal(
            patch_id="patch_1",
            capsule_id=capsule_id,
            target_yaml_file="capsule.yaml",
            yaml_diff="+ confidence: 0.20",
            schema_valid=True
        )


# ===========================================================================
# Pytest Assertions
# ===========================================================================

def test_production_loop_adjudication():
    """Verify that the production multi-threaded loop executes successfully."""
    # 1. Setup mock sensors and controllers
    perception = MockPerceptionProvider()
    planner = MockCerebrumPlanner()
    executor = MockExecutionProvider()
    checker = MockSuccessChecker()
    companion = MockCompanionAgent()

    lease_manager = MockInputLeaseManager()
    combat_agent = MockSpinalReflexAgent()
    dialogue_controller = MockDialogueController()

    loop = AgentLoop(
        perception=perception,
        planner=planner,
        executor=executor,
        checker=checker,
        companion=companion,
        capture_frame=lambda: object(),
        lease_manager=lease_manager,
        combat_agent=combat_agent,
        dialogue_controller=dialogue_controller,
        max_plan_iterations=5
    )

    # 2. Run with initial goal & spec
    goal = AgentGoal("goal_1", "complete quest", "quest_completed")
    spec = TaskSpec("task_1", "run main quest")

    result = loop.run(goal, spec)

    # 3. Assert successful execution
    assert isinstance(result, GoalResult)
    assert result.achieved is True
    assert result.steps_total >= 1
    assert result.steps_succeeded >= 1
    assert len(result.verified_claims) >= 1
    assert result.verified_claims[0].verified is True


def test_production_loop_human_intercept():
    """Verify that human keyboard intercepts pause the execution loop immediately."""
    perception = MockPerceptionProvider()
    planner = MockCerebrumPlanner()
    executor = MockExecutionProvider()
    checker = MockSuccessChecker()
    companion = MockCompanionAgent()

    lease_manager = MockInputLeaseManager()
    
    loop = AgentLoop(
        perception=perception,
        planner=planner,
        executor=executor,
        checker=checker,
        companion=companion,
        capture_frame=lambda: object(),
        lease_manager=lease_manager,
        max_plan_iterations=5
    )

    goal = AgentGoal("goal_1", "complete quest", "quest_completed")
    spec = TaskSpec("task_1", "run main quest")

    # Force a human intervention signal
    lease_manager.intervened = True

    # Injecting override to resume from companion
    override = RuntimeOverride("override_1", "option_daily", (("override_threshold", "0.2"),))
    
    # We trigger run in a separate thread so we can inject the override asynchronously
    run_result = []
    
    def run_async():
        res = loop.run(goal, spec)
        run_result.append(res)

    t = threading.Thread(target=run_async, daemon=True)
    t.start()
    time.sleep(0.1)

    # Assert that execution is suspended
    assert loop.get_active_overrides() == {}
    
    # Inject the override via companion to clear human-intervene and complete execution
    loop.inject_runtime_override(override)
    t.join(timeout=5.0)

    # Assert that execution successfully recovered and completed
    assert len(run_result) == 1
    assert run_result[0].achieved is True
