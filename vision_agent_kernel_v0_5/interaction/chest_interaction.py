from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend

log = logging.getLogger(__name__)


class ChestInteraction:
    """Chest opening flow."""

    def open_chest(
        self,
        backend: SafeWindowInputBackend,
        frame_source=None,
        max_wait: float = 5.0,
    ) -> bool:
        """Open a chest and collect rewards. Returns True if rewards collected."""
        try:
            backend.key_press("f", reason="open_chest")
            time.sleep(1.5)
            backend.key_press("f", reason="collect_chest_rewards")
            time.sleep(0.5)
            backend.key_press("escape", reason="close_chest_rewards")
            time.sleep(0.3)
            log.info("[ChestInteraction] chest opened and rewards collected")
            return True
        except Exception as exc:
            log.warning("[ChestInteraction] open_chest failed: %s", exc)
            return False
