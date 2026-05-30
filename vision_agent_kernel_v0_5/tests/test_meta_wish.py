"""Tests for meta-learning engine and wish/shop system."""
from __future__ import annotations

import pytest

from planning.meta_learning import (
    EnemyProfile,
    FightRecord,
    MetaLearningEngine,
    Outcome,
    StrategyAdjustment,
)
from planning.wish_shop_system import (
    HARD_PITY_5STAR,
    HARD_PITY_4STAR,
    SOFT_PITY_START,
    BannerInfo,
    PityCounter,
    WishDecisionEngine,
    WishRarity,
    WishStrategy,
)


# ---------------------------------------------------------------------------
# Meta-learning tests
# ---------------------------------------------------------------------------

class TestEnemyProfile:
    def test_win_rate_zero(self) -> None:
        p = EnemyProfile("test_enemy")
        assert p.win_rate == 0.0

    def test_win_rate_calculation(self) -> None:
        p = EnemyProfile("test_enemy", total_encounters=10, wins=7)
        assert abs(p.win_rate - 0.7) < 0.01


class TestFightRecord:
    def test_create_record(self) -> None:
        r = FightRecord("f1", "boss", "childe", ("xiangling", "bennett"),
                        Outcome.WIN, 90.0)
        assert r.outcome == Outcome.WIN
        assert r.duration_sec == 90.0


class TestMetaLearningEngine:
    def _engine(self) -> MetaLearningEngine:
        return MetaLearningEngine()

    def test_record_fight(self) -> None:
        engine = self._engine()
        engine.record_fight(FightRecord(
            "f1", "boss", "dvalin", ("amber", "kaeya"), Outcome.WIN, 60.0,
        ))
        assert engine.total_fights == 1
        profile = engine.get_profile("dvalin")
        assert profile is not None
        assert profile.total_encounters == 1
        assert profile.wins == 1

    def test_best_duration_tracking(self) -> None:
        engine = self._engine()
        engine.record_fight(FightRecord("f1", "boss", "dvalin", ("a",), Outcome.WIN, 90.0))
        engine.record_fight(FightRecord("f2", "boss", "dvalin", ("b",), Outcome.WIN, 50.0))
        profile = engine.get_profile("dvalin")
        assert profile.best_duration_sec == 50.0

    def test_best_team_updated(self) -> None:
        engine = self._engine()
        engine.record_fight(FightRecord("f1", "boss", "childe", ("xiangling",), Outcome.WIN, 60.0))
        profile = engine.get_profile("childe")
        assert profile.best_team == ("xiangling",)

    def test_pattern_learning(self) -> None:
        engine = self._engine()
        engine.record_fight(FightRecord(
            "f1", "boss", "signora", ("a",), Outcome.LOSS, 120.0,
            key_events=("cold_gauge_max", "fire_gauge_max"),
        ))
        profile = engine.get_profile("signora")
        assert "cold_gauge_max" in profile.attack_patterns_learned

    def test_analyze_empty(self) -> None:
        engine = self._engine()
        assert engine.analyze_performance() == []

    def test_analyze_low_win_rate(self) -> None:
        engine = self._engine()
        for i in range(5):
            engine.record_fight(FightRecord(
                f"f{i}", "boss", "childe", ("a",), Outcome.LOSS, 180.0,
            ))
        adjustments = engine.analyze_performance()
        assert len(adjustments) > 0
        assert any("gear_up" in a.adjustment_type or "change" in a.adjustment_type for a in adjustments)

    def test_analyze_high_deaths(self) -> None:
        engine = self._engine()
        for i in range(5):
            engine.record_fight(FightRecord(
                f"f{i}", "boss", "dvalin", ("a",), Outcome.WIN, 60.0,
                deaths=3,
            ))
        adjustments = engine.analyze_performance()
        assert any("food" in a.adjustment_type for a in adjustments)

    def test_cross_boss_knowledge(self) -> None:
        engine = self._engine()
        engine.record_fight(FightRecord(
            "f1", "boss", "childe", ("a",), Outcome.WIN, 60.0,
            key_events=("whale_attack",),
        ))
        engine.record_fight(FightRecord(
            "f2", "boss", "narwhal", ("a",), Outcome.LOSS, 120.0,
            key_events=("whale_attack", "charge"),
        ))
        result = engine.get_cross_boss_knowledge("narwhal")
        assert "source" in result

    def test_online_guide_integration(self) -> None:
        engine = self._engine()
        result = engine.get_online_guide_integration("signora")
        assert len(result["search_queries"]) > 0

    def test_profiles_accessible(self) -> None:
        engine = self._engine()
        engine.record_fight(FightRecord("f1", "boss", "dvalin", ("a",), Outcome.WIN, 60.0))
        assert "dvalin" in engine.profiles


# ---------------------------------------------------------------------------
# Pity counter tests
# ---------------------------------------------------------------------------

class TestPityCounter:
    def test_initial_state(self) -> None:
        pc = PityCounter("test")
        assert pc.pulls_until_hard_pity == HARD_PITY_5STAR
        assert not pc.is_soft_pity

    def test_record_3star(self) -> None:
        pc = PityCounter("test")
        pc.record_pull(WishRarity.THREE_STAR)
        assert pc.pulls_since_5star == 1
        assert pc.pulls_since_4star == 1

    def test_record_4star_resets(self) -> None:
        pc = PityCounter("test")
        for _ in range(9):
            pc.record_pull(WishRarity.THREE_STAR)
        assert pc.pulls_since_4star == 9
        pc.record_pull(WishRarity.FOUR_STAR)
        assert pc.pulls_since_4star == 0
        assert pc.pulls_since_5star == 10

    def test_record_5star_resets(self) -> None:
        pc = PityCounter("test")
        for _ in range(50):
            pc.record_pull(WishRarity.THREE_STAR)
        pc.record_pull(WishRarity.FIVE_STAR)
        assert pc.pulls_since_5star == 0

    def test_soft_pity(self) -> None:
        pc = PityCounter("test")
        for _ in range(74):
            pc.record_pull(WishRarity.THREE_STAR)
        assert pc.is_soft_pity

    def test_estimated_rate_increases(self) -> None:
        pc = PityCounter("test")
        base_rate = pc.estimated_5star_rate
        for _ in range(80):
            pc.record_pull(WishRarity.THREE_STAR)
        assert pc.estimated_5star_rate > base_rate

    def test_5050_tracking(self) -> None:
        pc = PityCounter("test")
        assert not pc.guaranteed_featured
        pc.record_5050_lost()
        assert pc.guaranteed_featured
        pc.record_5050_won()
        assert not pc.guaranteed_featured


# ---------------------------------------------------------------------------
# Wish decision engine tests
# ---------------------------------------------------------------------------

class TestWishDecisionEngine:
    def _engine(self, primogems: int = 0, pity: int = 0) -> WishDecisionEngine:
        engine = WishDecisionEngine(primogems=primogems)
        for _ in range(pity):
            engine.character_banner_pity.record_pull(WishRarity.THREE_STAR)
        return engine

    def test_skip_weapon_banner(self) -> None:
        engine = self._engine(primogems=16000)
        banner = BannerInfo("wpn1", "weapon", featured_5star="Staff of Homa")
        result = engine.evaluate_banner(banner)
        assert result["strategy"] == WishStrategy.SKIP

    def test_skip_standard(self) -> None:
        engine = self._engine(primogems=16000)
        banner = BannerInfo("std", "standard")
        result = engine.evaluate_banner(banner)
        assert result["strategy"] == WishStrategy.SKIP

    def test_near_pity_pull(self) -> None:
        engine = self._engine(primogems=4800, pity=70)
        banner = BannerInfo("char1", "character", featured_5star="Xiangling")
        result = engine.evaluate_banner(banner)
        assert result["strategy"] == WishStrategy.PULL_IF_NEAR_PITY

    def test_not_enough_skip(self) -> None:
        engine = self._engine(primogems=1600)  # 10 wishes only
        banner = BannerInfo("char1", "character", featured_5star="Raiden")
        result = engine.evaluate_banner(banner)
        assert result["strategy"] == WishStrategy.SKIP

    def test_monthly_shop_plan(self) -> None:
        engine = WishDecisionEngine(stardust=1000, starglitter=20)
        plan = engine.monthly_shop_plan()
        assert len(plan) > 0
        # Should include intertwined fates
        items = [p["item"] for p in plan]
        assert any("Intertwined" in item for item in items)

    def test_monthly_shop_no_stardust(self) -> None:
        engine = WishDecisionEngine(stardust=0)
        plan = engine.monthly_shop_plan()
        assert len(plan) == 0

    def test_should_buy_monthly(self) -> None:
        engine = WishDecisionEngine(stardust=100)
        assert engine.should_buy_monthly()

    def test_should_not_buy_monthly(self) -> None:
        engine = WishDecisionEngine(stardust=50)
        assert not engine.should_buy_monthly()

    def test_total_wishes_calculation(self) -> None:
        engine = WishDecisionEngine(primogems=1600, intertwined_fates=3)
        assert engine.total_wishes_available == 13  # 10 from primos + 3 fates
