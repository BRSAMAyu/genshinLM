"""Tests for the strategic decision engine."""
from __future__ import annotations

from planning.daily_loop_scheduler import (
    ActionCategory,
    DailySchedule,
    FailureAnalyzer,
    FailureDiagnosis,
    GamePhase,
    GameStateSnapshot,
    StrategicDecisionEngine,
    determine_phase,
)


class TestPhaseDetermination:
    def test_early(self) -> None:
        assert determine_phase(1) == GamePhase.EARLY
        assert determine_phase(29) == GamePhase.EARLY

    def test_mid(self) -> None:
        assert determine_phase(30) == GamePhase.MID
        assert determine_phase(44) == GamePhase.MID

    def test_late(self) -> None:
        assert determine_phase(45) == GamePhase.LATE
        assert determine_phase(54) == GamePhase.LATE

    def test_endgame(self) -> None:
        assert determine_phase(55) == GamePhase.ENDGAME
        assert determine_phase(60) == GamePhase.ENDGAME


class TestStrategicDecisionEngine:
    def _engine(self) -> StrategicDecisionEngine:
        return StrategicDecisionEngine()

    def test_commissions_always_first(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(adventure_rank=10, daily_commissions_done=False)
        schedule = engine.evaluate(state)
        assert schedule.actions[0].category == ActionCategory.COMMISSIONS
        assert schedule.phase == GamePhase.EARLY

    def test_commissions_skip_when_done(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(daily_commissions_done=True)
        schedule = engine.evaluate(state)
        cats = [a.category for a in schedule.actions]
        assert ActionCategory.COMMISSIONS not in cats

    def test_early_game_resin_to_boss(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(adventure_rank=15, resin_current=80, daily_commissions_done=True)
        schedule = engine.evaluate(state)
        resin_actions = [a for a in schedule.actions if a.category == ActionCategory.RESIN_SPEND]
        assert len(resin_actions) == 1
        assert "boss" in resin_actions[0].target.lower()

    def test_mid_game_resin_to_domains(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(adventure_rank=35, resin_current=80, daily_commissions_done=True)
        schedule = engine.evaluate(state)
        resin_actions = [a for a in schedule.actions if a.category == ActionCategory.RESIN_SPEND]
        assert len(resin_actions) == 1
        assert "domain" in resin_actions[0].target.lower()

    def test_late_game_resin_to_artifacts(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(adventure_rank=48, resin_current=80, daily_commissions_done=True)
        schedule = engine.evaluate(state)
        resin_actions = [a for a in schedule.actions if a.category == ActionCategory.RESIN_SPEND]
        assert len(resin_actions) == 1
        assert "artifact" in resin_actions[0].target.lower()

    def test_weekly_boss_on_reset(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(is_weekly_reset_day=True, weekly_bosses_done=1)
        schedule = engine.evaluate(state)
        boss_actions = [a for a in schedule.actions if a.category == ActionCategory.COMBAT_BOSS]
        assert len(boss_actions) == 1
        assert boss_actions[0].resin_cost == 60  # 2 remaining * 30

    def test_no_weekly_boss_when_all_done(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(is_weekly_reset_day=True, weekly_bosses_done=3)
        schedule = engine.evaluate(state)
        boss_actions = [a for a in schedule.actions if a.category == ActionCategory.COMBAT_BOSS]
        assert len(boss_actions) == 0

    def test_weapon_upgrade_recommendation(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(
            adventure_rank=30,
            daily_commissions_done=True,
            main_dps_level=60,
            main_dps_weapon_level=20,
        )
        schedule = engine.evaluate(state)
        build_actions = [a for a in schedule.actions if a.category == ActionCategory.CHARACTER_BUILD]
        assert len(build_actions) >= 1
        assert any("weapon" in a.target for a in build_actions)

    def test_archon_quest_included(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(
            adventure_rank=25,
            main_dps_level=40,
            daily_commissions_done=True,
            resin_current=0,
        )
        schedule = engine.evaluate(state)
        quest_actions = [a for a in schedule.actions if a.category == ActionCategory.QUEST_ARCHON]
        assert len(quest_actions) >= 1

    def test_actions_sorted_by_priority(self) -> None:
        engine = self._engine()
        state = GameStateSnapshot(adventure_rank=35)
        schedule = engine.evaluate(state)
        priorities = [a.priority for a in schedule.actions]
        assert priorities == sorted(priorities)


class TestFailureAnalyzer:
    def _analyzer(self) -> FailureAnalyzer:
        return FailureAnalyzer()

    def test_weapon_underleveled(self) -> None:
        analyzer = self._analyzer()
        state = GameStateSnapshot(main_dps_level=70, main_dps_weapon_level=40)
        diag = analyzer.diagnose(state, boss_level=60)
        assert diag.likely_cause == "undergeared"
        assert diag.should_retreat is True
        assert diag.should_retry is False

    def test_level_gap_too_large(self) -> None:
        analyzer = self._analyzer()
        state = GameStateSnapshot(main_dps_level=40, main_dps_weapon_level=40)
        diag = analyzer.diagnose(state, boss_level=80)
        assert diag.likely_cause == "undergeared"
        assert diag.should_retreat is True

    def test_one_shot_death(self) -> None:
        analyzer = self._analyzer()
        state = GameStateSnapshot(main_dps_level=70, main_dps_weapon_level=70)
        diag = analyzer.diagnose(state, boss_level=70, death_cause="one_shot_burst")
        assert diag.likely_cause == "mechanics"
        assert diag.should_retry is True
        assert diag.should_retreat is False

    def test_repeated_failures(self) -> None:
        analyzer = self._analyzer()
        state = GameStateSnapshot(main_dps_level=70, main_dps_weapon_level=70)
        diag = analyzer.diagnose(state, boss_level=70, attempts=3)
        assert diag.likely_cause == "team_comp"
        assert diag.should_retreat is True

    def test_default_retry(self) -> None:
        analyzer = self._analyzer()
        state = GameStateSnapshot(main_dps_level=70, main_dps_weapon_level=70)
        diag = analyzer.diagnose(state, boss_level=70, attempts=1)
        assert diag.should_retry is True
        assert diag.should_retreat is False
