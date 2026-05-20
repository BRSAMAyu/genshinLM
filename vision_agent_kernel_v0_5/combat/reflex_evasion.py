from __future__ import annotations

from core.events import Interrupt
from core.timebase import Timebase
from combat.danger_detector import DangerDetector
from combat.dodge_policy import DodgePolicy


class ReflexEvasion:
    def __init__(self, timebase: Timebase | None = None) -> None:
        self._timebase = timebase or Timebase()
        self._detector = DangerDetector()
        self._policy = DodgePolicy()

    def evaluate(
        self,
        signals: dict[str, float],
        context_priority: float = 0.0,
        checkpoint: str | None = None,
    ) -> tuple[Interrupt | None, dict[str, object] | None]:
        danger = self._detector.evaluate(signals, context_priority=context_priority)
        if danger.level != "HIGH":
            return None, None
        dodge = self._policy.choose_dodge(danger)
        interrupt = Interrupt(
            priority=1,
            timestamp=self._timebase.now(),
            code="DODGE_REFLEX",
            source="reflex_evasion",
            payload={
                "danger_score": danger.score,
                "dominant_signal": danger.dominant_signal,
                "checkpoint": checkpoint,
                "dodge": dodge,
            },
        )
        return interrupt, dodge
