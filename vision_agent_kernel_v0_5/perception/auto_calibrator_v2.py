"""AutoCalibratorV2: VLM-driven UI landmark discovery.

Automatically discovers and calibrates screen regions for any game
by using a VLM to identify UI elements. Replaces hand-crafted ROI
constants with auto-discovered landmarks.

Phase 2 roadmap: eliminates per-game manual calibration.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Landmark:
    name: str
    bbox_norm: tuple[float, float, float, float]  # (x1, y1, x2, y2) normalized 0-1
    element_type: str  # health_bar, minimap, skill_icon, dialog, menu_button, etc.
    confidence: float


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    game_id: str
    landmarks: tuple[Landmark, ...]
    screen_resolution: tuple[int, int]
    confidence: float


@dataclass(slots=True)
class CalibrationProfile:
    """Stores calibrated landmarks for a game."""
    game_id: str
    landmarks: dict[str, Landmark] = field(default_factory=dict)


class VLMProvider(Protocol):
    def describe_image(self, image: Any, prompt: str) -> Any: ...
    def ground_ui(self, image: Any, description: str) -> Any: ...


_CALIBRATION_PROMPT = (
    "Identify all UI elements in this game screenshot. For each element, describe: "
    "1) What it is (health bar, minimap, skill icons, dialog box, inventory button, etc.) "
    "2) Its approximate position as a fraction of the screen (x1, y1, x2, y2 from 0.0 to 1.0). "
    "Reply in JSON format: [{\"name\": \"...\", \"type\": \"...\", \"bbox\": [x1, y1, x2, y2]}]"
)

_COMMON_LANDMARKS: list[str] = [
    "health_bar", "minimap", "skill_icons", "dialog_box",
    "notification_area", "death_screen", "loading_indicator",
    "menu_button", "quest_tracker", "stamina_bar",
]


class AutoCalibratorV2:
    """Auto-discover UI landmarks using VLM."""

    def __init__(self, vlm: VLMProvider | None = None) -> None:
        self._vlm = vlm
        self._profiles: dict[str, CalibrationProfile] = {}

    def calibrate(self, frame: np.ndarray, game_id: str = "") -> CalibrationResult:
        """Discover UI landmarks from a single frame."""
        h, w = frame.shape[:2]

        if self._vlm is None:
            landmarks = self._heuristic_landmarks(w, h)
            calibration = CalibrationResult(
                game_id=game_id,
                landmarks=tuple(landmarks),
                screen_resolution=(w, h),
                confidence=0.3,
            )
            self._store_profile(game_id, landmarks)
            return calibration

        landmarks: list[Landmark] = []

        # Try VLM-based discovery
        try:
            result = self._vlm.describe_image(frame, _CALIBRATION_PROMPT)
            description = getattr(result, "description", str(result))
            landmarks = self._parse_vlm_response(description)
        except Exception as exc:
            log.debug("[AutoCalibrator] VLM call failed: %s", exc)

        # Fallback: heuristic common positions
        if not landmarks:
            landmarks = self._heuristic_landmarks(w, h)

        calibration = CalibrationResult(
            game_id=game_id,
            landmarks=tuple(landmarks),
            screen_resolution=(w, h),
            confidence=0.6 if landmarks else 0.0,
        )

        # Store profile
        self._store_profile(game_id, landmarks)

        return calibration

    def get_profile(self, game_id: str) -> CalibrationProfile | None:
        return self._profiles.get(game_id)

    def get_landmark(self, game_id: str, name: str) -> Landmark | None:
        profile = self._profiles.get(game_id)
        if profile is None:
            return None
        return profile.landmarks.get(name)

    def _store_profile(self, game_id: str, landmarks: list[Landmark]) -> None:
        profile = self._profiles.get(game_id, CalibrationProfile(game_id=game_id))
        for lm in landmarks:
            profile.landmarks[lm.name] = lm
        self._profiles[game_id] = profile

    @staticmethod
    def _parse_vlm_response(response: str) -> list[Landmark]:
        """Parse VLM JSON response into Landmark objects."""
        import json
        landmarks: list[Landmark] = []
        try:
            # Try to extract JSON from response
            json_str = response
            if "[" not in response:
                return landmarks
            start = response.index("[")
            end = response.rindex("]") + 1
            json_str = response[start:end]
            items = json.loads(json_str)
            for item in items:
                bbox = item.get("bbox", [0, 0, 0, 0])
                if len(bbox) != 4:
                    continue
                landmarks.append(Landmark(
                    name=item.get("name", "unknown"),
                    bbox_norm=tuple(bbox),  # type: ignore[arg-type]
                    element_type=item.get("type", "unknown"),
                    confidence=0.7,
                ))
        except (json.JSONDecodeError, ValueError):
            pass
        return landmarks

    @staticmethod
    def _heuristic_landmarks(w: int, h: int) -> list[Landmark]:
        """Generate fallback landmarks at common game UI positions."""
        return [
            Landmark(
                name="health_bar",
                bbox_norm=(0.30, 0.88, 0.70, 0.94),
                element_type="health_bar",
                confidence=0.3,
            ),
            Landmark(
                name="minimap",
                bbox_norm=(0.0, 0.0, 0.12, 0.12),
                element_type="minimap",
                confidence=0.3,
            ),
            Landmark(
                name="skill_icons",
                bbox_norm=(0.78, 0.87, 0.99, 0.99),
                element_type="skill_icons",
                confidence=0.3,
            ),
        ]
