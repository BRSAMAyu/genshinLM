from __future__ import annotations

import time
from dataclasses import dataclass

from combat.danger_detector import DangerState


@dataclass(slots=True)
class DodgePolicyState:
    last_dodge_at: float = 0.0
    consecutive_dodges: int = 0
    last_result: str = "idle"


class DodgePolicy:
    def __init__(self, min_interval_ms: int = 500, max_consecutive_dodges: int = 3, recovery_window_ms: int = 1200) -> None:
        self._min_interval = min_interval_ms / 1000.0
        self._max_consecutive = max_consecutive_dodges
        self._recovery_window = recovery_window_ms / 1000.0
        self._state = DodgePolicyState()

    def choose_dodge(self, danger: DangerState) -> dict[str, object]:
        now = time.time()
        if now - self._state.last_dodge_at < self._min_interval:
            cooldown_ms = int((self._min_interval - (now - self._state.last_dodge_at)) * 1000)
            self._state.last_result = "cooldown"
            return {
                "ok": False,
                "reason": "cooldown",
                "cooldown_ms": cooldown_ms,
                "consecutive_dodges": self._state.consecutive_dodges,
                "resume": "hold_current_checkpoint",
            }
        if now - self._state.last_dodge_at > self._recovery_window:
            self._state.consecutive_dodges = 0
        if self._state.consecutive_dodges >= self._max_consecutive:
            self._state.last_result = "max_consecutive_dodges"
            return {
                "ok": False,
                "reason": "max_consecutive_dodges",
                "cooldown_ms": int(self._recovery_window * 1000),
                "consecutive_dodges": self._state.consecutive_dodges,
                "resume": "fallback_basic_loop",
            }
        self._state.last_dodge_at = now
        self._state.consecutive_dodges += 1
        self._state.last_result = "executed"
        direction = "right" if danger.components.get("projectile_threat_score", 0.0) >= danger.components.get("generic_warning_score", 0.0) else "left"
        return {
            "ok": True,
            "intent": "DODGE",
            "direction": direction,
            "lease_ms": 180,
            "resume": "reacquire_target_or_resume_checkpoint",
            "consecutive_dodges": self._state.consecutive_dodges,
            "cooldown_ms": int(self._min_interval * 1000),
            "reason": danger.dominant_signal,
        }

    def snapshot(self) -> dict[str, object]:
        now = time.time()
        cooldown_ms = max(0, int((self._min_interval - (now - self._state.last_dodge_at)) * 1000))
        return {
            "cooldown_ms": cooldown_ms,
            "consecutive_dodges": self._state.consecutive_dodges,
            "last_result": self._state.last_result,
            "max_consecutive_dodges": self._max_consecutive,
        }
