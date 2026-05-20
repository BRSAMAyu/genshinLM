from __future__ import annotations

import pytest

from missions.genshin_daily_commission import (
    CommissionInfo,
    CommissionStatus,
    DailyCommissionRunner,
    DailyCommissionState,
    DailyProgress,
)
from missions.genshin_resin_manager import (
    DOMAINS,
    DomainInfo,
    DomainType,
    ResinManager,
)


# ---------------------------------------------------------------------------
# Daily Commission tests
# ---------------------------------------------------------------------------


class TestDailyCommissionInitialState:
    def test_status_not_started(self) -> None:
        runner = DailyCommissionRunner()
        assert runner.state.status == "not_started"

    def test_zero_done_initially(self) -> None:
        runner = DailyCommissionRunner()
        assert runner.state.progress.commissions_done == 0

    def test_total_four_initially(self) -> None:
        runner = DailyCommissionRunner()
        assert runner.state.progress.commissions_total == 4


class TestDailyCommissionIsComplete:
    def test_not_complete_initially(self) -> None:
        runner = DailyCommissionRunner()
        assert runner.is_complete is False


class TestDailyCommissionTickNavigating:
    def test_tick_starts_navigating(self) -> None:
        runner = DailyCommissionRunner()
        commission = CommissionInfo(
            commission_id="comm_001",
            name="Flora's Commission",
            region="mondstadt",
            waypoint_id="tp_mondstadt_city",
            commission_type="collection",
            description="Collect flowers for Flora",
            estimated_duration_ms=60000,
        )
        runner.set_commissions([commission])
        runner.start()
        assert runner.state.status == CommissionStatus.NAVIGATING.value

        action = runner.tick(dt_ms=100.0, screen_state="world_hud")
        assert action is not None
        assert action["input"] == "navigate"
        assert action["target_waypoint"] == "tp_mondstadt_city"

    def test_tick_transitions_to_in_progress(self) -> None:
        runner = DailyCommissionRunner()
        commission = CommissionInfo(
            commission_id="comm_002",
            name="Hilichurl Cleanup",
            region="mondstadt",
            waypoint_id="tp_windrise",
            commission_type="combat",
            description="Defeat hilichurls",
            estimated_duration_ms=90000,
        )
        runner.set_commissions([commission])
        runner.start()

        runner.tick(dt_ms=100.0, screen_state="world_hud")
        assert runner.state.status == CommissionStatus.IN_PROGRESS.value

    def test_tick_combat_commission(self) -> None:
        runner = DailyCommissionRunner()
        commission = CommissionInfo(
            commission_id="comm_003",
            name="Combat Test",
            region="mondstadt",
            waypoint_id="tp_mondstadt_city",
            commission_type="combat",
            description="Fight enemies",
            estimated_duration_ms=60000,
        )
        runner.set_commissions([commission])
        runner.start()
        runner.tick(dt_ms=100.0, screen_state="world_hud")

        action = runner.tick(dt_ms=100.0, screen_state="combat")
        assert action is not None
        assert action["input"] == "start_combat"

    def test_tick_danger_retreat(self) -> None:
        runner = DailyCommissionRunner()
        commission = CommissionInfo(
            commission_id="comm_004",
            name="Danger Test",
            region="mondstadt",
            waypoint_id="tp_mondstadt_city",
            commission_type="combat",
            description="Danger test",
            estimated_duration_ms=60000,
        )
        runner.set_commissions([commission])
        runner.start()
        runner.tick(dt_ms=100.0, screen_state="world_hud")

        action = runner.tick(dt_ms=100.0, screen_state="combat", danger_score=0.9)
        assert action is not None
        assert action["key"] == "escape"

    def test_advance_commission_increments_done(self) -> None:
        runner = DailyCommissionRunner()
        commissions = [
            CommissionInfo(
                commission_id=f"comm_{i}",
                name=f"Test {i}",
                region="mondstadt",
                waypoint_id="tp_mondstadt_city",
                commission_type="combat",
                description=f"Test commission {i}",
                estimated_duration_ms=30000,
            )
            for i in range(2)
        ]
        runner.set_commissions(commissions)
        runner.start()

        runner.tick(dt_ms=100.0, screen_state="world_hud")
        runner.advance_commission(success=True)

        assert runner.state.progress.commissions_done == 1
        assert runner.state.status == CommissionStatus.NAVIGATING.value

    def test_advance_all_marks_complete(self) -> None:
        runner = DailyCommissionRunner()
        commission = CommissionInfo(
            commission_id="comm_final",
            name="Final",
            region="mondstadt",
            waypoint_id="tp_mondstadt_city",
            commission_type="dialog",
            description="Final commission",
            estimated_duration_ms=30000,
        )
        runner.set_commissions([commission])
        runner.start()
        runner.tick(dt_ms=100.0, screen_state="world_hud")
        runner.advance_commission(success=True)

        assert runner.state.progress.commissions_done == 1
        assert runner.state.status == CommissionStatus.COMPLETED.value
        assert runner.is_complete is True


class TestDailyProgressDataclass:
    def test_progress_fields(self) -> None:
        p = DailyProgress(
            commissions_done=2,
            commissions_total=4,
            katheryne_visited=False,
            rewards_claimed=False,
            bonus_reward_claimed=False,
        )
        assert p.commissions_done == 2
        assert p.commissions_total == 4
        assert p.katheryne_visited is False
        assert p.rewards_claimed is False
        assert p.bonus_reward_claimed is False

    def test_progress_frozen(self) -> None:
        p = DailyProgress(1, 4, False, False, False)
        with pytest.raises(AttributeError):
            p.commissions_done = 5  # type: ignore[misc]


class TestDailyCommissionClaimRewards:
    def test_claim_rewards_sequence(self) -> None:
        runner = DailyCommissionRunner()
        rewards = runner._claim_rewards()
        assert len(rewards) == 4
        assert rewards[0]["label"] == "return_to_katheryne"
        assert rewards[1]["label"] == "talk_to_katheryne"
        assert rewards[2]["label"] == "claim_reward"
        assert rewards[3]["label"] == "close_dialog"


class TestCommissionInfoDataclass:
    def test_commission_info_fields(self) -> None:
        info = CommissionInfo(
            commission_id="test_001",
            name="Test Commission",
            region="liyue",
            waypoint_id="tp_liyue_harbor",
            commission_type="puzzle",
            description="Solve the puzzle",
            estimated_duration_ms=120000,
        )
        assert info.commission_id == "test_001"
        assert info.region == "liyue"
        assert info.commission_type == "puzzle"
        assert info.estimated_duration_ms == 120000


# ---------------------------------------------------------------------------
# Resin Manager tests
# ---------------------------------------------------------------------------


class TestResinManagerInitialResin:
    def test_default_160_resin(self) -> None:
        mgr = ResinManager()
        assert mgr.current_resin == 160

    def test_custom_initial_resin(self) -> None:
        mgr = ResinManager(current_resin=80)
        assert mgr.current_resin == 80


class TestResinPlanArtifactDomains:
    def test_160_resin_artifact_domains(self) -> None:
        mgr = ResinManager(current_resin=160)
        plan = mgr.plan_resin_usage("auto")
        assert len(plan) > 0
        assert all(d.domain_type == DomainType.ARTIFACT_DOMAIN for d in plan)

    def test_160_resin_yields_8_artifact_runs(self) -> None:
        mgr = ResinManager(current_resin=160)
        plan = mgr.plan_resin_usage("artifact")
        assert len(plan) == 8

    def test_100_resin_artifact_domains(self) -> None:
        mgr = ResinManager(current_resin=100)
        plan = mgr.plan_resin_usage("auto")
        assert all(d.domain_type == DomainType.ARTIFACT_DOMAIN for d in plan)


class TestResinPlanBossDomains:
    def test_80_resin_boss_domains(self) -> None:
        mgr = ResinManager(current_resin=80)
        plan = mgr.plan_resin_usage("auto")
        assert len(plan) > 0
        assert all(d.domain_type == DomainType.BOSS_DOMAIN for d in plan)

    def test_60_resin_boss_domains(self) -> None:
        mgr = ResinManager(current_resin=60)
        plan = mgr.plan_resin_usage("auto")
        assert all(d.domain_type == DomainType.BOSS_DOMAIN for d in plan)
        assert len(plan) == 1

    def test_80_resin_explicit_boss(self) -> None:
        mgr = ResinManager(current_resin=80)
        plan = mgr.plan_resin_usage("boss")
        assert len(plan) == 2
        assert all(d.domain_type == DomainType.BOSS_DOMAIN for d in plan)


class TestResinPlanLeylineFallback:
    def test_low_resin_leyline(self) -> None:
        mgr = ResinManager(current_resin=20)
        plan = mgr.plan_resin_usage("auto")
        assert len(plan) > 0
        assert all(d.domain_type == DomainType.LEYLINE for d in plan)

    def test_30_resin_leyline(self) -> None:
        mgr = ResinManager(current_resin=30)
        plan = mgr.plan_resin_usage("auto")
        assert all(d.domain_type == DomainType.LEYLINE for d in plan)
        assert len(plan) == 1

    def test_zero_resin_empty_plan(self) -> None:
        mgr = ResinManager(current_resin=0)
        plan = mgr.plan_resin_usage("auto")
        assert plan == []


class TestResinRecordRun:
    def test_record_run_reduces_resin(self) -> None:
        mgr = ResinManager(current_resin=160)
        mgr.record_run(20)
        assert mgr.current_resin == 140
        assert mgr.runs_done == 1

    def test_record_multiple_runs(self) -> None:
        mgr = ResinManager(current_resin=80)
        mgr.record_run(40)
        mgr.record_run(40)
        assert mgr.current_resin == 0
        assert mgr.runs_done == 2

    def test_record_run_does_not_go_negative(self) -> None:
        mgr = ResinManager(current_resin=10)
        mgr.record_run(20)
        assert mgr.current_resin == 0


class TestResinRegenTime:
    def test_regen_80_to_160(self) -> None:
        mgr = ResinManager(current_resin=80)
        hours = mgr.estimate_resin_regen_time(160)
        assert hours == pytest.approx(640.0 / 60.0)

    def test_regen_zero_to_160(self) -> None:
        mgr = ResinManager(current_resin=0)
        hours = mgr.estimate_resin_regen_time(160)
        assert hours == pytest.approx(1280.0 / 60.0)

    def test_regen_already_at_target(self) -> None:
        mgr = ResinManager(current_resin=160)
        hours = mgr.estimate_resin_regen_time(160)
        assert hours == 0.0

    def test_regen_above_target(self) -> None:
        mgr = ResinManager(current_resin=180)
        hours = mgr.estimate_resin_regen_time(160)
        assert hours == 0.0

    def test_regen_single_resin(self) -> None:
        mgr = ResinManager(current_resin=159)
        hours = mgr.estimate_resin_regen_time(160)
        assert hours == pytest.approx(8.0 / 60.0)


class TestCreateRunPlanSteps:
    def test_run_plan_correct_step_count(self) -> None:
        mgr = ResinManager(current_resin=60)
        domain = DOMAINS["midsummer_courtyard"]
        plan = mgr.create_run_plan(domain, runs=2)
        assert len(plan) == 10  # 5 steps per run * 2 runs

    def test_run_plan_step_types(self) -> None:
        mgr = ResinManager(current_resin=60)
        domain = DOMAINS["midsummer_courtyard"]
        plan = mgr.create_run_plan(domain, runs=1)
        steps = [p["step"] for p in plan]
        assert steps == [
            "navigate", "enter_domain", "complete_domain",
            "claim_rewards", "check_continue",
        ]

    def test_run_plan_navigate_has_waypoint(self) -> None:
        mgr = ResinManager(current_resin=60)
        domain = DOMAINS["midsummer_courtyard"]
        plan = mgr.create_run_plan(domain, runs=1)
        nav = plan[0]
        assert nav["target_waypoint"] == "tp_mondstadt_city"
        assert nav["domain_id"] == "midsummer_courtyard"

    def test_run_plan_claim_has_resin_cost(self) -> None:
        mgr = ResinManager(current_resin=60)
        domain = DOMAINS["midsummer_courtyard"]
        plan = mgr.create_run_plan(domain, runs=1)
        claim = plan[3]
        assert claim["resin_cost"] == 20

    def test_run_plan_auto_calculates_runs(self) -> None:
        mgr = ResinManager(current_resin=160)
        domain = DOMAINS["midsummer_courtyard"]
        plan = mgr.create_run_plan(domain)
        assert len(plan) == 40  # 8 runs * 5 steps

    def test_run_plan_boss_domain(self) -> None:
        mgr = ResinManager(current_resin=80)
        domain = DOMAINS["pyro_regisvine_domain"]
        plan = mgr.create_run_plan(domain, runs=2)
        assert len(plan) == 10
        claim = plan[3]
        assert claim["resin_cost"] == 40


class TestDomainDatabaseCompleteness:
    def test_at_least_8_domains(self) -> None:
        assert len(DOMAINS) >= 8

    def test_all_domain_types_present(self) -> None:
        types = {d.domain_type for d in DOMAINS.values()}
        assert DomainType.ARTIFACT_DOMAIN in types
        assert DomainType.TALENT_DOMAIN in types
        assert DomainType.BOSS_DOMAIN in types
        assert DomainType.LEYLINE in types

    def test_domain_info_frozen(self) -> None:
        domain = DOMAINS["midsummer_courtyard"]
        with pytest.raises(AttributeError):
            domain.name = "changed"  # type: ignore[misc]
