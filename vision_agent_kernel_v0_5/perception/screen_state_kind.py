"""ScreenStateKind canonicalization — unified screen state taxonomy.

Provides a canonical enum for screen states that maps game-specific states
to a universal taxonomy. All components should use ScreenStateKind instead
of raw strings when comparing or storing screen state.
"""
from __future__ import annotations

from enum import Enum
from typing import Mapping


class ScreenStateKind(str, Enum):
    """Canonical screen states — game-agnostic taxonomy.

    Each game capsule maps its specific states to these canonical kinds.
    """
    # Core states
    UNKNOWN = "unknown"
    LOADING = "loading"
    OVERWORLD = "overworld"
    DIALOG = "dialog"
    MENU = "menu"
    CUTSCENE = "cutscene"

    # Combat states
    COMBAT = "combat"
    COMBAT_RESULT = "combat_result"

    # Navigation
    MAP = "map"
    TELEPORT = "teleport"

    # UI overlays
    INVENTORY = "inventory"
    QUEST_LOG = "quest_log"
    PARTY_SETUP = "party_setup"
    SHOP = "shop"

    # System
    BLACK_SCREEN = "black_screen"
    CRASH = "crash"
    DISCONNECTED = "disconnected"
    LOGIN = "login"
    TITLE = "title"

    # Exploration
    COLLECTION = "collection"
    PUZZLE = "puzzle"


# Game-specific → canonical mappings
_GENSHIN_MAP: dict[str, ScreenStateKind] = {
    "loading_screen": ScreenStateKind.LOADING,
    "world_hud": ScreenStateKind.OVERWORLD,
    "overworld": ScreenStateKind.OVERWORLD,
    "dialog": ScreenStateKind.DIALOG,
    "dialogue": ScreenStateKind.DIALOG,
    "menu": ScreenStateKind.MENU,
    "main_menu": ScreenStateKind.MENU,
    "combat": ScreenStateKind.COMBAT,
    "combat_result": ScreenStateKind.COMBAT_RESULT,
    "victory": ScreenStateKind.COMBAT_RESULT,
    "defeat": ScreenStateKind.COMBAT_RESULT,
    "map": ScreenStateKind.MAP,
    "bigmap": ScreenStateKind.MAP,
    "inventory": ScreenStateKind.INVENTORY,
    "bag": ScreenStateKind.INVENTORY,
    "quest_log": ScreenStateKind.QUEST_LOG,
    "quest": ScreenStateKind.QUEST_LOG,
    "party_setup": ScreenStateKind.PARTY_SETUP,
    "shop": ScreenStateKind.SHOP,
    "black_screen": ScreenStateKind.BLACK_SCREEN,
    "cutscene": ScreenStateKind.CUTSCENE,
    "teleport": ScreenStateKind.TELEPORT,
    "login": ScreenStateKind.LOGIN,
    "title": ScreenStateKind.TITLE,
    "crash": ScreenStateKind.CRASH,
    "disconnected": ScreenStateKind.DISCONNECTED,
    "collection": ScreenStateKind.COLLECTION,
    "puzzle": ScreenStateKind.PUZZLE,
}

_HSR_MAP: dict[str, ScreenStateKind] = {
    "loading_screen": ScreenStateKind.LOADING,
    "map_hud": ScreenStateKind.OVERWORLD,
    "overworld": ScreenStateKind.OVERWORLD,
    "dialog": ScreenStateKind.DIALOG,
    "menu": ScreenStateKind.MENU,
    "combat": ScreenStateKind.COMBAT,
    "combat_result": ScreenStateKind.COMBAT_RESULT,
    "map": ScreenStateKind.MAP,
    "inventory": ScreenStateKind.INVENTORY,
    "black_screen": ScreenStateKind.BLACK_SCREEN,
}

_GAME_MAPPINGS: dict[str, dict[str, ScreenStateKind]] = {
    "genshin": _GENSHIN_MAP,
    "hsr": _HSR_MAP,
}


def canonicalize(raw_state: str, game_id: str = "") -> ScreenStateKind:
    """Convert a raw screen state string to canonical ScreenStateKind.

    If game_id is provided, uses that game's mapping first.
    Falls back to direct enum value match, then UNKNOWN.
    """
    # Try game-specific mapping first
    if game_id:
        game_map = _GAME_MAPPINGS.get(game_id, {})
        if raw_state in game_map:
            return game_map[raw_state]

    # Try direct enum match (case-insensitive)
    normalized = raw_state.lower().strip()
    for kind in ScreenStateKind:
        if kind.value == normalized:
            return kind

    # Try all game mappings as fallback
    for game_map in _GAME_MAPPINGS.values():
        if raw_state in game_map:
            return game_map[raw_state]

    return ScreenStateKind.UNKNOWN


def register_game_mapping(game_id: str, mapping: Mapping[str, ScreenStateKind]) -> None:
    """Register a custom game-specific state mapping."""
    _GAME_MAPPINGS[game_id] = dict(mapping)


def get_game_mapping(game_id: str) -> dict[str, ScreenStateKind]:
    """Get the mapping for a specific game, or empty dict if not registered."""
    return dict(_GAME_MAPPINGS.get(game_id, {}))
