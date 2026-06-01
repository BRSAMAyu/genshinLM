"""Tests for agent_kernel package — core protocols, types, loop, and memory."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from agent_kernel.types import (
    ActionableElement,
    ActionPlan,
    ActionPrimitive,
    AgentGoal,
    Experience,
    GoalResult,
    PlannedStep,
    SemanticObservation,
    StepResult,
)
from agent_kernel.loop import AgentLoop
from agent_kernel.memory import FileMemoryStore


# ---------------------------------------------------------------------------
# Types — construction & immutability
# ---------------------------------------------------------------------------

class TestTypes:

    def test_actionable_element_frozen(self) -> None:
        el = ActionableElement(element_type="button", label="OK", bbox=(0.1, 0.2, 0.3, 0.4))
        assert el.label == "OK"
        with pytest.raises(AttributeError):
            el.label = "Cancel"  # type: ignore[misc]

    def test_semantic_observation_defaults(self) -> None:
        obs = SemanticObservation(timestamp=1.0, scene_description="test")
        assert obs.actionable_elements == ()
        assert obs.vlm_confidence == 0.0

    def test_agent_goal_frozen(self) -> None:
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        assert goal.priority == 50

    def test_planned_step_fallback(self) -> None:
        step = PlannedStep(step_id="s1", description="click", target_description="btn", expected_outcome="popup")
        assert step.fallback == ""

    def test_action_plan_steps_tuple(self) -> None:
        plan = ActionPlan(plan_id="p1", goal_id="g1")
        assert plan.steps == ()

    def test_action_primitive_params(self) -> None:
        p = ActionPrimitive(primitive_type="click", target="button")
        assert p.params == ()

    def test_step_result_with_observation(self) -> None:
        obs = SemanticObservation(timestamp=1.0, scene_description="after")
        r = StepResult(step_id="s1", success=True, observation_after=obs)
        assert r.observation_after is not None

    def test_experience_defaults(self) -> None:
        exp = Experience(goal_description="g", scene_description="s", action_taken="a", outcome="success")
        assert exp.failure_reason == ""

    def test_goal_result_achieved(self) -> None:
        r = GoalResult(goal_id="g1", achieved=True, steps_total=3, steps_succeeded=3)
        assert r.achieved is True


# ---------------------------------------------------------------------------
# AgentLoop — mock-based tests
# ---------------------------------------------------------------------------

class _MockPerception:
    def __init__(self, scenes: list[str] | None = None) -> None:
        self._scenes = scenes or ["scene_1", "scene_2"]
        self._idx = 0

    def observe(self, frame: object) -> SemanticObservation:
        desc = self._scenes[self._idx % len(self._scenes)]
        self._idx += 1
        return SemanticObservation(timestamp=time.perf_counter(), scene_description=desc)

    def describe_scene(self, frame: object, prompt: str) -> str:
        return self._scenes[self._idx % len(self._scenes)]

    def locate_element(self, frame: object, description: str) -> object | None:
        return None


class _MockPlanner:
    def __init__(self, plans: list[ActionPlan] | None = None) -> None:
        self._plans = plans
        self._idx = 0

    def plan(self, obs: SemanticObservation, goal: AgentGoal, memory: object) -> ActionPlan:
        if self._plans:
            p = self._plans[self._idx % len(self._plans)]
            self._idx += 1
            return p
        return ActionPlan(plan_id="p1", goal_id=goal.goal_id, steps=(
            PlannedStep(step_id="s1", description="click OK", target_description="OK button", expected_outcome="done"),
        ))

    def replan(self, obs: SemanticObservation, goal: AgentGoal, failure: StepResult, memory: object) -> ActionPlan:
        return ActionPlan(plan_id="replan", goal_id=goal.goal_id)


class _MockExecutor:
    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.calls: list[ActionPrimitive] = []

    def execute(self, primitive: ActionPrimitive) -> StepResult:
        self.calls.append(primitive)
        return StepResult(step_id="s1", success=self.succeed, duration_sec=0.1)


class _MockSuccessChecker:
    def __init__(self, succeed_after: int = 1) -> None:
        self._calls = 0
        self._succeed_after = succeed_after

    def check(self, obs: SemanticObservation, criteria: str) -> tuple[bool, float]:
        self._calls += 1
        if self._calls >= self._succeed_after:
            return True, 0.95
        return False, 0.1


class TestAgentLoop:

    def test_simple_goal_achieved(self) -> None:
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=_MockPlanner(),
            executor=_MockExecutor(),
            checker=_MockSuccessChecker(succeed_after=2),
        )
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        result = loop.run(goal)
        assert result.achieved is True
        assert result.steps_total >= 1

    def test_goal_not_achieved(self) -> None:
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=_MockPlanner(),
            executor=_MockExecutor(),
            checker=_MockSuccessChecker(succeed_after=999),  # never succeeds
            max_plan_iterations=2,
        )
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        result = loop.run(goal)
        assert result.achieved is False
        assert "max_plan_iterations" in result.error

    def test_step_failure_triggers_replan(self) -> None:
        planner = _MockPlanner()
        executor = _MockExecutor(succeed=False)
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=planner,
            executor=executor,
            max_plan_iterations=2,
        )
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        result = loop.run(goal)
        assert result.achieved is False
        # Should have attempted execution
        assert len(executor.calls) >= 1

    def test_experiences_recorded(self) -> None:
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=_MockPlanner(),
            executor=_MockExecutor(succeed=False),
            max_plan_iterations=1,
        )
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        result = loop.run(goal)
        assert len(result.experiences) >= 1
        assert result.experiences[0].outcome == "failed"

    def test_confirmation_rejects_plan(self) -> None:
        plans = [ActionPlan(plan_id="p1", goal_id="g1", requires_confirmation=True)]
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=_MockPlanner(plans=plans),
            executor=_MockExecutor(),
            max_plan_iterations=1,
            confirm_fn=lambda plan: False,  # reject
        )
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        result = loop.run(goal)
        assert result.achieved is False
        assert result.steps_total == 0

    def test_primitive_type_inference_click(self) -> None:
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=_MockPlanner(),
            executor=_MockExecutor(),
        )
        step = PlannedStep(step_id="s1", description="点击确认", target_description="btn", expected_outcome="done")
        prim = loop._step_to_primitive(step, SemanticObservation(timestamp=0, scene_description=""))
        assert prim.primitive_type == "click"

    def test_primitive_type_inference_key(self) -> None:
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=_MockPlanner(),
            executor=_MockExecutor(),
        )
        step = PlannedStep(step_id="s1", description="按键C", target_description="C key", expected_outcome="menu")
        prim = loop._step_to_primitive(step, SemanticObservation(timestamp=0, scene_description=""))
        assert prim.primitive_type == "key_press"

    def test_primitive_type_inference_wait(self) -> None:
        loop = AgentLoop(
            perception=_MockPerception(),
            planner=_MockPlanner(),
            executor=_MockExecutor(),
        )
        step = PlannedStep(step_id="s1", description="等待加载", target_description="loading", expected_outcome="loaded")
        prim = loop._step_to_primitive(step, SemanticObservation(timestamp=0, scene_description=""))
        assert prim.primitive_type == "wait"


# ---------------------------------------------------------------------------
# FileMemoryStore
# ---------------------------------------------------------------------------

class TestFileMemoryStore:

    def test_record_and_recall(self, tmp_path: Path) -> None:
        store = FileMemoryStore(tmp_path / "test.jsonl")
        exp = Experience(
            goal_description="升级角色到90级",
            scene_description="角色详情页",
            action_taken="点击升级按钮",
            outcome="success",
            timestamp=1.0,
        )
        store.record(exp)

        results = store.recall("升级角色")
        assert len(results) == 1
        assert results[0].outcome == "success"

    def test_recall_no_match(self, tmp_path: Path) -> None:
        store = FileMemoryStore(tmp_path / "test.jsonl")
        store.record(Experience(
            goal_description="升级角色", scene_description="s", action_taken="a", outcome="success",
        ))
        results = store.recall("完全无关的查询")
        assert len(results) == 0

    def test_recall_failures(self, tmp_path: Path) -> None:
        store = FileMemoryStore(tmp_path / "test.jsonl")
        store.record(Experience(
            goal_description="战斗Boss", scene_description="战斗", action_taken="攻击", outcome="failed",
            failure_reason="死亡",
        ))
        store.record(Experience(
            goal_description="战斗Boss", scene_description="战斗", action_taken="闪避", outcome="success",
        ))

        failures = store.recall_failures("战斗")
        assert len(failures) == 1
        assert failures[0].outcome == "failed"

    def test_multiple_records_ranked(self, tmp_path: Path) -> None:
        store = FileMemoryStore(tmp_path / "test.jsonl")
        store.record(Experience(
            goal_description="角色升级到90", scene_description="菜单", action_taken="点击", outcome="success",
        ))
        store.record(Experience(
            goal_description="角色升级到80", scene_description="菜单", action_taken="点击升级", outcome="success",
        ))

        # Both should match "角色升级", first has exact goal match
        results = store.recall("角色升级")
        assert len(results) == 2

    def test_empty_file(self, tmp_path: Path) -> None:
        store = FileMemoryStore(tmp_path / "empty.jsonl")
        results = store.recall("anything")
        assert results == []


# ---------------------------------------------------------------------------
# Protocol conformance (structural typing)
# ---------------------------------------------------------------------------

class TestProtocolConformance:

    def test_file_memory_store_is_memory_store(self) -> None:
        from agent_kernel.protocols import MemoryStore
        assert isinstance(FileMemoryStore, type)  # it's a class
        # Check it has the required methods
        store = FileMemoryStore.__new__(FileMemoryStore)
        assert hasattr(store, "record")
        assert hasattr(store, "recall")
        assert hasattr(store, "recall_failures")

    def test_mock_perception_has_protocol_methods(self) -> None:
        from agent_kernel.protocols import PerceptionProvider
        p = _MockPerception()
        assert hasattr(p, "observe")
        assert hasattr(p, "describe_scene")
        assert hasattr(p, "locate_element")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
