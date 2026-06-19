"""Crash recovery physical actions — executes real game restart and reconnect.

Extends CrashRecoveryOrchestrator with actual physical actions through
the execution plane: game restart, reconnect, and state restoration.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)


class RecoveryAction(str, Enum):
    """Physical recovery actions."""
    NONE = "none"
    WAIT = "wait"
    PRESS_KEY = "press_key"
    CLICK_POSITION = "click_position"
    LAUNCH_GAME = "launch_game"
    WAIT_FOR_WINDOW = "wait_for_window"
    NAVIGATE_MENU = "navigate_menu"


@dataclass(slots=True, frozen=True)
class RecoveryStep:
    """A single physical recovery step."""
    action: RecoveryAction
    params: dict[str, Any]
    timeout_sec: float = 10.0
    description: str = ""


@runtime_checkable
class PhysicalExecutor(Protocol):
    """Protocol for executing physical recovery actions."""
    def execute_step(self, step: RecoveryStep) -> bool: ...


class CrashRecoveryPhysicalActions:
    """Executes physical recovery actions for crash recovery.

    Provides high-level recovery sequences (restart, reconnect, restore)
    that translate to concrete physical actions through the execution plane.
    """

    # Timing constants
    GAME_LAUNCH_WAIT_SEC = 30.0
    RECONNECT_WAIT_SEC = 15.0
    MENU_NAVIGATION_DELAY = 0.5

    def __init__(self, executor: PhysicalExecutor | None = None) -> None:
        self._executor = executor

    def execute_restart_sequence(self, game_executable: str = "") -> list[RecoveryStep]:
        """Generate and execute the restart sequence.

        Returns the list of steps executed (for audit/logging).
        """
        steps = self._build_restart_steps(game_executable)
        if self._executor is None:
            log.warning("[CrashPhysical] No executor — steps planned but not executed")
            return steps

        for step in steps:
            success = self._executor.execute_step(step)
            if not success:
                log.warning("[CrashPhysical] Step failed: %s", step.description)
                break
            log.info("[CrashPhysical] Step completed: %s", step.description)

        return steps

    def execute_reconnect_sequence(self) -> list[RecoveryStep]:
        """Generate and execute reconnect sequence after game restart."""
        steps = [
            RecoveryStep(
                action=RecoveryAction.WAIT,
                params={"duration_sec": self.RECONNECT_WAIT_SEC},
                timeout_sec=self.RECONNECT_WAIT_SEC + 5.0,
                description="Wait for server connection",
            ),
            RecoveryStep(
                action=RecoveryAction.WAIT_FOR_WINDOW,
                params={"window_title": "原神", "alt_titles": ["Genshin Impact"]},
                timeout_sec=60.0,
                description="Wait for game window to appear",
            ),
            RecoveryStep(
                action=RecoveryAction.WAIT,
                params={"duration_sec": 5.0},
                timeout_sec=10.0,
                description="Wait for loading to settle",
            ),
        ]

        if self._executor is None:
            return steps

        for step in steps:
            success = self._executor.execute_step(step)
            if not success:
                log.warning("[CrashPhysical] Reconnect step failed: %s", step.description)
                break

        return steps

    def execute_restore_sequence(
        self,
        quest_id: str = "",
        quest_phase: str = "",
    ) -> list[RecoveryStep]:
        """Generate and execute state restoration steps."""
        steps = []

        if quest_id:
            steps.append(RecoveryStep(
                action=RecoveryAction.NAVIGATE_MENU,
                params={"menu": "quest_log", "quest_id": quest_id},
                timeout_sec=15.0,
                description=f"Navigate to quest {quest_id}",
            ))

        if quest_phase:
            steps.append(RecoveryStep(
                action=RecoveryAction.NAVIGATE_MENU,
                params={"action": "continue_quest", "phase": quest_phase},
                timeout_sec=10.0,
                description=f"Continue quest at phase {quest_phase}",
            ))

        if self._executor is None:
            return steps

        for step in steps:
            success = self._executor.execute_step(step)
            if not success:
                log.warning("[CrashPhysical] Restore step failed: %s", step.description)
                break

        return steps

    def _build_restart_steps(self, game_executable: str) -> list[RecoveryStep]:
        steps: list[RecoveryStep] = []

        if game_executable:
            steps.append(RecoveryStep(
                action=RecoveryAction.LAUNCH_GAME,
                params={"executable": game_executable},
                timeout_sec=5.0,
                description="Launch game executable",
            ))

        steps.append(RecoveryStep(
            action=RecoveryAction.WAIT,
            params={"duration_sec": self.GAME_LAUNCH_WAIT_SEC},
            timeout_sec=self.GAME_LAUNCH_WAIT_SEC + 10.0,
            description="Wait for game to initialize",
        ))

        steps.append(RecoveryStep(
            action=RecoveryAction.WAIT_FOR_WINDOW,
            params={"window_title": "原神", "alt_titles": ["Genshin Impact"]},
            timeout_sec=60.0,
            description="Wait for game window",
        ))

        return steps
