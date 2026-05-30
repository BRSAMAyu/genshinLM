"""Tests for mainline progression components."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from knowledge.genshin_archon_quests import ARCHON_QUESTS, ArchonQuest, QuestStep
from planning.quest_state_machine import QuestStateMachine
from planning.quest_objective_detector import QuestObjectiveDetector
from interaction.dialog_branch_analyzer import DialogBranchAnalyzer
from navigation.minimap_quest_reader import MinimapQuestReader
from execution.loading_waiter import LoadingWaiter
from combat.character_switch_manager import CharacterSwitchManager
from combat.reaction_executor import ReactionExecutor


class TestQuestStateMachine:
    def test_initial_state(self):
        sm = QuestStateMachine(ARCHON_QUESTS)
        assert sm.current_step is not None
        assert sm._current_quest_idx == 0
        assert sm._current_step_idx == 0

    def test_advance(self):
        sm = QuestStateMachine(ARCHON_QUESTS)
        first = sm.current_step
        assert first is not None
        second = sm.advance(evidence="test")
        # After advancing, step should be different or None
        if second is not None:
            assert second.step_id != first.step_id

    def test_save_load_roundtrip(self):
        sm = QuestStateMachine(ARCHON_QUESTS)
        sm.advance(evidence="test1")
        sm.advance(evidence="test2")
        state = sm.save_state()
        sm2 = QuestStateMachine(ARCHON_QUESTS)
        sm2.load_state(state)
        assert sm2._current_quest_idx == sm._current_quest_idx
        assert sm2._current_step_idx == sm._current_step_idx

    def test_completed_set(self):
        sm = QuestStateMachine(ARCHON_QUESTS)
        step = sm.current_step
        assert step is not None
        sm.advance(evidence="test")
        assert step.step_id in sm._completed

    def test_is_mainline_complete(self):
        sm = QuestStateMachine(ARCHON_QUESTS)
        assert not sm.is_mainline_complete()

    def test_single_quest_chain(self):
        quest = ArchonQuest("TEST001", "测试章", "测试任务", [
            QuestStep("T01", "步骤1", objective="dialog_complete"),
            QuestStep("T02", "步骤2", objective="combat_complete"),
        ])
        sm = QuestStateMachine([quest])
        assert sm.current_step is not None
        sm.advance(evidence="test")
        sm.advance(evidence="test")
        assert sm.is_mainline_complete()


class TestDialogBranchAnalyzer:
    def test_default_first_choice(self):
        analyzer = DialogBranchAnalyzer()
        result = analyzer.analyze_choices(["普通对话", "另一个选项"], context={})
        assert result == 0

    def test_accept_keyword(self):
        analyzer = DialogBranchAnalyzer()
        result = analyzer.analyze_choices(["接受任务", "拒绝"], context={"is_mainline": True})
        assert result == 0  # "接受" should be preferred

    def test_empty_options(self):
        analyzer = DialogBranchAnalyzer()
        result = analyzer.analyze_choices([], context={})
        assert result == 0


class TestMinimapQuestReader:
    def test_no_marker_on_black_frame(self):
        reader = MinimapQuestReader()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = reader.read_quest_direction(frame)
        assert result is None

    def test_has_quest_marker_black_frame(self):
        reader = MinimapQuestReader()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        assert not reader.has_quest_marker(frame)


class TestReactionExecutor:
    def test_available_reactions(self):
        reactions = ReactionExecutor.available_reactions(["pyro", "hydro", "anemo", "cryo"])
        assert "vaporize" in reactions
        assert "melt" in reactions

    def test_no_reactions_single_element(self):
        reactions = ReactionExecutor.available_reactions(["pyro"])
        assert reactions == []

    def test_available_reactions_overloaded(self):
        reactions = ReactionExecutor.available_reactions(["electro", "pyro", "hydro", "dendro"])
        assert "overloaded" in reactions


class TestCharacterSwitchManager:
    def test_invalid_slot(self):
        class MockBackend:
            def key_press(self, key, reason=""):
                pass
        mgr = CharacterSwitchManager(MockBackend())
        assert not mgr.switch_to(0)
        assert not mgr.switch_to(5)


class TestArchonQuestData:
    def test_archon_quests_not_empty(self):
        assert len(ARCHON_QUESTS) > 0

    def test_each_quest_has_steps(self):
        for quest in ARCHON_QUESTS:
            assert len(quest.steps) > 0, f"Quest {quest.quest_id} has no steps"

    def test_step_ids_unique(self):
        all_ids = set()
        for quest in ARCHON_QUESTS:
            for step in quest.steps:
                assert step.step_id not in all_ids, f"Duplicate step_id: {step.step_id}"
                all_ids.add(step.step_id)
