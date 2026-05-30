"""UI operation primitives for Genshin Impact menu interactions.

Covers U-13 through U-22 atomic UI capabilities:
- U-13: Tab switching within menus
- U-14: List scrolling to target items
- U-15: Confirm/cancel popup handling
- U-16: Quantity selection in numeric selectors
- U-17: Dropdown menu selection
- U-18: Drag-and-drop for party configuration
- U-19: Map zoom/pan controls
- U-20: Auto-identify current UI page
- U-21: Multi-tab navigation (adventurer's handbook)
- U-22: Search/filter in item lists

All operations build UIFlow steps compatible with UIFlowExecutor.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from interaction.ui_flow_engine import (
    STEP_CLICK_AT,
    STEP_CONFIRM,
    STEP_CANCEL,
    STEP_DELAY,
    STEP_HOLD_CLICK,
    STEP_PRESS_KEY,
    STEP_SCROLL,
    STEP_SCROLL_DOWN,
    STEP_SCROLL_UP,
    STEP_WAIT_STATE,
    UIStep,
)

# ---------------------------------------------------------------------------
# Normalised coordinate constants
# ---------------------------------------------------------------------------

# Character screen tabs
CHAR_TAB_X: dict[str, float] = {
    "details": 0.25,
    "weapon": 0.35,
    "artifacts": 0.45,
    "talents": 0.55,
    "constellation": 0.65,
}
CHAR_TAB_Y: float = 0.06

# Backpack tabs
BACKPACK_TAB_X: dict[str, float] = {
    "weapons": 0.15,
    "artifacts": 0.25,
    "character_dev": 0.35,
    "food": 0.45,
    "materials": 0.55,
    "gadgets": 0.65,
    "quests": 0.75,
}
BACKPACK_TAB_Y: float = 0.08

# Adventure handbook tabs (6 tabs)
HANDBOOK_TAB_X: dict[str, float] = {
    "chapters": 0.15,
    "enemies": 0.30,
    "domains": 0.45,
    "collection": 0.60,
    "guide": 0.75,
    "bonus": 0.88,
}
HANDBOOK_TAB_Y: float = 0.08

# Quantity selector area
QTY_MINUS_X: float = 0.35
QTY_PLUS_X: float = 0.55
QTY_SLIDER_Y: float = 0.72
QTY_MAX_BUTTON_X: float = 0.70

# Filter/search area
FILTER_BUTTON_X: float = 0.90
FILTER_BUTTON_Y: float = 0.08
SEARCH_INPUT_X: float = 0.80
SEARCH_INPUT_Y: float = 0.12

# Party slots (4 positions)
PARTY_SLOT_X: list[float] = [0.25, 0.42, 0.58, 0.75]
PARTY_SLOT_Y: float = 0.50

# Map controls
MAP_ZOOM_IN_X: float = 0.92
MAP_ZOOM_OUT_X: float = 0.92
MAP_ZOOM_Y: float = 0.70

# Dropdown default area
DROPDOWN_ARROW_X: float = 0.85
DROPDOWN_DROP_Y_START: float = 0.20
DROPDOWN_DROP_Y_STEP: float = 0.06


class UIPage(str, Enum):
    """Identifiable UI pages in Genshin Impact."""
    OVERWORLD = "overworld"
    COMBAT = "combat"
    DIALOG = "dialog"
    LOADING = "loading_screen"
    PAIMON_MENU = "paimon_menu"
    CHARACTER_SCREEN = "character_screen"
    BACKPACK = "backpack"
    MAP = "map"
    QUEST_MENU = "quest_menu"
    PARTY_SETUP = "party_setup"
    WISH = "wish"
    ADVENTURE_HANDBOOK = "adventure_handbook"
    BATTLE_PASS = "battle_pass"
    EVENTS = "events"
    SHOP = "shop"
    DOMAIN = "domain"
    COOKING = "cooking"
    CRAFTING = "crafting"
    SETTINGS = "settings"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Step builder functions (U-13 ~ U-22)
# ---------------------------------------------------------------------------

def tab_switch(tab_name: str, *, tab_positions: dict[str, float] | None = None,
               tab_y: float = 0.06, delay_ms: int = 500) -> UIStep:
    """U-13: Switch to a named tab within a menu.

    Looks up the tab's normalised x position and clicks it.
    """
    positions = tab_positions or CHAR_TAB_X
    nx = positions.get(tab_name)
    if nx is None:
        raise ValueError(f"Unknown tab {tab_name!r}. Known: {sorted(positions)}")
    return UIStep(
        type=STEP_CLICK_AT,
        nx=nx,
        ny=tab_y,
        delay_ms=delay_ms,
        reason=f"tab_switch:{tab_name}",
    )


def list_scroll_to(item_index: int, items_per_page: int = 7,
                   scroll_per_item: int = 3) -> list[UIStep]:
    """U-14: Scroll a list to bring item_index into view.

    Returns a list of scroll steps. Items are 0-indexed.
    """
    if item_index < items_per_page:
        # Item is visible without scrolling
        return []

    scroll_needed = (item_index - items_per_page + 1) * scroll_per_item
    steps: list[UIStep] = []
    for _ in range(scroll_needed):
        steps.append(UIStep(
            type=STEP_SCROLL_DOWN,
            delta=1,
            reason="scroll_list_down",
        ))
    return steps


def list_click_item(item_row: int, list_x: float = 0.30,
                    list_top_y: float = 0.25, row_height: float = 0.08) -> UIStep:
    """Click on item at given row (0-indexed) in a list."""
    ny = list_top_y + item_row * row_height
    return UIStep(
        type=STEP_CLICK_AT,
        nx=list_x,
        ny=ny,
        delay_ms=300,
        reason=f"click_list_item_row_{item_row}",
    )


def confirm_popup(confirm_x: float = 0.65, confirm_y: float = 0.85) -> UIStep:
    """U-15: Click confirm on a popup dialog."""
    return UIStep(
        type=STEP_CLICK_AT,
        nx=confirm_x,
        ny=confirm_y,
        delay_ms=300,
        reason="confirm_popup",
    )


def cancel_popup(cancel_x: float = 0.35, cancel_y: float = 0.85) -> UIStep:
    """U-15: Click cancel on a popup dialog."""
    return UIStep(
        type=STEP_CLICK_AT,
        nx=cancel_x,
        ny=cancel_y,
        delay_ms=300,
        reason="cancel_popup",
    )


def quantity_adjust(target: int, current: int = 0, step: int = 1) -> list[UIStep]:
    """U-16: Adjust quantity selector to reach target from current.

    Clicks +/- buttons or the max button.
    """
    if target <= current:
        return []

    steps: list[UIStep] = []
    # Check if we should use max button (target >= 99)
    if target >= 99:
        steps.append(UIStep(
            type=STEP_CLICK_AT,
            nx=QTY_MAX_BUTTON_X,
            ny=QTY_SLIDER_Y,
            delay_ms=300,
            reason="quantity_max",
        ))
        return steps

    clicks_needed = (target - current) // step
    for _ in range(clicks_needed):
        steps.append(UIStep(
            type=STEP_CLICK_AT,
            nx=QTY_PLUS_X,
            ny=QTY_SLIDER_Y,
            delay_ms=100,
            reason="quantity_plus",
        ))
    return steps


def dropdown_select(option_index: int, dropdown_x: float = 0.85,
                    option_start_y: float = 0.20, option_step_y: float = 0.06) -> list[UIStep]:
    """U-17: Open dropdown and select option by index (0-indexed).

    Clicks the dropdown arrow then the option row.
    """
    return [
        # Open dropdown
        UIStep(
            type=STEP_CLICK_AT,
            nx=dropdown_x,
            ny=option_start_y - 0.03,
            delay_ms=300,
            reason="open_dropdown",
        ),
        # Select option
        UIStep(
            type=STEP_CLICK_AT,
            nx=dropdown_x - 0.15,
            ny=option_start_y + option_index * option_step_y,
            delay_ms=300,
            reason=f"select_dropdown_option_{option_index}",
        ),
    ]


def drag_drop_party_slot(from_slot: int, to_slot: int,
                         hold_ms: int = 800) -> list[UIStep]:
    """U-18: Drag character from one party slot to another.

    Uses hold_click at source position, then click at destination.
    """
    if from_slot < 0 or from_slot > 3 or to_slot < 0 or to_slot > 3:
        raise ValueError("Party slots must be 0-3")

    return [
        # Pick up character at source slot
        UIStep(
            type=STEP_HOLD_CLICK,
            nx=PARTY_SLOT_X[from_slot],
            ny=PARTY_SLOT_Y,
            hold_ms=hold_ms,
            delay_ms=200,
            reason=f"drag_from_slot_{from_slot}",
        ),
        # Drop at destination slot
        UIStep(
            type=STEP_CLICK_AT,
            nx=PARTY_SLOT_X[to_slot],
            ny=PARTY_SLOT_Y,
            delay_ms=300,
            reason=f"drop_to_slot_{to_slot}",
        ),
    ]


def map_zoom(clicks: int = 3) -> list[UIStep]:
    """U-19: Zoom the map. Positive = zoom in, negative = zoom out."""
    steps: list[UIStep] = []
    for _ in range(abs(clicks)):
        if clicks > 0:
            steps.append(UIStep(
                type=STEP_CLICK_AT,
                nx=MAP_ZOOM_IN_X,
                ny=MAP_ZOOM_Y,
                delay_ms=100,
                reason="map_zoom_in",
            ))
        else:
            steps.append(UIStep(
                type=STEP_CLICK_AT,
                nx=MAP_ZOOM_OUT_X,
                ny=MAP_ZOOM_Y + 0.06,
                delay_ms=100,
                reason="map_zoom_out",
            ))
    return steps


def map_pan(dx: float, dy: float) -> list[UIStep]:
    """U-19: Pan the map by clicking at offset from center.

    dx/dy in normalised coordinates, typically -0.3 to 0.3.
    """
    cx = 0.50 + dx
    cy = 0.50 + dy
    return [
        UIStep(
            type=STEP_HOLD_CLICK,
            nx=cx,
            ny=cy,
            hold_ms=500,
            delay_ms=300,
            reason=f"map_pan_dx{dx:.1f}_dy{dy:.1f}",
        ),
    ]


def handbook_tab(tab_name: str) -> UIStep:
    """U-21: Switch tabs in the adventurer's handbook."""
    return tab_switch(tab_name, tab_positions=HANDBOOK_TAB_X,
                      tab_y=HANDBOOK_TAB_Y, delay_ms=500)


def filter_open() -> UIStep:
    """U-22: Open filter panel."""
    return UIStep(
        type=STEP_CLICK_AT,
        nx=FILTER_BUTTON_X,
        ny=FILTER_BUTTON_Y,
        delay_ms=500,
        reason="open_filter",
    )


def filter_option(option_index: int, filter_x: float = 0.85,
                  option_start_y: float = 0.20, option_step_y: float = 0.06) -> UIStep:
    """U-22: Select a filter option from the filter panel."""
    return UIStep(
        type=STEP_CLICK_AT,
        nx=filter_x - 0.05,
        ny=option_start_y + option_index * option_step_y,
        delay_ms=300,
        reason=f"select_filter_option_{option_index}",
    )


def filter_confirm() -> UIStep:
    """U-22: Confirm filter selection."""
    return UIStep(
        type=STEP_CLICK_AT,
        nx=0.65,
        ny=0.85,
        delay_ms=300,
        reason="confirm_filter",
    )


# ---------------------------------------------------------------------------
# Page identification (U-20)
# ---------------------------------------------------------------------------

_STATE_MAP: dict[str, UIPage] = {
    "overworld": UIPage.OVERWORLD,
    "combat": UIPage.COMBAT,
    "dialog": UIPage.DIALOG,
    "loading_screen": UIPage.LOADING,
    "paimon_menu": UIPage.PAIMON_MENU,
    "character_screen": UIPage.CHARACTER_SCREEN,
    "backpack": UIPage.BACKPACK,
    "map": UIPage.MAP,
    "quest_menu": UIPage.QUEST_MENU,
    "party_setup": UIPage.PARTY_SETUP,
    "wish": UIPage.WISH,
    "adventure_handbook": UIPage.ADVENTURE_HANDBOOK,
    "battle_pass": UIPage.BATTLE_PASS,
    "events": UIPage.EVENTS,
    "shop": UIPage.SHOP,
    "domain": UIPage.DOMAIN,
    "cooking": UIPage.COOKING,
    "crafting": UIPage.CRAFTING,
    "settings": UIPage.SETTINGS,
}

_ESCAPE_DEPTH: dict[UIPage, int] = {
    UIPage.PAIMON_MENU: 1,
    UIPage.CHARACTER_SCREEN: 2,
    UIPage.BACKPACK: 2,
    UIPage.MAP: 1,
    UIPage.QUEST_MENU: 1,
    UIPage.PARTY_SETUP: 1,
    UIPage.WISH: 2,
    UIPage.ADVENTURE_HANDBOOK: 1,
    UIPage.BATTLE_PASS: 1,
    UIPage.EVENTS: 1,
    UIPage.SHOP: 2,
    UIPage.SETTINGS: 2,
    UIPage.DOMAIN: 1,
    UIPage.COOKING: 2,
    UIPage.CRAFTING: 2,
}


class PageIdentifier:
    """U-20: Identifies the current UI page from screen state.

    Maps known screen state strings to UIPage enum values.
    Works with GenshinScreenClassifier output.
    """

    def identify(self, screen_state: str) -> UIPage:
        """Map a screen state string to a UIPage enum."""
        return _STATE_MAP.get(screen_state, UIPage.UNKNOWN)

    def is_menu(self, page: UIPage) -> bool:
        """Check if the page is a menu (not gameplay)."""
        return page not in (
            UIPage.OVERWORLD, UIPage.COMBAT, UIPage.DIALOG,
            UIPage.LOADING, UIPage.UNKNOWN,
        )

    def escape_to_overworld_steps(self, current_page: UIPage) -> list[UIStep]:
        """Generate escape key presses to return to overworld from any page."""
        if current_page == UIPage.OVERWORLD:
            return []

        escapes = _ESCAPE_DEPTH.get(current_page, 1)
        steps: list[UIStep] = []
        for _ in range(escapes):
            steps.append(UIStep(
                type=STEP_PRESS_KEY,
                key="escape",
                delay_ms=300,
                reason="escape_to_overworld",
            ))
        return steps
