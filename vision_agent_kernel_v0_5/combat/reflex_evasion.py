import logging
from typing import Any
import numpy as np
from core.events import Interrupt
from core.timebase import Timebase
from combat.danger_detector import DangerDetector
from combat.dodge_policy import DodgePolicy

log = logging.getLogger(__name__)


class ReflexEvasion:
    def __init__(self, timebase: Timebase | None = None) -> None:
        self._timebase = timebase or Timebase()
        self._detector = DangerDetector()
        self._policy = DodgePolicy()

    def check_and_dodge(
        self,
        frame: np.ndarray,
        prev_frame: np.ndarray | None = None,
        input_backend: Any = None,
    ) -> bool:
        """Evaluates raw frames at 50Hz and triggers a physical dodge reflex if danger level is HIGH."""
        from combat.danger_detector import GenshinDangerSignalExtractor
        extractor = GenshinDangerSignalExtractor()
        signals = extractor.extract(frame, prev_frame)
        should, dominant, priority = extractor.should_dodge(signals)
        if should:
            log.warning(f"[ReflexEvasion] HIGH THREAT DETECTED: {dominant} (Priority {priority})! Dodging instantly.")
            if input_backend is not None and hasattr(input_backend, "right_click"):
                input_backend.right_click(reason="50hz_combat_reflex_dodge")
            return True
        return False

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
