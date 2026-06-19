"""Loading screen waiter — uses screen classifier protocol, not concrete import."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)

FrameSource = Callable[[], object]  # Returns np.ndarray | None


class ScreenClassifier(Protocol):
    """Protocol for screen state classification — avoids cross-plane import."""
    def classify(self, frame: Any) -> Any: ...


class LoadingWaiter:
    """Reliably wait for loading screen to complete."""

    def __init__(self, classifier: ScreenClassifier, max_wait: float = 60.0) -> None:
        self._classifier = classifier
        self._max_wait = max_wait

    def wait_for_load_complete(
        self,
        frame_source: FrameSource,
        shutdown_event: threading.Event | None = None,
    ) -> bool:
        """Wait for loading to complete. Returns True if load finished, False on timeout."""
        import numpy as np
        deadline = time.perf_counter() + self._max_wait
        saw_loading = False

        while time.perf_counter() < deadline:
            if shutdown_event and shutdown_event.is_set():
                return False

            frame = frame_source()
            if frame is not None and isinstance(frame, np.ndarray):
                state = self._classifier.classify(frame)
                state_str = getattr(state, "state", str(state))
                if state_str == "loading_screen":
                    saw_loading = True
                elif saw_loading and state_str in ("world_hud", "dialog", "overworld", "menu"):
                    log.info("[LoadingWaiter] loading complete, state=%s", state_str)
                    return True
                elif not saw_loading and state_str in ("world_hud", "overworld"):
                    return True

            time.sleep(0.3)

        log.warning("[LoadingWaiter] timed out after %.1fs", self._max_wait)
        return False
