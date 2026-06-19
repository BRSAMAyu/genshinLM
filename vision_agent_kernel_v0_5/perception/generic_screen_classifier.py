"""GenericScreenClassifier: VLM-driven screen state classification for any game.

Unlike GenshinScreenClassifier which uses hand-crafted HSV/color heuristics,
this classifier uses a Vision-Language Model to describe the screen and maps
the description to a standard game state taxonomy.

Phase 2 roadmap: generic perception that works across games without per-game tuning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GenericScreenState:
    state: str
    confidence: float
    description: str
    raw_vlm_response: str = ""


class VLMProvider(Protocol):
    """Minimal protocol for VLM-based image description."""

    def describe_image(self, image: Any, prompt: str) -> Any: ...


# Standard game state taxonomy — game-agnostic
_STATE_TAXONOMY: dict[str, list[str]] = {
    "overworld": ["world", "exploring", "field", "outdoor", "walking", "running", "open world"],
    "combat": ["fighting", "battle", "enemy", "attack", "combat", "boss", "damage"],
    "dialog": ["dialog", "talking", "conversation", "npc", "speech", "chat", "dialogue"],
    "menu": ["menu", "inventory", "settings", "options", "pause", "shop", "character screen"],
    "map": ["map", "world map", "teleport", "waypoint", "fast travel"],
    "loading": ["loading", "black screen", "transition", "splash"],
    "cutscene": ["cutscene", "cinematic", "movie", "video", "story scene"],
    "death": ["death", "game over", "defeated", "respawn", "revive"],
    "unknown": [],
}

_VLM_PROMPT = (
    "Describe this game screenshot in one short sentence. "
    "Focus on: is the player in combat, exploring, in a menu, watching a cutscene, "
    "talking to an NPC, looking at a map, or in a loading screen? "
    "Reply with just the description, nothing else."
)


class GenericScreenClassifier:
    """Classify game screen state using VLM description → taxonomy mapping."""

    def __init__(self, vlm: VLMProvider | None = None) -> None:
        self._vlm = vlm
        self._cache: dict[int, GenericScreenState] = {}
        self._cache_max = 64

    def classify(self, frame: np.ndarray) -> GenericScreenState:
        """Classify a game frame into a standard state taxonomy."""
        if self._vlm is None:
            return GenericScreenState(
                state="unknown",
                confidence=0.1,
                description="no_vlm_provider",
            )

        frame_hash = self._frame_hash(frame)
        cached = self._cache.get(frame_hash)
        if cached is not None:
            return cached

        try:
            result = self._vlm.describe_image(frame, _VLM_PROMPT)
            description = getattr(result, "description", str(result))
            confidence = getattr(result, "confidence", 0.6)
        except Exception as exc:
            log.debug("[GenericClassifier] VLM call failed: %s", exc)
            return GenericScreenState(
                state="unknown",
                confidence=0.1,
                description=f"vlm_error: {exc}",
            )

        state = self._map_to_taxonomy(description)
        result_state = GenericScreenState(
            state=state,
            confidence=min(confidence, 0.95),
            description=description,
            raw_vlm_response=description,
        )

        if len(self._cache) >= self._cache_max:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[frame_hash] = result_state

        return result_state

    def _map_to_taxonomy(self, description: str) -> str:
        """Map a VLM text description to the state taxonomy."""
        desc_lower = description.lower()
        best_state = "unknown"
        best_score = 0

        for state, keywords in _STATE_TAXONOMY.items():
            if state == "unknown":
                continue
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > best_score:
                best_score = score
                best_state = state

        return best_state

    @staticmethod
    def _frame_hash(frame: np.ndarray) -> int:
        """Cheap hash for frame caching (downsample + hash)."""
        step = max(1, frame.shape[0] // 16)
        small = frame[::step, ::step]
        return hash(small.tobytes())
