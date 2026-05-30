from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from interaction.dialog_branch_analyzer import DialogBranchAnalyzer
from perception.genshin_screen_classifier import GenshinScreenClassifier

if TYPE_CHECKING:
    from execution.safe_window_backend import SafeWindowInputBackend

log = logging.getLogger(__name__)


class DialogDriver:
    """Drive dialog to completion with auto-advance and choice selection."""

    def __init__(
        self,
        backend: SafeWindowInputBackend,
        classifier: GenshinScreenClassifier,
        analyzer: DialogBranchAnalyzer | None = None,
    ) -> None:
        self._backend = backend
        self._classifier = classifier
        self._analyzer = analyzer or DialogBranchAnalyzer()

    def drive_dialog_to_completion(
        self,
        frame_source,
        max_clicks: int = 100,
        shutdown_event: threading.Event | None = None,
    ) -> bool:
        """Advance dialog until it ends. Returns True if dialog completed."""
        clicks = 0
        consecutive_no_dialog = 0

        while clicks < max_clicks:
            if shutdown_event and shutdown_event.is_set():
                return False

            frame = frame_source()
            if frame is None:
                time.sleep(0.1)
                continue

            state = self._classifier.classify(frame)

            if state.state != "dialog":
                consecutive_no_dialog += 1
                if consecutive_no_dialog >= 3:
                    log.info("[DialogDriver] dialog ended after %d clicks", clicks)
                    return True
                time.sleep(0.1)
                continue

            consecutive_no_dialog = 0
            # Click to advance dialog (bottom center of screen)
            try:
                self._backend.click_at(
                    self._backend.client_rect().center[0],
                    self._backend.client_rect().top + int(self._backend.client_rect().height * 0.85),
                    reason="advance_dialog",
                )
            except Exception as exc:
                log.debug("[DialogDriver] click failed: %s", exc)

            clicks += 1
            time.sleep(0.3)

        log.warning("[DialogDriver] max_clicks (%d) reached", max_clicks)
        return False
