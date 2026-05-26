"""Tests for ScreenStateTree and ActionMask."""
from __future__ import annotations

import pytest

from perception.screen_state_tree import (
    ModalState,
    NormalizedRect,
    RegionNode,
    ScreenStateTree,
    TextBlock,
    UIElementNode,
)
from planning.action_mask import ActionMask, MaskedAction


# -- Helpers --

def _rect(left: float = 0.0, top: float = 0.0, right: float = 1.0, bottom: float = 1.0) -> NormalizedRect:
    return NormalizedRect(left, top, right, bottom)


def _element(
    element_id: str = "e1",
    role: str = "button",
    text: str = "OK",
    clickable: bool = True,
    enabled: bool = True,
) -> UIElementNode:
    return UIElementNode(
        element_id=element_id,
        semantic_role=role,
        text=text,
        bbox_norm=_rect(),
        clickable=clickable,
        enabled=enabled,
    )


def _tree(page_id: str = "world_viewport", elements: tuple[UIElementNode, ...] = ()) -> ScreenStateTree:
    return ScreenStateTree(
        frame_id=1,
        game_id="test",
        screen_state=page_id,
        page_id=page_id,
        confidence=0.9,
        elements=elements,
    )


class TestNormalizedRect:
    def test_center(self) -> None:
        r = _rect(0.2, 0.3, 0.8, 0.7)
        assert r.center == (0.5, 0.5)

    def test_area(self) -> None:
        r = _rect(0.0, 0.0, 0.5, 0.5)
        assert r.area == pytest.approx(0.25)


class TestScreenStateTree:
    def test_find_element_by_role(self) -> None:
        elements = (
            _element("e1", "dialog_option", "Option A"),
            _element("e2", "button", "Continue"),
        )
        tree = _tree("dialogue", elements)
        assert tree.find_element_by_role("dialog_option") is not None
        assert tree.find_element_by_role("dialog_option").text == "Option A"

    def test_find_element_by_text(self) -> None:
        elements = (
            _element("e1", "button", "Continue"),
            _element("e2", "button", "Cancel"),
        )
        tree = _tree("dialogue", elements)
        found = tree.find_element_by_text("cancel")
        assert len(found) == 1

    def test_clickable_elements(self) -> None:
        elements = (
            _element("e1", "button", "Click Me", clickable=True),
            _element("e2", "label", "Read Only", clickable=False),
        )
        tree = _tree("world_viewport", elements)
        clickable = tree.clickable_elements()
        assert len(clickable) == 1

    def test_dialog_options(self) -> None:
        elements = (
            _element("d1", "dialog_option", "Yes"),
            _element("d2", "dialog_option", "No"),
            _element("b1", "button", "OK"),
        )
        tree = _tree("dialogue", elements)
        assert len(tree.dialog_options()) == 2

    def test_quest_entries(self) -> None:
        elements = (
            _element("q1", "quest_entry", "Main Quest: Prologue"),
            _element("b1", "button", "Track"),
        )
        tree = _tree("quest_log", elements)
        assert len(tree.quest_entries()) == 1

    def test_with_modal(self) -> None:
        modal = ModalState("dialog", "Choose your path", ("Path A", "Path B"))
        tree = ScreenStateTree(
            frame_id=1, game_id="test", screen_state="dialogue",
            page_id="dialogue", confidence=0.9, active_modal=modal,
        )
        assert tree.active_modal is not None
        assert tree.active_modal.options == ("Path A", "Path B")

    def test_to_dict(self) -> None:
        tree = _tree("world_viewport", (_element(),))
        d = tree.to_dict()
        assert d["page_id"] == "world_viewport"
        assert d["element_count"] == 1


class TestActionMask:
    def setup_method(self) -> None:
        self.mask = ActionMask()

    def test_world_allows_movement(self) -> None:
        assert self.mask.is_action_allowed("world_viewport", "wasd_move")
        assert self.mask.is_action_allowed("world_viewport", "observe")

    def test_dialogue_forbids_movement(self) -> None:
        assert not self.mask.is_action_allowed("dialogue", "wasd_move")
        assert not self.mask.is_action_allowed("dialogue", "normal_attack")

    def test_combat_allows_combat_actions(self) -> None:
        assert self.mask.is_action_allowed("combat", "normal_attack")
        assert self.mask.is_action_allowed("combat", "e_skill")
        assert self.mask.is_action_allowed("combat", "q_burst")

    def test_map_forbids_combat(self) -> None:
        assert not self.mask.is_action_allowed("map", "normal_attack")
        assert self.mask.is_action_allowed("map", "select_marker")

    def test_unknown_restricts_to_safe(self) -> None:
        assert self.mask.is_action_allowed("unknown", "observe")
        assert self.mask.is_action_allowed("unknown", "back")
        assert not self.mask.is_action_allowed("unknown", "wasd_move")
        assert not self.mask.is_action_allowed("unknown", "normal_attack")

    def test_forbidden_actions_always_rejected(self) -> None:
        assert not self.mask.is_action_allowed("world_viewport", "raw_coordinate_click")
        assert not self.mask.is_action_allowed("world_viewport", "bypass_safety")

    def test_validate_action_returns_reason(self) -> None:
        ok, reason = self.mask.validate_action("dialogue", "advance_dialogue")
        assert ok
        assert reason == "allowed"

        ok, reason = self.mask.validate_action("dialogue", "wasd_move")
        assert not ok
        assert "not in mask" in reason

    def test_combat_allowed_only_in_combat_pages(self) -> None:
        assert self.mask.combat_allowed("world_viewport")
        assert self.mask.combat_allowed("combat")
        assert not self.mask.combat_allowed("dialogue")
        assert not self.mask.combat_allowed("map")

    def test_movement_only_in_world(self) -> None:
        assert self.mask.movement_allowed("world_viewport")
        assert not self.mask.movement_allowed("combat")
        assert not self.mask.movement_allowed("dialogue")

    def test_action_ids(self) -> None:
        ids = self.mask.action_ids("dialogue")
        assert "advance_dialogue" in ids
        assert "wasd_move" not in ids

    def test_custom_mask_override(self) -> None:
        custom = ActionMask(custom_masks={
            "custom_page": (
                MaskedAction("custom_action", "Custom", "ui"),
            ),
        })
        assert custom.is_action_allowed("custom_page", "custom_action")
        assert not custom.is_action_allowed("custom_page", "wasd_move")

    def test_character_menu_actions(self) -> None:
        assert self.mask.is_action_allowed("character_menu", "select_tab")
        assert self.mask.is_action_allowed("character_menu", "back")
        assert not self.mask.is_action_allowed("character_menu", "normal_attack")

    def test_loading_only_observe_wait(self) -> None:
        assert self.mask.is_action_allowed("loading", "observe")
        assert self.mask.is_action_allowed("loading", "wait")
        assert not self.mask.is_action_allowed("loading", "wasd_move")
