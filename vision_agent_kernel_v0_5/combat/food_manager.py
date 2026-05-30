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


class FoodManager:
    """Manage food/potion usage during combat and death recovery."""

    def use_healing_food(self, backend: SafeWindowInputBackend) -> bool:
        """Quick-use healing food via bag shortcut. Returns True if executed."""
        try:
            backend.key_press("b", reason="open_bag_for_food")
            _chunked_sleep(0.5)
            backend.key_press("right", reason="food_tab")
            _chunked_sleep(0.3)
            backend.key_press("enter", reason="use_food")
            _chunked_sleep(0.3)
            backend.key_press("escape", reason="close_bag")
            _chunked_sleep(0.3)
            log.info("[FoodManager] healing food used")
            return True
        except Exception as exc:
            log.warning("[FoodManager] use_healing_food failed: %s", exc)
            return False

    def use_revival_food(self, backend: SafeWindowInputBackend) -> bool:
        """Use revival food from death screen. Returns True if executed."""
        try:
            backend.mouse_click(0.5, 0.55, reason="revive_with_food")
            _chunked_sleep(0.5)
            backend.key_press("enter", reason="confirm_revival_food")
            _chunked_sleep(0.5)
            log.info("[FoodManager] revival food used")
            return True
        except Exception as exc:
            log.warning("[FoodManager] use_revival_food failed: %s", exc)
            return False
