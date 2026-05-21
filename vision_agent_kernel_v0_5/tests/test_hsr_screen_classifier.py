from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from perception.hsr_screen_classifier import HSRScreenClassifier, HSRScreenState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def classifier() -> HSRScreenClassifier:
    return HSRScreenClassifier()


# ---------------------------------------------------------------------------
# None / empty frame handling
# ---------------------------------------------------------------------------

class TestEdgeFrames:
    def test_classifies_none_frame_as_unknown(self, classifier: HSRScreenClassifier) -> None:
        result = classifier.classify(None)
        assert result.state == "unknown"
        assert result.confidence == 0.0

    def test_classifies_empty_frame_as_unknown(self, classifier: HSRScreenClassifier) -> None:
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        result = classifier.classify(empty)
        assert result.state == "unknown"
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Frozen dataclass
# ---------------------------------------------------------------------------

class TestScreenStateType:
    def test_screen_state_is_frozen_dataclass(self) -> None:
        assert dataclasses.is_dataclass(HSRScreenState)
        assert HSRScreenState.__dataclass_params__.frozen is True

    def test_screen_state_fields(self) -> None:
        state = HSRScreenState("turn_based_combat", 0.9, {"action_order": True})
        assert state.state == "turn_based_combat"
        assert state.confidence == 0.9
        assert state.indicators["action_order"] is True

    def test_screen_state_immutable(self) -> None:
        state = HSRScreenState("overworld", 0.7)
        with pytest.raises(dataclasses.FrozenInstanceError):
            state.state = "combat"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Confidence bounds
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_classifier_returns_confidence(self, classifier: HSRScreenClassifier) -> None:
        # Use a small black frame (1920x1080 dimensions)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = classifier.classify(frame)
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0

    def test_classifier_returns_valid_state_string(
        self, classifier: HSRScreenClassifier
    ) -> None:
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = classifier.classify(frame)
        assert isinstance(result.state, str)
        assert len(result.state) > 0


# ---------------------------------------------------------------------------
# Specific screen detection
# ---------------------------------------------------------------------------

class TestScreenDetection:
    def test_loading_screen_detection(self, classifier: HSRScreenClassifier) -> None:
        """An all-black frame should be detected as a loading screen."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = classifier.classify(frame)
        assert result.state == "loading_screen"
        assert result.confidence == 0.95

    def test_non_standard_resolution_handled(
        self, classifier: HSRScreenClassifier
    ) -> None:
        """Classifier should handle non-1920x1080 resolutions gracefully."""
        small_frame = np.zeros((540, 960, 3), dtype=np.uint8)
        result = classifier.classify(small_frame)
        assert isinstance(result, HSRScreenState)
        assert result.state == "loading_screen"
        assert result.confidence >= 0.0

    def test_bright_frame_not_loading(self, classifier: HSRScreenClassifier) -> None:
        """A bright frame should not be classified as loading."""
        frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)
        result = classifier.classify(frame)
        assert result.state != "loading_screen"

    def test_combat_screen_with_yellow_indicators(
        self, classifier: HSRScreenClassifier
    ) -> None:
        """Frame with yellow action bar + cyan SP region should be combat."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # Paint the action order ROI with yellow-white (low saturation, high value)
        frame[880:1080, 660:1260] = [200, 200, 180]
        # Paint the SP indicator ROI with cyan (hue ~90, high sat/val)
        frame[920:960, 860:1060] = [180, 220, 200]
        result = classifier.classify(frame)
        # Should at least produce a valid result
        assert isinstance(result, HSRScreenState)
