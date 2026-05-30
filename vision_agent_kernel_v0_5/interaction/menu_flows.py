"""Paimon menu navigation flows for core game sub-systems.

Covers U-06 through U-12:
- U-06: Party configuration (L key → character drag/save)
- U-07: Wish system (F3 → banner select → pull)
- U-08: Adventurer's Handbook (F1 → tabs navigation)
- U-09: Battle Pass (F4 → daily/weekly rewards)
- U-10: Events panel (F5 → event navigation/rewards)
- U-11: Co-op / Friends (F2 → online mode)
- U-12: Settings menu (Esc → settings → graphics/control/audio)

All flows are built as UIFlow declarative step sequences, compatible
with UIFlowExecutor for interrupt-safe, state-aware execution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from interaction.ui_flow_engine import (
    UIFlow,
    UIStep,
    click,
    click_menu_button,
    confirm,
    cancel,
    delay,
    open_menu,
    press,
    scroll,
    wait_state,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UI page state constants
# ---------------------------------------------------------------------------

class MenuPage(str, Enum):
    """Screen states for game menus."""
    PAIMON_MENU = "paimon_menu"
    PARTY_SETUP = "party_setup"
    WISH_SCREEN = "wish_screen"
    HANDBOOK = "adventurer_handbook"
    BATTLE_PASS = "battle_pass"
    EVENTS = "events_panel"
    COOP = "coop_screen"
    SETTINGS = "settings_menu"
    WORLD = "world_hud"


# ---------------------------------------------------------------------------
# U-06: Party Configuration
# ---------------------------------------------------------------------------

def build_party_config_flow() -> UIFlow:
    """U-06: Open party configuration screen (L key or via Paimon menu)."""
    return UIFlow(
        name="MENU_PARTY_CONFIG",
        description="Open party configuration via L key",
        steps=(
            press("l", reason="open_party_config"),
            delay(500),
            wait_state("party_setup", timeout_ms=3000, reason="wait_party_screen"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


def build_party_config_via_menu_flow() -> UIFlow:
    """U-06 alt: Open party config through Paimon menu (fallback if L fails)."""
    return UIFlow(
        name="MENU_PARTY_VIA_MENU",
        description="Open party config through Paimon menu",
        steps=(
            press("escape", reason="open_paimon_menu"),
            delay(500),
            click_menu_button("party", delay_ms=300),
            wait_state("party_setup", timeout_ms=3000, reason="wait_party_screen"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


def build_party_save_flow(slot_name: str = "") -> UIFlow:
    """U-06: Save current party configuration."""
    steps: list[UIStep] = [
        # Click party save button (top-right area of party screen)
        click(0.90, 0.08, reason="click_party_save", delay_ms=300),
    ]
    if slot_name:
        steps.append(click(0.50, 0.50, reason="select_save_slot", delay_ms=200))
    steps.append(confirm(reason="confirm_party_save"))
    return UIFlow(
        name="MENU_PARTY_SAVE",
        description="Save current party configuration",
        steps=tuple(steps),
        precondition_state="party_setup",
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# U-07: Wish / Gacha System
# ---------------------------------------------------------------------------

def build_wish_open_flow() -> UIFlow:
    """U-07: Open wish/gacha screen via F3 key."""
    return UIFlow(
        name="MENU_WISH_OPEN",
        description="Open wish screen via F3",
        steps=(
            press("f3", reason="open_wish"),
            delay(800),
            wait_state("wish_screen", timeout_ms=5000, reason="wait_wish"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


def build_wish_ten_pull_flow() -> UIFlow:
    """U-07: Execute a 10-pull wish on the current banner."""
    return UIFlow(
        name="MENU_WISH_TEN_PULL",
        description="Execute 10-pull on current banner",
        steps=(
            # Click "Wish ×10" button
            click(0.50, 0.88, reason="click_ten_pull", delay_ms=500),
            # Confirm purchase
            confirm(reason="confirm_wish_pull"),
            delay(3000),
            # Wait for animation to complete
            click(0.50, 0.50, reason="skip_animation", delay_ms=2000),
            # Close results
            press("escape", reason="close_wish_results"),
        ),
        precondition_state="wish_screen",
        escape_on_failure=True,
    )


def build_wish_select_banner_flow(banner_position: int = 0) -> UIFlow:
    """U-07: Select a specific wish banner by position (0-3)."""
    # Banner tabs are at the top of the wish screen
    _BANNER_X = [0.15, 0.35, 0.55, 0.75]
    nx = _BANNER_X[min(banner_position, 3)]
    return UIFlow(
        name="MENU_WISH_SELECT_BANNER",
        description=f"Select wish banner at position {banner_position}",
        steps=(
            click(nx, 0.08, reason=f"select_banner_{banner_position}", delay_ms=500),
        ),
        precondition_state="wish_screen",
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# U-08: Adventurer's Handbook
# ---------------------------------------------------------------------------

def build_handbook_open_flow() -> UIFlow:
    """U-08: Open adventurer's handbook via F1 key."""
    return UIFlow(
        name="MENU_HANDBOOK_OPEN",
        description="Open adventurer's handbook via F1",
        steps=(
            press("f1", reason="open_handbook"),
            delay(500),
            wait_state("adventurer_handbook", timeout_ms=3000, reason="wait_handbook"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


# Handbook tab positions (6 tabs: Chapters, Enemies, Domains, Collection, ...)
_HANDBOOK_TAB_X: list[float] = [0.10, 0.25, 0.40, 0.55, 0.70, 0.85]
_HANDBOOK_TAB_Y: float = 0.10


def build_handbook_tab_flow(tab_index: int) -> UIFlow:
    """U-08: Switch to a specific handbook tab (0-5).

    Tabs: 0=Chapters, 1=Enemies, 2=Domains, 3=Collection,
          4=Guidance, 5=Reputation
    """
    if tab_index < 0 or tab_index > 5:
        raise ValueError(f"tab_index must be 0-5, got {tab_index}")
    return UIFlow(
        name=f"MENU_HANDBOOK_TAB_{tab_index}",
        description=f"Switch handbook to tab {tab_index}",
        steps=(
            click(_HANDBOOK_TAB_X[tab_index], _HANDBOOK_TAB_Y,
                  reason=f"handbook_tab_{tab_index}", delay_ms=300),
        ),
        precondition_state="adventurer_handbook",
        escape_on_failure=True,
    )


def build_handbook_track_enemy_flow() -> UIFlow:
    """U-08: Navigate to enemy tab and click track on first enemy."""
    return UIFlow(
        name="MENU_HANDBOOK_TRACK_ENEMY",
        description="Navigate to enemy tab and track first enemy",
        steps=(
            # Switch to Enemies tab (index 1)
            click(_HANDBOOK_TAB_X[1], _HANDBOOK_TAB_Y,
                  reason="handbook_enemy_tab", delay_ms=300),
            # Click track/navigate button for first enemy
            click(0.85, 0.30, reason="track_enemy", delay_ms=300),
        ),
        precondition_state="adventurer_handbook",
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# U-09: Battle Pass
# ---------------------------------------------------------------------------

def build_battle_pass_open_flow() -> UIFlow:
    """U-09: Open battle pass via F4 key."""
    return UIFlow(
        name="MENU_BATTLE_PASS_OPEN",
        description="Open battle pass via F4",
        steps=(
            press("f4", reason="open_battle_pass"),
            delay(500),
            wait_state("battle_pass", timeout_ms=3000, reason="wait_battle_pass"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


def build_battle_pass_claim_flow() -> UIFlow:
    """U-09: Claim available battle pass rewards."""
    return UIFlow(
        name="MENU_BATTLE_PASS_CLAIM",
        description="Claim battle pass rewards",
        steps=(
            # Click claim button (typically bottom-right)
            click(0.80, 0.90, reason="claim_bp_reward", delay_ms=500),
            confirm(reason="confirm_claim"),
            delay(300),
        ),
        precondition_state="battle_pass",
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# U-10: Events Panel
# ---------------------------------------------------------------------------

def build_events_open_flow() -> UIFlow:
    """U-10: Open events panel via F5 key."""
    return UIFlow(
        name="MENU_EVENTS_OPEN",
        description="Open events panel via F5",
        steps=(
            press("f5", reason="open_events"),
            delay(500),
            wait_state("events_panel", timeout_ms=3000, reason="wait_events"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


def build_events_navigate_flow(event_index: int = 0) -> UIFlow:
    """U-10: Navigate to a specific event by index."""
    # Events are displayed as a vertical list on the left
    ny = min(0.20 + event_index * 0.10, 0.80)
    return UIFlow(
        name=f"MENU_EVENTS_NAVIGATE_{event_index}",
        description=f"Navigate to event at index {event_index}",
        steps=(
            click(0.15, ny, reason=f"select_event_{event_index}", delay_ms=500),
        ),
        precondition_state="events_panel",
        escape_on_failure=True,
    )


def build_events_claim_reward_flow() -> UIFlow:
    """U-10: Claim event reward."""
    return UIFlow(
        name="MENU_EVENTS_CLAIM",
        description="Claim event reward",
        steps=(
            click(0.75, 0.85, reason="claim_event_reward", delay_ms=300),
            confirm(reason="confirm_event_claim"),
            delay(300),
        ),
        precondition_state="events_panel",
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# U-11: Co-op / Friends
# ---------------------------------------------------------------------------

def build_coop_open_flow() -> UIFlow:
    """U-11: Open co-op/friends screen via F2 key."""
    return UIFlow(
        name="MENU_COOP_OPEN",
        description="Open co-op screen via F2",
        steps=(
            press("f2", reason="open_coop"),
            delay(500),
            wait_state("coop_screen", timeout_ms=3000, reason="wait_coop"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


def build_coop_enter_flow() -> UIFlow:
    """U-11: Enter co-op mode (join random or specific host)."""
    return UIFlow(
        name="MENU_COOP_ENTER",
        description="Enter co-op mode",
        steps=(
            # Click "Join" or "Start Co-op" button
            click(0.50, 0.85, reason="join_coop", delay_ms=500),
            delay(1000),
            # Confirm joining
            confirm(reason="confirm_coop_join"),
        ),
        precondition_state="coop_screen",
        escape_on_failure=True,
    )


def build_coop_exit_flow() -> UIFlow:
    """U-11: Exit co-op mode back to single player."""
    return UIFlow(
        name="MENU_COOP_EXIT",
        description="Exit co-op mode",
        steps=(
            press("escape", reason="open_coop_menu"),
            delay(300),
            click(0.50, 0.60, reason="click_leave_coop", delay_ms=300),
            confirm(reason="confirm_leave_coop"),
            delay(500),
        ),
        precondition_state="coop_screen",
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# U-12: Settings Menu
# ---------------------------------------------------------------------------

def build_settings_open_flow() -> UIFlow:
    """U-12: Open settings menu through Paimon menu."""
    return UIFlow(
        name="MENU_SETTINGS_OPEN",
        description="Open settings via Paimon menu",
        steps=(
            press("escape", reason="open_paimon_menu"),
            delay(500),
            click_menu_button("settings", delay_ms=300),
            wait_state("settings_menu", timeout_ms=3000, reason="wait_settings"),
        ),
        precondition_state="world_hud",
        escape_on_failure=True,
    )


def build_settings_graphics_flow() -> UIFlow:
    """U-12: Navigate to graphics settings tab."""
    return UIFlow(
        name="MENU_SETTINGS_GRAPHICS",
        description="Navigate to graphics settings",
        steps=(
            click(0.15, 0.20, reason="graphics_tab", delay_ms=300),
        ),
        precondition_state="settings_menu",
        escape_on_failure=True,
    )


def build_settings_controls_flow() -> UIFlow:
    """U-12: Navigate to controls settings tab."""
    return UIFlow(
        name="MENU_SETTINGS_CONTROLS",
        description="Navigate to controls settings",
        steps=(
            click(0.15, 0.35, reason="controls_tab", delay_ms=300),
        ),
        precondition_state="settings_menu",
        escape_on_failure=True,
    )


def build_settings_audio_flow() -> UIFlow:
    """U-12: Navigate to audio settings tab."""
    return UIFlow(
        name="MENU_SETTINGS_AUDIO",
        description="Navigate to audio settings",
        steps=(
            click(0.15, 0.50, reason="audio_tab", delay_ms=300),
        ),
        precondition_state="settings_menu",
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# Combined: Return to world from any menu
# ---------------------------------------------------------------------------

def build_return_to_world_flow(max_escapes: int = 3) -> UIFlow:
    """Press Escape repeatedly to return to world HUD from any menu depth."""
    steps: list[UIStep] = []
    for i in range(max_escapes):
        steps.append(press("escape", reason=f"escape_{i}"))
        steps.append(delay(300))
    steps.append(wait_state("world_hud", timeout_ms=3000, reason="verify_world"))
    return UIFlow(
        name="MENU_RETURN_TO_WORLD",
        description="Return to world from any menu",
        steps=tuple(steps),
        escape_on_failure=True,
    )


# ---------------------------------------------------------------------------
# Flow registry for lookup by name
# ---------------------------------------------------------------------------

ALL_MENU_FLOWS: dict[str, UIFlow] = {
    "party_config": build_party_config_flow(),
    "party_config_via_menu": build_party_config_via_menu_flow(),
    "party_save": build_party_save_flow(),
    "wish_open": build_wish_open_flow(),
    "wish_ten_pull": build_wish_ten_pull_flow(),
    "wish_select_banner_0": build_wish_select_banner_flow(0),
    "wish_select_banner_1": build_wish_select_banner_flow(1),
    "wish_select_banner_2": build_wish_select_banner_flow(2),
    "wish_select_banner_3": build_wish_select_banner_flow(3),
    "handbook_open": build_handbook_open_flow(),
    "handbook_tab_0": build_handbook_tab_flow(0),
    "handbook_tab_1": build_handbook_tab_flow(1),
    "handbook_tab_2": build_handbook_tab_flow(2),
    "handbook_tab_3": build_handbook_tab_flow(3),
    "handbook_tab_4": build_handbook_tab_flow(4),
    "handbook_tab_5": build_handbook_tab_flow(5),
    "handbook_track_enemy": build_handbook_track_enemy_flow(),
    "battle_pass_open": build_battle_pass_open_flow(),
    "battle_pass_claim": build_battle_pass_claim_flow(),
    "events_open": build_events_open_flow(),
    "events_navigate_0": build_events_navigate_flow(0),
    "events_navigate_1": build_events_navigate_flow(1),
    "events_claim": build_events_claim_reward_flow(),
    "coop_open": build_coop_open_flow(),
    "coop_enter": build_coop_enter_flow(),
    "coop_exit": build_coop_exit_flow(),
    "settings_open": build_settings_open_flow(),
    "settings_graphics": build_settings_graphics_flow(),
    "settings_controls": build_settings_controls_flow(),
    "settings_audio": build_settings_audio_flow(),
    "return_to_world": build_return_to_world_flow(),
}


def get_menu_flow(name: str) -> UIFlow | None:
    """Look up a menu flow by name."""
    return ALL_MENU_FLOWS.get(name)
