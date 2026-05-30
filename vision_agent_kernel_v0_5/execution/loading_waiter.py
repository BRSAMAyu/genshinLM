from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

from perception.genshin_screen_classifier import GenshinScreenClassifier

log = logging.getLogger(__name__)

FrameSource = Callable[[], object]  # Returns np.ndarray | None


class LoadingWaiter:
    """Reliably wait for loading screen to complete."""

    def __init__(self, classifier: GenshinScreenClassifier, max_wait: float = 60.0) -> None:
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
                if state.state == "loading_screen":
                    saw_loading = True
                elif saw_loading and state.state in ("world_hud", "dialog", "overworld", "menu"):
                    log.info("[LoadingWaiter] loading complete, state=%s", state.state)
                    return True
                elif not saw_loading and state.state in ("world_hud", "overworld"):
                    # Already past loading
                    return True

            time.sleep(0.3)

        log.warning("[LoadingWaiter] timed out after %.1fs", self._max_wait)
        return False
