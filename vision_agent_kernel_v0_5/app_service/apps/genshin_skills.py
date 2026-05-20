from __future__ import annotations

import time

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import SkillResult


class GenshinCombatSkill:
    name = "GenshinCombatSkill"

    def __init__(self, state_bus: StateBus, timebase: Timebase | None = None) -> None:
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()

    def run(self) -> SkillResult:
        now = self._timebase.now()
        danger_slot = self._state_bus.get_slot("genshin.danger_signals")
        danger_data = danger_slot.get() if danger_slot else None
        if danger_data and danger_data.get("should_dodge"):
            return SkillResult(
                skill_name=self.name,
                status="CANCELLED",
                failure_code="DODGE_TRIGGERED",
                started_at=now,
                finished_at=now,
                payload={"reason": "danger_detected", "danger": danger_data},
            )
        screen_slot = self._state_bus.get_slot("genshin.screen_state")
        screen_data = screen_slot.get() if screen_slot else None
        if screen_data and screen_data.get("state") == "dialog":
            return SkillResult(
                skill_name=self.name,
                status="SUCCESS",
                failure_code=None,
                started_at=now,
                finished_at=now,
                payload={"transition": "dialog_detected"},
            )
        return SkillResult(
            skill_name=self.name,
            status="SUCCESS",
            failure_code=None,
            started_at=now,
            finished_at=now,
            payload={"status": "combat_idle"},
        )


class GenshinDodgeReflexSkill:
    name = "GenshinDodgeReflexSkill"

    def __init__(self, state_bus: StateBus, danger_slot=None, timebase: Timebase | None = None) -> None:
        self._state_bus = state_bus
        self._danger_slot = danger_slot
        self._timebase = timebase or Timebase()

    def run(self) -> SkillResult:
        now = self._timebase.now()
        return SkillResult(
            skill_name=self.name,
            status="SUCCESS",
            failure_code=None,
            started_at=now,
            finished_at=now,
            payload={"action": "dodge_executed"},
        )
