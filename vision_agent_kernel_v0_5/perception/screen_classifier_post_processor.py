"""Screen classifier post-processor: populates observation.ui_state from
GenshinScreenClassifier analysis on each frame.
"""
from __future__ import annotations

import time

import numpy as np

from core.state_bus import StateBus
from core.types import Observation, UIStateEstimate
from perception.genshin_screen_classifier import GenshinScreenClassifier


class GenshinScreenClassifierPostProcessor:
    """Runs GenshinScreenClassifier on each frame and populates observation.ui_state."""

    def __init__(self, classifier: GenshinScreenClassifier | None = None) -> None:
        self._classifier = classifier or GenshinScreenClassifier()

    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None:
        result = self._classifier.classify(frame)
        observation.ui_state = UIStateEstimate(
            frame_id=observation.frame_id,
            timestamp=observation.t_processed,
            state=result.state,
            confidence=result.confidence,
            payload={"indicators": result.indicators},
        )
