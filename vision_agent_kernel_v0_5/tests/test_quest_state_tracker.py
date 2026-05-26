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
