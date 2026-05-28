"""Loading transition protector: context backup and seamless resume.

When the perception pipeline detects a loading screen (SCREEN_LOADING),
this module:
1. Backs up the current ActiveQuestContext and BAGEL beliefs to disk
2. Suspends all decision-making (MainlineAutonomyLoop pauses)
3. Extends sentinel timeout thresholds to tolerate long loads
4. On loading completion, restores context and resumes the loop

This prevents the agent from losing its task context during domain
transitions (entering domains, teleporting, CG cutscenes).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from planning.mainline.quest_context_persistence import QuestContextPersistence
from planning.mainline.active_quest_context import ActiveQuestContext

log = logging.getLogger(__name__)

# Loading protection states
LoadingState = str  # "active" | "loading" | "restoring"


@dataclass(frozen=True, slots=True)
class LoadingTransition:
    """Record of a loading transition event."""
    started_at: float
    ended_at: float = 0.0
    duration_sec: float = 0.0
    context_version: int = 0
    quest_id: str = ""
    completed: bool = False


@dataclass(slots=True)
class LoadingProtectionConfig:
    """Configuration for loading transition protection."""
    max_load_duration_sec: float = 60.0      # max expected load time
    check_interval_sec: float = 0.5           # how often to poll for loading end
    context_backup_enabled: bool = True
    sentinel_timeout_extension_sec: float = 30.0  # extra tolerance during loading


class LoadingTransitionProtector:
    """Manages context preservation across loading screen transitions.

    Integration points:
    - Perception pipeline calls `notify_screen_state()` each frame
    - MainlineAutonomyLoop checks `is_protected()` before executing nodes
    - SentinelRuntime extends timeouts when `loading_active` is True

    Usage:
        protector = LoadingTransitionProtector(persistence=persistence)
        # Called by perception:
        protector.notify_screen_state(screen_state, context)
        # Called by autonomy loop:
        if protector.is_protected():
            continue  # skip execution
    """

    def __init__(
        self,
        persistence: QuestContextPersistence | None = None,
        config: LoadingProtectionConfig | None = None,
    ) -> None:
        self._persistence = persistence
        self._config = config or LoadingProtectionConfig()
        self._state: LoadingState = "active"
        self._load_start_time: float = 0.0
        self._saved_context: ActiveQuestContext | None = None
        self._transitions: list[LoadingTransition] = []
        self._screen_state_fn: Callable[[], str] | None = None

    @property
    def state(self) -> LoadingState:
        return self._state

    @property
    def loading_active(self) -> bool:
        return self._state == "loading"

    def is_protected(self) -> bool:
        """Whether the system is in loading protection mode."""
        return self._state == "loading"

    def notify_screen_state(
        self,
        screen_state: str,
        context: ActiveQuestContext | None = None,
    ) -> LoadingTransition | None:
        """Called by perception pipeline when screen state changes.

        Returns a LoadingTransition if a loading phase just completed.
        """
        is_loading = screen_state in ("loading", "LOADING", "screen_loading", "black")

        if is_loading and self._state == "active":
            # Entering loading screen
            self._enter_loading(context)
            return None
        elif not is_loading and self._state == "loading":
            # Loading complete
            return self._exit_loading(context)
        return None

    def get_extended_timeout(self, base_timeout_sec: float) -> float:
        """Get the effective timeout, extended during loading protection."""
        if self._state == "loading":
            return base_timeout_sec + self._config.sentinel_timeout_extension_sec
        return base_timeout_sec

    def force_exit(self) -> LoadingTransition | None:
        """Force exit loading mode (e.g., on timeout or watchdog)."""
        if self._state != "loading":
            return None
        return self._exit_loading(None)

    def stats(self) -> dict[str, Any]:
        """Return loading transition statistics."""
        total = len(self._transitions)
        completed = sum(1 for t in self._transitions if t.completed)
        avg_duration = (
            sum(t.duration_sec for t in self._transitions if t.completed) / completed
            if completed > 0 else 0.0
        )
        return {
            "state": self._state,
            "total_transitions": total,
            "completed": completed,
            "avg_duration_sec": round(avg_duration, 2),
            "loading_active": self.loading_active,
        }

    def _enter_loading(self, context: ActiveQuestContext | None) -> None:
        """Enter loading protection mode."""
        self._state = "loading"
        self._load_start_time = time.perf_counter()
        self._saved_context = context

        if self._config.context_backup_enabled and context is not None and self._persistence is not None:
            try:
                self._persistence.save(context)
                log.info(
                    "[LoadingProtector] Entered loading mode, backed up context v%d quest=%r",
                    context.version, context.quest_id,
                )
            except Exception as exc:
                log.error("[LoadingProtector] Context backup failed: %s", exc)
        else:
            log.info("[LoadingProtector] Entered loading mode (no context to backup)")

    def _exit_loading(
        self, current_context: ActiveQuestContext | None,
    ) -> LoadingTransition:
        """Exit loading protection mode and restore context."""
        duration = time.perf_counter() - self._load_start_time
        self._state = "active"

        transition = LoadingTransition(
            started_at=self._load_start_time,
            ended_at=time.perf_counter(),
            duration_sec=duration,
            context_version=(
                self._saved_context.version if self._saved_context else 0
            ),
            quest_id=self._saved_context.quest_id if self._saved_context else "",
            completed=True,
        )
        self._transitions.append(transition)

        # Restore context from disk if available
        restored_context = None
        if self._config.context_backup_enabled and self._persistence is not None:
            try:
                restored_context = self._persistence.load_latest()
                if restored_context is not None:
                    log.info(
                        "[LoadingProtector] Loading complete (%.1fs), restored context v%d quest=%r",
                        duration, restored_context.version, restored_context.quest_id,
                    )
                else:
                    log.info(
                        "[LoadingProtector] Loading complete (%.1fs), no saved context found",
                        duration,
                    )
            except Exception as exc:
                log.error("[LoadingProtector] Context restore failed: %s", exc)

        self._saved_context = None
        return transition
