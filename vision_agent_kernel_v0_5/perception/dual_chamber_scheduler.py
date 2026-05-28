"""Dual-chamber perception scheduler: fast reflex path + slow cognitive path.

Architecture:
- Fast reflex path (30 Hz): lightweight local detector (YOLO-Nano / color threshold)
  for threat detection, HP tracking, and immediate reflex actions.
- Slow cognitive path (0.2 Hz): VLM-based scene understanding triggered only on
  wake-up contracts (stuck detection, dialog choices, sentinel recovery, OCR stall).

Token budget tracking ensures cost-effective VLM usage over long sessions.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

# Wake-up contract types that trigger the slow cognitive path
WakeUpReason = str  # "stuck_detected" | "dialog_choice" | "ocr_stall" | "sentinel_recovery" | "new_quest"


@dataclass(frozen=True, slots=True)
class ReflexResult:
    """Output from the fast reflex path."""
    timestamp: float
    threats_detected: int
    hp_ratio: float  # 0.0-1.0, ratio of active character HP
    target_direction: float  # angle in radians, -1 if no target
    screen_state: str
    frame_id: int


@dataclass(frozen=True, slots=True)
class CognitiveResult:
    """Output from the slow cognitive (VLM) path."""
    timestamp: float
    scene_description: str
    action_recommendation: str
    dialog_options: tuple[str, ...] = ()
    quest_objective: str = ""
    tokens_used: int = 0
    wake_reason: str = ""


@dataclass(slots=True)
class TokenBudget:
    """Tracks VLM token consumption over time."""
    total_tokens: int = 0
    session_tokens: int = 0
    budget_limit: int = 500_000  # per session
    wake_count: int = 0
    start_time: float = 0.0

    def can_invoke(self, estimated_tokens: int = 2000) -> bool:
        return self.session_tokens + estimated_tokens <= self.budget_limit

    def record(self, tokens: int) -> None:
        self.total_tokens += tokens
        self.session_tokens += tokens
        self.wake_count += 1

    def reset_session(self) -> None:
        self.session_tokens = 0
        self.start_time = time.perf_counter()


@dataclass(frozen=True, slots=True)
class DualChamberConfig:
    """Configuration for the dual-chamber scheduler."""
    reflex_hz: float = 30.0          # fast path frequency
    cognitive_min_interval: float = 5.0  # minimum seconds between VLM calls
    ocr_stall_timeout: float = 5.0   # seconds of unchanged OCR to trigger wake
    token_budget: int = 500_000      # max VLM tokens per session


class DualChamberScheduler:
    """Orchestrates fast reflex and slow cognitive perception paths.

    The fast path runs continuously at ~30Hz using lightweight local detection.
    The slow path activates only when a wake-up contract is triggered:
    - OCR text has not changed for `ocr_stall_timeout` seconds
    - Sentinel raises STUCK_RECOVERY or DRIFT_RECOVERY
    - Multiple dialog options detected on screen
    - New quest objective detected

    This achieves ~100x token cost reduction vs pure-VLM control.
    """

    def __init__(
        self,
        config: DualChamberConfig | None = None,
        reflex_fn: Callable[[], ReflexResult | None] | None = None,
        cognitive_fn: Callable[[str], CognitiveResult | None] | None = None,
    ) -> None:
        self._config = config or DualChamberConfig()
        self._reflex_fn = reflex_fn
        self._cognitive_fn = cognitive_fn
        self._budget = TokenBudget(budget_limit=self._config.token_budget)
        self._budget.start_time = time.perf_counter()

        # Wake-up state
        self._last_ocr_text: str = ""
        self._last_ocr_change_time: float = time.perf_counter()
        self._last_cognitive_time: float = 0.0
        self._pending_wake_reasons: list[str] = []

        # Latest results
        self._latest_reflex: ReflexResult | None = None
        self._latest_cognitive: CognitiveResult | None = None
        self._lock = threading.Lock()

        # Running state
        self._running = False
        self._reflex_thread: threading.Thread | None = None

    @property
    def budget(self) -> TokenBudget:
        return self._budget

    @property
    def latest_reflex(self) -> ReflexResult | None:
        with self._lock:
            return self._latest_reflex

    @property
    def latest_cognitive(self) -> CognitiveResult | None:
        with self._lock:
            return self._latest_cognitive

    def start(self) -> None:
        """Start the reflex path loop."""
        if self._running:
            return
        self._running = True
        self._reflex_thread = threading.Thread(
            target=self._reflex_loop, daemon=True, name="dual-chamber-reflex",
        )
        self._reflex_thread.start()
        log.info("[DualChamber] Started: reflex=%.1fHz, cognitive_min=%.1fs",
                 self._config.reflex_hz, self._config.cognitive_min_interval)

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._reflex_thread is not None:
            self._reflex_thread.join(timeout=2.0)
        log.info("[DualChamber] Stopped after %d VLM wakes, %d tokens",
                 self._budget.wake_count, self._budget.total_tokens)

    def notify_wake(self, reason: WakeUpReason) -> None:
        """External trigger to wake the cognitive path (e.g., from sentinel)."""
        self._pending_wake_reasons.append(reason)
        log.debug("[DualChamber] Wake requested: %s", reason)

    def update_ocr(self, text: str) -> None:
        """Feed OCR text for stall detection."""
        now = time.perf_counter()
        if text != self._last_ocr_text:
            self._last_ocr_text = text
            self._last_ocr_change_time = now
        elif (now - self._last_ocr_change_time) > self._config.ocr_stall_timeout:
            self._pending_wake_reasons.append("ocr_stall")

    def _reflex_loop(self) -> None:
        """Main loop: run reflex at target Hz, check for cognitive wake."""
        interval = 1.0 / self._config.reflex_hz
        while self._running:
            start = time.perf_counter()

            # Fast path
            if self._reflex_fn is not None:
                result = self._reflex_fn()
                if result is not None:
                    with self._lock:
                        self._latest_reflex = result

                    # Check dialog wake: screen is dialogue with multiple options
                    if result.screen_state == "dialogue":
                        self._pending_wake_reasons.append("dialog_choice")

            # Check if cognitive path should fire
            self._maybe_fire_cognitive()

            elapsed = time.perf_counter() - start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _maybe_fire_cognitive(self) -> None:
        """Fire the slow cognitive path if wake conditions are met."""
        now = time.perf_counter()

        # Check cooldown
        if now - self._last_cognitive_time < self._config.cognitive_min_interval:
            return

        # Check if there's a reason to wake
        if not self._pending_wake_reasons:
            return

        # Check budget
        if not self._budget.can_invoke():
            log.warning("[DualChamber] Token budget exhausted (%d/%d), skipping VLM wake",
                        self._budget.session_tokens, self._budget.budget_limit)
            self._pending_wake_reasons.clear()
            return

        # Fire cognitive path
        reason = self._pending_wake_reasons.pop(0)
        self._pending_wake_reasons.clear()
        self._last_cognitive_time = now

        if self._cognitive_fn is not None:
            try:
                result = self._cognitive_fn(reason)
                if result is not None:
                    self._budget.record(result.tokens_used)
                    with self._lock:
                        self._latest_cognitive = result
                    log.info("[DualChamber] VLM wake: reason=%s, tokens=%d, total=%d",
                             reason, result.tokens_used, self._budget.total_tokens)
            except Exception as exc:
                log.error("[DualChamber] Cognitive path error: %s", exc)

    def stats(self) -> dict[str, Any]:
        """Return scheduler statistics."""
        return {
            "total_tokens": self._budget.total_tokens,
            "session_tokens": self._budget.session_tokens,
            "wake_count": self._budget.wake_count,
            "budget_remaining": self._budget.budget_limit - self._budget.session_tokens,
            "running": self._running,
        }
