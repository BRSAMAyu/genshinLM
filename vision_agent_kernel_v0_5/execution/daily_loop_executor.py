"""Daily loop executor: orchestrates all repeatable daily/weekly tasks.

Covers DL-01 through DL-07:
- DL-01: Complete 4 daily commissions + claim Katheryne reward
- DL-02: Resin spending loop (domains, bosses, leylines based on schedule)
- DL-03: Weekly boss challenges (3 discounted per week)
- DL-04: Expedition dispatch (reset daily)
- DL-05: Battle pass daily/weekly task completion
- DL-06: Limited-time event participation
- DL-07: Unified daily loop scheduler

Integrates with:
- planning/daily_loop_scheduler.py for strategic priority ordering
- planning/resource_manager.py for resin/mora/food tracking
- interaction/ui_flow_engine.py for UI automation
- interaction/ui_flows/ for predefined flow templates
- planning/wish_shop_system.py for monthly shop purchases
- planning/exploration_engine.py for exploration tasks
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planning.daily_loop_scheduler import ActionRecommendation, DailySchedule, GameStateSnapshot

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LoopPhase(str, Enum):
    """Phases within a single daily loop iteration."""
    IDLE = "idle"
    COMMISSIONS = "commissions"
    RESIN_SPEND = "resin_spend"
    WEEKLY_BOSS = "weekly_boss"
    EXPEDITIONS = "expeditions"
    BATTLE_PASS = "battle_pass"
    EVENTS = "events"
    ARCHON_QUEST = "archon_quest"
    EXPLORATION = "exploration"
    COMPLETE = "complete"


class LoopStatus(str, Enum):
    """Status of a loop phase execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class LoopPhaseResult:
    """Result of executing one loop phase."""
    phase: LoopPhase
    status: LoopStatus
    message: str = ""
    resin_spent: int = 0
    rewards_obtained: list[str] = field(default_factory=list)
    time_elapsed_sec: float = 0.0


@dataclass(slots=True)
class DailyLoopState:
    """Tracks state across a daily loop execution."""
    current_phase: LoopPhase = LoopPhase.IDLE
    phase_results: dict[LoopPhase, LoopPhaseResult] = field(default_factory=dict)
    total_resin_spent: int = 0
    total_rewards: list[str] = field(default_factory=list)
    commissions_completed: int = 0
    weekly_bosses_completed: int = 0
    expeditions_dispatched: int = 0
    events_participated: int = 0
    failure_count: int = 0

    @property
    def is_complete(self) -> bool:
        return self.current_phase == LoopPhase.COMPLETE

    def record_result(self, result: LoopPhaseResult) -> None:
        self.phase_results[result.phase] = result
        self.total_resin_spent += result.resin_spent
        self.total_rewards.extend(result.rewards_obtained)
        if result.status == LoopStatus.FAILED:
            self.failure_count += 1


# ---------------------------------------------------------------------------
# Commission executor (DL-01)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CommissionInfo:
    """Tracks a single daily commission."""
    commission_id: str
    location: str = ""
    commission_type: str = ""  # "combat", "delivery", "timed_challenge", "photography"
    is_complete: bool = False


class CommissionExecutor:
    """Manages daily commission completion (DL-01).

    Handles tracking 4 daily commissions and Katheryne reward claim.
    Integrates with quest_ui_manager.CommissionManager for state.
    """

    MAX_COMMISSIONS = 4

    def __init__(self) -> None:
        self._commissions: list[CommissionInfo] = []
        self._katheryne_claimed: bool = False

    @property
    def commissions(self) -> list[CommissionInfo]:
        return list(self._commissions)

    @property
    def katheryne_claimed(self) -> bool:
        return self._katheryne_claimed

    def register_commissions(self, commissions: list[CommissionInfo]) -> None:
        self._commissions = commissions[:self.MAX_COMMISSIONS]
        self._katheryne_claimed = False

    def mark_completed(self, commission_id: str) -> None:
        for c in self._commissions:
            if c.commission_id == commission_id:
                c.is_complete = True
                break

    def all_done(self) -> bool:
        return (len(self._commissions) >= self.MAX_COMMISSIONS
                and all(c.is_complete for c in self._commissions))

    def next_commission(self) -> CommissionInfo | None:
        for c in self._commissions:
            if not c.is_complete:
                return c
        return None

    def claim_katheryne(self) -> LoopPhaseResult:
        """Claim Katheryne reward after all commissions done."""
        if not self.all_done():
            return LoopPhaseResult(
                phase=LoopPhase.COMMISSIONS,
                status=LoopStatus.FAILED,
                message="Not all commissions complete",
            )
        self._katheryne_claimed = True
        return LoopPhaseResult(
            phase=LoopPhase.COMMISSIONS,
            status=LoopStatus.DONE,
            message="Katheryne reward claimed",
            rewards_obtained=["60_primogems", "ar_exp", "mora"],
        )


# ---------------------------------------------------------------------------
# Resin spending executor (DL-02)
# ---------------------------------------------------------------------------

class ResinSpendingExecutor:
    """Manages resin consumption based on strategic priorities (DL-02).

    Dispatches to appropriate activities:
    - AR < 30: World bosses (character ascension materials)
    - AR 30-44: Talent/weapon domains
    - AR 45+: Artifact domains
    """

    RESIN_PER_DOMAIN = 20
    RESIN_PER_BOSS = 40
    RESIN_PER_WEEKLY_BOSS = 30  # Discounted
    RESIN_PER_LEYLINE = 20

    def __init__(self) -> None:
        self._runs_completed: int = 0

    @property
    def runs_completed(self) -> int:
        return self._runs_completed

    def plan_runs(self, resin_current: int, adventure_rank: int,
                  domain_schedule: dict[str, bool] | None = None,
                  ) -> list[dict[str, int | str]]:
        """Plan resin spending based on AR and available resin.

        Returns list of run plans: {"activity": str, "resin_cost": int, "target": str}
        """
        if resin_current < self.RESIN_PER_DOMAIN:
            return []

        runs: list[dict[str, int | str]] = []

        if adventure_rank < 30:
            # World bosses for ascension materials
            while resin_current >= self.RESIN_PER_BOSS:
                runs.append({
                    "activity": "world_boss",
                    "resin_cost": self.RESIN_PER_BOSS,
                    "target": "ascension_materials",
                })
                resin_current -= self.RESIN_PER_BOSS

        elif adventure_rank < 45:
            # Talent/weapon domains based on daily schedule
            available_books = domain_schedule or {}
            while resin_current >= self.RESIN_PER_DOMAIN:
                if available_books.get("talent_domain", False):
                    runs.append({
                        "activity": "talent_domain",
                        "resin_cost": self.RESIN_PER_DOMAIN,
                        "target": "talent_books",
                    })
                elif available_books.get("weapon_domain", False):
                    runs.append({
                        "activity": "weapon_domain",
                        "resin_cost": self.RESIN_PER_DOMAIN,
                        "target": "weapon_materials",
                    })
                else:
                    # Ley line as fallback
                    runs.append({
                        "activity": "leyline",
                        "resin_cost": self.RESIN_PER_LEYLINE,
                        "target": "mora_or_exp",
                    })
                resin_current -= self.RESIN_PER_DOMAIN

        else:
            # AR45+: Artifact domains priority
            while resin_current >= self.RESIN_PER_DOMAIN:
                runs.append({
                    "activity": "artifact_domain",
                    "resin_cost": self.RESIN_PER_DOMAIN,
                    "target": "5star_artifacts",
                })
                resin_current -= self.RESIN_PER_DOMAIN

        return runs

    def execute_run(self, activity: str, resin_cost: int) -> LoopPhaseResult:
        """Record completion of a resin-spending run."""
        self._runs_completed += 1
        return LoopPhaseResult(
            phase=LoopPhase.RESIN_SPEND,
            status=LoopStatus.DONE,
            message=f"Completed {activity}",
            resin_spent=resin_cost,
            rewards_obtained=[f"{activity}_rewards"],
        )


# ---------------------------------------------------------------------------
# Weekly boss executor (DL-03)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WeeklyBossInfo:
    """Tracks a weekly boss fight."""
    boss_name: str
    resin_cost: int = 30       # Discounted cost
    is_completed: bool = False
    materials_obtained: list[str] = field(default_factory=list)


class WeeklyBossExecutor:
    """Manages weekly boss completion (DL-03).

    Tracks 3 discounted weekly boss kills per week.
    """

    MAX_DISCOUNTED = 3
    DISCOUNTED_RESIN = 30
    FULL_RESIN = 60

    def __init__(self) -> None:
        self._bosses: list[WeeklyBossInfo] = []
        self._discounted_remaining: int = self.MAX_DISCOUNTED

    @property
    def discounted_remaining(self) -> int:
        return self._discounted_remaining

    @property
    def completed_count(self) -> int:
        return sum(1 for b in self._bosses if b.is_completed)

    def plan_bosses(self, bosses_available: list[str],
                    resin_current: int) -> list[WeeklyBossInfo]:
        """Plan which weekly bosses to fight."""
        plan: list[WeeklyBossInfo] = []
        for boss_name in bosses_available:
            if self._discounted_remaining <= 0:
                break
            resin_cost = self.DISCOUNTED_RESIN
            if resin_current < resin_cost:
                break
            plan.append(WeeklyBossInfo(boss_name=boss_name, resin_cost=resin_cost))
            resin_current -= resin_cost
        return plan

    def execute_boss(self, boss_name: str) -> LoopPhaseResult:
        """Record completion of a weekly boss fight."""
        if self._discounted_remaining <= 0:
            return LoopPhaseResult(
                phase=LoopPhase.WEEKLY_BOSS,
                status=LoopStatus.SKIPPED,
                message="No discounted bosses remaining",
            )

        self._discounted_remaining -= 1
        info = WeeklyBossInfo(
            boss_name=boss_name,
            resin_cost=self.DISCOUNTED_RESIN,
            is_completed=True,
        )
        self._bosses.append(info)

        return LoopPhaseResult(
            phase=LoopPhase.WEEKLY_BOSS,
            status=LoopStatus.DONE,
            message=f"Defeated {boss_name} ({self._discounted_remaining} discounted left)",
            resin_spent=self.DISCOUNTED_RESIN,
            rewards_obtained=[f"{boss_name}_talent_material", "artifacts", "billets"],
        )

    def reset_weekly(self) -> None:
        """Reset weekly boss tracking on Monday reset."""
        self._bosses.clear()
        self._discounted_remaining = self.MAX_DISCOUNTED


# ---------------------------------------------------------------------------
# Expedition executor (DL-04)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ExpeditionSlot:
    """A single expedition dispatch slot."""
    slot_id: int
    region: str = ""
    duration_hours: int = 20
    resource_type: str = ""    # "mora", "ore", "fowl", "fruit", "crystal"
    is_active: bool = False
    is_complete: bool = False


class ExpeditionExecutor:
    """Manages daily expedition dispatches (DL-04).

    Dispatches 3-5 expedition slots based on AR:
    - AR 1-24: 3 slots
    - AR 25-34: 4 slots
    - AR 35+: 5 slots
    """

    DEFAULT_DURATION = 20  # hours

    def __init__(self, max_slots: int = 5) -> None:
        self._max_slots = max_slots
        self._slots: list[ExpeditionSlot] = []

    @staticmethod
    def slots_for_ar(ar: int) -> int:
        """Return the number of expedition slots available at given AR."""
        if ar < 25:
            return 3
        if ar < 35:
            return 4
        return 5
        self._slots: list[ExpeditionSlot] = []

    @property
    def slots(self) -> list[ExpeditionSlot]:
        return list(self._slots)

    def plan_dispatches(self, active_slots: list[ExpeditionSlot] | None = None,
                        ) -> list[ExpeditionSlot]:
        """Plan which expedition slots to dispatch."""
        if active_slots is not None:
            self._slots = active_slots[:self._max_slots]

        pending = [s for s in self._slots if not s.is_active and not s.is_complete]
        return pending

    def dispatch(self, slot_id: int, region: str = "",
                 resource_type: str = "mora") -> LoopPhaseResult:
        """Dispatch an expedition to a slot."""
        for slot in self._slots:
            if slot.slot_id == slot_id:
                slot.region = region
                slot.resource_type = resource_type
                slot.duration_hours = self.DEFAULT_DURATION
                slot.is_active = True
                return LoopPhaseResult(
                    phase=LoopPhase.EXPEDITIONS,
                    status=LoopStatus.DONE,
                    message=f"Dispatched slot {slot_id} to {region} for {resource_type}",
                )

        return LoopPhaseResult(
            phase=LoopPhase.EXPEDITIONS,
            status=LoopStatus.FAILED,
            message=f"Slot {slot_id} not found",
        )

    def collect_completed(self) -> list[LoopPhaseResult]:
        """Collect results from completed expeditions."""
        results: list[LoopPhaseResult] = []
        for slot in self._slots:
            if slot.is_complete and slot.is_active:
                results.append(LoopPhaseResult(
                    phase=LoopPhase.EXPEDITIONS,
                    status=LoopStatus.DONE,
                    message=f"Collected {slot.resource_type} from {slot.region}",
                    rewards_obtained=[slot.resource_type],
                ))
                slot.is_active = False
                slot.is_complete = False
        return results


# ---------------------------------------------------------------------------
# Battle pass executor (DL-05)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BattlePassTask:
    """A single battle pass daily/weekly task."""
    task_id: str
    description: str
    task_type: str = "daily"   # "daily" or "weekly"
    progress: int = 0
    target: int = 1
    is_complete: bool = False

    @property
    def progress_ratio(self) -> float:
        return min(self.progress / max(self.target, 1), 1.0)


class BattlePassExecutor:
    """Manages battle pass task tracking and completion (DL-05)."""

    def __init__(self) -> None:
        self._tasks: list[BattlePassTask] = []

    @property
    def tasks(self) -> list[BattlePassTask]:
        return list(self._tasks)

    def register_tasks(self, tasks: list[BattlePassTask]) -> None:
        self._tasks = tasks

    def incomplete_daily_tasks(self) -> list[BattlePassTask]:
        return [t for t in self._tasks if t.task_type == "daily" and not t.is_complete]

    def incomplete_weekly_tasks(self) -> list[BattlePassTask]:
        return [t for t in self._tasks if t.task_type == "weekly" and not t.is_complete]

    def update_progress(self, task_id: str, progress: int) -> None:
        for t in self._tasks:
            if t.task_id == task_id:
                t.progress = progress
                if t.progress >= t.target:
                    t.is_complete = True
                break

    def evaluate(self) -> LoopPhaseResult:
        """Evaluate battle pass progress and recommend next action."""
        incomplete = self.incomplete_daily_tasks()
        if not incomplete:
            return LoopPhaseResult(
                phase=LoopPhase.BATTLE_PASS,
                status=LoopStatus.DONE,
                message="All daily BP tasks complete",
            )
        return LoopPhaseResult(
            phase=LoopPhase.BATTLE_PASS,
            status=LoopStatus.IN_PROGRESS,
            message=f"{len(incomplete)} daily BP tasks remaining",
        )


# ---------------------------------------------------------------------------
# Event executor (DL-06)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EventInfo:
    """Tracks a limited-time event."""
    event_id: str
    event_name: str
    end_date: str = ""          # ISO format
    is_active: bool = True
    is_completed: bool = False
    rewards_remaining: int = 0


class EventExecutor:
    """Manages limited-time event participation (DL-06)."""

    def __init__(self) -> None:
        self._events: list[EventInfo] = []

    @property
    def events(self) -> list[EventInfo]:
        return list(self._events)

    def register_events(self, events: list[EventInfo]) -> None:
        self._events = [e for e in events if e.is_active]

    def active_events(self) -> list[EventInfo]:
        return [e for e in self._events if e.is_active and not e.is_completed]

    def next_event(self) -> EventInfo | None:
        active = self.active_events()
        if not active:
            return None
        # Prefer events ending soonest (by end_date if available)
        dated = [e for e in active if e.end_date]
        if dated:
            return min(dated, key=lambda e: e.end_date)
        # Fallback: fewest rewards remaining
        return min(active, key=lambda e: e.rewards_remaining)

    def complete_event(self, event_id: str) -> LoopPhaseResult:
        """Mark an event as completed."""
        for event in self._events:
            if event.event_id == event_id:
                event.is_completed = True
                return LoopPhaseResult(
                    phase=LoopPhase.EVENTS,
                    status=LoopStatus.DONE,
                    message=f"Completed event: {event.event_name}",
                    rewards_obtained=[f"{event.event_name}_rewards"],
                )
        return LoopPhaseResult(
            phase=LoopPhase.EVENTS,
            status=LoopStatus.FAILED,
            message=f"Event {event_id} not found",
        )


# ---------------------------------------------------------------------------
# Unified daily loop scheduler (DL-07)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DailyLoopConfig:
    """Configuration for a daily loop iteration."""
    resin_threshold: int = 160       # Start loop when resin >= this
    max_failures: int = 5            # Abort loop after this many failures
    include_exploration: bool = True
    include_events: bool = True
    weekly_boss_budget: int = 3      # Max weekly bosses per cycle


class DailyLoopExecutor:
    """Unified daily loop orchestrator (DL-07).

    Coordinates all daily/weekly tasks in priority order.
    Delegates to specialized executors for each task type.

    Integration points:
    - StrategicDecisionEngine for priority ordering
    - ResourceManager for resin/mora tracking
    - UIFlowExecutor for UI automation
    - QuestStateMachine for archon quest progress
    """

    def __init__(self, config: DailyLoopConfig | None = None) -> None:
        self._config = config or DailyLoopConfig()
        self._state = DailyLoopState()
        self._commissions = CommissionExecutor()
        self._resin = ResinSpendingExecutor()
        self._weekly_boss = WeeklyBossExecutor()
        self._expeditions = ExpeditionExecutor()
        self._battle_pass = BattlePassExecutor()
        self._events = EventExecutor()

    @property
    def state(self) -> DailyLoopState:
        return self._state

    @property
    def commissions(self) -> CommissionExecutor:
        return self._commissions

    @property
    def resin(self) -> ResinSpendingExecutor:
        return self._resin

    @property
    def weekly_boss(self) -> WeeklyBossExecutor:
        return self._weekly_boss

    @property
    def expeditions(self) -> ExpeditionExecutor:
        return self._expeditions

    @property
    def battle_pass(self) -> BattlePassExecutor:
        return self._battle_pass

    @property
    def events(self) -> EventExecutor:
        return self._events

    def build_phase_order(self, game_state: GameStateSnapshot) -> list[LoopPhase]:
        """Build ordered list of phases based on game state priorities.

        Uses StrategicDecisionEngine logic for priority ordering:
        P0: Commissions (always first if not done)
        P1: Weekly bosses (on reset day)
        P2: Resin spending
        P3: Expeditions
        P4: Battle pass tasks
        P5: Events
        P6: Archon quest (if recommended)
        P7: Exploration (if time permits)
        """
        phases: list[LoopPhase] = []

        # P0: Commissions
        if not game_state.daily_commissions_done:
            phases.append(LoopPhase.COMMISSIONS)

        # P1: Weekly bosses
        if game_state.is_weekly_reset_day and game_state.weekly_bosses_done < self._config.weekly_boss_budget:
            phases.append(LoopPhase.WEEKLY_BOSS)

        # P2: Resin
        if game_state.resin_current >= self._config.resin_threshold:
            phases.append(LoopPhase.RESIN_SPEND)

        # P3: Expeditions
        phases.append(LoopPhase.EXPEDITIONS)

        # P4: Battle pass
        phases.append(LoopPhase.BATTLE_PASS)

        # P5: Events
        if self._config.include_events:
            phases.append(LoopPhase.EVENTS)

        # P6: Archon quest
        phases.append(LoopPhase.ARCHON_QUEST)

        # P7: Exploration
        if self._config.include_exploration:
            phases.append(LoopPhase.EXPLORATION)

        phases.append(LoopPhase.COMPLETE)
        return phases

    def execute_loop(self, game_state: GameStateSnapshot,
                     max_phases: int | None = None,
                     ) -> DailyLoopState:
        """Execute a complete daily loop iteration.

        Args:
            game_state: Current game state snapshot.
            max_phases: Optional limit on phases to execute (for testing).

        Returns:
            Updated DailyLoopState with results.
        """
        phases = self.build_phase_order(game_state)
        executed = 0

        for phase in phases:
            if max_phases is not None and executed >= max_phases:
                break

            if self._state.failure_count >= self._config.max_failures:
                log.warning("Aborting daily loop: %d failures reached",
                            self._state.failure_count)
                break

            self._state.current_phase = phase

            if phase == LoopPhase.COMPLETE:
                self._state.current_phase = LoopPhase.COMPLETE
                break

            result = self._execute_phase(phase, game_state)
            self._state.record_result(result)
            executed += 1

            if result.status == LoopStatus.FAILED:
                log.warning("Phase %s failed: %s", phase.value, result.message)

        return self._state

    def _execute_phase(self, phase: LoopPhase,
                       game_state: GameStateSnapshot) -> LoopPhaseResult:
        """Execute a single phase, dispatching to the appropriate executor."""
        if phase == LoopPhase.COMMISSIONS:
            return self._execute_commissions()
        if phase == LoopPhase.RESIN_SPEND:
            return self._execute_resin(game_state)
        if phase == LoopPhase.WEEKLY_BOSS:
            return self._execute_weekly_boss()
        if phase == LoopPhase.EXPEDITIONS:
            return self._execute_expeditions()
        if phase == LoopPhase.BATTLE_PASS:
            return self._battle_pass.evaluate()
        if phase == LoopPhase.EVENTS:
            return self._execute_events()
        if phase == LoopPhase.ARCHON_QUEST:
            return LoopPhaseResult(
                phase=LoopPhase.ARCHON_QUEST,
                status=LoopStatus.SKIPPED,
                message="Archon quest handled by quest system",
            )
        if phase == LoopPhase.EXPLORATION:
            return LoopPhaseResult(
                phase=LoopPhase.EXPLORATION,
                status=LoopStatus.SKIPPED,
                message="Exploration handled by exploration engine",
            )

        return LoopPhaseResult(
            phase=phase,
            status=LoopStatus.SKIPPED,
            message=f"Unknown phase: {phase.value}",
        )

    def _execute_commissions(self) -> LoopPhaseResult:
        """Execute commission completion."""
        if self._commissions.all_done():
            if not self._commissions.katheryne_claimed:
                return self._commissions.claim_katheryne()
            return LoopPhaseResult(
                phase=LoopPhase.COMMISSIONS,
                status=LoopStatus.DONE,
                message="Commissions already complete",
                rewards_obtained=["katheryne_reward"],
            )
        return LoopPhaseResult(
            phase=LoopPhase.COMMISSIONS,
            status=LoopStatus.IN_PROGRESS,
            message=f"Commissions in progress ({sum(1 for c in self._commissions.commissions if c.is_complete)}/4)",
        )

    def _execute_resin(self, game_state: GameStateSnapshot) -> LoopPhaseResult:
        """Execute resin spending."""
        runs = self._resin.plan_runs(
            resin_current=game_state.resin_current,
            adventure_rank=game_state.adventure_rank,
        )
        if not runs:
            return LoopPhaseResult(
                phase=LoopPhase.RESIN_SPEND,
                status=LoopStatus.SKIPPED,
                message="Not enough resin to spend",
            )

        total_spent = 0
        rewards: list[str] = []
        for run in runs:
            cost = int(run["resin_cost"])
            activity = str(run["activity"])
            result = self._resin.execute_run(activity, cost)
            total_spent += result.resin_spent
            rewards.extend(result.rewards_obtained)

        return LoopPhaseResult(
            phase=LoopPhase.RESIN_SPEND,
            status=LoopStatus.DONE,
            message=f"Spent {total_spent} resin in {len(runs)} runs",
            resin_spent=total_spent,
            rewards_obtained=rewards,
        )

    def _execute_weekly_boss(self) -> LoopPhaseResult:
        """Execute weekly boss fights."""
        if self._weekly_boss.discounted_remaining <= 0:
            return LoopPhaseResult(
                phase=LoopPhase.WEEKLY_BOSS,
                status=LoopStatus.SKIPPED,
                message="Weekly bosses already completed",
            )
        return LoopPhaseResult(
            phase=LoopPhase.WEEKLY_BOSS,
            status=LoopStatus.IN_PROGRESS,
            message=f"{self._weekly_boss.discounted_remaining} discounted bosses remaining",
        )

    def _execute_expeditions(self) -> LoopPhaseResult:
        """Execute expedition dispatches."""
        pending = self._expeditions.plan_dispatches()
        dispatched = len(pending)
        if dispatched == 0:
            return LoopPhaseResult(
                phase=LoopPhase.EXPEDITIONS,
                status=LoopStatus.DONE,
                message="All expeditions already dispatched",
            )
        return LoopPhaseResult(
            phase=LoopPhase.EXPEDITIONS,
            status=LoopStatus.DONE,
            message=f"{dispatched} expeditions dispatched",
        )

    def _execute_events(self) -> LoopPhaseResult:
        """Execute event participation."""
        active = self._events.active_events()
        if not active:
            return LoopPhaseResult(
                phase=LoopPhase.EVENTS,
                status=LoopStatus.DONE,
                message="No active events",
            )
        return LoopPhaseResult(
            phase=LoopPhase.EVENTS,
            status=LoopStatus.IN_PROGRESS,
            message=f"{len(active)} active events available",
        )

    def reset_daily(self) -> None:
        """Reset daily state (call at server reset time)."""
        self._state = DailyLoopState()
        self._commissions = CommissionExecutor()
        self._expeditions = ExpeditionExecutor()
        # Clear daily battle pass tasks (keep weekly)
        daily_tasks = [t for t in self._battle_pass.tasks if t.task_type == "weekly"]
        self._battle_pass.register_tasks(daily_tasks)

    def reset_weekly(self) -> None:
        """Reset weekly state (call on Monday reset)."""
        self._weekly_boss.reset_weekly()
