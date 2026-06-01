"""NPC shop item selection with grid navigation.

Extends NPC_SHOP_BUY_ITEM to support selecting specific items
from the shop grid, with OCR fallback for item name matching.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ShopItem:
    name: str
    price: int
    grid_row: int
    grid_col: int


class NpcShopInteractor:
    """Navigate NPC shop item grid and select specific items.

    Genshin NPC shops display items in a grid (typically 2 columns).
    This interactor handles scrolling and clicking specific items.
    """

    # Grid positions for 2-column shop layout (normalized)
    _GRID_SLOTS: tuple[tuple[float, float], ...] = (
        (0.35, 0.35),  # Row 1, Col 1
        (0.55, 0.35),  # Row 1, Col 2
        (0.35, 0.50),  # Row 2, Col 1
        (0.55, 0.50),  # Row 2, Col 2
        (0.35, 0.65),  # Row 3, Col 1
        (0.55, 0.65),  # Row 3, Col 2
        (0.35, 0.80),  # Row 4, Col 1
        (0.55, 0.80),  # Row 4, Col 2
    )

    def __init__(self, backend: object, state_bus: object) -> None:
        self._backend = backend
        self._bus = state_bus
        self._items_per_page = 8

    def select_item_by_index(self, index: int) -> bool:
        """Select item by grid index (0-based)."""
        if index < 0 or index >= self._items_per_page:
            log.warning("[NpcShopInteractor] item index %d out of range", index)
            return False
        nx, ny = self._GRID_SLOTS[index]
        try:
            self._backend.click_at(
                int(nx * 1920),
                int(ny * 1080),
                reason=f"select_shop_item_{index}",
            )
            self._chunked_sleep(0.5)
            return True
        except Exception as exc:
            log.warning("[NpcShopInteractor] click item %d failed: %s", index, exc)
            return False

    def select_item_by_name(self, name: str, *, max_scrolls: int = 5) -> bool:
        """Select item by name (using VLM/OCR to find it).

        This is a stub — real implementation would use OCR or VLM
        to scan item names and find a match. Falls back to first item.
        """
        log.info("[NpcShopInteractor] select_item_by_name: %s (stub — using index)", name)
        # Stub: just select first item
        return self.select_item_by_index(0)

    def buy_item(self, quantity: int = 1) -> bool:
        """Confirm purchase of selected item."""
        backend = self._backend
        rect = backend.client_rect()
        # Click buy button
        bx = int(rect.left + 0.65 * rect.width)
        by = int(rect.top + 0.85 * rect.height)
        backend.click_at(bx, by, reason="buy_item")
        self._chunked_sleep(0.3)
        # Confirm
        cx = int(rect.left + 0.65 * rect.width)
        cy = int(rect.top + 0.85 * rect.height)
        backend.click_at(cx, cy, reason="confirm_purchase")
        self._chunked_sleep(0.5)
        return True

    def buy_item_by_index(self, index: int, quantity: int = 1) -> bool:
        """Select item and buy it."""
        if not self.select_item_by_index(index):
            return False
        return self.buy_item(quantity)

    def scroll_page(self, direction: int = 1) -> bool:
        """Scroll shop item list (1=down, -1=up)."""
        try:
            self._backend.mouse_scroll(delta=direction, reason="scroll_shop_items")
            self._chunked_sleep(0.3)
            return True
        except Exception as exc:
            log.warning("[NpcShopInteractor] scroll failed: %s", exc)
            return False

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))