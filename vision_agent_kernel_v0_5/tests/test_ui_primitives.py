"""Tests for UI operation primitives (U-13~U-22)."""
from __future__ import annotations

import pytest

from interaction.ui_primitives import (
    CHAR_TAB_X,
    BACKPACK_TAB_X,
    HANDBOOK_TAB_X,
    PARTY_SLOT_X,
    UIPage,
    PageIdentifier,
    cancel_popup,
    confirm_popup,
    drag_drop_party_slot,
    dropdown_select,
    filter_confirm,
    filter_open,
    filter_option,
    handbook_tab,
    list_click_item,
    list_scroll_to,
    map_pan,
    map_zoom,
    quantity_adjust,
    tab_switch,
)
from interaction.ui_flow_engine import (
    STEP_CLICK_AT,
    STEP_HOLD_CLICK,
    STEP_PRESS_KEY,
    STEP_SCROLL_DOWN,
)


# ---------------------------------------------------------------------------
# Tab switching (U-13)
# ---------------------------------------------------------------------------
class TestTabSwitch:
    def test_known_tab(self) -> None:
        step = tab_switch("weapon")
        assert step.type == STEP_CLICK_AT
        assert step.nx == pytest.approx(CHAR_TAB_X["weapon"])

    def test_custom_tab_positions(self) -> None:
        custom = {"alpha": 0.10, "beta": 0.50}
        step = tab_switch("beta", tab_positions=custom)
        assert step.nx == pytest.approx(0.50)

    def test_unknown_tab_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tab"):
            tab_switch("nonexistent")

    def test_backpack_tab(self) -> None:
        step = tab_switch("food", tab_positions=BACKPACK_TAB_X,
                          tab_y=0.08, delay_ms=400)
        assert step.ny == pytest.approx(0.08)
        assert step.delay_ms == 400

    def test_has_reason(self) -> None:
        step = tab_switch("details")
        assert "details" in step.reason


# ---------------------------------------------------------------------------
# List scrolling (U-14)
# ---------------------------------------------------------------------------
class TestListScroll:
    def test_no_scroll_needed(self) -> None:
        steps = list_scroll_to(2, items_per_page=7)
        assert len(steps) == 0

    def test_scroll_needed(self) -> None:
        steps = list_scroll_to(10, items_per_page=7, scroll_per_item=3)
        assert len(steps) == 12  # (10-7+1) * 3 = 12
        assert all(s.type == STEP_SCROLL_DOWN for s in steps)

    def test_first_item_no_scroll(self) -> None:
        steps = list_scroll_to(0)
        assert len(steps) == 0


class TestListClickItem:
    def test_click_row_zero(self) -> None:
        step = list_click_item(0)
        assert step.ny == pytest.approx(0.25)

    def test_click_row_custom(self) -> None:
        step = list_click_item(3, list_x=0.40, list_top_y=0.20, row_height=0.10)
        assert step.ny == pytest.approx(0.50)
        assert step.nx == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# Confirm/cancel (U-15)
# ---------------------------------------------------------------------------
class TestConfirmCancel:
    def test_confirm_default(self) -> None:
        step = confirm_popup()
        assert step.type == STEP_CLICK_AT
        assert step.nx == pytest.approx(0.65)

    def test_cancel_default(self) -> None:
        step = cancel_popup()
        assert step.type == STEP_CLICK_AT
        assert step.nx == pytest.approx(0.35)

    def test_custom_positions(self) -> None:
        step = confirm_popup(confirm_x=0.50, confirm_y=0.90)
        assert step.nx == pytest.approx(0.50)
        assert step.ny == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# Quantity selection (U-16)
# ---------------------------------------------------------------------------
class TestQuantityAdjust:
    def test_no_adjustment_needed(self) -> None:
        steps = quantity_adjust(target=5, current=5)
        assert len(steps) == 0

    def test_zero_target(self) -> None:
        steps = quantity_adjust(target=0, current=0)
        assert len(steps) == 0

    def test_single_click(self) -> None:
        steps = quantity_adjust(target=1, current=0, step=1)
        assert len(steps) == 1
        assert steps[0].nx == pytest.approx(0.55)  # QTY_PLUS_X

    def test_multiple_clicks(self) -> None:
        steps = quantity_adjust(target=10, current=0, step=1)
        assert len(steps) == 10

    def test_large_step(self) -> None:
        steps = quantity_adjust(target=10, current=0, step=5)
        assert len(steps) == 2

    def test_max_button(self) -> None:
        steps = quantity_adjust(target=99, current=0)
        assert len(steps) == 1
        assert steps[0].nx == pytest.approx(0.70)  # QTY_MAX_BUTTON_X


# ---------------------------------------------------------------------------
# Dropdown selection (U-17)
# ---------------------------------------------------------------------------
class TestDropdownSelect:
    def test_select_option_zero(self) -> None:
        steps = dropdown_select(0)
        assert len(steps) == 2
        assert steps[0].reason == "open_dropdown"
        assert steps[1].reason == "select_dropdown_option_0"

    def test_select_option_custom_index(self) -> None:
        steps = dropdown_select(3)
        assert len(steps) == 2
        # Third option is further down
        assert steps[1].ny > steps[0].ny


# ---------------------------------------------------------------------------
# Drag-and-drop party (U-18)
# ---------------------------------------------------------------------------
class TestDragDropParty:
    def test_swap_slots(self) -> None:
        steps = drag_drop_party_slot(0, 3)
        assert len(steps) == 2
        assert steps[0].type == STEP_HOLD_CLICK
        assert steps[1].type == STEP_CLICK_AT
        assert steps[0].nx == pytest.approx(PARTY_SLOT_X[0])
        assert steps[1].nx == pytest.approx(PARTY_SLOT_X[3])

    def test_invalid_slot_raises(self) -> None:
        with pytest.raises(ValueError, match="0-3"):
            drag_drop_party_slot(0, 5)

    def test_negative_slot_raises(self) -> None:
        with pytest.raises(ValueError):
            drag_drop_party_slot(-1, 2)


# ---------------------------------------------------------------------------
# Map zoom/pan (U-19)
# ---------------------------------------------------------------------------
class TestMapZoom:
    def test_zoom_in(self) -> None:
        steps = map_zoom(clicks=3)
        assert len(steps) == 3
        assert all(s.reason == "map_zoom_in" for s in steps)

    def test_zoom_out(self) -> None:
        steps = map_zoom(clicks=-2)
        assert len(steps) == 2
        assert all(s.reason == "map_zoom_out" for s in steps)

    def test_zero_zoom(self) -> None:
        steps = map_zoom(clicks=0)
        assert len(steps) == 0


class TestMapPan:
    def test_pan_right(self) -> None:
        steps = map_pan(0.2, 0.0)
        assert len(steps) == 1
        assert steps[0].nx == pytest.approx(0.70)

    def test_pan_left(self) -> None:
        steps = map_pan(-0.2, 0.0)
        assert len(steps) == 1
        assert steps[0].nx == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Handbook tab (U-21)
# ---------------------------------------------------------------------------
class TestHandbookTab:
    def test_enemies_tab(self) -> None:
        step = handbook_tab("enemies")
        assert step.type == STEP_CLICK_AT
        assert step.nx == pytest.approx(HANDBOOK_TAB_X["enemies"])

    def test_unknown_tab_raises(self) -> None:
        with pytest.raises(ValueError):
            handbook_tab("nonexistent")


# ---------------------------------------------------------------------------
# Filter/search (U-22)
# ---------------------------------------------------------------------------
class TestFilter:
    def test_filter_open(self) -> None:
        step = filter_open()
        assert step.type == STEP_CLICK_AT
        assert "open_filter" in step.reason

    def test_filter_option(self) -> None:
        step = filter_option(2)
        assert step.type == STEP_CLICK_AT

    def test_filter_confirm(self) -> None:
        step = filter_confirm()
        assert step.type == STEP_CLICK_AT


# ---------------------------------------------------------------------------
# Page identifier (U-20)
# ---------------------------------------------------------------------------
class TestPageIdentifier:
    def test_identify_known(self) -> None:
        pid = PageIdentifier()
        assert pid.identify("overworld") == UIPage.OVERWORLD
        assert pid.identify("map") == UIPage.MAP
        assert pid.identify("character_screen") == UIPage.CHARACTER_SCREEN

    def test_identify_unknown(self) -> None:
        pid = PageIdentifier()
        assert pid.identify("weird_state") == UIPage.UNKNOWN

    def test_is_menu(self) -> None:
        pid = PageIdentifier()
        assert pid.is_menu(UIPage.CHARACTER_SCREEN)
        assert pid.is_menu(UIPage.MAP)
        assert not pid.is_menu(UIPage.OVERWORLD)
        assert not pid.is_menu(UIPage.COMBAT)

    def test_escape_from_overworld(self) -> None:
        pid = PageIdentifier()
        steps = pid.escape_to_overworld_steps(UIPage.OVERWORLD)
        assert len(steps) == 0

    def test_escape_from_character_screen(self) -> None:
        pid = PageIdentifier()
        steps = pid.escape_to_overworld_steps(UIPage.CHARACTER_SCREEN)
        assert len(steps) == 2
        assert all(s.key == "escape" for s in steps)

    def test_escape_from_map(self) -> None:
        pid = PageIdentifier()
        steps = pid.escape_to_overworld_steps(UIPage.MAP)
        assert len(steps) == 1

    def test_escape_from_unknown(self) -> None:
        pid = PageIdentifier()
        steps = pid.escape_to_overworld_steps(UIPage.UNKNOWN)
        assert len(steps) == 1  # default depth


# ---------------------------------------------------------------------------
# UIPage enum
# ---------------------------------------------------------------------------
class TestUIPageEnum:
    def test_all_pages_have_values(self) -> None:
        for page in UIPage:
            assert isinstance(page.value, str)
            assert len(page.value) > 0

    def test_page_count(self) -> None:
        assert len(UIPage) == 20  # 20 distinct pages
