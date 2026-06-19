from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend

log = logging.getLogger(__name__)


def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
    import time
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))


class NotificationHandler:
    """Handle various popup notifications."""

    def __init__(
        self,
        backend: SafeWindowInputBackend,
        classifier: Any | None = None,
    ) -> None:
        self._backend = backend
        self._classifier = classifier

    def handle_notification(self, frame: np.ndarray | None = None) -> bool:
        """Detect and dismiss popup notifications. Returns True if handled."""
        try:
            self._backend.key_press("escape", reason="dismiss_notification")
            _chunked_sleep(0.3)
            self._backend.mouse_click(0.1, 0.1, reason="click_away_notification")
            _chunked_sleep(0.3)
            log.info("[NotificationHandler] notification dismissed")
            return True
        except Exception as exc:
            log.warning("[NotificationHandler] handle_notification failed: %s", exc)
            return False

    def is_blocking_notification(self, frame: np.ndarray | None = None) -> bool:
        """Check if a blocking notification is present using classifier."""
        if self._classifier is None or frame is None:
            return False
        state = self._classifier.classify(frame)
        return state.state == "notification"
