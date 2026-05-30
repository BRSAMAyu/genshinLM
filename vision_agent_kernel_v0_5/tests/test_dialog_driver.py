"""Tests for interaction/dialog_driver.py: conditional dialog + affection system."""
from __future__ import annotations

from interaction.dialog_branch_analyzer import ConsequenceTracker
from interaction.dialog_driver import (
    AffectionDialogManager,
    AffectionLevel,
    ConditionalDialogSelector,
    DialogCondition,
    NpcRelationship,
)


class TestConditionalDialogSelector:
    def test_no_conditions_uses_analyzer(self):
        selector = ConditionalDialogSelector()
        idx = selector.select_choice(["No thanks", "当然可以"])
        assert idx == 1

    def test_quest_active_condition_met(self):
        selector = ConditionalDialogSelector()
        selector.update_quest_state("q001", "active")
        cond = DialogCondition(condition_type="quest_active", key="q001")
        idx = selector.select_choice(
            ["Skip quest dialog", "Talk about quest"],
            conditions=[None, cond],
            context={"quest_id": "q001", "npc_name": "npc"},
        )
        assert idx == 1

    def test_quest_condition_not_met_falls_back(self):
        selector = ConditionalDialogSelector()
        cond = DialogCondition(condition_type="quest_active", key="q999")
        idx = selector.select_choice(
            ["Generic option", "Quest option"],
            conditions=[cond],
        )
        assert idx == 0  # Falls back since condition not met

    def test_item_condition(self):
        selector = ConditionalDialogSelector()
        selector.update_inventory({"windwheel_aster", "dandelion"})
        cond = DialogCondition(condition_type="item_owned", key="dandelion")
        idx = selector.select_choice(
            ["No item response", "Give dandelion"],
            conditions=[None, cond],
        )
        assert idx == 1

    def test_affection_condition(self):
        selector = ConditionalDialogSelector()
        selector.update_affection("katheryne", 5)
        cond = DialogCondition(condition_type="affection_level", key="katheryne", value=3)
        idx = selector.select_choice(
            ["Normal greeting", "Close friend dialog"],
            conditions=[None, cond],
        )
        assert idx == 1

    def test_empty_choices(self):
        selector = ConditionalDialogSelector()
        assert selector.select_choice([]) == 0

    def test_prefers_accept_among_viable(self):
        selector = ConditionalDialogSelector()
        # Both viable but second has accept keyword
        idx = selector.select_choice(
            ["Maybe later", "当然接受"],
            conditions=[None, None],
        )
        assert idx == 1


class TestNpcRelationship:
    def test_stranger_level(self):
        rel = NpcRelationship(npc_name="amber")
        assert rel.level == AffectionLevel.STRANGER

    def test_acquaintance_level(self):
        rel = NpcRelationship(npc_name="amber", affection=25)
        assert rel.level == AffectionLevel.ACQUAINTANCE

    def test_friend_level(self):
        rel = NpcRelationship(npc_name="amber", affection=50)
        assert rel.level == AffectionLevel.FRIEND

    def test_trusted_level(self):
        rel = NpcRelationship(npc_name="amber", affection=90)
        assert rel.level == AffectionLevel.TRUSTED


class TestAffectionDialogManager:
    def test_on_dialog_increases_affection(self):
        mgr = AffectionDialogManager()
        mgr.on_dialog("amber")
        rel = mgr.get_or_create("amber")
        assert rel.affection == 2
        assert rel.dialog_count == 1

    def test_on_quest_complete_large_boost(self):
        mgr = AffectionDialogManager()
        mgr.on_quest_complete("katheryne")
        rel = mgr.get_or_create("katheryne")
        assert rel.affection == 10

    def test_on_gift(self):
        mgr = AffectionDialogManager()
        mgr.on_gift("zhongli")
        rel = mgr.get_or_create("zhongli")
        assert rel.affection == 5

    def test_affection_capped_at_100(self):
        mgr = AffectionDialogManager()
        for _ in range(30):
            mgr.on_quest_complete("npc")
        rel = mgr.get_or_create("npc")
        assert rel.affection == 100

    def test_is_unlocked(self):
        mgr = AffectionDialogManager()
        assert not mgr.is_unlocked("amber", AffectionLevel.FRIEND)
        for _ in range(10):
            mgr.on_quest_complete("amber")
        assert mgr.is_unlocked("amber", AffectionLevel.FRIEND)

    def test_get_level(self):
        mgr = AffectionDialogManager()
        assert mgr.get_level("npc") == AffectionLevel.STRANGER
        mgr.on_quest_complete("npc")
        mgr.on_quest_complete("npc")
        assert mgr.get_level("npc") == AffectionLevel.ACQUAINTANCE

    def test_get_all_relationships(self):
        mgr = AffectionDialogManager()
        mgr.on_dialog("a")
        mgr.on_dialog("b")
        all_rels = mgr.get_all_relationships()
        assert "a" in all_rels
        assert "b" in all_rels
