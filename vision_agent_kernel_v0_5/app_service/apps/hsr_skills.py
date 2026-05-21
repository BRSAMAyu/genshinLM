from __future__ import annotations

from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import SkillResult


class HSRCombatSkill:
    """HSR turn-based combat skill with SP management."""
    name = "HSRCombatSkill"

    def __init__(self, state_bus: StateBus, timebase: Timebase | None = None) -> None:
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()

    def run(self) -> SkillResult:
        now = self._timebase.now()
        # Read SP state
        sp_slot = self._state_bus.get_slot("hsr.skill_points")
        sp_data = sp_slot.get() if sp_slot else None
        current_sp = sp_data.get("current", 3) if sp_data else 3

        # Read screen state
        screen_slot = self._state_bus.get_slot("hsr.screen_state")
        screen_data = screen_slot.get() if screen_slot else None
        screen_state = screen_data.get("state", "overworld") if screen_data else "overworld"

        if screen_state != "turn_based_combat":
            return SkillResult(
                skill_name=self.name,
                status="SUCCESS",
                failure_code=None,
                started_at=now,
                finished_at=now,
                payload={"status": "not_in_combat", "screen": screen_state},
            )

        # SP management decision
        if current_sp >= 3:
            action = "skill"
            sp_change = -1
            new_sp = current_sp + sp_change
        elif current_sp >= 2:
            action = "skill"  # still use skill at SP>=2
            sp_change = -1
            new_sp = current_sp + sp_change
        else:
            action = "basic_attack"
            sp_change = +1
            new_sp = min(current_sp + sp_change, 5)

        # Update SP slot
        if sp_slot:
            sp_slot.put({"current": new_sp, "max": 5})

        return SkillResult(
            skill_name=self.name,
            status="SUCCESS",
            failure_code=None,
            started_at=now,
            finished_at=now,
            payload={
                "action": action,
                "sp_before": current_sp,
                "sp_after": new_sp,
                "sp_change": sp_change,
            },
        )


class HSRNavigationSkill:
    """HSR map-based navigation skill."""
    name = "HSRNavigationSkill"

    def __init__(self, state_bus: StateBus, timebase: Timebase | None = None) -> None:
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()

    def run(self) -> SkillResult:
        now = self._timebase.now()
        return SkillResult(
            skill_name=self.name,
            status="SUCCESS",
            failure_code=None,
            started_at=now,
            finished_at=now,
            payload={"action": "navigate", "method": "map_teleport"},
        )


class HSRSimpleSkill:
    """Simple pass-through skill for menu/dialog/screen_classification."""

    def __init__(self, skill_id: str, timebase: Timebase | None = None) -> None:
        self.name = skill_id
        self.skill_id = skill_id
        self._timebase = timebase or Timebase()

    def run(self) -> SkillResult:
        now = self._timebase.now()
        return SkillResult(
            skill_name=self.skill_id,
            status="SUCCESS",
            failure_code=None,
            started_at=now,
            finished_at=now,
            payload={"capsule_id": "hsr", "skill_id": self.skill_id},
        )

    def execute(self, params: dict | None = None) -> dict:
        result = self.run()
        return {"status": result.status, "skill_id": self.skill_id}
