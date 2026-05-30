"""Popup handler for game dialogs and confirmation popups.

Handles:
- U-45: Resin insufficient confirmation popup
- U-46: Material insufficient popup
- U-47: Wish animation skip detection and result recognition
- U-48: Popup click retry with 3-5s timeout
- U-51: Constellation upgrade double-confirm popup
- U-52: Shop "mora insufficient" popup

All cross-plane communication goes through StateBus. No blocking waits --
every poll loop uses chunked sleeps (~50 ms). Monotonic clock only
(time.perf_counter).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease, SkillResult
from execution.input_worker import InputWorker
from perception.perception_enhancements import PopupDetector, PopupDetection, PopupType

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Popup type constants
# ---------------------------------------------------------------------------

RESIN_INSUFFICIENT = "resin_insufficient"
MATERIAL_INSUFFICIENT = "material_insufficient"
MORA_INSUFFICIENT = "mora_insufficient"
CONSTELLATION_CONFIRM = "constellation_confirm"
WISH_RESULT = "wish_result"
DIALOG_BRANCH = "dialog_branch"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PopupHandlerError(Exception):
    pass


class PopupTimeout(PopupHandlerError):
    pass


class PopupNotFound(PopupHandlerError):
    pass


# ---------------------------------------------------------------------------
# Wish result types
# ---------------------------------------------------------------------------

class WishResultType(str, Enum):
    PERMANENT = "permanent"      # 纠缠之缘祈愿
    INTERTWINED = "intertwined"  # 相遇之缘祈愿
    ARMORY = "armory"           # 武器祈愿
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WishResult:
    """Recognized wish/祈愿 result."""
    result_type: WishResultType
    rarity: tuple[int, int, int] = (0, 0, 0)  # (three_star, four_star, five_star)
    five_star_items: tuple[str, ...] = ()
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Popup handler config
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PopupHandlerConfig:
    """Configuration for popup detection and handling."""
    click_retry_timeout_ms: int = 4000       # U-48: 3-5s retry timeout
    click_retry_interval_ms: int = 500       # retry interval
    wish_animation_timeout_ms: int = 30000  # wish animation max duration
    max_retry_attempts: int = 3


# ---------------------------------------------------------------------------
# Popup handler
# ---------------------------------------------------------------------------

class PopupHandler:
    """Handles game popups with retry logic (U-45, U-46, U-47, U-48, U-51, U-52).

    Integrates with PopupDetector from perception_enhancements.py.
    All waits use chunked polling with interrupt checking.
    """

    def __init__(
        self,
        state_bus: StateBus,
        input_worker: InputWorker,
        timebase: Timebase | None = None,
        config: PopupHandlerConfig | None = None,
    ) -> None:
        self._bus = state_bus
        self._worker = input_worker
        self._tb = timebase or Timebase()
        self._config = config or PopupHandlerConfig()
        self._detector = PopupDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_resin_insufficient(self, frame: Any) -> SkillResult:
        """Handle U-45: Resin insufficient confirmation popup.

        Detects the '树脂不足' dialog and clicks confirm.
        """
        return self._handle_popup_with_confirm(
            frame=frame,
            popup_keyword="树脂",
            confirm_text="确认",
            skill_name="popup:resin_insufficient",
        )

    def handle_material_insufficient(self, frame: Any) -> SkillResult:
        """Handle U-46: Material insufficient popup.

        Detects material shortage dialog and dismisses it.
        """
        return self._handle_popup_with_confirm(
            frame=frame,
            popup_keyword="材料",
            confirm_text="确定",
            skill_name="popup:material_insufficient",
        )

    def handle_mora_insufficient(self, frame: Any) -> SkillResult:
        """Handle U-52: Shop mora insufficient popup.

        Detects '摩拉不足' dialog and dismisses it.
        """
        return self._handle_popup_with_confirm(
            frame=frame,
            popup_keyword="摩拉",
            confirm_text="确定",
            skill_name="popup:mora_insufficient",
        )

    def handle_constellation_confirm(self, frame: Any) -> SkillResult:
        """Handle U-51: Constellation upgrade double-confirm popup.

        Detects the constellation upgrade confirmation dialog
        and clicks confirm to proceed.
        """
        return self._handle_popup_with_confirm(
            frame=frame,
            popup_keyword="命座",
            confirm_text="确认",
            skill_name="popup:constellation_confirm",
        )

    def detect_wish_animation(self, frame: Any) -> bool:
        """Detect U-47: Wish animation (祈愿动画) is playing.

        Detects the characteristic star animation during wish pulls.
        """
        # Wish animation detection: look for bright moving star particles
        # This is a placeholder - real implementation would analyze
        # bright point clusters that move radially from center
        notification_data = {
            "has_gold_tint": False,
            "text": "",
            "region": "center",
        }
        detection = self._detector.classify_popup(notification_data)
        # Wish animation has characteristic golden glow
        return detection.confidence > 0.7

    def detect_wish_result(self, frame: Any) -> WishResult:
        """Detect U-47: Wish result from the result screen.

        Recognizes which type of wish and item rarities.
        """
        # Placeholder detection logic
        # Real implementation would OCR the result screen
        return WishResult(
            result_type=WishResultType.UNKNOWN,
            rarity=(0, 0, 0),
            confidence=0.0,
        )

    def dismiss_popup(self, frame: Any, confirm: bool = True) -> SkillResult:
        """Dismiss any detected popup by clicking confirm or cancel.

        Args:
            frame: Current screen frame
            confirm: If True click confirm button, else cancel
        """
        started = self._tb.now()
        success = False
        attempts = 0

        while attempts < self._config.max_retry_attempts:
            self._check_interrupt()
            if self._is_popup_visible(frame):
                self._click_popup_button(confirm=confirm)
                self._sleep(0.5)  # Wait for animation
                if not self._is_popup_visible(frame):
                    success = True
                    break
            attempts += 1
            self._sleep(self._config.click_retry_interval_ms / 1000.0)

        finished = self._tb.now()
        return SkillResult(
            skill_name="popup:dismiss",
            status="SUCCESS" if success else "FAILED",
            failure_code=None if success else "POPUP_NOT_DISMISSED",
            started_at=started,
            finished_at=finished,
            payload={"attempts": attempts, "confirm": confirm},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_popup_with_confirm(
        self,
        frame: Any,
        popup_keyword: str,
        confirm_text: str,
        skill_name: str,
    ) -> SkillResult:
        """Generic handler for popups with confirm/cancel buttons."""
        started = self._tb.now()
        deadline = started + self._config.click_retry_timeout_ms / 1000.0

        attempts = 0
        success = False

        while self._tb.now() < deadline and attempts < self._config.max_retry_attempts:
            self._check_interrupt()

            if self._is_popup_visible(frame):
                log.info("[PopupHandler] %s detected, clicking confirm", skill_name)
                self._click_confirm_button()
                self._sleep(0.5)  # Wait for dialog animation

                if not self._is_popup_visible(frame):
                    success = True
                    break

            attempts += 1
            remaining = max(0.0, deadline - self._tb.now())
            self._sleep(min(self._config.click_retry_interval_ms / 1000.0, remaining))

        finished = self._tb.now()
        status = "SUCCESS" if success else "TIMEOUT"
        failure_code = None if success else f"TIMEOUT:{popup_keyword}"

        log.info("[PopupHandler] %s done status=%s attempts=%d", skill_name, status, attempts)
        return SkillResult(
            skill_name=skill_name,
            status=status,
            failure_code=failure_code,
            started_at=started,
            finished_at=finished,
            payload={"keyword": popup_keyword, "attempts": attempts},
        )

    def _is_popup_visible(self, frame: Any) -> bool:
        """Check if any game popup is currently visible.

        Uses screen state from StateBus and simple heuristics.
        """
        obs = self._bus.latest_observation.get()
        if obs is None:
            return False

        # Check for popup-related UI states
        ui_state = obs.ui_state.state if obs.ui_state else ""
        popup_states = {
            "dialog", "popup", "confirmation", "notice",
            "resin_insufficient", "material_insufficient",
            "mora_insufficient", "constellation_confirm",
        }
        if ui_state in popup_states:
            return True

        return False

    def _click_confirm_button(self) -> None:
        """Click the canonical confirm button position."""
        backend = self._worker.backend
        rect = backend.client_rect()
        # Standard confirm button is lower-right area
        nx, ny = 0.65, 0.85
        sx = int(rect.left + nx * rect.width)
        sy = int(rect.top + ny * rect.height)
        backend.click_at(sx, sy, reason="popup_handler:confirm")

    def _click_cancel_button(self) -> None:
        """Click the canonical cancel button position."""
        backend = self._worker.backend
        rect = backend.client_rect()
        nx, ny = 0.35, 0.85
        sx = int(rect.left + nx * rect.width)
        sy = int(rect.top + ny * rect.height)
        backend.click_at(sx, sy, reason="popup_handler:cancel")

    def _click_popup_button(self, confirm: bool = True) -> None:
        """Click popup button at canonical position."""
        if confirm:
            self._click_confirm_button()
        else:
            self._click_cancel_button()

    def _check_interrupt(self) -> None:
        """Check for high-priority interrupts and re-raise."""
        interrupt = self._bus.next_interrupt(timeout=0.0)
        if interrupt is not None and interrupt.priority <= 10:
            raise PopupHandlerError(f"interrupted: {interrupt.code}")

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep in chunks."""
        deadline = self._tb.now() + seconds
        chunk = 0.05  # 50ms chunks
        while self._tb.now() < deadline:
            self._check_interrupt()
            remaining = max(0.0, deadline - self._tb.now())
            time.sleep(min(chunk, remaining))


# ---------------------------------------------------------------------------
# Flow helpers for UIFlow integration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PopupDismissFlow:
    """Pre-defined flow for dismissing a specific popup type."""

    popup_type: str
    confirm: bool = True


def build_resin_dismiss_flow() -> tuple:
    """Build a UIFlow for dismissing resin insufficient popup."""
    from interaction.ui_flow_engine import UIStep, STEP_CLICK_AT, STEP_DELAY
    return (
        UIStep(type=STEP_CLICK_AT, nx=0.65, ny=0.85, reason="dismiss_resin", delay_ms=500),
        UIStep(type=STEP_DELAY, timeout_ms=500),
    )


def build_material_dismiss_flow() -> tuple:
    """Build a UIFlow for dismissing material insufficient popup."""
    from interaction.ui_flow_engine import UIStep, STEP_CLICK_AT, STEP_DELAY
    return (
        UIStep(type=STEP_CLICK_AT, nx=0.65, ny=0.85, reason="dismiss_material", delay_ms=500),
        UIStep(type=STEP_DELAY, timeout_ms=500),
    )


def build_mora_dismiss_flow() -> tuple:
    """Build a UIFlow for dismissing mora insufficient popup."""
    from interaction.ui_flow_engine import UIStep, STEP_CLICK_AT, STEP_DELAY
    return (
        UIStep(type=STEP_CLICK_AT, nx=0.65, ny=0.85, reason="dismiss_mora", delay_ms=500),
        UIStep(type=STEP_DELAY, timeout_ms=500),
    )


def build_constellation_confirm_flow() -> tuple:
    """Build a UIFlow for confirming constellation upgrade."""
    from interaction.ui_flow_engine import UIStep, STEP_CLICK_AT, STEP_DELAY
    return (
        UIStep(type=STEP_CLICK_AT, nx=0.65, ny=0.85, reason="confirm_constellation", delay_ms=500),
        UIStep(type=STEP_DELAY, timeout_ms=1000),
    )