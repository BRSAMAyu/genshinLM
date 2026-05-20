from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CombatCheckpoint:
    checkpoint_id: str
    combo_step: str
    target_state: str
    remaining_steps: list[str] = field(default_factory=list)


class CheckpointRuntime:
    def __init__(self) -> None:
        self._latest: CombatCheckpoint | None = None

    def save(self, checkpoint_id: str, combo_step: str, target_state: str = "visible", remaining_steps: list[str] | None = None) -> CombatCheckpoint:
        self._latest = CombatCheckpoint(checkpoint_id, combo_step, target_state, remaining_steps or [])
        return self._latest

    def resume(self) -> CombatCheckpoint | None:
        return self._latest

    def resume_plan(self) -> dict[str, object]:
        if self._latest is None:
            return {"ok": False, "reason": "no checkpoint", "steps": []}
        return {
            "ok": True,
            "checkpoint_id": self._latest.checkpoint_id,
            "resume_from": self._latest.combo_step,
            "target_state": self._latest.target_state,
            "steps": self._latest.remaining_steps,
        }
