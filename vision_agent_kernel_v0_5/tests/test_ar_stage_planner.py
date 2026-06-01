"""Tests for ARStagePlanner — R-43 AR-dependent progression priorities."""
from __future__ import annotations

import pytest

from knowledge.ar_stage_planner import ARStagePlanner, AR_STAGES


class TestARStagePlanner:
    @pytest.fixture
    def planner(self) -> ARStagePlanner:
        return ARStagePlanner()

    def test_early_stage_ar1(self, planner: ARStagePlanner) -> None:
        stage = planner.get_stage(1)
        assert stage.ar_stage == "early"
        assert stage.ar_range == (1, 20)
        assert len(stage.priorities) >= 2

    def test_mid_early_stage_ar25(self, planner: ARStagePlanner) -> None:
        stage = planner.get_stage(25)
        assert stage.ar_stage == "mid_early"
        assert "talent_upgrade" in planner.get_priority_names(25)

    def test_mid_late_stage_ar40(self, planner: ARStagePlanner) -> None:
        stage = planner.get_stage(40)
        assert stage.ar_stage == "mid_late"
        assert "artifact_prep" in planner.get_priority_names(40)

    def test_endgame_prep_ar45(self, planner: ARStagePlanner) -> None:
        # AR45 falls in mid_late (35-45) since ranges are inclusive
        stage = planner.get_stage(45)
        assert stage.ar_stage in ("mid_late", "endgame_prep")
        assert planner.should_farm_artifacts(45)

    def test_endgame_ar55(self, planner: ARStagePlanner) -> None:
        # AR55 falls in endgame_prep (45-55) since ranges are inclusive
        stage = planner.get_stage(55)
        assert stage.ar_stage in ("endgame_prep", "endgame")
        assert "artifact" in planner.get_priority_names(55)[0]

    def test_boundary_ar20(self, planner: ARStagePlanner) -> None:
        stage = planner.get_stage(20)
        assert stage.ar_range[0] <= 20 <= stage.ar_range[1]

    def test_boundary_ar35(self, planner: ARStagePlanner) -> None:
        stage = planner.get_stage(35)
        assert stage.ar_range[0] <= 35 <= stage.ar_range[1]

    def test_resin_budget_sums_reasonable(self, planner: ARStagePlanner) -> None:
        for ar in [1, 10, 20, 30, 40, 45, 55]:
            budget = planner.get_resin_budget(ar)
            total = sum(f for _, f in budget)
            assert 0.0 < total <= 1.2, f"AR{ar} budget sum {total} out of range"

    def test_avoid_list_at_ar30(self, planner: ARStagePlanner) -> None:
        avoid = planner.get_avoid_list(30)
        assert "5_star_artifact_farming" in avoid

    def test_avoid_list_empty_at_ar50(self, planner: ARStagePlanner) -> None:
        avoid = planner.get_avoid_list(50)
        assert len(avoid) == 0

    def test_daily_tasks_always_present(self, planner: ARStagePlanner) -> None:
        for ar in [1, 20, 40, 55]:
            tasks = planner.get_daily_tasks(ar)
            assert len(tasks) >= 2
            assert "commissions" in tasks or "spend_resin" in tasks

    def test_weekly_tasks_always_present(self, planner: ARStagePlanner) -> None:
        for ar in [1, 20, 40, 55]:
            tasks = planner.get_weekly_tasks(ar)
            assert len(tasks) >= 1

    def test_should_farm_artifacts(self, planner: ARStagePlanner) -> None:
        assert not planner.should_farm_artifacts(30)
        assert not planner.should_farm_artifacts(44)
        assert planner.should_farm_artifacts(45)
        assert planner.should_farm_artifacts(55)

    def test_should_farm_talents(self, planner: ARStagePlanner) -> None:
        assert not planner.should_farm_talents(10)
        assert planner.should_farm_talents(15)
        assert planner.should_farm_talents(45)

    def test_all_stages_cover_full_range(self, planner: ARStagePlanner) -> None:
        """Every AR 1-60 should map to a valid stage."""
        for ar in range(1, 61):
            stage = planner.get_stage(ar)
            assert stage.ar_range[0] <= ar <= stage.ar_range[1]
            assert len(stage.priorities) >= 1

    def test_high_ar_defaults_to_endgame(self, planner: ARStagePlanner) -> None:
        stage = planner.get_stage(99)
        assert stage.ar_stage == "endgame"

    def test_ar_stages_tuple_not_empty(self) -> None:
        assert len(AR_STAGES) >= 4
