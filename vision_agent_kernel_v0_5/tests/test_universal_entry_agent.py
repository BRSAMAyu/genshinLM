"""Tests for UniversalEntryAgent."""
from __future__ import annotations

from app_service.universal_entry_agent import UniversalEntryAgent


class TestUniversalEntryAgent:
    def test_daily_commission_intent(self) -> None:
        agent = UniversalEntryAgent()
        plan = agent.process("做每日委托")
        assert plan.goal_type == "daily"
        assert len(plan.steps) >= 3

    def test_combat_intent(self) -> None:
        agent = UniversalEntryAgent()
        plan = agent.process("打boss战斗")
        assert plan.goal_type == "combat"
        assert plan.requires_combat

    def test_explore_intent(self) -> None:
        agent = UniversalEntryAgent()
        plan = agent.process("探索宝箱")
        assert plan.goal_type == "explore"
        assert plan.requires_navigation

    def test_quest_intent_english(self) -> None:
        agent = UniversalEntryAgent()
        plan = agent.process("complete main quest")
        assert plan.goal_type == "quest"

    def test_upgrade_intent(self) -> None:
        agent = UniversalEntryAgent()
        plan = agent.process("升级角色")
        assert plan.goal_type == "upgrade"
        assert not plan.requires_combat

    def test_custom_intent(self) -> None:
        agent = UniversalEntryAgent()
        plan = agent.process("random thing to do")
        assert plan.goal_type == "custom"
        assert plan.plan_id  # should have an ID

    def test_game_id_passed(self) -> None:
        agent = UniversalEntryAgent()
        plan = agent.process("daily", game_id="starrail")
        assert plan.plan_id
