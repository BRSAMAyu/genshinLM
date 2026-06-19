"""Tests for GenericScreenClassifier."""
from __future__ import annotations

import numpy as np
import pytest

from perception.generic_screen_classifier import GenericScreenClassifier, GenericScreenState


class _MockVLM:
    def __init__(self, description: str = "", confidence: float = 0.8) -> None:
        self.description = description
        self.confidence = confidence

    def describe_image(self, image: object, prompt: str) -> object:
        return _MockResult(self.description, self.confidence)


class _MockResult:
    def __init__(self, description: str, confidence: float) -> None:
        self.description = description
        self.confidence = confidence


class TestGenericScreenClassifier:
    def test_no_vlm_returns_unknown(self) -> None:
        clf = GenericScreenClassifier(vlm=None)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = clf.classify(frame)
        assert result.state == "unknown"
        assert result.confidence <= 0.2

    def test_combat_detection(self) -> None:
        vlm = _MockVLM(description="The player is fighting a boss enemy in combat")
        clf = GenericScreenClassifier(vlm=vlm)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = clf.classify(frame)
        assert result.state == "combat"

    def test_dialog_detection(self) -> None:
        vlm = _MockVLM(description="NPC dialog with speech bubbles")
        clf = GenericScreenClassifier(vlm=vlm)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = clf.classify(frame)
        assert result.state == "dialog"

    def test_menu_detection(self) -> None:
        vlm = _MockVLM(description="Game pause menu with inventory options")
        clf = GenericScreenClassifier(vlm=vlm)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = clf.classify(frame)
        assert result.state == "menu"

    def test_overworld_detection(self) -> None:
        vlm = _MockVLM(description="Player exploring an open world field")
        clf = GenericScreenClassifier(vlm=vlm)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = clf.classify(frame)
        assert result.state == "overworld"

    def test_caching_same_frame(self) -> None:
        call_count = 0

        class CountingVLM:
            def describe_image(self, image: object, prompt: str) -> object:
                nonlocal call_count
                call_count += 1
                return _MockResult("combat scene", 0.8)

        clf = GenericScreenClassifier(vlm=CountingVLM())
        frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 128
        r1 = clf.classify(frame)
        r2 = clf.classify(frame)
        assert r1.state == r2.state
        assert call_count == 1

    def test_vlm_error_returns_unknown(self) -> None:
        class FailingVLM:
            def describe_image(self, image: object, prompt: str) -> object:
                raise RuntimeError("API unavailable")

        clf = GenericScreenClassifier(vlm=FailingVLM())
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = clf.classify(frame)
        assert result.state == "unknown"
        assert "vlm_error" in result.description

    def test_taxonomy_mapping(self) -> None:
        clf = GenericScreenClassifier()
        assert clf._map_to_taxonomy("loading screen") == "loading"
        assert clf._map_to_taxonomy("world map with waypoints") == "map"
        assert clf._map_to_taxonomy("game over screen") == "death"
        assert clf._map_to_taxonomy("cinematic cutscene playing") == "cutscene"
        assert clf._map_to_taxonomy("random text") == "unknown"

    def test_result_is_frozen(self) -> None:
        result = GenericScreenState(state="combat", confidence=0.8, description="test")
        with pytest.raises(AttributeError):
            result.state = "menu"  # type: ignore[misc]
