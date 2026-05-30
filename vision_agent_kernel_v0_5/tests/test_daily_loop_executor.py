"""Tests for the daily loop executor (DL-01~DL-07)."""
from __future__ import annotations

import pytest

from execution.daily_loop_executor import (
    BattlePassExecutor,
    BattlePassTask,
    CommissionExecutor,
    CommissionInfo,
    DailyLoopConfig,
    DailyLoopExecutor,
    DailyLoopState,
    EventExecutor,
    EventInfo,
    ExpeditionExecutor,
    ExpeditionSlot,
    LoopPhase,
    LoopPhaseResult,
    LoopStatus,
    ResinSpendingExecutor,
    WeeklyBossExecutor,
    WeeklyBossInfo,
)
from planning.daily_loop_scheduler import GameStateSnapshot


# ---------------------------------------------------------------------------
# CommissionExecutor (DL-01)
# ---------------------------------------------------------------------------
class TestCommissionExecutor:
    def test_register_commissions(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([
            CommissionInfo(commission_id="c1"),
            CommissionInfo(commission_id="c2"),
            CommissionInfo(commission_id="c3"),
            CommissionInfo(commission_id="c4"),
        ])
        assert len(ex.commissions) == 4

    def test_max_four_commissions(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([
            CommissionInfo(commission_id=f"c{i}") for i in range(6)
        ])
        assert len(ex.commissions) == 4

    def test_mark_completed(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([CommissionInfo(commission_id="c1")])
        ex.mark_completed("c1")
        assert ex.commissions[0].is_complete

    def test_all_done(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([
            CommissionInfo(commission_id=f"c{i}", is_complete=True) for i in range(4)
        ])
        assert ex.all_done()

    def test_not_all_done(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([
            CommissionInfo(commission_id="c1", is_complete=True),
            CommissionInfo(commission_id="c2"),
        ])
        assert not ex.all_done()

    def test_next_commission(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([
            CommissionInfo(commission_id="c1", is_complete=True),
            CommissionInfo(commission_id="c2"),
            CommissionInfo(commission_id="c3"),
        ])
        result = ex.next_commission()
        assert result is not None
        assert result.commission_id == "c2"

    def test_next_commission_none_when_all_done(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([
            CommissionInfo(commission_id=f"c{i}", is_complete=True) for i in range(4)
        ])
        assert ex.next_commission() is None

    def test_claim_katheryne_success(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([
            CommissionInfo(commission_id=f"c{i}", is_complete=True) for i in range(4)
        ])
        result = ex.claim_katheryne()
        assert result.status == LoopStatus.DONE
        assert "60_primogems" in result.rewards_obtained
        assert ex.katheryne_claimed

    def test_claim_katheryne_fail_not_done(self) -> None:
        ex = CommissionExecutor()
        ex.register_commissions([CommissionInfo(commission_id="c1")])
        result = ex.claim_katheryne()
        assert result.status == LoopStatus.FAILED


# ---------------------------------------------------------------------------
# ResinSpendingExecutor (DL-02)
# ---------------------------------------------------------------------------
class TestResinSpendingExecutor:
    def test_plan_runs_early_ar(self) -> None:
        ex = ResinSpendingExecutor()
        runs = ex.plan_runs(resin_current=160, adventure_rank=20)
        assert len(runs) == 4  # 160 / 40
        assert all(r["activity"] == "world_boss" for r in runs)

    def test_plan_runs_mid_ar_talent_domain(self) -> None:
        ex = ResinSpendingExecutor()
        runs = ex.plan_runs(
            resin_current=100, adventure_rank=35,
            domain_schedule={"talent_domain": True, "weapon_domain": False},
        )
        assert len(runs) == 5  # 100 / 20
        assert all(r["activity"] == "talent_domain" for r in runs)

    def test_plan_runs_mid_ar_fallback_leyline(self) -> None:
        ex = ResinSpendingExecutor()
        runs = ex.plan_runs(
            resin_current=60, adventure_rank=35,
            domain_schedule={"talent_domain": False, "weapon_domain": False},
        )
        assert all(r["activity"] == "leyline" for r in runs)

    def test_plan_runs_late_ar_artifacts(self) -> None:
        ex = ResinSpendingExecutor()
        runs = ex.plan_runs(resin_current=80, adventure_rank=50)
        assert len(runs) == 4  # 80 / 20
        assert all(r["activity"] == "artifact_domain" for r in runs)

    def test_plan_runs_insufficient_resin(self) -> None:
        ex = ResinSpendingExecutor()
        runs = ex.plan_runs(resin_current=10, adventure_rank=50)
        assert len(runs) == 0

    def test_execute_run(self) -> None:
        ex = ResinSpendingExecutor()
        result = ex.execute_run("world_boss", 40)
        assert result.status == LoopStatus.DONE
        assert result.resin_spent == 40
        assert ex.runs_completed == 1


# ---------------------------------------------------------------------------
# WeeklyBossExecutor (DL-03)
# ---------------------------------------------------------------------------
class TestWeeklyBossExecutor:
    def test_plan_bosses(self) -> None:
        ex = WeeklyBossExecutor()
        plan = ex.plan_bosses(["childe", "signora", "raiden"], resin_current=90)
        assert len(plan) == 3
        assert all(b.resin_cost == 30 for b in plan)

    def test_plan_bosses_limited_by_resin(self) -> None:
        ex = WeeklyBossExecutor()
        plan = ex.plan_bosses(["childe", "signora", "raiden"], resin_current=50)
        assert len(plan) == 1

    def test_execute_boss(self) -> None:
        ex = WeeklyBossExecutor()
        result = ex.execute_boss("childe")
        assert result.status == LoopStatus.DONE
        assert result.resin_spent == 30
        assert ex.discounted_remaining == 2
        assert ex.completed_count == 1

    def test_execute_boss_no_discounts_left(self) -> None:
        ex = WeeklyBossExecutor()
        for _ in range(3):
            ex.execute_boss("boss")
        result = ex.execute_boss("extra_boss")
        assert result.status == LoopStatus.SKIPPED

    def test_reset_weekly(self) -> None:
        ex = WeeklyBossExecutor()
        ex.execute_boss("childe")
        ex.reset_weekly()
        assert ex.discounted_remaining == 3
        assert ex.completed_count == 0


# ---------------------------------------------------------------------------
# ExpeditionExecutor (DL-04)
# ---------------------------------------------------------------------------
class TestExpeditionExecutor:
    def test_plan_dispatches(self) -> None:
        ex = ExpeditionExecutor()
        slots = [
            ExpeditionSlot(slot_id=1, resource_type="mora"),
            ExpeditionSlot(slot_id=2, resource_type="ore"),
        ]
        ex.plan_dispatches(slots)
        pending = ex.plan_dispatches()
        assert len(pending) == 2

    def test_dispatch(self) -> None:
        ex = ExpeditionExecutor()
        ex.plan_dispatches([ExpeditionSlot(slot_id=1)])
        result = ex.dispatch(1, region="liyue", resource_type="mora")
        assert result.status == LoopStatus.DONE
        assert "liyue" in result.message

    def test_dispatch_missing_slot(self) -> None:
        ex = ExpeditionExecutor()
        result = ex.dispatch(99)
        assert result.status == LoopStatus.FAILED

    def test_collect_completed(self) -> None:
        ex = ExpeditionExecutor()
        ex.plan_dispatches([
            ExpeditionSlot(slot_id=1, is_active=True, is_complete=True,
                           resource_type="mora", region="mondstadt"),
        ])
        results = ex.collect_completed()
        assert len(results) == 1
        assert results[0].status == LoopStatus.DONE


# ---------------------------------------------------------------------------
# BattlePassExecutor (DL-05)
# ---------------------------------------------------------------------------
class TestBattlePassExecutor:
    def test_incomplete_daily_tasks(self) -> None:
        ex = BattlePassExecutor()
        ex.register_tasks([
            BattlePassTask(task_id="bp1", description="Kill 10 enemies", task_type="daily",
                           progress=5, target=10),
            BattlePassTask(task_id="bp2", description="Use 5 skills", task_type="daily",
                           progress=5, target=5, is_complete=True),
        ])
        incomplete = ex.incomplete_daily_tasks()
        assert len(incomplete) == 1
        assert incomplete[0].task_id == "bp1"

    def test_update_progress_completes_task(self) -> None:
        ex = BattlePassExecutor()
        ex.register_tasks([
            BattlePassTask(task_id="bp1", description="Test", target=3, progress=0),
        ])
        ex.update_progress("bp1", 3)
        assert ex.tasks[0].is_complete

    def test_evaluate_incomplete(self) -> None:
        ex = BattlePassExecutor()
        ex.register_tasks([
            BattlePassTask(task_id="bp1", description="Test", task_type="daily"),
        ])
        result = ex.evaluate()
        assert result.status == LoopStatus.IN_PROGRESS

    def test_evaluate_all_done(self) -> None:
        ex = BattlePassExecutor()
        ex.register_tasks([
            BattlePassTask(task_id="bp1", description="Test", task_type="daily",
                           is_complete=True),
        ])
        result = ex.evaluate()
        assert result.status == LoopStatus.DONE

    def test_progress_ratio(self) -> None:
        task = BattlePassTask(task_id="t1", description="", progress=5, target=10)
        assert task.progress_ratio == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# EventExecutor (DL-06)
# ---------------------------------------------------------------------------
class TestEventExecutor:
    def test_active_events(self) -> None:
        ex = EventExecutor()
        ex.register_events([
            EventInfo(event_id="e1", event_name="Test Event 1", rewards_remaining=5),
            EventInfo(event_id="e2", event_name="Test Event 2", is_completed=True),
            EventInfo(event_id="e3", event_name="Test Event 3", is_active=False),
        ])
        active = ex.active_events()
        assert len(active) == 1
        assert active[0].event_id == "e1"

    def test_next_event(self) -> None:
        ex = EventExecutor()
        ex.register_events([
            EventInfo(event_id="e1", event_name="Big Event", rewards_remaining=10),
            EventInfo(event_id="e2", event_name="Small Event", rewards_remaining=2),
        ])
        result = ex.next_event()
        assert result is not None
        assert result.event_id == "e2"  # Fewest rewards = ending soonest

    def test_next_event_none(self) -> None:
        ex = EventExecutor()
        assert ex.next_event() is None

    def test_complete_event(self) -> None:
        ex = EventExecutor()
        ex.register_events([
            EventInfo(event_id="e1", event_name="Test Event"),
        ])
        result = ex.complete_event("e1")
        assert result.status == LoopStatus.DONE

    def test_complete_event_not_found(self) -> None:
        ex = EventExecutor()
        result = ex.complete_event("nonexistent")
        assert result.status == LoopStatus.FAILED


# ---------------------------------------------------------------------------
# DailyLoopExecutor (DL-07)
# ---------------------------------------------------------------------------
class TestDailyLoopExecutor:
    def _make_state(self, **kwargs: int | bool | float) -> GameStateSnapshot:
        defaults = {
            "adventure_rank": 45,
            "world_level": 6,
            "resin_current": 160,
            "daily_commissions_done": False,
            "is_weekly_reset_day": False,
            "weekly_bosses_done": 0,
        }
        defaults.update(kwargs)  # type: ignore[arg-type]
        return GameStateSnapshot(**defaults)  # type: ignore[arg-type]

    def test_build_phase_order_commissions_first(self) -> None:
        ex = DailyLoopExecutor()
        phases = ex.build_phase_order(self._make_state(daily_commissions_done=False))
        assert phases[0] == LoopPhase.COMMISSIONS

    def test_build_phase_order_weekly_on_reset(self) -> None:
        ex = DailyLoopExecutor()
        phases = ex.build_phase_order(
            self._make_state(is_weekly_reset_day=True, weekly_bosses_done=1)
        )
        assert LoopPhase.WEEKLY_BOSS in phases

    def test_build_phase_order_no_weekly_if_done(self) -> None:
        ex = DailyLoopExecutor()
        phases = ex.build_phase_order(
            self._make_state(is_weekly_reset_day=True, weekly_bosses_done=3)
        )
        assert LoopPhase.WEEKLY_BOSS not in phases

    def test_execute_loop_basic(self) -> None:
        ex = DailyLoopExecutor()
        state = ex.execute_loop(
            self._make_state(
                daily_commissions_done=True,
                is_weekly_reset_day=False,
                resin_current=10,
            ),
            max_phases=3,
        )
        assert state.failure_count == 0

    def test_execute_loop_commissions(self) -> None:
        ex = DailyLoopExecutor()
        ex.commissions.register_commissions([
            CommissionInfo(commission_id=f"c{i}", is_complete=True) for i in range(4)
        ])
        state = ex.execute_loop(
            self._make_state(daily_commissions_done=False),
            max_phases=2,
        )
        assert LoopPhase.COMMISSIONS in state.phase_results

    def test_execute_loop_resin_spending(self) -> None:
        ex = DailyLoopExecutor()
        state = ex.execute_loop(
            self._make_state(
                daily_commissions_done=True,
                resin_current=160,
            ),
            max_phases=3,
        )
        assert LoopPhase.RESIN_SPEND in state.phase_results
        result = state.phase_results[LoopPhase.RESIN_SPEND]
        assert result.resin_spent > 0

    def test_execute_loop_max_failures_aborts(self) -> None:
        config = DailyLoopConfig(max_failures=1)
        ex = DailyLoopExecutor(config)
        # Force a failure by trying to claim katheryne without completing commissions
        ex.commissions.register_commissions([CommissionInfo(commission_id="c1")])
        state = ex.execute_loop(self._make_state(), max_phases=10)
        # Should abort after first failure
        assert state.failure_count <= 2

    def test_reset_daily(self) -> None:
        ex = DailyLoopExecutor()
        ex.commissions.register_commissions([
            CommissionInfo(commission_id="c1", is_complete=True),
        ])
        ex.reset_daily()
        assert len(ex.commissions.commissions) == 0

    def test_reset_weekly(self) -> None:
        ex = DailyLoopExecutor()
        ex.weekly_boss.execute_boss("childe")
        assert ex.weekly_boss.discounted_remaining == 2
        ex.reset_weekly()
        assert ex.weekly_boss.discounted_remaining == 3

    def test_state_is_complete(self) -> None:
        state = DailyLoopState()
        assert not state.is_complete
        state.current_phase = LoopPhase.COMPLETE
        assert state.is_complete

    def test_state_record_result(self) -> None:
        state = DailyLoopState()
        result = LoopPhaseResult(
            phase=LoopPhase.RESIN_SPEND,
            status=LoopStatus.DONE,
            resin_spent=40,
            rewards_obtained=["artifacts"],
        )
        state.record_result(result)
        assert state.total_resin_spent == 40
        assert "artifacts" in state.total_rewards
        assert state.failure_count == 0

    def test_state_records_failures(self) -> None:
        state = DailyLoopState()
        state.record_result(LoopPhaseResult(
            phase=LoopPhase.COMMISSIONS, status=LoopStatus.FAILED,
        ))
        assert state.failure_count == 1


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------
class TestDataclassSlots:
    def test_commission_info_slots(self) -> None:
        ci = CommissionInfo(commission_id="c1")
        assert hasattr(ci, "__slots__")

    def test_weekly_boss_info_slots(self) -> None:
        wb = WeeklyBossInfo(boss_name="childe")
        assert hasattr(wb, "__slots__")

    def test_expedition_slot_slots(self) -> None:
        es = ExpeditionSlot(slot_id=1)
        assert hasattr(es, "__slots__")

    def test_battle_pass_task_slots(self) -> None:
        bt = BattlePassTask(task_id="t1", description="test")
        assert hasattr(bt, "__slots__")

    def test_event_info_slots(self) -> None:
        ei = EventInfo(event_id="e1", event_name="test")
        assert hasattr(ei, "__slots__")

    def test_loop_phase_result_slots(self) -> None:
        lr = LoopPhaseResult(phase=LoopPhase.IDLE, status=LoopStatus.PENDING)
        assert hasattr(lr, "__slots__")

    def test_daily_loop_config_slots(self) -> None:
        dc = DailyLoopConfig()
        assert hasattr(dc, "__slots__")
