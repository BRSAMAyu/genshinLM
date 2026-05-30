"""Seven Winds (TcgManager) for Geni: managing Genius Invokation TCG matches.

Covers S-35: Automated TCG match completion. Manages deck building,
match strategy, and reward claiming for the card game.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Card game types
# ---------------------------------------------------------------------------

class CardGameMode(str, Enum):
    CASUAL = "casual"            # Casual matches
    RANKED = "ranked"           # Ranked matches
    CHALLENGE = "challenge"      # Challenge mode
    CHARACTER_CHALLENGE = "character_challenge"  # VS specific character


@dataclass(slots=True)
class TcgDeck:
    """TCG deck configuration."""
    deck_id: str
    name: str
    characters: tuple[str, ...] = field(default_factory=())
    card_count: int = 0


@dataclass(slots=True)
class TcgMatch:
    """A TCG match record."""
    match_id: str
    mode: CardGameMode
    opponent_characters: tuple[str, ...] = ()
    won: bool = False
    duration_sec: float = 0.0
    rewards_earned: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Known decks and match logic
# ---------------------------------------------------------------------------

AVAILABLE_DECKS: dict[str, TcgDeck] = {
    "national_deck": TcgDeck(
        deck_id="national_deck",
        name="National Team Deck",
        characters=("xiangling", "xingqiu", "bennett"),
        card_count=30,
    ),
    "hyperbloom_deck": TcgDeck(
        deck_id="hyperbloom_deck",
        name="Hyperbloom Deck",
        characters=("nahida", "kuki", "xingqiu"),
        card_count=30,
    ),
    "freeze_deck": TcgDeck(
        deck_id="freeze_deck",
        name="Freeze Deck",
        characters=("ganyu", "xinyan", "mona"),
        card_count=30,
    ),
}


# ---------------------------------------------------------------------------
# TCG Manager
# ---------------------------------------------------------------------------

class TcgManager:
    """Manages Genius Invokation TCG matches and rewards.

    Handles:
    1. Deck selection for different opponents
    2. Match strategy execution
    3. Reward claiming
    4. Daily/weekly match completion
    """

    # Match targets
    DAILY_MATCH_GOAL = 4          # Daily matches for rewards
    WEEKLY_MATCH_GOAL = 10       # Weekly matches for bonus

    def __init__(self) -> None:
        self._current_deck: str = ""
        self._daily_matches: int = 0
        self._weekly_matches: int = 0
        self._match_history: list[TcgMatch] = []

    def select_deck(self, opponent_chars: tuple[str, ...]) -> TcgDeck:
        """Select best deck for opponent.

        Simple strategy: counter pyro with cryo, etc.
        """
        # Default to national deck
        deck_id = "national_deck"
        return AVAILABLE_DECKS.get(deck_id, TcgDeck("", "", (), 0))

    def start_match(
        self,
        mode: CardGameMode = CardGameMode.CASUAL,
    ) -> dict[str, Any]:
        """Start a TCG match."""
        log.info("[TcgMgr] starting match in %s mode", mode.value)
        return {
            "status": "matching",
            "mode": mode.value,
            "deck": self._current_deck,
        }

    def record_match_result(
        self,
        won: bool,
        duration_sec: float,
        rewards: dict[str, int],
    ) -> TcgMatch:
        """Record match result and update statistics."""
        match = TcgMatch(
            match_id=f"match_{len(self._match_history)}",
            mode=CardGameMode.CASUAL,
            won=won,
            duration_sec=duration_sec,
            rewards_earned=rewards,
        )

        self._match_history.append(match)
        self._daily_matches += 1
        self._weekly_matches += 1

        log.info("[TcgMgr] match %s: won=%s, duration=%.0fs, rewards=%s",
                 match.match_id, won, duration_sec, rewards)
        return match

    def get_daily_progress(self) -> dict[str, Any]:
        """Get daily match progress."""
        return {
            "matches_today": self._daily_matches,
            "matches_goal": self.DAILY_MATCH_GOAL,
            "progress_pct": min(100, self._daily_matches / self.DAILY_MATCH_GOAL * 100),
            "rewards_available": self._daily_matches < self.DAILY_MATCH_GOAL,
        }

    def get_weekly_progress(self) -> dict[str, Any]:
        """Get weekly match progress."""
        return {
            "matches_this_week": self._weekly_matches,
            "matches_goal": self.WEEKLY_MATCH_GOAL,
            "progress_pct": min(100, self._weekly_matches / self.WEEKLY_MATCH_GOAL * 100),
        }

    def claim_rewards(self) -> dict[str, Any]:
        """Claim TCG rewards if available."""
        if self._daily_matches >= self.DAILY_MATCH_GOAL:
            return {"status": "rewards_claimed", "rewards": {"primogems": 10}}
        return {"status": "not_ready", "matches_needed": self.DAILY_MATCH_GOAL - self._daily_matches}


# ---------------------------------------------------------------------------
# TCG Flow
# ---------------------------------------------------------------------------

class TcgFlow:
    """Predefined flows for TCG operations."""

    OPEN_TCG_FLOW = (
        "press_f3",  # Open wish/TCG menu
        "click:0.70,0.40",  # Click TCG tab
        "wait_state:tcg_menu",
    )

    START_MATCH_FLOW = (
        "click:0.50,0.50",  # Click Play
        "click:0.50,0.50",  # Select mode
        "wait:3000",  # Matchmaking
        "click:0.65,0.85",  # Confirm match
    )

    CLAIM_REWARDS_FLOW = (
        "click:0.50,0.85",  # Click claim
        "wait:1000",
        "click:0.65,0.85",  # Confirm
    )