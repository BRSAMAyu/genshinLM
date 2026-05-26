from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from combat.hsr_combat_planner import HSRCombatPlan, HSRTurnAction

_log = logging.getLogger("HSRPlaybookExecutor")


@dataclass(slots=True)
class PlaybookState:
    plan: HSRCombatPlan | None = None
    current_step: int = 0
    sp_level: int = 3
    wave: int = 1
    auto_battle: bool = False
    started_at: float = 0.0
    finished_at: float = 0.0


@dataclass(frozen=True, slots=True)
class PlaybookSnapshot:
    step_index: int
    total_steps: int
    current_sp: int
    wave: int
    action: str
    complete: bool


class HSRPlaybookExecutor:
    """Execute HSR turn-based combat playbooks with SP tracking and wave management."""

    def __init__(self, max_sp: int = 5) -> None:
        self._max_sp = max_sp
        self._state = PlaybookState(sp_level=3)

    def start(self, plan: HSRCombatPlan, initial_sp: int = 3) -> None:
        self._state = PlaybookState(
            plan=plan,
            current_step=0,
            sp_level=initial_sp,
            wave=1,
            started_at=time.perf_counter(),
        )
        _log.info("HSR playbook started: %s with SP=%d", plan.plan_id, initial_sp)

    def tick(self) -> PlaybookSnapshot | None:
        """Advance one step in the playbook."""
        if self._state.plan is None:
            return None

        plan = self._state.plan
        if self._state.current_step >= len(plan.turn_rotation):
            self._state.finished_at = time.perf_counter()
            _log.info("HSR playbook complete: %s", plan.plan_id)
            return PlaybookSnapshot(
                step_index=self._state.current_step,
                total_steps=len(plan.turn_rotation),
                current_sp=self._state.sp_level,
                wave=self._state.wave,
                action="complete",
                complete=True,
            )

        action = plan.turn_rotation[self._state.current_step]

        # Check SP availability before executing skill
        effective_action = action.action
        if action.action == "skill" and self._state.sp_level < action.sp_cost:
            _log.warning(
                "SP exhausted at step %d (need %d, have %d), falling back to basic",
                self._state.current_step, action.sp_cost, self._state.sp_level,
            )
            effective_action = "basic_attack"
            self._state.sp_level = min(self._state.sp_level + 1, self._max_sp)
        elif action.action == "basic_attack":
            self._state.sp_level = min(self._state.sp_level + action.sp_gain, self._max_sp)
        elif action.action == "skill":
            self._state.sp_level -= action.sp_cost

        self._state.current_step += 1

        return PlaybookSnapshot(
            step_index=self._state.current_step - 1,
            total_steps=len(plan.turn_rotation),
            current_sp=self._state.sp_level,
            wave=self._state.wave,
            action=effective_action,
            complete=False,
        )

    def check_ultimate_available(self) -> list[HSRTurnAction]:
        """Return available ultimate interrupts."""
        if self._state.plan is None:
            return []
        return self._state.plan.ultimate_interrupts

    def advance_wave(self) -> None:
        """Move to next wave in multi-wave encounter."""
        self._state.wave += 1
        self._state.current_step = 0

    @property
    def is_complete(self) -> bool:
        if self._state.plan is None:
            return True
        return self._state.current_step >= len(self._state.plan.turn_rotation)

    @property
    def state(self) -> PlaybookState:
        return self._state

    def snapshot(self) -> PlaybookSnapshot | None:
        if self._state.plan is None:
            return None
        return PlaybookSnapshot(
            step_index=self._state.current_step,
            total_steps=len(self._state.plan.turn_rotation),
            current_sp=self._state.sp_level,
            wave=self._state.wave,
            action=self._state.plan.turn_rotation[self._state.current_step].action
            if self._state.current_step < len(self._state.plan.turn_rotation)
            else "complete",
            complete=self.is_complete,
        )
