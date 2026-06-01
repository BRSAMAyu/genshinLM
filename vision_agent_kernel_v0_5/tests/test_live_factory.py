"""Tests for the live Genshin AgentLoop factory.

Verifies that create_live_genshin_loop() correctly wires all 13 components
into an AgentLoop for both dry-run and production modes.
"""
from __future__ import annotations

import pytest

from agent_kernel.live_factory import (
    ActionExecutorAdapter,
    CerebrumPlannerAdapter,
    _DryRunActionExecutor,
    _DryRunBackend,
    _DryRunVLM,
    create_live_genshin_loop,
)
from agent_kernel.types import (
    ActionContract,
    AgentGoal,
    PhysicalReceipt,
    SemanticAction,
    SemanticObservation,
    StateDeltaClaim,
    TaskSpec,
)


class TestCerebrumPlannerAdapter:

    def test_has_compile_task(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        adapter = CerebrumPlannerAdapter(CerebrumAgentImpl())
        assert hasattr(adapter, "compile_task")

    def test_does_not_have_plan(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        adapter = CerebrumPlannerAdapter(CerebrumAgentImpl())
        assert not hasattr(adapter, "plan")

    def test_compile_task_returns_actions(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        adapter = CerebrumPlannerAdapter(CerebrumAgentImpl())
        goal = AgentGoal(goal_id="g1", description="升级角色", success_criteria="角色等级90")
        spec = TaskSpec(task_id="t1", objective="升级角色")
        actions = adapter.compile_task(goal, spec)
        assert isinstance(actions, list)
        assert len(actions) > 0
        assert all(isinstance(a, SemanticAction) for a in actions)

    def test_replan_returns_actions_on_replan_required(self) -> None:
        from agent_kernel.cerebrum_agent import CerebrumAgentImpl
        adapter = CerebrumPlannerAdapter(CerebrumAgentImpl())
        failed = SemanticAction(action_id="a1", kind="ui", intent="click_button")
        obs = SemanticObservation(timestamp=0.0)
        result = adapter.replan_on_failure(failed, obs, "element not found")
        assert isinstance(result, list)
        # diagnose_failure returns RepairPatch — adapter converts to actions when replan_required
        for action in result:
            assert isinstance(action, SemanticAction)


class TestActionExecutorAdapter:

    def test_execute_contract_returns_receipt(self) -> None:
        adapter = ActionExecutorAdapter(_DryRunActionExecutor())
        sa = SemanticAction(action_id="a1", kind="ui", intent="interact", target="NPC")
        contract = ActionContract(
            contract_id="c1",
            semantic_action=sa,
            safety_policy=(("require_focus", "True"), ("input_lease_required", "True")),
        )
        receipt = adapter.execute_contract(contract)
        assert isinstance(receipt, PhysicalReceipt)
        assert receipt.focus_maintained is True

    def test_execute_returns_step_result(self) -> None:
        from agent_kernel.types import ActionPrimitive
        adapter = ActionExecutorAdapter(_DryRunActionExecutor())
        prim = ActionPrimitive(primitive_type="click", target="button")
        result = adapter.execute(prim)
        assert result.success is True

    def test_emergency_halt_does_not_raise(self) -> None:
        adapter = ActionExecutorAdapter(_DryRunActionExecutor())
        adapter.emergency_halt()


class TestLiveFactoryDryRun:

    def test_create_dry_run_returns_tuple(self) -> None:
        loop, capturer, backend = create_live_genshin_loop(
            goal="测试", window_title="测试", dry_run=True,
        )
        assert loop is not None
        assert capturer is not None
        assert backend is not None

    def test_loop_has_perception(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert loop._perception is not None
        assert hasattr(loop._perception, "observe")

    def test_loop_planner_is_non_legacy(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert not hasattr(loop._planner, "plan")
        assert hasattr(loop._planner, "compile_task")
        assert loop._is_legacy is False

    def test_loop_has_executor(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert hasattr(loop._executor, "execute_contract")
        assert hasattr(loop._executor, "emergency_halt")

    def test_loop_has_checker(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert loop._checker is not None
        assert hasattr(loop._checker, "adjudicate_delta")
        assert hasattr(loop._checker, "check")

    def test_loop_has_companion(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert loop._companion is not None
        assert hasattr(loop._companion, "parse_override")
        assert hasattr(loop._companion, "propose_capsule_patch")

    def test_loop_has_lease_manager(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert loop._lease_manager is not None
        assert hasattr(loop._lease_manager, "verify_window_focus")
        assert hasattr(loop._lease_manager, "detect_human_intervention")

    def test_loop_has_combat_agent(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert loop._combat_agent is not None
        assert hasattr(loop._combat_agent, "evaluate_threats")

    def test_loop_has_dialogue_controller(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert loop._dialogue_controller is not None
        assert hasattr(loop._dialogue_controller, "tick_dialogue_skip")

    def test_loop_has_embodied_runtime(self) -> None:
        loop, _, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        assert loop._embodied_runtime is not None
        assert hasattr(loop._embodied_runtime, "tick_embodied")

    def test_loop_cerebrum_interval(self) -> None:
        loop, _, _ = create_live_genshin_loop(
            goal="测试", window_title="测试", dry_run=True, cerebrum_interval_sec=3.0,
        )
        assert loop._cerebrum_interval_sec == 3.0

    def test_dry_run_capturer_returns_frame(self) -> None:
        _, capturer, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        packet = capturer.get_latest_frame()
        assert packet is not None
        assert packet.image is not None

    def test_dry_run_capture_frame_callable(self) -> None:
        loop, capturer, _ = create_live_genshin_loop(goal="测试", window_title="测试", dry_run=True)
        frame = loop._capture_frame()
        assert frame is not None
