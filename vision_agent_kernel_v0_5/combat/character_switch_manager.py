from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend

log = logging.getLogger(__name__)


def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
    import time
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))


class CharacterSwitchManager:
    """Manage character switching during combat."""

    def __init__(self, backend: SafeWindowInputBackend) -> None:
        self._backend = backend
        self._switch_cooldown = 1.0
        self._last_switch_time = 0.0

    def switch_to(self, slot: int, reason: str = "") -> bool:
        """Switch to character slot (1-4). Returns True if switch was executed."""
        if slot < 1 or slot > 4:
            return False
        import time
        now = time.perf_counter()
        if now - self._last_switch_time < self._switch_cooldown:
            return False
        try:
            self._backend.key_press(str(slot), reason=f"switch_char_{slot}_{reason}")
        except Exception:
            return False
        self._last_switch_time = now
        _chunked_sleep(0.5)  # switch animation
        return True

    def switch_to_healthiest(self, hp_ratios: list[float]) -> int | None:
        """Switch to character with highest HP. Returns slot number or None."""
        if not hp_ratios:
            return None
        best_idx = max(range(len(hp_ratios)), key=lambda i: hp_ratios[i])
        slot = best_idx + 1
        if self.switch_to(slot, reason="survival"):
            return slot
        return None

    def get_recommended_switch(self, context: dict) -> int | None:
        """Recommend character switch based on combat context."""
        hp_ratios = context.get("hp_ratios", [1.0, 1.0, 1.0, 1.0])
        active_hp = hp_ratios[0] if hp_ratios else 1.0
        if active_hp < 0.3:
            return self.switch_to_healthiest(hp_ratios)
        return None
