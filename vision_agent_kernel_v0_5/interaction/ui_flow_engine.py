"""Declarative UI flow engine for multi-step menu navigation.

Extends the VisualActionBlock pattern with screen-state-aware step types
suited for Genshin Impact's menu-driven UI: clicking at normalized
coordinates, waiting for specific screen states, scrolling lists,
handling popups, and sequencing arbitrary menu operations.

All cross-plane communication goes through StateBus.  No blocking waits --
every poll loop uses chunked sleeps (~50 ms).  Monotonic clock only
(time.perf_counter).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import InputLease, Observation, SkillResult
from execution.input_worker import InputWorker
from perception.genshin_screen_classifier import GenshinScreenClassifier

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UIFlowInterrupted(RuntimeError):
    def __init__(self, interrupt: Interrupt) -> None:
        self.interrupt = interrupt
        super().__init__(f"ui flow interrupted: {interrupt.code}")


class UIFlowTimeout(RuntimeError):
    pass


class UIFlowPreconditionFailed(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

TelemetrySink = Callable[[str, dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Step & Flow definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class UIStep:
    """A single atomic UI operation inside a UIFlow."""

    type: str
    # press_key / key_combo
    key: str | None = None
    # click_at
    nx: float | None = None   # normalised x  (0.0 – 1.0, relative to client area)
    ny: float | None = None   # normalised y
    # wait_state
    target_state: str | None = None
    # scroll
    delta: int = 0            # scroll clicks; negative = up, positive = down
    # timing
    timeout_ms: int = 5000
    delay_ms: int = 0         # extra fixed delay after step completes
    # general
    reason: str = ""
    # hold
    hold_ms: int = 0


@dataclass(frozen=True, slots=True)
class UIFlow:
    """A named, declarative sequence of UISteps."""

    name: str
    description: str = ""
    steps: tuple[UIStep, ...] = ()
    precondition_state: str | None = None  # required screen state before starting
    escape_on_failure: bool = True         # press Escape to clean up on failure


# ---------------------------------------------------------------------------
# Step-type constants (for type-safe step construction)
# ---------------------------------------------------------------------------

STEP_PRESS_KEY = "press_key"
STEP_CLICK_AT = "click_at"
STEP_WAIT_STATE = "wait_state"
STEP_WAIT_LOADING = "wait_loading"
STEP_WAIT_NOT_LOADING = "wait_not_loading"
STEP_DELAY = "delay"
STEP_SCROLL = "scroll"
STEP_CONFIRM = "confirm"
STEP_CANCEL = "cancel"
STEP_SCROLL_UP = "scroll_up"
STEP_SCROLL_DOWN = "scroll_down"
STEP_OPEN_MENU = "open_menu"
STEP_HOLD_CLICK = "hold_click"

# Canonical confirm / cancel positions (normalised to client area)
_CONFIRM_NX = 0.65
_CONFIRM_NY = 0.85
_CANCEL_NX = 0.35
_CANCEL_NY = 0.85

# Canonical menu button positions (Paimon menu grid)
_MENU_BUTTONS: dict[str, tuple[float, float]] = {
    "character":     (0.35, 0.30),
    "backpack":      (0.55, 0.30),
    "map":           (0.75, 0.30),
    "quest":         (0.35, 0.48),
    "party":         (0.55, 0.48),
    "wish":          (0.75, 0.48),
    "adventure":     (0.35, 0.66),
    "battle_pass":   (0.55, 0.66),
    "events":        (0.75, 0.66),
    "shop":          (0.35, 0.84),
    "settings":      (0.55, 0.84),
    "feedback":      (0.75, 0.84),
}

# Character screen tabs (normalised x positions)
_CHAR_TABS: dict[str, float] = {
    "details":    0.25,
    "weapon":     0.35,
    "artifacts":  0.45,
    "talents":    0.55,
    "constellation": 0.65,
}


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class UIFlowExecutor:
    """Execute declarative UIFlow sequences against Genshin's UI."""

    def __init__(
        self,
        state_bus: StateBus,
        input_worker: InputWorker,
        classifier: GenshinScreenClassifier | None = None,
        timebase: Timebase | None = None,
        wait_chunk_ms: int = 50,
        telemetry_sink: TelemetrySink | None = None,
    ) -> None:
        if wait_chunk_ms <= 0 or wait_chunk_ms > 200:
            raise ValueError("wait_chunk_ms must be in 1..200")
        self._bus = state_bus
        self._worker = input_worker
        self._classifier = classifier
        self._tb = timebase or Timebase()
        self._chunk = wait_chunk_ms / 1000.0
        self._telemetry = telemetry_sink

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, flow: UIFlow) -> SkillResult:
        """Run all steps in *flow*.  Returns a SkillResult."""
        started = self._tb.now()
        payload: dict[str, Any] = {"flow": flow.name}
        log.info("[UIFlow] start name=%s", flow.name)
        try:
            self._check_interrupt()
            self._check_shutdown()
            self._check_precondition(flow)
            for idx, step in enumerate(flow.steps):
                self._check_interrupt()
                self._check_shutdown()
                self._emit("step_start", {"flow": flow.name, "idx": idx, "type": step.type})
                self._exec_step(flow.name, idx, step)
                self._emit("step_done", {"flow": flow.name, "idx": idx, "type": step.type})
                if step.delay_ms > 0:
                    self._sleep(step.delay_ms / 1000.0)
            status, failure_code = "SUCCESS", None
        except UIFlowInterrupted as exc:
            payload["interrupt"] = {"code": exc.interrupt.code, "priority": exc.interrupt.priority}
            status, failure_code = "CANCELLED", exc.interrupt.code
        except UIFlowTimeout as exc:
            payload["timeout_detail"] = str(exc)
            status, failure_code = "TIMEOUT", str(exc)
        except UIFlowPreconditionFailed as exc:
            payload["precondition"] = str(exc)
            status, failure_code = "PRECONDITION_FAILED", str(exc)
        except Exception as exc:
            payload["error"] = repr(exc)
            status, failure_code = "FAILED", repr(exc)
            if flow.escape_on_failure:
                self._try_escape()
        payload["final_state"] = self._current_screen_state()
        finished = self._tb.now()
        result = SkillResult(
            skill_name=f"ui_flow:{flow.name}",
            status=status,
            failure_code=failure_code,
            started_at=started,
            finished_at=finished,
            payload=payload,
        )
        log.info("[UIFlow] done name=%s status=%s", flow.name, status)
        return result

    # ------------------------------------------------------------------
    # Step dispatch
    # ------------------------------------------------------------------

    def _exec_step(self, flow_name: str, idx: int, step: UIStep) -> None:
        handler = {
            STEP_PRESS_KEY:      self._step_press_key,
            STEP_CLICK_AT:       self._step_click_at,
            STEP_WAIT_STATE:     self._step_wait_state,
            STEP_WAIT_LOADING:   self._step_wait_loading,
            STEP_WAIT_NOT_LOADING: self._step_wait_not_loading,
            STEP_DELAY:          self._step_delay,
            STEP_SCROLL:         self._step_scroll,
            STEP_CONFIRM:        self._step_confirm,
            STEP_CANCEL:         self._step_cancel,
            STEP_SCROLL_UP:      self._step_scroll_up,
            STEP_SCROLL_DOWN:    self._step_scroll_down,
            STEP_OPEN_MENU:      self._step_open_menu,
            STEP_HOLD_CLICK:     self._step_hold_click,
        }.get(step.type)
        if handler is None:
            raise ValueError(f"unsupported UIStep type: {step.type!r}")
        handler(step)

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _step_press_key(self, step: UIStep) -> None:
        if step.key is None:
            raise ValueError("press_key step requires 'key'")
        now = self._tb.now()
        lease_ms = 120
        down = InputLease(
            lease_id=str(uuid.uuid4()),
            owner="ui_flow",
            priority=30,
            key_states={step.key: "DOWN"},
            mouse_delta=None,
            created_at=now,
            expires_at=now + lease_ms / 1000.0,
            reason=step.reason or f"ui_flow:press_key:{step.key}",
        )
        if not self._worker.submit_lease(down):
            raise RuntimeError("input worker rejected key-down lease")
        up = InputLease(
            lease_id=str(uuid.uuid4()),
            owner="ui_flow:release",
            priority=30,
            key_states={step.key: "UP"},
            mouse_delta=None,
            created_at=now,
            expires_at=now + lease_ms / 1000.0 + 0.05,
            reason=f"ui_flow:key_up:{step.key}",
        )
        if not self._worker.submit_lease(up):
            raise RuntimeError("input worker rejected key-up lease")

    def _step_click_at(self, step: UIStep) -> None:
        if step.nx is None or step.ny is None:
            raise ValueError("click_at step requires 'nx' and 'ny'")
        backend = self._worker.backend
        rect = backend.client_rect()
        sx = int(rect.left + step.nx * rect.width)
        sy = int(rect.top + step.ny * rect.height)
        backend.click_at(sx, sy, reason=step.reason or f"ui_flow:click_at:({step.nx:.2f},{step.ny:.2f})")

    def _step_wait_state(self, step: UIStep) -> None:
        if step.target_state is None:
            raise ValueError("wait_state step requires 'target_state'")
        deadline = self._tb.now() + step.timeout_ms / 1000.0
        while self._tb.now() < deadline:
            self._check_interrupt()
            state = self._current_screen_state()
            if state == step.target_state:
                return
            remaining = max(0.0, deadline - self._tb.now())
            self._sleep(min(self._chunk, remaining))
        raise UIFlowTimeout(f"timeout waiting for state {step.target_state!r}")

    def _step_wait_loading(self, step: UIStep) -> None:
        deadline = self._tb.now() + step.timeout_ms / 1000.0
        while self._tb.now() < deadline:
            self._check_interrupt()
            state = self._current_screen_state()
            if state == "loading_screen":
                return
            remaining = max(0.0, deadline - self._tb.now())
            self._sleep(min(self._chunk, remaining))
        raise UIFlowTimeout("timeout waiting for loading screen")

    def _step_wait_not_loading(self, step: UIStep) -> None:
        deadline = self._tb.now() + step.timeout_ms / 1000.0
        while self._tb.now() < deadline:
            self._check_interrupt()
            state = self._current_screen_state()
            if state != "loading_screen" and state != "unknown":
                return
            remaining = max(0.0, deadline - self._tb.now())
            self._sleep(min(self._chunk, remaining))
        raise UIFlowTimeout("timeout waiting for loading to finish")

    def _step_delay(self, step: UIStep) -> None:
        self._sleep(step.timeout_ms / 1000.0)

    def _step_scroll(self, step: UIStep) -> None:
        backend = self._worker.backend
        for _ in range(abs(step.delta)):
            self._check_interrupt()
            backend.mouse_scroll(delta=-1 if step.delta < 0 else 1, reason=step.reason or "ui_flow:scroll")
            self._sleep(0.05)

    def _step_confirm(self, step: UIStep) -> None:
        backend = self._worker.backend
        rect = backend.client_rect()
        backend.click_at(
            int(rect.left + _CONFIRM_NX * rect.width),
            int(rect.top + _CONFIRM_NY * rect.height),
            reason=step.reason or "ui_flow:confirm",
        )

    def _step_cancel(self, step: UIStep) -> None:
        backend = self._worker.backend
        rect = backend.client_rect()
        backend.click_at(
            int(rect.left + _CANCEL_NX * rect.width),
            int(rect.top + _CANCEL_NY * rect.height),
            reason=step.reason or "ui_flow:cancel",
        )

    def _step_scroll_up(self, step: UIStep) -> None:
        backend = self._worker.backend
        n = abs(step.delta) if step.delta != 0 else 3
        for _ in range(n):
            self._check_interrupt()
            backend.mouse_scroll(delta=-1, reason=step.reason or "ui_flow:scroll_up")
            self._sleep(0.05)

    def _step_scroll_down(self, step: UIStep) -> None:
        backend = self._worker.backend
        n = abs(step.delta) if step.delta != 0 else 3
        for _ in range(n):
            self._check_interrupt()
            backend.mouse_scroll(delta=1, reason=step.reason or "ui_flow:scroll_down")
            self._sleep(0.05)

    def _step_open_menu(self, step: UIStep) -> None:
        self._step_press_key(UIStep(type=STEP_PRESS_KEY, key="escape", reason="open_paimon_menu"))
        self._sleep(0.3)

    def _step_hold_click(self, step: UIStep) -> None:
        if step.nx is None or step.ny is None:
            raise ValueError("hold_click step requires 'nx' and 'ny'")
        backend = self._worker.backend
        rect = backend.client_rect()
        sx = int(rect.left + step.nx * rect.width)
        sy = int(rect.top + step.ny * rect.height)
        # Move cursor to position first, then hold-click at that position
        backend._user32.SetCursorPos(sx, sy)
        time.sleep(0.02)
        duration = step.hold_ms / 1000.0 if step.hold_ms > 0 else 0.5
        backend.hold_click(duration_sec=duration, reason=step.reason or "ui_flow:hold_click")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_screen_state(self) -> str:
        obs = self._bus.latest_observation.get()
        if obs is not None and obs.ui_state is not None:
            return obs.ui_state.state
        return "unknown"

    def _check_precondition(self, flow: UIFlow) -> None:
        if flow.precondition_state is None:
            return
        current = self._current_screen_state()
        if current != flow.precondition_state:
            raise UIFlowPreconditionFailed(
                f"need {flow.precondition_state!r} but got {current!r}"
            )

    def _check_interrupt(self) -> None:
        deferred: list[Interrupt] = []
        interrupt = self._bus.next_interrupt(timeout=0.0)
        while interrupt is not None:
            if interrupt.priority <= 10:
                for item in deferred:
                    self._bus.publish_interrupt(item)
                raise UIFlowInterrupted(interrupt)
            deferred.append(interrupt)
            interrupt = self._bus.next_interrupt(timeout=0.0)
        for item in deferred:
            try:
                self._bus.publish_interrupt(item)
            except Exception:
                log.warning("[UIFlow] failed to re-publish deferred interrupt")

    def _check_shutdown(self) -> None:
        if self._bus.shutdown_flag.is_set():
            raise UIFlowInterrupted(Interrupt(
                priority=0, timestamp=self._tb.now(),
                code="SHUTDOWN", source="ui_flow_engine",
            ))

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep in chunks.  Used by polling loops and delay steps."""
        deadline = self._tb.now() + seconds
        while self._tb.now() < deadline:
            self._check_interrupt()
            remaining = max(0.0, deadline - self._tb.now())
            time.sleep(min(self._chunk, remaining))

    def _try_escape(self) -> None:
        try:
            self._step_press_key(UIStep(type=STEP_PRESS_KEY, key="escape", reason="cleanup"))
        except Exception:
            pass

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._telemetry is not None:
            self._telemetry(event, {"ts": self._tb.now(), **payload})


# ---------------------------------------------------------------------------
# Flow builder helpers — ergonomic constructors for common flows
# ---------------------------------------------------------------------------

def press(key: str, reason: str = "") -> UIStep:
    return UIStep(type=STEP_PRESS_KEY, key=key, reason=reason)


def click(nx: float, ny: float, reason: str = "", delay_ms: int = 0) -> UIStep:
    return UIStep(type=STEP_CLICK_AT, nx=nx, ny=ny, reason=reason, delay_ms=delay_ms)


def wait_state(state: str, timeout_ms: int = 5000, reason: str = "") -> UIStep:
    return UIStep(type=STEP_WAIT_STATE, target_state=state, timeout_ms=timeout_ms, reason=reason)


def wait_loading(timeout_ms: int = 15000, reason: str = "") -> UIStep:
    return UIStep(type=STEP_WAIT_LOADING, timeout_ms=timeout_ms, reason=reason)


def wait_not_loading(timeout_ms: int = 15000, reason: str = "") -> UIStep:
    return UIStep(type=STEP_WAIT_NOT_LOADING, timeout_ms=timeout_ms, reason=reason)


def delay(ms: int) -> UIStep:
    return UIStep(type=STEP_DELAY, timeout_ms=ms)


def scroll(delta: int, reason: str = "") -> UIStep:
    return UIStep(type=STEP_SCROLL, delta=delta, reason=reason)


def confirm(reason: str = "") -> UIStep:
    return UIStep(type=STEP_CONFIRM, reason=reason)


def cancel(reason: str = "") -> UIStep:
    return UIStep(type=STEP_CANCEL, reason=reason)


def open_menu(reason: str = "") -> UIStep:
    return UIStep(type=STEP_OPEN_MENU, reason=reason)


def click_menu_button(name: str, delay_ms: int = 500) -> UIStep:
    pos = _MENU_BUTTONS.get(name)
    if pos is None:
        raise ValueError(f"unknown menu button: {name!r}.  Known: {list(_MENU_BUTTONS)}")
    return UIStep(type=STEP_CLICK_AT, nx=pos[0], ny=pos[1], reason=f"menu:{name}", delay_ms=delay_ms)


def click_char_tab(tab: str, delay_ms: int = 300) -> UIStep:
    nx = _CHAR_TABS.get(tab)
    if nx is None:
        raise ValueError(f"unknown char tab: {tab!r}.  Known: {list(_CHAR_TABS)}")
    return UIStep(type=STEP_CLICK_AT, nx=nx, ny=0.10, reason=f"char_tab:{tab}", delay_ms=delay_ms)
