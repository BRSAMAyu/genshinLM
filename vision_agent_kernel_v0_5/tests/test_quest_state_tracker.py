from __future__ import annotations

import pytest

from planning.goal_stack import GoalStack
from planning.quest_tracker import QuestStateTracker, QuestState
from planning.screen_state_claim import ScreenStateClaim, UIElementClaim


class TestQuestAndGoalStack:
    def test_goal_stack_ordering_and_duplication(self):
        stack = GoalStack()
        assert stack.size == 0

        # Push elements
        stack.push("claim_reward")
        stack.push("open_menu")
        assert stack.size == 2
        assert stack.peek() == "open_menu"

        # Push duplicate -> moves duplicate to top (LIFO cycle prevention)
        stack.push("claim_reward")
        assert stack.size == 2
        assert stack.peek() == "claim_reward"

        # Pop element
        top = stack.pop()
        assert top == "claim_reward"
        assert stack.peek() == "open_menu"
        assert stack.size == 1

        stack.clear()
        assert stack.size == 0

    def test_quest_tracker_ocr_parsing(self):
        tracker = QuestStateTracker()

        # Test English pattern
        claim = ScreenStateClaim(
            game_id="genshin",
            screen_state="overworld",
            confidence=0.9,
            source="ocr",
            raw_ocr_texts=("Quest: Talk to Katheryne", "Genshin Impact"),
        )
        state = tracker.update_state(claim)
        assert state.active_quest_id != "unknown"
        assert state.objective_text == "Talk to Katheryne"
        assert not state.is_blocked
        assert state.active_quest_id == QuestStateTracker().update_state(claim).active_quest_id

        # Test Chinese pattern
        claim_zh = ScreenStateClaim(
            game_id="genshin",
            screen_state="overworld",
            confidence=0.9,
            source="ocr",
            raw_ocr_texts=("任务: 调查遗迹", "委托任务"),
        )
        state_zh = tracker.update_state(claim_zh)
        assert state_zh.objective_text == "调查遗迹"

    def test_quest_tracker_stuck_blocked_detection(self):
        tracker = QuestStateTracker()

        claim = ScreenStateClaim(
            game_id="genshin",
            screen_state="overworld",
            confidence=0.9,
            source="ocr",
            raw_ocr_texts=("Quest: Go to marker", "stuck in obstacle"),
        )
        state = tracker.update_state(claim)
        assert state.objective_text == "Go to marker"
        assert state.is_blocked
        assert state.failure_count == 1

        # Push another claim where it's still blocked -> failure_count increments
        claim_blocked_again = ScreenStateClaim(
            game_id="genshin",
            screen_state="overworld",
            confidence=0.9,
            source="ocr",
            raw_ocr_texts=("Quest: Go to marker", "stuck"),
        )
        state_updated = tracker.update_state(claim_blocked_again)
        assert state_updated.is_blocked
        assert state_updated.failure_count == 2

    def test_quest_tracker_vlm_scene_description_fallback(self):
        """L3: When OCR has no quest keywords, extract objective from VLM scene_description."""
        tracker = QuestStateTracker()

        claim = ScreenStateClaim(
            game_id="genshin",
            screen_state="overworld",
            confidence=0.85,
            source="vlm",
            raw_ocr_texts=("Genshin Impact", "HP: 100%"),
            scene_description="The quest objective is reach the teleport waypoint",
        )
        state = tracker.update_state(claim)
        assert state.objective_text != ""
        assert "waypoint" in state.objective_text.lower() or "teleport" in state.objective_text.lower()
        assert state.active_quest_id != "unknown"

    def test_quest_tracker_chinese_no_colon_pattern(self):
        """L4: Chinese 委托/追踪 pattern without colon (e.g. '委托 寻找失踪的旅行者')."""
        tracker = QuestStateTracker()

        claim = ScreenStateClaim(
            game_id="genshin",
            screen_state="overworld",
            confidence=0.9,
            source="ocr",
            raw_ocr_texts=("委托 寻找失踪的旅行者",),
        )
        state = tracker.update_state(claim)
        assert state.objective_text != ""
        # The no-colon pattern captures text after 委托 + whitespace
        assert "寻找失踪的旅行者" in state.objective_text

    def test_quest_tracker_no_false_positive_for_cannot_miss(self):
        """M4 regression: 'cannot miss' should NOT trigger is_blocked."""
        tracker = QuestStateTracker()

        claim = ScreenStateClaim(
            game_id="genshin",
            screen_state="overworld",
            confidence=0.9,
            source="ocr",
            raw_ocr_texts=("Quest: Find the star", "you cannot miss it"),
        )
        state = tracker.update_state(claim)
        assert state.objective_text == "Find the star"
        assert not state.is_blocked

    def test_goal_stack_to_list_and_len(self):
        """L5: to_list() returns correct ordered snapshot bottom→top; size matches."""
        stack = GoalStack()
        assert stack.to_list() == []
        assert stack.size == 0

        stack.push("main_quest")
        stack.push("sub_quest")
        stack.push("sub_sub_quest")

        snapshot = stack.to_list()
        assert len(snapshot) == 3
        assert stack.size == len(snapshot)
        # Last pushed should be last in list (top of stack)
        assert snapshot[-1] == "sub_sub_quest"
        assert snapshot[0] == "main_quest"

        # to_list() is a copy — mutating doesn't affect stack
        snapshot.clear()
        assert stack.size == 3
