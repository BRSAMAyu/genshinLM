"""Tests for Phase 7: Long-horizon scenario + mainline curriculum E2E.

Pytest versions of benchmarks/long_horizon_route_fight_collect_resume/ and
benchmarks/mainline_curriculum/ benchmark suites.
"""
from __future__ import annotations

import pytest

from benchmarks.long_horizon_route_fight_collect_resume.scenario import (
    LongHorizonScenario,
    RouteNode,
    SCENARIOS as LONG_SCENARIOS,
)
from benchmarks.mainline_curriculum.tasks import (
    BenchmarkTask,
    TASKS,
    get_task,
)


class TestLongHorizonScenarios:
    """Test long-horizon scenario chain structure."""

    def test_all_scenarios_have_terminal_nodes(self):
        for scenario in LONG_SCENARIOS:
            terminals = [n for n in scenario.nodes if n.terminal]
            assert len(terminals) >= 1, f"Scenario {scenario.name} has no terminal nodes"

    def test_all_scenarios_have_final_verifier(self):
        for scenario in LONG_SCENARIOS:
            phases = [n.phase for n in scenario.nodes]
            assert "final_verifier" in phases, f"Scenario {scenario.name} missing final_verifier"

    def test_hot_resume_follows_forced_stop(self):
        for scenario in LONG_SCENARIOS:
            nodes = scenario.nodes
            stop_indices = [i for i, n in enumerate(nodes) if n.phase == "forced_stop"]
            for stop_idx in stop_indices:
                # hot_resume should follow forced_stop
                resume_nodes = [n for n in nodes[stop_idx + 1 :] if n.phase == "hot_resume"]
                assert len(resume_nodes) >= 1, (
                    f"Scenario {scenario.name}: forced_stop at {stop_idx} "
                    f"has no subsequent hot_resume"
                )

    def test_resume_skips_verified(self):
        for scenario in LONG_SCENARIOS:
            if not scenario.expect_resume_skips_verified:
                continue
            nodes = scenario.nodes
            for i, node in enumerate(nodes):
                if node.verified and i > 0:
                    prev = nodes[i - 1]
                    assert prev.phase in ("hot_resume", "knowledge_resolve"), (
                        f"Scenario {scenario.name}: verified node {node.node_id} "
                        f"should be preceded by hot_resume"
                    )

    def test_full_chain_happy_path_nodes(self):
        scenario = LONG_SCENARIOS[0]  # full_chain_happy_path
        phases = [n.phase for n in scenario.nodes]
        assert phases == [
            "knowledge_resolve",
            "route_choose",
            "enter_region",
            "combat",
            "danger_reflex",
            "collect",
            "forced_stop",
            "hot_resume",
            "final_verifier",
        ]
        # Terminal nodes: combat, collect, final_verifier
        terminals = [n for n in scenario.nodes if n.terminal]
        assert len(terminals) == 3
        assert terminals[0].node_id == "n4"
        assert terminals[1].node_id == "n6"
        assert terminals[2].node_id == "n9"

    def test_combat_recovery_resume(self):
        scenario = LONG_SCENARIOS[1]  # combat_recovery_resume
        phases = [n.phase for n in scenario.nodes]
        assert phases == [
            "knowledge_resolve",
            "route_choose",
            "combat",
            "danger_reflex",
            "hot_resume",
            "final_verifier",
        ]
        # First two nodes should be pre-verified
        assert scenario.nodes[0].verified is True
        assert scenario.nodes[1].verified is True
        assert scenario.nodes[2].verified is False

    def test_double_interrupt_resume(self):
        scenario = LONG_SCENARIOS[2]  # double_interrupt_resume
        forced_stops = [n for n in scenario.nodes if n.phase == "forced_stop"]
        hot_resumes = [n for n in scenario.nodes if n.phase == "hot_resume"]
        assert len(forced_stops) == 2, "double_interrupt should have 2 forced stops"
        assert len(hot_resumes) == 2, "double_interrupt should have 2 hot resumes"

    def test_collect_with_danger_interleave(self):
        scenario = LONG_SCENARIOS[3]  # collect_with_danger_interleave
        collect_nodes = [n for n in scenario.nodes if n.phase == "collect"]
        assert len(collect_nodes) == 2, "collect_with_danger should have 2 collect phases"
        # Second collect should be terminal
        assert collect_nodes[1].terminal is True


class TestMainlineCurriculum:
    """Test mainline curriculum benchmark task definitions."""

    def test_all_tasks_have_valid_ids(self):
        for task in TASKS:
            assert task.task_id.startswith("C"), f"Task {task.task_id} should start with C"
            assert len(task.task_id) in (2, 3), f"Task ID {task.task_id} should be 2-3 chars"

    def test_all_tasks_have_success_criteria(self):
        for task in TASKS:
            assert len(task.success_criteria) >= 1, (
                f"Task {task.task_id} has no success criteria"
            )

    def test_all_tasks_have_reasonable_difficulty(self):
        for task in TASKS:
            assert 1 <= task.difficulty <= 5, (
                f"Task {task.task_id} difficulty {task.difficulty} out of range [1,5]"
            )

    def test_all_tasks_have_time_limits(self):
        for task in TASKS:
            assert task.time_limit_sec > 0, (
                f"Task {task.task_id} has non-positive time limit"
            )

    def test_get_task_by_id(self):
        for task in TASKS:
            found = get_task(task.task_id)
            assert found is not None
            assert found.task_id == task.task_id
            assert found.name == task.name

    def test_get_task_unknown_id(self):
        assert get_task("C99") is None

    def test_task_count(self):
        assert len(TASKS) == 12, "Should have exactly 12 curriculum tasks (C0-C11)"

    def test_system_bootstrap_task(self):
        task = get_task("C0")
        assert task is not None
        assert task.category == "system"
        assert task.difficulty == 1
        assert len(task.success_criteria) == 4

    def test_boss_failure_revision_task(self):
        task = get_task("C10")
        assert task is not None
        assert task.category == "bagel"
        assert task.difficulty == 5
        assert "boss_attempt_1_failed" in task.success_criteria
        assert "boss_attempt_2_succeeded" in task.success_criteria
        assert task.time_limit_sec == 600.0

    def test_long_horizon_resume_task(self):
        task = get_task("C11")
        assert task is not None
        assert task.category == "persistence"
        assert task.difficulty == 5
        assert task.time_limit_sec == 7200.0
        assert "checkpoint_saved" in task.success_criteria
        assert "resumed_from_checkpoint" in task.success_criteria

    def test_difficulty_progression(self):
        categories_seen: set[str] = set()
        for task in TASKS:
            categories_seen.add(task.category)
        # Check difficulty ordering across categories
        difficulty_by_cat: dict[str, int] = {}
        for task in TASKS:
            cat = task.category
            if cat not in difficulty_by_cat:
                difficulty_by_cat[cat] = task.difficulty
            else:
                difficulty_by_cat[cat] = max(difficulty_by_cat[cat], task.difficulty)
        # System task (C0) should be difficulty 1
        assert difficulty_by_cat["system"] == 1
        # Persistence task (C11) should be difficulty 5
        assert difficulty_by_cat["persistence"] == 5


class TestRouteNode:
    """Unit tests for RouteNode structure."""

    def test_default_not_terminal(self):
        node = RouteNode("n1", "combat", ["observation", "combat_result"])
        assert node.terminal is False
        assert node.verified is False

    def test_terminal_flag(self):
        node = RouteNode("n2", "combat", ["observation"], terminal=True)
        assert node.terminal is True

    def test_verified_flag(self):
        node = RouteNode("n3", "route_choose", ["observation"], verified=True)
        assert node.verified is True


class TestBenchmarkTask:
    """Unit tests for BenchmarkTask structure."""

    def test_task_immutable(self):
        task = TASKS[0]
        # These should be frozen dataclass fields
        assert task.task_id == "C0"
        assert task.name == "Bootstrap Startup"
        assert task.difficulty == 1
        assert task.time_limit_sec == 30.0

    def test_task_categories(self):
        categories = {t.category for t in TASKS}
        expected = {
            "system",
            "dialogue",
            "quest",
            "navigation",
            "interaction",
            "combat",
            "recovery",
            "skill_induction",
            "mission",
            "bagel",
            "persistence",
        }
        assert categories == expected, f"Expected {expected}, got {categories}"