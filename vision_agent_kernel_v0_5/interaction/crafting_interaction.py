from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend

log = logging.getLogger(__name__)


class CraftingInteraction:
    """Cooking and forging interaction."""

    def cook_recipe(
        self,
        backend: SafeWindowInputBackend,
        recipe_name: str = "",
    ) -> bool:
        """Cook at a cooking station. Returns True if cooking completed."""
        try:
            backend.key_press("f", reason="interact_cooking")
            time.sleep(1.0)
            if recipe_name:
                log.info("[CraftingInteraction] cooking: %s", recipe_name)
            backend.mouse_click(0.5, 0.8, reason="auto_cook")
            time.sleep(0.5)
            backend.key_press("enter", reason="confirm_cook")
            time.sleep(0.5)
            backend.key_press("escape", reason="close_cooking")
            time.sleep(0.3)
            log.info("[CraftingInteraction] cooking completed")
            return True
        except Exception as exc:
            log.warning("[CraftingInteraction] cook_recipe failed: %s", exc)
            return False

    def forge_item(
        self,
        backend: SafeWindowInputBackend,
        item_name: str = "",
    ) -> bool:
        """Forge at a forging station. Returns True if forging initiated."""
        try:
            backend.key_press("f", reason="interact_forge")
            time.sleep(1.0)
            if item_name:
                log.info("[CraftingInteraction] forging: %s", item_name)
            backend.mouse_click(0.5, 0.8, reason="forge_item")
            time.sleep(0.5)
            backend.key_press("enter", reason="confirm_forge")
            time.sleep(0.5)
            backend.key_press("escape", reason="close_forge")
            time.sleep(0.3)
            log.info("[CraftingInteraction] forging completed")
            return True
        except Exception as exc:
            log.warning("[CraftingInteraction] forge_item failed: %s", exc)
            return False
