from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend

log = logging.getLogger(__name__)


class StatueInteraction:
    """Seven Statues of The Seven interaction."""

    def heal_at_statue(
        self,
        backend: SafeWindowInputBackend,
        classifier: Any | None = None,
    ) -> bool:
        """Interact with statue to heal party. Returns True if interaction completed."""
        try:
            backend.key_press("f", reason="statue_interact")
            time.sleep(1.0)
            backend.key_press("escape", reason="close_statue_menu")
            time.sleep(0.3)
            log.info("[StatueInteraction] healed at statue")
            return True
        except Exception as exc:
            log.warning("[StatueInteraction] heal_at_statue failed: %s", exc)
            return False

    def activate_statue(self, backend: SafeWindowInputBackend) -> bool:
        """Activate an unlocked statue. Returns True if successful."""
        try:
            backend.key_press("f", reason="activate_statue")
            time.sleep(2.0)
            log.info("[StatueInteraction] activated statue")
            return True
        except Exception as exc:
            log.warning("[StatueInteraction] activate_statue failed: %s", exc)
            return False
