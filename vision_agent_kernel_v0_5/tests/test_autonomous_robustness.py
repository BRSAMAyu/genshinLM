"""Tests for autonomous recovery, unknown-scene exploration, and per-node tracking.

Verifies:
- replan_on_failure is called on execution failure
- UnknownScene handler is attached from live_factory
- Per-node traces have real values
- Recovery actions differ from failed action (strategy change)
- Skill trust promotion after repeated verification
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from agent_kernel.types import (
    ActionContract,
    AgentGoal,
    NodeExecutionTrace,
    PhysicalReceipt,
    SemanticAction,
    SemanticObservation,
    StateDeltaClaim,
    TaskSpec,
)


def _make_receipt(action_id: str, success: bool) -> PhysicalReceipt:
    now = time.perf_counter()
    return PhysicalReceipt(
        receipt_id=uuid.uuid4(),
        lease_id=uuid.uuid4(),
        issued_at=now,
        expires_at=now + 0.25,
        action_type="click",
        execution_latency_ms=0.0,
        focus_maintained=success,
        action_id=action_id,
        status="verified" if success else "failed",
        submitted_at=now,
        lease_accepted=True,
        focus_ok=success,
        duration_ms=0.0,
    )


# Dummy numpy-like frame for capture_frame
_DUMMY_FRAME = [0] * 100


class _FailOnceExecutor:
    """Fails first action, succeeds on all subsequent (including recovery)."""

    def __init__(self) -> None:
        self._failed_once = False

    def execute_contract(self, contract: ActionContract) -> PhysicalReceipt:
        if not self._failed_once:
            self._failed_once = True
            return _make_receipt(contract.semantic_action.action_id, False)
        return _make_receipt(contract.semantic_action.action_id, True)

    def emergency_halt(self) -> None:
        pass


class _RecoveryPlanner:
    """Planner that returns recovery actions on replan_on_failure."""

    def __init__(self) -> None:
        self.replan_called = False
        self.replan_error_msg = ""

    def compile_task(self, goal: AgentGoal, spec: TaskSpec) -> tuple[SemanticAction, ...]:
        return (
            SemanticAction(action_id="action_1", kind="ui", intent="click_button", target="test"),
        )

    def replan_on_failure(
        self,
        failed_action: SemanticAction,
        observation: SemanticObservation,
        error_msg: str,
    ) -> tuple[SemanticAction, ...]:
        self.replan_called = True
        self.replan_error_msg = error_msg
        return (
            SemanticAction(
                action_id="recovery_1",
                kind="ui",
                intent="retry_with_different_strategy",
                target="alternative_target",
            ),
        )


class _AlwaysSucceedExecutor:

    def execute_contract(self, contract: ActionContract) -> PhysicalReceipt:
        return _make_receipt(contract.semantic_action.action_id, True)

    def emergency_halt(self) -> None:
        pass


class _MockPerception:

    def observe(self, frame: Any, frame_id: int = 0) -> SemanticObservation:
        return SemanticObservation(
            timestamp=time.perf_counter(),
            frame_id=frame_id,
            scene_description="test_scene",
            screen_state="overworld",
        )


class _MockChecker:

    def adjudicate_delta(
        self, pre_obs: SemanticObservation, post_obs: SemanticObservation, criteria: str,
    ) -> StateDeltaClaim:
        return StateDeltaClaim(
            claim_id=f"claim_{uuid.uuid4().hex[:8]}",
            pre_frame_id=pre_obs.frame_id,
            post_frame_id=post_obs.frame_id,
            delta_description=f"criteria={criteria}",
            verified=True,
            confidence=0.8,
            attributions=("test:",),
            timestamp=time.perf_counter(),
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_replan_on_execution_failure() -> None:
    """When execution fails, replan_on_failure is called and recovery actions run."""
    from agent_kernel.loop import AgentLoop

    planner = _RecoveryPlanner()
    executor = _FailOnceExecutor()
    loop = AgentLoop(
        perception=_MockPerception(),
        planner=planner,
        executor=executor,
        checker=_MockChecker(),
        capture_frame=lambda: _DUMMY_FRAME,
        max_plan_iterations=1,
    )
    goal = AgentGoal(goal_id="g1", description="test goal", success_criteria="test")
    spec = TaskSpec(task_id="t1", objective="test goal")
    result = loop.run(goal, spec)

    assert planner.replan_called is True
    assert result.steps_total >= 2  # original action + recovery action
    assert result.steps_succeeded >= 1  # recovery action should succeed


def test_unknown_scene_handler_attached() -> None:
    """AgentLoop from live_factory has unknown_scene_handler attached."""
    from agent_kernel.live_factory import create_live_genshin_loop

    loop, _, _ = create_live_genshin_loop(
        goal="test", window_title="test", dry_run=True,
    )
    assert loop._unknown_scene_handler is not None
    assert hasattr(loop._unknown_scene_handler, "observe_and_hypothesize")
    assert hasattr(loop._unknown_scene_handler, "probe")


def test_node_trace_has_real_values() -> None:
    """GoalResult.node_traces contains real data."""
    from agent_kernel.loop import AgentLoop

    planner = _RecoveryPlanner()
    executor = _AlwaysSucceedExecutor()
    loop = AgentLoop(
        perception=_MockPerception(),
        planner=planner,
        executor=executor,
        checker=_MockChecker(),
        capture_frame=lambda: _DUMMY_FRAME,
        max_plan_iterations=1,
    )
    goal = AgentGoal(goal_id="g2", description="test", success_criteria="test")
    spec = TaskSpec(task_id="t2", objective="test")
    result = loop.run(goal, spec)

    assert result.achieved is True
    assert len(result.node_traces) >= 1
    trace = result.node_traces[0]
    assert isinstance(trace, NodeExecutionTrace)
    assert trace.node_id == "action_1"


def test_recovery_trace_on_failure() -> None:
    """When recovery happens, recovery_trace_id is non-empty in node traces."""
    from agent_kernel.loop import AgentLoop

    planner = _RecoveryPlanner()
    executor = _FailOnceExecutor()
    loop = AgentLoop(
        perception=_MockPerception(),
        planner=planner,
        executor=executor,
        checker=_MockChecker(),
        capture_frame=lambda: _DUMMY_FRAME,
        max_plan_iterations=1,
    )
    goal = AgentGoal(goal_id="g3", description="test", success_criteria="test")
    spec = TaskSpec(task_id="t3", objective="test")
    result = loop.run(goal, spec)

    has_recovery = any(nt.recovery_trace_id for nt in result.node_traces)
    assert has_recovery, "Expected at least one node with recovery_trace_id after failure"


def test_skill_trust_promotion(tmp_path: Path) -> None:
    """Candidate skill gets promoted to 'verified' after 3 verifications."""
    from app_service.goal_executor import GoalExecutor, LearningPatchProposal
    from app_service.skill_manager import SkillStore

    profiles = tmp_path / "configs" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "default_1920x1080.json").write_text(
        '{"profile_id":"default_1920x1080","window_title":"unit","source_resolution":[1920,1080],"rois":{}}',
        encoding="utf-8",
    )
    store = SkillStore(tmp_path)
    executor_obj = GoalExecutor(tmp_path, store)

    patch = LearningPatchProposal(
        patch_id="patch_001",
        node_id="unknown_scene_observe",
        summary="Test patch",
        learned_action="probe",
        confidence=0.6,
    )

    # 1st: creates candidate with verification_count=0
    skill_id_1 = executor_obj._persist_patch_as_skill("default_1920x1080", patch)
    skill = store.get_skill(skill_id_1)
    assert skill.metadata.get("trust_level") == "candidate"
    assert skill.metadata.get("verification_count") == 0

    # 2nd: increments to 1
    skill_id_2 = executor_obj._persist_patch_as_skill("default_1920x1080", patch)
    skill = store.get_skill(skill_id_2)
    assert skill.metadata.get("verification_count") == 1

    # 3rd: increments to 2 → promoted to verified
    skill_id_3 = executor_obj._persist_patch_as_skill("default_1920x1080", patch)
    skill = store.get_skill(skill_id_3)
    assert skill.metadata.get("verification_count") == 2
    assert skill.metadata.get("trust_level") == "verified"


def test_no_blind_retry() -> None:
    """Recovery actions must differ from the failed action (strategy change)."""
    planner = _RecoveryPlanner()

    original = planner.compile_task(
        AgentGoal(goal_id="g", description="test", success_criteria="test"),
        TaskSpec(task_id="t", objective="test"),
    )[0]

    obs = SemanticObservation(timestamp=0.0)
    recovery = planner.replan_on_failure(original, obs, "execution_failed")

    assert len(recovery) >= 1
    for ra in recovery:
        strategy_changed = ra.intent != original.intent or ra.target != original.target
        assert strategy_changed, "Recovery action must differ from failed action"
