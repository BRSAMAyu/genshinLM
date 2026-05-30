from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.genshin_game_agent import GenshinActionExecutor
    from perception.genshin_screen_classifier import GenshinScreenClassifier

log = logging.getLogger(__name__)


class TeleportSequence:
    """Complete map -> select waypoint -> teleport confirmation flow."""

    def __init__(
        self,
        executor: GenshinActionExecutor,
        classifier: GenshinScreenClassifier,
    ) -> None:
        self._executor = executor
        self._classifier = classifier

    def teleport_to_waypoint(
        self,
        waypoint_name: str,
        region: str = "",
        frame_source=None,
        shutdown_event: threading.Event | None = None,
        timeout: float = 30.0,
    ) -> bool:
        """Execute full teleport sequence:
        1. Open map (M)
        2. Wait for map screen
        3. Select region tab if needed
        4. Find and click waypoint
        5. Confirm teleport
        6. Wait for loading
        """
        started = time.perf_counter()

        # Step 1: Open map
        try:
            self._executor._press_key_safe("m", "open_map", 0.5)
        except Exception as exc:
            log.warning("[Teleport] open map failed: %s", exc)
            return False

        # Step 2: Wait for map screen
        if not self._wait_for_screen("map", frame_source, 5.0, shutdown_event):
            log.warning("[Teleport] map screen did not appear")
            self._executor._press_key_safe("escape", "close_map", 0.3)
            return False

        # Step 3: Click waypoint area (approximate center of map for now)
        # In production, VLM would locate the waypoint by name
        try:
            self._executor._click_at_normalized(0.5, 0.5, reason=f"select_{waypoint_name}")
            self._chunked_sleep(0.5, shutdown_event)
        except Exception as exc:
            log.warning("[Teleport] click waypoint failed: %s", exc)
            self._executor._press_key_safe("escape", "close_map", 0.3)
            return False

        # Step 4: Click teleport button (bottom right of map)
        try:
            self._executor._click_at_normalized(0.85, 0.85, reason="teleport_confirm")
            self._chunked_sleep(0.5, shutdown_event)
        except Exception as exc:
            log.warning("[Teleport] confirm failed: %s", exc)
            self._executor._press_key_safe("escape", "close_map", 0.3)
            return False

        # Step 5: Wait for loading screen to appear and then complete
        if not self._wait_for_loading_complete(frame_source, timeout, shutdown_event):
            log.warning("[Teleport] loading did not complete within %.1fs", timeout)
            return False

        # Q-20: Wait for quest marker to refresh after teleport (1-2 second delay)
        if not self._wait_for_marker_refresh(frame_source, 3.0, shutdown_event):
            log.warning("[Teleport] marker refresh timeout - continuing anyway")

        elapsed = time.perf_counter() - started
        log.info("[Teleport] teleported to %s in %.1fs", waypoint_name, elapsed)
        return True

    def _wait_for_screen(
        self,
        target_state: str,
        frame_source,
        timeout: float,
        shutdown_event: threading.Event | None,
    ) -> bool:
        """Wait until classifier detects target screen state."""
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if shutdown_event and shutdown_event.is_set():
                return False
            if frame_source:
                frame = frame_source()
                if frame is not None:
                    state = self._classifier.classify(frame)
                    if state.state == target_state:
                        return True
            time.sleep(0.2)
        return False

    def _wait_for_loading_complete(
        self,
        frame_source,
        timeout: float,
        shutdown_event: threading.Event | None,
    ) -> bool:
        """Wait for loading screen to appear then disappear."""
        deadline = time.perf_counter() + timeout
        saw_loading = False
        while time.perf_counter() < deadline:
            if shutdown_event and shutdown_event.is_set():
                return False
            if frame_source:
                frame = frame_source()
                if frame is not None:
                    state = self._classifier.classify(frame)
                    if state.state == "loading_screen":
                        saw_loading = True
                    elif saw_loading and state.state in ("world_hud", "dialog", "overworld"):
                        return True
                    elif not saw_loading and state.state in ("world_hud", "overworld"):
                        # Teleport might have been instant
                        return True
            time.sleep(0.3)
        return False

    # Q-20: Wait for quest marker refresh after teleport
    def _wait_for_marker_refresh(
        self,
        frame_source,
        timeout: float,
        shutdown_event: threading.Event | None,
    ) -> bool:
        """Wait for quest marker to update after teleport (1-2 second delay)."""
        deadline = time.perf_counter() + timeout
        # Wait for marker to start updating (with interrupt check)
        self._chunked_sleep(1.5, shutdown_event)
        while time.perf_counter() < deadline:
            if shutdown_event and shutdown_event.is_set():
                return False
            if frame_source:
                frame = frame_source()
                if frame is not None:
                    state = self._classifier.classify(frame)
                    # Check if screen is stable and markers are visible
                    if state.state in ("world_hud", "overworld"):
                        return True
            self._chunked_sleep(0.2, shutdown_event)
        return False

    def _chunked_sleep(self, seconds: float, shutdown_event: threading.Event | None) -> None:
        """Non-blocking chunked sleep with interrupt check (CLAUDE.md compliance)."""
        deadline = time.perf_counter() + seconds
        chunk = 0.05
        while time.perf_counter() < deadline:
            if shutdown_event and shutdown_event.is_set():
                return
            remaining = max(0.0, deadline - time.perf_counter())
            time.sleep(min(chunk, remaining))
