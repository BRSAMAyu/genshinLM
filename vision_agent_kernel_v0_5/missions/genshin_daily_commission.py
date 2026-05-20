from __future__ import annotations

import time
from dataclasses import dataclass, replace
from enum import Enum


class CommissionStatus(Enum):
    NOT_STARTED = "not_started"
    NAVIGATING = "navigating"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CommissionInfo:
    commission_id: str
    name: str
    region: str
    waypoint_id: str
    commission_type: str  # "combat", "collection", "escort", "dialog", "puzzle"
    description: str
    estimated_duration_ms: int


@dataclass(frozen=True, slots=True)
class DailyProgress:
    commissions_done: int
    commissions_total: int
    katheryne_visited: bool
    rewards_claimed: bool
    bonus_reward_claimed: bool


@dataclass(frozen=True, slots=True)
class DailyCommissionState:
    status: str
    current_commission: str | None
    progress: DailyProgress
    elapsed_ms: float


class DailyCommissionRunner:
    """Automate daily commission completion in Genshin Impact.

    Flow:
    1. Accept commissions from Katheryne (Adventure Guild)
    2. For each commission:
       a. Navigate to commission location
       b. Complete commission (combat/collection/dialog/escort)
       c. Verify completion
    3. Return to Katheryne
    4. Claim rewards
    """

    def __init__(self) -> None:
        self._state = DailyCommissionState(
            "not_started", None,
            DailyProgress(0, 4, False, False, False),
            0.0,
        )
        self._commissions: list[CommissionInfo] = []
        self._start_time: float = 0.0
        self._current_index: int = 0

    def start(self) -> None:
        """Begin daily commission routine."""
        self._start_time = time.perf_counter()
        self._state = DailyCommissionState(
            status=CommissionStatus.NAVIGATING.value,
            current_commission=None,
            progress=self._state.progress,
            elapsed_ms=0.0,
        )

    def tick(self, dt_ms: float, screen_state: str, danger_score: float = 0.0) -> dict | None:
        """Advance commission state machine by one tick.

        Returns action dict or None if waiting.
        """
        if self._state.status == CommissionStatus.NOT_STARTED.value:
            return None

        if self._state.status == CommissionStatus.COMPLETED.value:
            return None

        if self._state.status == CommissionStatus.FAILED.value:
            return None

        elapsed = self._state.elapsed_ms + dt_ms

        if danger_score > 0.8:
            self._state = replace(self._state, elapsed_ms=elapsed)
            return {"input": "press_key", "key": "escape", "label": "danger_retreat"}

        if self._state.status == CommissionStatus.NAVIGATING.value:
            if self._current_index < len(self._commissions):
                commission = self._commissions[self._current_index]
                self._state = DailyCommissionState(
                    status=CommissionStatus.IN_PROGRESS.value,
                    current_commission=commission.commission_id,
                    progress=self._state.progress,
                    elapsed_ms=elapsed,
                )
                return self._navigate_to_commission(commission)
            if self._state.progress.commissions_done >= self._state.progress.commissions_total:
                self._state = replace(
                    self._state,
                    status=CommissionStatus.COMPLETED.value,
                    elapsed_ms=elapsed,
                )
                return None
            return None

        if self._state.status == CommissionStatus.IN_PROGRESS.value:
            commission = self._commissions[self._current_index] if self._current_index < len(self._commissions) else None
            if commission is None:
                self._state = replace(self._state, elapsed_ms=elapsed)
                return None

            if screen_state == "dialog":
                return self._execute_dialog_commission()

            if screen_state == "combat":
                return self._execute_combat_commission()

            if commission.commission_type == "collection":
                return self._execute_collection_commission()

            if commission.commission_type == "dialog":
                return self._execute_dialog_commission()

            return self._execute_combat_commission()

        self._state = replace(self._state, elapsed_ms=elapsed)
        return None

    def advance_commission(self, success: bool = True) -> None:
        """Mark current commission as done and advance to next."""
        done = self._state.progress.commissions_done + (1 if success else 0)
        self._current_index += 1

        all_done = done >= self._state.progress.commissions_total
        new_progress = replace(
            self._state.progress,
            commissions_done=done,
            katheryne_visited=all_done,
        )

        if all_done:
            self._state = replace(
                self._state,
                status=CommissionStatus.COMPLETED.value,
                current_commission=None,
                progress=replace(new_progress, rewards_claimed=True),
            )
        else:
            self._state = DailyCommissionState(
                status=CommissionStatus.NAVIGATING.value,
                current_commission=None,
                progress=new_progress,
                elapsed_ms=self._state.elapsed_ms,
            )

    def set_commissions(self, commissions: list[CommissionInfo]) -> None:
        """Set the list of commissions to complete."""
        self._commissions = list(commissions)
        self._state = replace(
            self._state,
            progress=replace(
                self._state.progress,
                commissions_total=len(commissions) if commissions else 4,
            ),
        )

    def _navigate_to_commission(self, commission: CommissionInfo) -> dict:
        """Generate navigation action to commission location."""
        return {
            "input": "navigate",
            "target_waypoint": commission.waypoint_id,
            "region": commission.region,
            "commission_id": commission.commission_id,
            "commission_type": commission.commission_type,
        }

    def _execute_combat_commission(self) -> dict:
        """Execute a combat-type commission."""
        return {
            "input": "start_combat",
            "playbook": "auto_combat",
            "label": "combat_commission",
        }

    def _execute_collection_commission(self) -> dict:
        """Execute a collection-type commission."""
        return {
            "input": "interact",
            "action": "collect",
            "label": "collection_commission",
        }

    def _execute_dialog_commission(self) -> dict:
        """Execute a dialog-type commission."""
        return {
            "input": "advance_dialog",
            "label": "dialog_commission",
        }

    def _claim_rewards(self) -> list[dict]:
        """Generate action sequence for claiming Katheryne rewards."""
        return [
            {"input": "navigate", "target_waypoint": "tp_katheryne", "label": "return_to_katheryne"},
            {"input": "interact", "action": "talk", "label": "talk_to_katheryne"},
            {"input": "click_at", "target": "commission_reward_button", "label": "claim_reward"},
            {"input": "click_at", "target": "dialog_area_center", "label": "close_dialog"},
        ]

    @property
    def state(self) -> DailyCommissionState:
        return self._state

    @property
    def is_complete(self) -> bool:
        return (
            self._state.progress.commissions_done >= self._state.progress.commissions_total
            and self._state.progress.rewards_claimed
        )
