from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DummyFrameResult:
    """Result from the dummy frame processor."""

    frame_id: int
    label: str
    confidence: float


class DummyProcessor:
    """A simple frame post-processor that publishes to a StateBus slot."""

    name: str = "dummy_processor"

    def __init__(self) -> None:
        self._slot: Any = None

    def bind_slot(self, slot: Any) -> None:
        """Bind the StateBus slot to publish results to."""
        self._slot = slot

    def process(self, frame_id: int, label: str = "idle", confidence: float = 1.0) -> DummyFrameResult:
        """Process a frame and publish the result to the bound slot."""
        result = DummyFrameResult(frame_id=frame_id, label=label, confidence=confidence)
        if self._slot is not None:
            self._slot.put(result)
        return result
