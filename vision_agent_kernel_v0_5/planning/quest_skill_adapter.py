"""Bridge quest-specific semantic actions to dialog/cutscene/navigation pipeline.

Handles dialog advancement, cutscene detection/skipping, quest marker
following, and quest state transitions by coordinating GenshinDialogHandler,
QuestStateMachine, and UIFlowSkillAdapter.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QuestSkillAdapterConfig:
    dialog_advance_delay_ms: int = 300
    cutscene_skip_delay_ms: int = 2000
    max_dialog_steps: int = 100
    quest_follow_timeout_sec: float = 60.0
    cutscene_check_interval_ms: int = 500


class QuestSkillAdapter:
    """Orchestrate quest actions: dialog, cutscene, navigation, state tracking.

    Coordinates with:
    - GenshinDialogHandler for dialog detection/advancement
    - QuestStateMachine for quest progression tracking
    - UIFlowSkillAdapter for semantic action dispatch
    """

    def __init__(
        self,
        *,
        backend: Any,
        state_bus: Any | None = None,
        dialog_handler: Any | None = None,
        quest_state_machine: Any | None = None,
        config: QuestSkillAdapterConfig | None = None,
    ) -> None:
        self._backend = backend
        self._bus = state_bus
        self._dialog_handler = dialog_handler
        self._quest_sm = quest_state_machine
        self._config = config or QuestSkillAdapterConfig()

    def drive_dialog(self, choice_selector: Callable[[list[str]], int] | None = None) -> bool:
        """Drive a dialog sequence to completion.

        Advances dialog by pressing F/clicking, selecting choices when presented.
        Returns True when dialog ends.
        """
        for step in range(self._config.max_dialog_steps):
            if self._bus is not None:
                obs = self._bus.latest_observation.get()
                if obs is not None:
                    state = getattr(obs, "ui_state", None)
                    if state is not None:
                        screen = getattr(state, "state", "unknown")
                        if screen != "dialog":
                            log.info("[QuestSkill] dialog ended after %d steps", step)
                            return True

            # Advance dialog
            self._advance_dialog()

            # Check for choices
            if self._dialog_handler is not None and choice_selector is not None:
                self._handle_dialog_choices(choice_selector)

        log.warning("[QuestSkill] dialog exceeded max steps (%d)", self._config.max_dialog_steps)
        return False

    def skip_cutscene(self, timeout_sec: float = 30.0) -> bool:
        """Skip cutscene by pressing Escape repeatedly until world_hud detected."""
        log.info("[QuestSkill] attempting to skip cutscene")
        deadline = time.perf_counter() + timeout_sec
        interval_sec = self._config.cutscene_check_interval_ms / 1000.0

        while time.perf_counter() < deadline:
            # Press escape to skip
            try:
                self._backend.key_press("escape", reason="skip_cutscene")
            except Exception:
                pass

            self._busy_wait(interval_sec, deadline)

            # Check if we're back in gameplay
            if self._bus is not None:
                obs = self._bus.latest_observation.get()
                if obs is not None:
                    state = getattr(obs, "ui_state", None)
                    if state is not None:
                        screen = getattr(state, "state", "unknown")
                        if screen in ("world_hud", "overworld", "dialog"):
                            log.info("[QuestSkill] cutscene skipped, screen=%s", screen)
                            return True

        log.warning("[QuestSkill] cutscene skip timed out after %.1fs", timeout_sec)
        return False

    def follow_quest_marker(self, navigate_fn: Callable[[], bool]) -> bool:
        """Follow quest marker using provided navigation function."""
        log.info("[QuestSkill] following quest marker")
        try:
            return navigate_fn()
        except Exception as exc:
            log.warning("[QuestSkill] quest marker following failed: %s", exc)
            return False

    def advance_quest(self, evidence: str = "") -> bool:
        """Advance quest state machine by one step."""
        if self._quest_sm is None:
            log.debug("[QuestSkill] no quest state machine, skipping advance")
            return True
        next_step = self._quest_sm.advance(evidence=evidence)
        if next_step is None:
            log.info("[QuestSkill] quest chain completed")
            return True
        log.info("[QuestSkill] advanced to step: %s", next_step.description)
        return True

    def check_prerequisites(self, current_ar: int = 0) -> bool:
        """Check if current quest step prerequisites are met."""
        if self._quest_sm is None:
            return True
        return self._quest_sm.check_prerequisites(current_ar)

    def _advance_dialog(self) -> None:
        """Send input to advance dialog by one step."""
        try:
            self._backend.key_down("f", reason="advance_dialog")
            self._busy_wait(0.08, time.perf_counter() + 0.08)
            self._backend.key_up("f", reason="advance_dialog_done")
        except Exception:
            pass
        self._busy_wait(
            self._config.dialog_advance_delay_ms / 1000.0,
            time.perf_counter() + self._config.dialog_advance_delay_ms / 1000.0
        )

    def _handle_dialog_choices(self, choice_selector: Callable[[list[str]], int]) -> None:
        """Handle dialog choices if present."""
        if self._dialog_handler is None:
            return
        try:
            # Try to extract choices from dialog handler if available
            choices: list[str] = []
            if hasattr(self._dialog_handler, "current_choices"):
                choices = list(getattr(self._dialog_handler, "current_choices", []))
            elif hasattr(self._dialog_handler, "get_choices"):
                get_fn = getattr(self._dialog_handler, "get_choices", None)
                if callable(get_fn):
                    choices = list(get_fn())

            # If no choices extracted, default to first option
            if not choices:
                choices = ["continue"]

            choice_idx = choice_selector(choices)
            if choice_idx < 0:
                choice_idx = 0
            result = self._dialog_handler.select_choice(choice_idx)
            if result.get("input") == "click_at":
                log.info("[QuestSkill] selected dialog choice %d", choice_idx)
        except Exception as exc:
            log.debug("[QuestSkill] dialog choice handling skipped: %s", exc)

    @staticmethod
    def _busy_wait(seconds: float, deadline: float) -> None:
        """Poll-based wait without blocking sleep.

        Uses a tight spin loop to avoid the cumulative latency that time.sleep()
        introduces when called repeatedly in a loop. Check deadline each iteration
        to support early-exit scenarios.
        """
        while time.perf_counter() < deadline and time.perf_counter() < deadline:
            pass  # Tight spin — exits as soon as deadline is reached

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        QuestSkillAdapter._busy_wait(seconds, deadline)
