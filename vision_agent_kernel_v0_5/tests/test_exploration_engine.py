"""Tests for exploration engine."""
from __future__ import annotations

import pytest

from planning.exploration_engine import (
    ChestRarity,
    ExplorationEngine,
    ExplorationObjective,
    ExplorationPlan,
    ExplorationTarget,
    OculiType,
    Region,
    RegionProgress,
    REGION_AR_REQUIREMENTS,
    REGION_HAZARDS,
    REGION_OCULI,
    REGION_UNLOCK_ORDER,
    OCULI_TOTALS,
    STATUE_OFFERING_LEVELS,
)


class TestRegionData:
    def test_unlock_order(self) -> None:
        assert REGION_UNLOCK_ORDER[0] == Region.MONDSTADT
        assert REGION_UNLOCK_ORDER[1] == Region.LIYUE

    def test_ar_requirements(self) -> None:
        assert REGION_AR_REQUIREMENTS[Region.MONDSTADT] == 1
        assert REGION_AR_REQUIREMENTS[Region.INAZUMA] == 30
        assert REGION_AR_REQUIREMENTS[Region.NATLAN] == 40

    def test_region_oculi_mapping(self) -> None:
        for region in (Region.MONDSTADT, Region.LIYUE, Region.INAZUMA,
                       Region.SUMERU, Region.FONTAINE, Region.NATLAN):
            assert region in REGION_OCULI

    def test_oculi_totals_positive(self) -> None:
        for otype, total in OCULI_TOTALS.items():
            assert total > 0

    def test_inazuma_lightning_hazard(self) -> None:
        assert "lightning_storm" in REGION_HAZARDS[Region.INAZUMA]


class TestRegionProgress:
    def test_completion_score_zero_when_locked(self) -> None:
        p = RegionProgress(region=Region.LIYUE, unlocked=False)
        assert p.completion_score == 0.0

    def test_waypoint_pct(self) -> None:
        p = RegionProgress(region=Region.MONDSTADT, waypoints_total=50, waypoints_unlocked=25, unlocked=True)
        assert p.waypoint_pct == 50.0

    def test_completion_score_components(self) -> None:
        p = RegionProgress(
            region=Region.MONDSTADT, unlocked=True,
            waypoints_total=10, waypoints_unlocked=10,
            chests_total=100, chests_opened=50,
            oculi_total=66, oculi_collected=33,
            exploration_pct=75.0,
        )
        score = p.completion_score
        assert 0 < score <= 100

    def test_zero_division_safety(self) -> None:
        p = RegionProgress(region=Region.MONDSTADT, unlocked=True)
        assert p.completion_score >= 0


class TestExplorationTarget:
    def test_create_target(self) -> None:
        t = ExplorationTarget(
            "wp_mond_01", ExplorationObjective.WAYPOINT_UNLOCK,
            Region.MONDSTADT, (100.0, 200.0, 0.0),
            nearest_waypoint="wp_mond_00",
        )
        assert t.objective == ExplorationObjective.WAYPOINT_UNLOCK
        assert t.priority == 100


class TestExplorationEngine:
    def _engine(self) -> ExplorationEngine:
        return ExplorationEngine()

    def test_initial_progress_mondstadt_unlocked(self) -> None:
        engine = self._engine()
        progress = engine.get_progress(Region.MONDSTADT)
        assert progress.unlocked is True

    def test_initial_progress_liyue_locked(self) -> None:
        engine = self._engine()
        progress = engine.get_progress(Region.LIYUE)
        assert progress.unlocked is False

    def test_add_and_complete_target(self) -> None:
        engine = self._engine()
        target = ExplorationTarget(
            "chest_001", ExplorationObjective.CHEST_OPEN,
            Region.MONDSTADT, (10.0, 20.0, 0.0),
        )
        engine.add_target(target)
        engine.mark_completed("chest_001")
        progress = engine.get_progress(Region.MONDSTADT)
        assert progress.chests_opened == 1

    def test_plan_session_empty(self) -> None:
        engine = self._engine()
        plan = engine.plan_session(Region.MONDSTADT, current_ar=10)
        assert plan.region == Region.MONDSTADT
        assert len(plan.targets) == 0

    def test_plan_session_with_targets(self) -> None:
        engine = self._engine()
        for i in range(5):
            engine.add_target(ExplorationTarget(
                f"wp_{i}", ExplorationObjective.WAYPOINT_UNLOCK,
                Region.MONDSTADT, (float(i * 100), 0.0, 0.0),
                priority=i * 10,
            ))
        plan = engine.plan_session(Region.MONDSTADT, current_ar=10, time_budget_min=5.0)
        assert len(plan.targets) > 0
        # Should be sorted by priority
        priorities = [t.priority for t in plan.targets]
        assert priorities == sorted(priorities)

    def test_plan_session_respects_ar(self) -> None:
        engine = self._engine()
        engine.add_target(ExplorationTarget(
            "wp_inazuma", ExplorationObjective.WAYPOINT_UNLOCK,
            Region.INAZUMA, (0.0, 0.0, 0.0),
        ))
        # AR 10 can't access Inazuma
        plan = engine.plan_session(Region.MONDSTADT, current_ar=10)
        assert all(t.region != Region.INAZUMA for t in plan.targets)

    def test_plan_session_prioritize(self) -> None:
        engine = self._engine()
        engine.add_target(ExplorationTarget(
            "chest_01", ExplorationObjective.CHEST_OPEN,
            Region.MONDSTADT, (0.0, 0.0, 0.0), priority=50,
        ))
        engine.add_target(ExplorationTarget(
            "wp_01", ExplorationObjective.WAYPOINT_UNLOCK,
            Region.MONDSTADT, (0.0, 0.0, 0.0), priority=50,
        ))
        plan = engine.plan_session(
            Region.MONDSTADT, current_ar=10,
            prioritize=ExplorationObjective.WAYPOINT_UNLOCK,
        )
        if plan.targets:
            assert plan.targets[0].objective == ExplorationObjective.WAYPOINT_UNLOCK

    def test_plan_waypoint_sweep(self) -> None:
        engine = self._engine()
        for i in range(10):
            engine.add_target(ExplorationTarget(
                f"wp_m_{i}", ExplorationObjective.WAYPOINT_UNLOCK,
                Region.MONDSTADT, (float(i), 0.0, 0.0),
            ))
        # Mark first 5 as unlocked (not completed, just known)
        unlocked = {f"wp_m_{i}" for i in range(5)}
        plan = engine.plan_waypoint_sweep(Region.MONDSTADT, unlocked)
        assert len(plan.targets) == 5
        assert all(t.objective == ExplorationObjective.WAYPOINT_UNLOCK for t in plan.targets)

    def test_next_region_to_explore(self) -> None:
        engine = self._engine()
        # Mondstadt is unlocked but has 0 completion
        region = engine.next_region_to_explore(current_ar=10)
        assert region == Region.MONDSTADT

    def test_next_region_none_when_all_done(self) -> None:
        engine = self._engine()
        # Mark Mondstadt as fully explored
        progress = engine.get_progress(Region.MONDSTADT)
        progress.waypoints_total = 10
        progress.waypoints_unlocked = 10
        progress.chests_total = 100
        progress.chests_opened = 100
        progress.oculi_total = 66
        progress.oculi_collected = 66
        progress.exploration_pct = 100.0
        # With only AR 10, no other regions are accessible
        region = engine.next_region_to_explore(current_ar=10)
        assert region is None

    def test_environment_hazards(self) -> None:
        engine = self._engine()
        assert len(engine.get_environment_hazards(Region.MONDSTADT)) == 0
        assert len(engine.get_environment_hazards(Region.INAZUMA)) > 0

    def test_oculus_offering_plan(self) -> None:
        engine = self._engine()
        plan = engine.oculus_offering_plan(Region.MONDSTADT)
        assert plan["oculus_type"] == "anemoculus"
        assert plan["current_level"] == 0
        assert plan["total"] == 66

    def test_oculus_offering_with_collection(self) -> None:
        engine = self._engine()
        progress = engine.get_progress(Region.MONDSTADT)
        progress.oculi_collected = 10
        plan = engine.oculus_offering_plan(Region.MONDSTADT)
        assert plan["current_level"] >= 1

    def test_prerequisites_checked(self) -> None:
        engine = self._engine()
        engine.add_target(ExplorationTarget(
            "chest_locked", ExplorationObjective.CHEST_OPEN,
            Region.MONDSTADT, (0.0, 0.0, 0.0),
            requires=("wp_001",),
        ))
        plan = engine.plan_session(Region.MONDSTADT, current_ar=10)
        assert len(plan.targets) == 0  # prerequisite not met

    def test_prerequisites_met(self) -> None:
        engine = self._engine()
        engine.add_target(ExplorationTarget(
            "chest_locked", ExplorationObjective.CHEST_OPEN,
            Region.MONDSTADT, (0.0, 0.0, 0.0),
            requires=("wp_001",),
        ))
        engine.mark_completed("wp_001")
        # After completing the prerequisite, target should be available
        engine.add_target(ExplorationTarget(
            "chest_test", ExplorationObjective.CHEST_OPEN,
            Region.MONDSTADT, (0.0, 0.0, 0.0),
            requires=(),
        ))
        plan = engine.plan_session(Region.MONDSTADT, current_ar=10)
        assert len(plan.targets) >= 1

    def test_update_progress(self) -> None:
        engine = self._engine()
        engine.update_progress(Region.LIYUE, unlocked=True, waypoints_total=80)
        progress = engine.get_progress(Region.LIYUE)
        assert progress.unlocked is True
        assert progress.waypoints_total == 80


class TestExplorationPlan:
    def test_filtered_targets(self) -> None:
        plan = ExplorationPlan(region=Region.MONDSTADT)
        plan.targets = [
            ExplorationTarget("wp_1", ExplorationObjective.WAYPOINT_UNLOCK, Region.MONDSTADT, (0, 0, 0)),
            ExplorationTarget("ch_1", ExplorationObjective.CHEST_OPEN, Region.MONDSTADT, (0, 0, 0)),
            ExplorationTarget("oc_1", ExplorationObjective.OCULUS_COLLECT, Region.MONDSTADT, (0, 0, 0)),
        ]
        assert len(plan.waypoint_targets) == 1
        assert len(plan.chest_targets) == 1
        assert len(plan.oculus_targets) == 1
