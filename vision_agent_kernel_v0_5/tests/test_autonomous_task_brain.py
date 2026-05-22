"""Tests for the generic autonomous task planning system."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from agent.autonomous_task_brain import AutonomousTaskBrain, TaskBrainConfig
from core.state_bus import StateBus
from learning.decision_memory import DecisionMemory, DecisionQuery
from planning.action_affordance import AffordanceDeriver
from planning.hierarchical_planner import HierarchicalPlanner, PlannerConfig, PlanResult
from planning.mission_graph_v3 import MissionGraph, MissionGraphBuilder, MissionNode
from planning.screen_state_claim import (
    ActionAffordance,
    PlayerStatusClaim,
    ScreenStateClaim,
    TaskStateSnapshot,
    UIElementClaim,
)
from planning.screen_state_claim_builder import (
    ClassifierOutput,
    OcrOutput,
    ScreenStateClaimBuilder,
    VLMOutput,
)
from runtime.claim_worker import ClaimGraphWorker


# ---------------------------------------------------------------------------
# ScreenStateClaim
# ---------------------------------------------------------------------------


class TestScreenStateClaim:
    def test_actionable_elements_filters_by_role(self):
        claim = ScreenStateClaim(
            game_id="hsr", screen_state="menu", confidence=0.9, source="vlm",
            ui_elements=(
                UIElementClaim("btn1", "button", "Start", (0.1, 0.2, 0.3, 0.1), 0.9, "vlm"),
                UIElementClaim("txt1", "text", "Label", (0.1, 0.4, 0.3, 0.1), 0.8, "vlm"),
                UIElementClaim("quest1", "quest_entry", "Daily", (0.1, 0.6, 0.3, 0.1), 0.85, "ocr"),
            ),
        )
        actionable = claim.actionable_elements()
        assert len(actionable) == 2
        assert actionable[0].element_id == "btn1"
        assert actionable[1].element_id == "quest1"

    def test_find_element_by_role(self):
        claim = ScreenStateClaim(
            game_id="hsr", screen_state="dialog", confidence=0.9, source="vlm",
            ui_elements=(
                UIElementClaim("dlg1", "dialog_option", "Accept", (0.1, 0.5, 0.3, 0.1), 0.9, "vlm"),
            ),
        )
        found = claim.find_element("dialog_option")
        assert found is not None
        assert found.text == "Accept"

    def test_find_elements_by_text_keyword(self):
        claim = ScreenStateClaim(
            game_id="genshin", screen_state="menu", confidence=0.9, source="vlm",
            ui_elements=(
                UIElementClaim("q1", "quest_text", "每日委托", (0.1, 0.2, 0.3, 0.1), 0.9, "ocr"),
                UIElementClaim("q2", "quest_text", "Weekly Boss", (0.1, 0.4, 0.3, 0.1), 0.9, "ocr"),
            ),
        )
        results = claim.find_elements_by_text("每日")
        assert len(results) == 1
        assert results[0].text == "每日委托"


# ---------------------------------------------------------------------------
# AffordanceDeriver
# ---------------------------------------------------------------------------


class TestAffordanceDeriver:
    def test_overworld_affordances(self):
        claim = ScreenStateClaim(
            game_id="genshin", screen_state="overworld", confidence=0.9, source="vlm",
            interaction_prompt="F - Talk",
        )
        deriver = AffordanceDeriver()
        actions = deriver.derive(claim)
        types = {a.action_type for a in actions}
        assert "move" in types
        assert "interact" in types
        assert "open_menu" in types

    def test_dialog_affordances(self):
        claim = ScreenStateClaim(
            game_id="hsr", screen_state="dialog", confidence=0.9, source="vlm",
            ui_elements=(
                UIElementClaim("opt1", "dialog_option", "Accept quest", (0.1, 0.5, 0.3, 0.1), 0.9, "vlm"),
            ),
        )
        deriver = AffordanceDeriver()
        actions = deriver.derive(claim)
        dialog_actions = [a for a in actions if a.action_type in ("advance_dialog", "select_option")]
        assert len(dialog_actions) >= 1

    def test_reward_screen_affordances(self):
        claim = ScreenStateClaim(
            game_id="hsr", screen_state="reward_screen", confidence=0.9, source="vlm",
        )
        deriver = AffordanceDeriver()
        actions = deriver.derive(claim)
        types = {a.action_type for a in actions}
        assert "claim_reward" in types
        assert "claim_all" in types

    def test_element_button_becomes_affordance(self):
        claim = ScreenStateClaim(
            game_id="hsr", screen_state="menu", confidence=0.9, source="vlm",
            ui_elements=(
                UIElementClaim("b1", "button", "领取奖励", (0.1, 0.2, 0.3, 0.1), 0.95, "ocr"),
            ),
        )
        deriver = AffordanceDeriver()
        actions = deriver.derive(claim)
        claim_actions = [a for a in actions if a.target_label == "领取奖励"]
        assert len(claim_actions) == 1
        assert claim_actions[0].action_type == "claim_reward"

    def test_sp_precondition_checked(self):
        claim = ScreenStateClaim(
            game_id="hsr", screen_state="turn_based_combat", confidence=0.9, source="vlm",
            player_status=PlayerStatusClaim(skill_points=0),
        )
        deriver = AffordanceDeriver()
        actions = deriver.derive(claim)
        skill_actions = [a for a in actions if a.action_type == "skill"]
        assert len(skill_actions) == 0

    def test_sp_sufficient_allows_skill(self):
        claim = ScreenStateClaim(
            game_id="hsr", screen_state="turn_based_combat", confidence=0.9, source="vlm",
            player_status=PlayerStatusClaim(skill_points=3),
        )
        deriver = AffordanceDeriver()
        actions = deriver.derive(claim)
        skill_actions = [a for a in actions if a.action_type == "skill"]
        assert len(skill_actions) >= 1


# ---------------------------------------------------------------------------
# MissionGraph
# ---------------------------------------------------------------------------


class TestMissionGraph:
    def test_build_linear_graph(self):
        graph = MissionGraphBuilder.from_decomposition("claim rewards", "hsr", [
            {"label": "Open menu", "semantic_action": "open_menu", "expected_state": "menu"},
            {"label": "Navigate to rewards", "semantic_action": "navigate_to", "target": "rewards"},
            {"label": "Claim all", "semantic_action": "claim_all"},
        ])
        assert graph.goal == "claim rewards"
        assert len(graph.nodes) == 5  # root + 3 steps + verify
        assert graph.root_node_id in graph.nodes
        root = graph.node(graph.root_node_id)
        assert root.node_type == "goal"

    def test_next_pending_returns_first_unfinished(self):
        graph = MissionGraphBuilder.from_decomposition("test", "hsr", [
            {"label": "Step 1", "semantic_action": "open_menu"},
            {"label": "Step 2", "semantic_action": "claim_reward"},
        ])
        first = graph.next_pending()
        assert first is not None
        assert "Step 1" in first.label or first.semantic_action == "open_menu"

    def test_progress_tracking(self):
        graph = MissionGraphBuilder.from_decomposition("test", "hsr", [
            {"label": "Step 1", "semantic_action": "observe"},
        ])
        done, total = graph.progress()
        assert done == 0
        assert total == 3  # root + step + verify

    def test_is_complete_when_all_terminal(self):
        graph = MissionGraphBuilder.from_decomposition("test", "hsr", [
            {"label": "Step 1", "semantic_action": "observe"},
        ])
        for node in graph.nodes.values():
            node.status = "completed"
        assert graph.is_complete()

    def test_to_dict_serializes(self):
        graph = MissionGraphBuilder.from_decomposition("test", "hsr", [
            {"label": "Step 1", "semantic_action": "observe"},
        ])
        d = graph.to_dict()
        assert d["goal"] == "test"
        assert "nodes" in d
        assert "edges" in d


# ---------------------------------------------------------------------------
# ScreenStateClaimBuilder
# ---------------------------------------------------------------------------


class TestScreenStateClaimBuilder:
    def test_fuses_vlm_and_classifier(self):
        builder = ScreenStateClaimBuilder()
        claim = builder.build(
            game_id="hsr",
            frame_id=1,
            vlm=VLMOutput(
                screen_state="menu",
                player_status={"health": "full"},
                visible_objects=[],
                ui_elements={"interaction_prompt": "Click to claim"},
                scene_description="Menu screen",
                suggested_action="click",
                raw_text="...",
            ),
            classifier=ClassifierOutput(screen_state="menu", confidence=0.95, source="hsv"),
        )
        assert claim.screen_state == "menu"
        assert claim.confidence >= 0.8
        assert claim.source == "hybrid"
        assert len(claim.ui_elements) >= 1

    def test_builds_from_ocr(self):
        builder = ScreenStateClaimBuilder()
        claim = builder.build(
            game_id="hsr",
            frame_id=2,
            ocr_results=[
                OcrOutput("领取奖励", 0.95, (0.1, 0.2, 0.3, 0.1), "paddle"),
                OcrOutput("F - 交互", 0.9, (0.4, 0.5, 0.2, 0.08), "paddle"),
            ],
        )
        texts = {e.text for e in claim.ui_elements}
        assert "领取奖励" in texts
        assert claim.interaction_prompt == "F - 交互"

    def test_no_inputs_returns_unknown(self):
        builder = ScreenStateClaimBuilder()
        claim = builder.build(game_id="hsr", frame_id=3)
        assert claim.screen_state == "unknown"
        assert claim.confidence < 0.5


# ---------------------------------------------------------------------------
# HierarchicalPlanner
# ---------------------------------------------------------------------------


class TestHierarchicalPlanner:
    def test_builds_plan_from_mock_llm(self):
        fake_response = {
            "choices": [{"message": {"content": json.dumps({
                "reasoning": "Simple reward claim",
                "steps": [
                    {"label": "Open menu", "node_type": "action", "semantic_action": "open_menu"},
                    {"label": "Navigate to rewards", "node_type": "action", "semantic_action": "navigate_to"},
                    {"label": "Claim", "node_type": "action", "semantic_action": "claim_reward"},
                ],
                "estimated_duration_sec": 30,
                "complexity": "simple",
                "confidence": 0.85,
            })}}],
        }
        config = PlannerConfig(api_key="test_key")
        planner = HierarchicalPlanner(config=config)
        with patch.object(planner, "_call_llm", return_value=fake_response):
            claim = ScreenStateClaim(game_id="hsr", screen_state="overworld", confidence=0.9, source="vlm")
            result = planner.plan("claim daily rewards", "hsr", claim)
            assert result.confidence == 0.85
            assert result.complexity == "simple"
            assert len(result.graph.nodes) >= 4  # root + 3 steps + verify

    def test_fallback_on_llm_failure(self):
        config = PlannerConfig(api_key="test_key")
        planner = HierarchicalPlanner(config=config)
        with patch.object(planner, "_call_llm", side_effect=RuntimeError("API down")):
            claim = ScreenStateClaim(game_id="hsr", screen_state="unknown", confidence=0.5, source="vlm")
            result = planner.plan("test goal", "hsr", claim)
            assert result.confidence == 0.3
            assert "fallback" in result.reasoning.lower() or "Fallback" in result.reasoning

    def test_missing_api_key_uses_local_fallback_without_network(self):
        config = PlannerConfig(api_key="")
        planner = HierarchicalPlanner(config=config)
        with patch.object(planner, "_call_llm", side_effect=AssertionError("network should not be called")):
            claim = ScreenStateClaim(game_id="hsr", screen_state="menu", confidence=0.8, source="classifier")
            result = planner.plan("claim reward", "hsr", claim)
            assert result.confidence == 0.3
            assert result.raw_text == "fallback"


# ---------------------------------------------------------------------------
# DecisionMemory
# ---------------------------------------------------------------------------


class TestDecisionMemory:
    def test_record_and_query(self):
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmpdir, "test_memory.db")
            memory = DecisionMemory(db_path=db_path)
            sid = memory.record(
                goal="claim daily rewards",
                capsule_id="hsr",
                screen_state="menu",
                plan=[{"label": "Open menu", "semantic_action": "open_menu"}],
                success=True,
                duration_sec=15.0,
                confidence=0.9,
            )
            assert "hsr:" in sid
            results = memory.query(DecisionQuery(goal="daily", capsule_id="hsr"))
            assert len(results) == 1
            assert results[0].success
            memory.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_best_strategy_picks_highest_confidence(self):
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmpdir, "test_memory.db")
            memory = DecisionMemory(db_path=db_path)
            memory.record("claim rewards", "hsr", "menu", [], True, 20.0, confidence=0.7)
            memory.record("claim rewards", "hsr", "menu", [], True, 10.0, confidence=0.95)
            best = memory.best_strategy_for("claim rewards", "hsr")
            assert best is not None
            assert best.confidence == 0.95
            memory.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_success_rate_calculation(self):
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmpdir, "test_memory.db")
            memory = DecisionMemory(db_path=db_path)
            memory.record("goal", "hsr", "menu", [], True, 10.0)
            memory.record("goal", "hsr", "menu", [], True, 10.0)
            memory.record("goal", "hsr", "menu", [], False, 10.0)
            rate = memory.success_rate(capsule_id="hsr")
            assert abs(rate - 2 / 3) < 0.01
            memory.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_stats_empty_db(self):
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmpdir, "empty.db")
            memory = DecisionMemory(db_path=db_path)
            stats = memory.stats()
            assert stats.total_records == 0
            assert stats.success_rate == 0.0
            memory.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TaskStateSnapshot
# ---------------------------------------------------------------------------


class TestTaskStateSnapshot:
    def test_safe_actions_filters_high_risk(self):
        snap = TaskStateSnapshot(
            claim=ScreenStateClaim(game_id="hsr", screen_state="shop", confidence=0.9, source="vlm"),
            available_actions=(
                ActionAffordance("a1", "buy", "item", 0.8, risk_level="high"),
                ActionAffordance("a2", "go_back", "close", 0.9, risk_level="low"),
                ActionAffordance("a3", "navigate", "item", 0.7, risk_level="medium"),
            ),
        )
        safe = snap.safe_actions()
        assert len(safe) == 2
        assert all(a.risk_level != "high" for a in safe)

    def test_has_action_type(self):
        snap = TaskStateSnapshot(
            claim=ScreenStateClaim(game_id="hsr", screen_state="menu", confidence=0.9, source="vlm"),
            available_actions=(
                ActionAffordance("a1", "navigate_menu", "item", 0.8),
            ),
        )
        assert snap.has_action_type("navigate_menu")
        assert not snap.has_action_type("attack")


# ---------------------------------------------------------------------------
# AutonomousTaskBrain claim-gated execution
# ---------------------------------------------------------------------------


class _NoopPerception:
    def capture_frame(self):
        return np.zeros((10, 10, 3), dtype=np.uint8)

    def analyze_vlm(self, frame, game_id):
        return None

    def classify_screen(self, frame):
        return None

    def ocr_scan(self, frame):
        return []


class _RecordingExecutor:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple[str, str]] = []

    def execute_semantic(self, action: str, target: str, context: dict[str, object]) -> bool:
        self.calls.append((action, target))
        return self.ok

    def is_target_focused(self) -> bool:
        return True


class TestAutonomousTaskBrainClaimGate:
    def _brain(self, claim_worker: ClaimGraphWorker | None = None) -> AutonomousTaskBrain:
        return AutonomousTaskBrain(
            _NoopPerception(),
            _RecordingExecutor(),
            TaskBrainConfig(capsule_id="hsr", game_id="hsr", record_strategies=False),
            claim_worker=claim_worker,
        )

    def test_boolean_executor_success_without_evidence_does_not_complete_node(self):
        brain = self._brain()
        brain._current_claim = ScreenStateClaim(
            game_id="hsr", screen_state="unknown", confidence=0.3, source="unknown", frame_id=1,
        )
        node = MissionNode("n1", "verify", "Verify reward", semantic_action="claim_reward", verifier="reward_claimed")
        assert not brain._execute_node(node, [])

    def test_terminal_node_requires_claim_adjudication_evidence(self):
        worker = ClaimGraphWorker()
        brain = self._brain(worker)
        brain._current_graph = MissionGraphBuilder.from_decomposition("claim reward", "hsr", [
            {"label": "Open menu", "semantic_action": "open_menu"},
        ])
        brain._current_claim = ScreenStateClaim(
            game_id="hsr", screen_state="menu", confidence=0.9, source="classifier", frame_id=7,
        )
        node = MissionNode("n2", "verify", "Verify menu", semantic_action="observe", verifier="screen_state")
        assert brain._execute_node(node, [])
        snapshot = worker.snapshot()
        assert snapshot["claim_count"] == 1
        assert "verified" in set(snapshot["claims"].values())

    def test_state_bus_receives_task_state_snapshot(self):
        bus = StateBus()
        brain = AutonomousTaskBrain(
            _NoopPerception(),
            _RecordingExecutor(),
            TaskBrainConfig(capsule_id="hsr", game_id="hsr", record_strategies=False),
            state_bus=bus,
        )
        brain._current_claim = ScreenStateClaim(
            game_id="hsr", screen_state="menu", confidence=0.9, source="classifier", frame_id=1,
        )
        brain._publish_task_state(())
        slot = bus.get_slot("agent.task_state_snapshot")
        assert slot is not None
        assert slot.get().claim.screen_state == "menu"
