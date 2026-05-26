from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from agent.exploration_agent import ExplorationAgent, ExplorationAction
from app_service.skill_manager import RecordedEvent
from learning.evolution_engine import EvolutionEngine
from learning.skill_induction_gate import SkillInductionGate
from planning.screen_state_claim import ScreenStateClaim, UIElementClaim
from planning.skill_capability_catalog import SkillCatalogEntry
from recording.semantic_distiller import SemanticSkillDistiller


class TestExplorationAndInduction:
    @pytest.fixture
    def mock_perception(self):
        perc = MagicMock()
        perc.capture_frame.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        perc.analyze_vlm.return_value = None
        return perc

    def test_exploration_agent_fallback_ocr_goal(self, mock_perception):
        agent = ExplorationAgent(mock_perception, risk_level="medium")
        state = ScreenStateClaim(
            game_id="hsr",
            screen_state="menu",
            confidence=0.9,
            source="vlm",
            ui_elements=(
                UIElementClaim("el1", "button", "领取奖励", (0.1, 0.2, 0.3, 0.1), 0.9, "ocr"),
            ),
        )
        action = agent.explore_next_step(np.zeros((10, 10, 3)), "领取", state)
        assert action.action_type == "click_anchor"
        assert action.target == "el1"
        assert not action.requires_human_approval

    def test_exploration_agent_high_risk_approval(self, mock_perception):
        agent = ExplorationAgent(mock_perception, risk_level="high")
        state = ScreenStateClaim(
            game_id="hsr",
            screen_state="menu",
            confidence=0.9,
            source="vlm",
            ui_elements=(
                UIElementClaim("el1", "button", "领取", (0.1, 0.2, 0.3, 0.1), 0.9, "ocr"),
            ),
        )
        action = agent.explore_next_step(np.zeros((10, 10, 3)), "领取", state)
        assert action.requires_human_approval

    def test_exploration_agent_rejects_unsafe_vlm_action(self, mock_perception):
        vlm = MagicMock()
        vlm.suggested_action = "raw_mouse_move"
        vlm.ui_elements = {}
        vlm.scene_description = "unsafe direct motor command"
        vlm.screen_state = "menu"
        mock_perception.analyze_vlm.return_value = vlm

        agent = ExplorationAgent(mock_perception, risk_level="medium")
        state = ScreenStateClaim(game_id="hsr", screen_state="menu", confidence=0.9, source="vlm")
        action = agent.explore_next_step(np.zeros((10, 10, 3)), "领取", state)
        assert action.action_type == "observe"
        assert action.requires_human_approval

    def test_skill_induction_gate_success(self):
        distiller = SemanticSkillDistiller()
        engine = MagicMock(spec=EvolutionEngine)
        engine._verify_in_sandbox.return_value = True

        gate = SkillInductionGate(distiller, engine)

        events = [
            RecordedEvent(
                event_type="mouse_click",
                timestamp=100.0,
                active_window_title="hsr",
                observation_summary={},
                target_state="TRACKED",
                payload={"x": 50.0, "y": 50.0, "anchor_id": "quest_button"},
            )
        ]

        entry = gate.induce_skill_from_trace(events, "click_quest", "menu")
        assert entry is not None
        assert entry.skill_id == "click_quest"
        assert len(entry.verifiers) == 1
        assert entry.verifiers[0] == "quest_button_post_click"
        assert entry.ui_anchors == ["quest_button"]
        assert engine._verify_in_sandbox.called

    def test_skill_induction_gate_rejects_coordinate_only_trace(self):
        distiller = SemanticSkillDistiller()
        engine = MagicMock(spec=EvolutionEngine)
        engine._verify_in_sandbox.return_value = True

        gate = SkillInductionGate(distiller, engine)

        events = [
            RecordedEvent(
                event_type="mouse_click",
                timestamp=100.0,
                active_window_title="hsr",
                observation_summary={},
                target_state="TRACKED",
                payload={"x": 50.0, "y": 50.0},
            )
        ]

        entry = gate.induce_skill_from_trace(events, "click_quest", "menu")
        assert entry is None
        assert not engine._verify_in_sandbox.called

    def test_skill_induction_gate_verification_failed(self):
        distiller = SemanticSkillDistiller()
        engine = MagicMock(spec=EvolutionEngine)
        engine._verify_in_sandbox.return_value = False

        gate = SkillInductionGate(distiller, engine)

        events = [
            RecordedEvent(
                event_type="mouse_click",
                timestamp=100.0,
                active_window_title="hsr",
                observation_summary={},
                target_state="TRACKED",
                payload={"x": 50.0, "y": 50.0, "anchor_id": "quest_button"},
            )
        ]

        entry = gate.induce_skill_from_trace(events, "click_quest", "menu")
        assert entry is None
        assert engine._verify_in_sandbox.called
