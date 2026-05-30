"""Tests for quest enhancement and dialog system."""
from __future__ import annotations

import pytest

from planning.quest_enhancement import (
    AR_BREAKTHROUGH_CONFIGS,
    ARCHON_NPC_PATTERNS,
    DialogChoice,
    DialogSession,
    DialogStrategy,
    EscortConfig,
    QuestLog,
    QuestMarkerColor,
    QuestMechanic,
    QuestMechanismRouter,
    QuestObjective,
    StealthConfig,
    TimedChallengeConfig,
    choose_dialog_option,
)


class TestQuestObjective:
    def test_create_objective(self) -> None:
        obj = QuestObjective("obj_001", "Talk to Katheryne", QuestMechanic.DIALOG)
        assert obj.mechanic == QuestMechanic.DIALOG
        assert obj.marker_color == QuestMarkerColor.YELLOW

    def test_timed_objective(self) -> None:
        obj = QuestObjective(
            "obj_002", "Collect 5 items", QuestMechanic.TIMED,
            time_limit_sec=60.0,
        )
        assert obj.time_limit_sec == 60.0


class TestQuestLog:
    def _log(self) -> QuestLog:
        return QuestLog()

    def test_add_and_track(self) -> None:
        ql = self._log()
        obj = QuestObjective("q1", "Test quest", QuestMechanic.NAVIGATION)
        ql.add_quest(obj)
        ql.track("q1")
        assert ql.tracked_quest_id == "q1"
        assert ql.get_tracked() == obj

    def test_complete_removes_from_active(self) -> None:
        ql = self._log()
        ql.add_quest(QuestObjective("q1", "Test", QuestMechanic.DIALOG))
        ql.track("q1")
        ql.complete_quest("q1")
        assert "q1" in ql.completed_quests
        assert ql.get_tracked() is None
        assert ql.tracked_quest_id is None

    def test_fail_objective_counter(self) -> None:
        ql = self._log()
        ql.fail_objective("obj_1")
        ql.fail_objective("obj_1")
        assert ql.failed_objectives["obj_1"] == 2

    def test_should_abandon(self) -> None:
        ql = self._log()
        for _ in range(3):
            ql.fail_objective("obj_1")
        assert ql.should_abandon("obj_1")

    def test_should_not_abandon_early(self) -> None:
        ql = self._log()
        ql.fail_objective("obj_1")
        assert not ql.should_abandon("obj_1")

    def test_get_by_mechanic(self) -> None:
        ql = self._log()
        ql.add_quest(QuestObjective("q1", "Fight", QuestMechanic.COMBAT))
        ql.add_quest(QuestObjective("q2", "Talk", QuestMechanic.DIALOG))
        ql.add_quest(QuestObjective("q3", "Sneak", QuestMechanic.STEALTH))
        combat = ql.get_by_mechanic(QuestMechanic.COMBAT)
        assert len(combat) == 1
        assert combat[0].objective_id == "q1"

    def test_empty_tracked(self) -> None:
        ql = self._log()
        assert ql.get_tracked() is None


class TestDialogChoice:
    def test_choose_first(self) -> None:
        choices = [
            DialogChoice("Option A", 0),
            DialogChoice("Option B", 1),
        ]
        result = choose_dialog_option(choices, DialogStrategy.FIRST_OPTION)
        assert result is not None
        assert result.text == "Option A"

    def test_choose_progression(self) -> None:
        choices = [
            DialogChoice("Tell me more", 0, is_flavor=True),
            DialogChoice("Let's go!", 1, is_progression=True),
        ]
        result = choose_dialog_option(choices, DialogStrategy.PROGRESSION_FIRST)
        assert result is not None
        assert result.is_progression

    def test_choose_skip(self) -> None:
        choices = [
            DialogChoice("More info", 0, is_flavor=True),
            DialogChoice("Goodbye", 1),
        ]
        result = choose_dialog_option(choices, DialogStrategy.SKIP_ALL)
        assert result is not None
        assert result.text == "More info"

    def test_choose_empty(self) -> None:
        assert choose_dialog_option([]) is None

    def test_choose_default_strategy(self) -> None:
        choices = [DialogChoice("A", 0), DialogChoice("B", 1)]
        result = choose_dialog_option(choices)
        assert result is not None


class TestDialogSession:
    def test_record_choice(self) -> None:
        session = DialogSession(npc_name="Katheryne")
        session.record_choice(DialogChoice("OK", 0, is_progression=True))
        assert session.turns == 1
        assert len(session.choices_made) == 1

    def test_key_choices_tracked(self) -> None:
        session = DialogSession()
        session.record_choice(DialogChoice("Flavor", 0, is_flavor=True))
        session.record_choice(DialogChoice("Important", 1, is_branch_point=True))
        assert len(session.key_choices) == 1

    def test_should_skip_after_many_turns(self) -> None:
        session = DialogSession(auto_play_enabled=True)
        for i in range(6):
            session.record_choice(DialogChoice(f"Choice {i}", i))
        assert session.should_skip()

    def test_should_not_skip_few_turns(self) -> None:
        session = DialogSession(auto_play_enabled=True)
        session.record_choice(DialogChoice("Hi", 0))
        assert not session.should_skip()


class TestStealthConfig:
    def test_defaults(self) -> None:
        cfg = StealthConfig()
        assert cfg.detection_radius_px > 0
        assert cfg.safe_distance_px > cfg.detection_radius_px


class TestEscortConfig:
    def test_defaults(self) -> None:
        cfg = EscortConfig()
        assert cfg.follow_distance_px > 0
        assert cfg.heal_npc_threshold > 0


class TestARBreakthroughConfigs:
    def test_all_ar_levels(self) -> None:
        for ar in (25, 35, 45, 50):
            assert ar in AR_BREAKTHROUGH_CONFIGS
            cfg = AR_BREAKTHROUGH_CONFIGS[ar]
            assert len(cfg.recommended_team) == 4


class TestNPCPatterns:
    def test_katheryne_exists(self) -> None:
        assert "katheryne_mondstadt" in ARCHON_NPC_PATTERNS

    def test_all_have_locations(self) -> None:
        for npc in ARCHON_NPC_PATTERNS.values():
            assert npc.location != ""


class TestQuestMechanismRouter:
    def _router(self) -> QuestMechanismRouter:
        return QuestMechanismRouter()

    def test_all_mechanics_have_handlers(self) -> None:
        router = self._router()
        for mech in QuestMechanic:
            handler = router.get_handler(mech)
            assert handler != "generic_handler" or mech == QuestMechanic.COLLECTION

    def test_stealth_config_injected(self) -> None:
        router = self._router()
        obj = QuestObjective("s1", "Sneak past guards", QuestMechanic.STEALTH)
        config = router.get_config(obj)
        assert "stealth_config" in config

    def test_timed_config_injected(self) -> None:
        router = self._router()
        obj = QuestObjective("t1", "Collect items", QuestMechanic.TIMED, time_limit_sec=90.0)
        config = router.get_config(obj)
        assert "timed_config" in config

    def test_elemental_requirement(self) -> None:
        router = self._router()
        obj = QuestObjective("e1", "Activate monument", QuestMechanic.ELEMENTAL,
                             element_required="Anemo")
        config = router.get_config(obj)
        assert config["element_required"] == "Anemo"

    def test_difficulty_assessment(self) -> None:
        router = self._router()
        assert router.assess_difficulty(
            QuestObjective("b", "Boss", QuestMechanic.BOSS_FIGHT)
        ) == "hard"
        assert router.assess_difficulty(
            QuestObjective("d", "Talk", QuestMechanic.DIALOG)
        ) == "easy"
        assert router.assess_difficulty(
            QuestObjective("c", "Fight", QuestMechanic.COMBAT)
        ) == "moderate"
