from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.genshin_game_agent import GenshinActionExecutor
    from perception.genshin_screen_classifier import GenshinScreenClassifier
    from interaction.ui_flow_engine import UIFlowExecutor
    from core.state_bus import StateBus

log = logging.getLogger(__name__)


def _chunked_sleep(seconds: float, shutdown_event: threading.Event | None = None) -> None:
    """Non-blocking chunked sleep with interrupt check (CLAUDE.md compliance)."""
    deadline = time.perf_counter() + seconds
    chunk = 0.05
    while time.perf_counter() < deadline:
        if shutdown_event and shutdown_event.is_set():
            return
        remaining = max(0.0, deadline - time.perf_counter())
        time.sleep(min(chunk, remaining))


class TeleportSequence:
    """Complete map -> select waypoint -> teleport confirmation flow.

    Delegates to UIFlowExecutor when available, falls back to raw executor.
    """

    def __init__(
        self,
        executor: Any | None = None,
        classifier: Any | None = None,
        ui_flow_executor: UIFlowExecutor | None = None,
    ) -> None:
        self._executor = executor
        self._classifier = classifier
        self._ui_flow_executor = ui_flow_executor

    def teleport_to_waypoint(
        self,
        waypoint_name: str,
        region: str = "",
        frame_source=None,
        shutdown_event: threading.Event | None = None,
        timeout: float = 30.0,
        waypoint_nx: float = 0.50,
        waypoint_ny: float = 0.50,
    ) -> bool:
        """Execute full teleport sequence.

        Uses UIFlowExecutor if available (declarative), otherwise raw executor.
        """
        if self._ui_flow_executor is not None:
            return self._teleport_via_ui_flow(
                waypoint_name, waypoint_nx, waypoint_ny,
                frame_source, shutdown_event, timeout,
            )

        # Fallback: raw executor path
        if self._executor is None:
            log.warning("[Teleport] no executor available")
            return False
        return self._teleport_via_raw(
            waypoint_name, region, frame_source, shutdown_event, timeout,
        )

    # ------------------------------------------------------------------
    # UIFlow-based teleport (preferred)
    # ------------------------------------------------------------------

    def _teleport_via_ui_flow(
        self,
        waypoint_name: str,
        waypoint_nx: float,
        waypoint_ny: float,
        frame_source: Any,
        shutdown_event: threading.Event | None,
        timeout: float,
    ) -> bool:
        """Delegate to UIFlowExecutor for declarative teleport."""
        from interaction.ui_flow_engine import UIFlow, UIStep
        from interaction.ui_flow_engine import (
            STEP_PRESS_KEY, STEP_CLICK_AT, STEP_WAIT_STATE,
            STEP_WAIT_LOADING, STEP_WAIT_NOT_LOADING, STEP_DELAY,
        )

        flow = UIFlow(
            name=f"teleport_{waypoint_name}",
            description=f"Teleport to {waypoint_name}",
            steps=(
                UIStep(type=STEP_PRESS_KEY, key="m", reason="open_map", delay_ms=500),
                UIStep(type=STEP_WAIT_STATE, target_state="map", timeout_ms=5000),
                UIStep(type=STEP_DELAY, timeout_ms=500),
                UIStep(type=STEP_CLICK_AT, nx=waypoint_nx, ny=waypoint_ny,
                       reason=f"click_{waypoint_name}", delay_ms=500),
                UIStep(type=STEP_CLICK_AT, nx=0.85, ny=0.85,
                       reason="teleport_confirm", delay_ms=300),
                UIStep(type=STEP_WAIT_LOADING, timeout_ms=15000),
                UIStep(type=STEP_WAIT_NOT_LOADING, timeout_ms=20000),
            ),
        )

        try:
            result = self._ui_flow_executor.execute(flow)
            if result.status == "SUCCESS":
                # Wait for marker refresh after teleport
                self._wait_for_marker_refresh(frame_source, 3.0, shutdown_event)
                log.info("[Teleport] teleported to %s via UIFlow", waypoint_name)
                return True
            log.warning("[Teleport] UIFlow failed: %s", result.failure_code)
            return False
        except Exception as exc:
            log.warning("[Teleport] UIFlow exception: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Raw executor teleport (fallback)
    # ------------------------------------------------------------------

    def _teleport_via_raw(
        self,
        waypoint_name: str,
        region: str,
        frame_source: Any,
        shutdown_event: threading.Event | None,
        timeout: float,
    ) -> bool:
        """Raw executor path — kept for backward compatibility."""
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

        # Step 3: Click waypoint area
        try:
            self._executor._click_at_normalized(0.5, 0.5, reason=f"select_{waypoint_name}")
            _chunked_sleep(0.5, shutdown_event)
        except Exception as exc:
            log.warning("[Teleport] click waypoint failed: %s", exc)
            self._executor._press_key_safe("escape", "close_map", 0.3)
            return False

        # Step 4: Click teleport button
        try:
            self._executor._click_at_normalized(0.85, 0.85, reason="teleport_confirm")
            _chunked_sleep(0.5, shutdown_event)
        except Exception as exc:
            log.warning("[Teleport] confirm failed: %s", exc)
            self._executor._press_key_safe("escape", "close_map", 0.3)
            return False

        # Step 5: Wait for loading
        if not self._wait_for_loading_complete(frame_source, timeout, shutdown_event):
            log.warning("[Teleport] loading did not complete within %.1fs", timeout)
            return False

        # Q-20: Wait for quest marker to refresh
        if not self._wait_for_marker_refresh(frame_source, 3.0, shutdown_event):
            log.warning("[Teleport] marker refresh timeout - continuing anyway")

        elapsed = time.perf_counter() - started
        log.info("[Teleport] teleported to %s in %.1fs", waypoint_name, elapsed)
        return True

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _wait_for_screen(
        self,
        target_state: str,
        frame_source: Any,
        timeout: float,
        shutdown_event: threading.Event | None,
    ) -> bool:
        """Wait until classifier detects target screen state."""
        if self._classifier is None:
            return True
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
        frame_source: Any,
        timeout: float,
        shutdown_event: threading.Event | None,
    ) -> bool:
        """Wait for loading screen to appear then disappear."""
        if self._classifier is None:
            _chunked_sleep(min(timeout, 3.0), shutdown_event)
            return True
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
                        return True
            time.sleep(0.3)
        return False

    def _wait_for_marker_refresh(
        self,
        frame_source: Any,
        timeout: float,
        shutdown_event: threading.Event | None,
    ) -> bool:
        """Wait for quest marker to update after teleport."""
        _chunked_sleep(1.5, shutdown_event)
        if self._classifier is None:
            return True
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if shutdown_event and shutdown_event.is_set():
                return False
            if frame_source:
                frame = frame_source()
                if frame is not None:
                    state = self._classifier.classify(frame)
                    if state.state in ("world_hud", "overworld"):
                        return True
            _chunked_sleep(0.2, shutdown_event)
        return False
