"""Unified recovery orchestrator: single entry point for all recovery scenarios.

Coordinates recovery from 7 failure categories:
1. Combat (death, defeat, low HP, boss failure)
2. Navigation (stuck, lost, target disappeared)
3. Quest (missing step, wrong order, marker gone)
4. UI (stuck in menu, dialog hung, loading timeout)
5. Environment (sheer cold, balethunder, fall damage)
6. System (crash, disconnect, model failure)
7. Resource (out of resin, no food, wrong team)

Routes to the appropriate recovery module and tracks escalation levels.
When all recovery attempts fail, escalates to human-agent collaboration.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Protocol

log = logging.getLogger(__name__)


class SemanticExecutor(Protocol):
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Recovery categories and severity
# ---------------------------------------------------------------------------

class RecoveryCategory(str, Enum):
    COMBAT = "combat"
    NAVIGATION = "navigation"
    QUEST = "quest"
    UI = "ui"
    ENVIRONMENT = "environment"
    SYSTEM = "system"
    RESOURCE = "resource"


class RecoverySeverity(IntEnum):
    TRIVIAL = 0     # Auto-retry, no user impact
    MINOR = 1       # Quick recovery (<30s), resumes where left off
    MODERATE = 2    # Recovery action needed (30s-2min)
    MAJOR = 3       # Significant setback (2-5min)
    CRITICAL = 4    # Full restart or human intervention needed


class EscalationLevel(IntEnum):
    AUTO = 0        # Automatic recovery
    ASSISTED = 1    # Recovery with guidance
    MANUAL = 2      # Human takes over
    ABORT = 3       # Abandon current task


# ---------------------------------------------------------------------------
# Recovery event
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RecoveryEvent:
    category: RecoveryCategory
    severity: RecoverySeverity
    description: str
    context: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    action_id: str
    category: RecoveryCategory
    action: str             # Semantic action to execute
    target: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    estimated_duration_sec: float = 10.0
    success_probability: float = 0.8


@dataclass(slots=True)
class RecoveryResult:
    success: bool
    category: RecoveryCategory
    escalation: EscalationLevel
    actions_taken: int = 0
    duration_sec: float = 0.0
    details: str = ""
    retry_recommended: bool = False


# ---------------------------------------------------------------------------
# Recovery strategy registry
# ---------------------------------------------------------------------------

_COMBAT_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    "character_death": RecoveryAction(
        "r_combat_death", RecoveryCategory.COMBAT,
        "navigate_to", target="nearest_statue",
        context={"reason": "revive"}, estimated_duration_sec=30.0,
    ),
    "boss_failure": RecoveryAction(
        "r_combat_boss", RecoveryCategory.COMBAT,
        "use_food", target="revive_food",
        context={"reason": "boss_retry_prep"}, estimated_duration_sec=15.0,
    ),
    "low_hp": RecoveryAction(
        "r_combat_hp", RecoveryCategory.COMBAT,
        "use_food", target="heal_food",
        context={"reason": "emergency_heal"}, estimated_duration_sec=5.0,
    ),
    "team_wipe": RecoveryAction(
        "r_combat_wipe", RecoveryCategory.COMBAT,
        "navigate_to", target="nearest_statue",
        context={"reason": "team_revive"}, estimated_duration_sec=45.0,
    ),
}

_NAVIGATION_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    "stuck": RecoveryAction(
        "r_nav_stuck", RecoveryCategory.NAVIGATION,
        "teleport_to", target="nearest_waypoint",
        context={"reason": "navigation_stuck"}, estimated_duration_sec=15.0,
    ),
    "lost": RecoveryAction(
        "r_nav_lost", RecoveryCategory.NAVIGATION,
        "navigate_to", target="quest_marker",
        context={"reason": "lost_recovery"}, estimated_duration_sec=20.0,
    ),
    "target_disappeared": RecoveryAction(
        "r_nav_target", RecoveryCategory.NAVIGATION,
        "navigate_to", target="area_center",
        context={"reason": "target_search"}, estimated_duration_sec=15.0,
    ),
}

_QUEST_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    "missing_step": RecoveryAction(
        "r_quest_step", RecoveryCategory.QUEST,
        "quest_advance",
        context={"reason": "step_recovery"}, estimated_duration_sec=10.0,
    ),
    "marker_gone": RecoveryAction(
        "r_quest_marker", RecoveryCategory.QUEST,
        "quest_follow_marker",
        context={"reason": "marker_recovery"}, estimated_duration_sec=15.0,
    ),
    "wrong_order": RecoveryAction(
        "r_quest_order", RecoveryCategory.QUEST,
        "quest_check_prerequisites",
        context={"reason": "order_fix"}, estimated_duration_sec=10.0,
    ),
}

_UI_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    "stuck_menu": RecoveryAction(
        "r_ui_menu", RecoveryCategory.UI,
        "press_escape",
        context={"reason": "exit_menu"}, estimated_duration_sec=3.0,
    ),
    "dialog_hung": RecoveryAction(
        "r_ui_dialog", RecoveryCategory.UI,
        "press_escape",
        context={"reason": "exit_dialog"}, estimated_duration_sec=3.0,
    ),
    "loading_timeout": RecoveryAction(
        "r_ui_loading", RecoveryCategory.UI,
        "press_escape",
        context={"reason": "loading_timeout"}, estimated_duration_sec=5.0,
    ),
}

_ENVIRONMENT_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    "sheer_cold": RecoveryAction(
        "r_env_cold", RecoveryCategory.ENVIRONMENT,
        "navigate_to", target="nearest_warmth",
        context={"reason": "sheer_cold_evacuate"}, estimated_duration_sec=10.0,
    ),
    "balethunder": RecoveryAction(
        "r_env_thunder", RecoveryCategory.ENVIRONMENT,
        "retreat",
        context={"reason": "balethunder_shelter"}, estimated_duration_sec=8.0,
    ),
    "drowning": RecoveryAction(
        "r_env_drown", RecoveryCategory.ENVIRONMENT,
        "navigate_to", target="nearest_shore",
        context={"reason": "drowning_recovery"}, estimated_duration_sec=10.0,
    ),
    "fall_damage": RecoveryAction(
        "r_env_fall", RecoveryCategory.ENVIRONMENT,
        "use_food", target="heal_food",
        context={"reason": "fall_recovery"}, estimated_duration_sec=5.0,
    ),
}

_SYSTEM_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    "crash": RecoveryAction(
        "r_sys_crash", RecoveryCategory.SYSTEM,
        "restart_session",
        estimated_duration_sec=60.0, success_probability=0.9,
    ),
    "disconnect": RecoveryAction(
        "r_sys_disconnect", RecoveryCategory.SYSTEM,
        "reconnect",
        estimated_duration_sec=30.0, success_probability=0.85,
    ),
    "model_failure": RecoveryAction(
        "r_sys_model", RecoveryCategory.SYSTEM,
        "fallback_model",
        estimated_duration_sec=10.0, success_probability=0.7,
    ),
}

_RESOURCE_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    "no_resin": RecoveryAction(
        "r_res_resin", RecoveryCategory.RESOURCE,
        "wait",
        context={"reason": "resin_recharge"}, estimated_duration_sec=480.0,
    ),
    "no_food": RecoveryAction(
        "r_res_food", RecoveryCategory.RESOURCE,
        "craft_item", target="sweet_madame",
        context={"reason": "food_crafting"}, estimated_duration_sec=30.0,
    ),
    "wrong_team": RecoveryAction(
        "r_res_team", RecoveryCategory.RESOURCE,
        "party_quick_config",
        context={"reason": "team_adjustment"}, estimated_duration_sec=20.0,
    ),
}

_ALL_RECOVERY_ACTIONS: dict[str, RecoveryAction] = {
    **_COMBAT_RECOVERY_ACTIONS,
    **_NAVIGATION_RECOVERY_ACTIONS,
    **_QUEST_RECOVERY_ACTIONS,
    **_UI_RECOVERY_ACTIONS,
    **_ENVIRONMENT_RECOVERY_ACTIONS,
    **_SYSTEM_RECOVERY_ACTIONS,
    **_RESOURCE_RECOVERY_ACTIONS,
}


# ---------------------------------------------------------------------------
# Unified Recovery Orchestrator
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RecoveryOrchestratorConfig:
    max_auto_retries: int = 3
    max_assisted_retries: int = 2
    max_actions_per_recovery: int = 5
    escalation_threshold_sec: float = 120.0


class RecoveryOrchestrator:
    """Single entry point for all recovery scenarios.

    Coordinates between 7 recovery categories, tracks escalation levels,
    and routes to the appropriate recovery strategy.

    Usage::

        orchestrator = RecoveryOrchestrator(executor=executor)
        result = orchestrator.recover(
            RecoveryEvent(RecoveryCategory.COMBAT, RecoverySeverity.MODERATE, "team_wipe")
        )
        if result.success:
            print("Recovered!")
        elif result.escalation >= EscalationLevel.MANUAL:
            print("Needs human intervention")
    """

    def __init__(
        self,
        executor: SemanticExecutor,
        config: RecoveryOrchestratorConfig | None = None,
    ) -> None:
        self._executor = executor
        self._config = config or RecoveryOrchestratorConfig()
        self._recovery_history: list[RecoveryResult] = []
        self._consecutive_failures: dict[RecoveryCategory, int] = {}
        self._last_recovery_time: float = 0.0

    @property
    def recovery_history(self) -> list[RecoveryResult]:
        return list(self._recovery_history)

    def recover(self, event: RecoveryEvent) -> RecoveryResult:
        """Execute recovery for the given event."""
        started = time.perf_counter()
        log.info(
            "[Recovery] event: category=%s severity=%s desc=%s",
            event.category.value, event.severity.name, event.description,
        )

        # Determine initial escalation level from severity
        escalation = self._severity_to_escalation(event.severity)

        # Check if we've been failing repeatedly in this category
        consecutive = self._consecutive_failures.get(event.category, 0)
        if consecutive >= self._config.max_auto_retries:
            escalation = EscalationLevel(max(escalation, EscalationLevel.ASSISTED))
        if consecutive >= self._config.max_auto_retries + self._config.max_assisted_retries:
            escalation = EscalationLevel(max(escalation, EscalationLevel.MANUAL))

        # Find recovery action
        action = self._find_recovery_action(event)
        if action is None:
            result = RecoveryResult(
                success=False,
                category=event.category,
                escalation=EscalationLevel.MANUAL,
                duration_sec=time.perf_counter() - started,
                details="no_recovery_action_found",
                retry_recommended=False,
            )
            self._record_result(result)
            return result

        # Execute recovery
        actions_taken = 0
        success = False
        for attempt in range(self._config.max_actions_per_recovery):
            ok = self._executor.execute_semantic(
                action.action, target=action.target, context=action.context,
            )
            actions_taken += 1
            if ok:
                success = True
                break
            # Retry with slight variation
            if attempt < self._config.max_actions_per_recovery - 1:
                self._chunked_sleep(1.0)

        elapsed = time.perf_counter() - started
        result = RecoveryResult(
            success=success,
            category=event.category,
            escalation=escalation if success else EscalationLevel(min(escalation + 1, 3)),
            actions_taken=actions_taken,
            duration_sec=elapsed,
            details=action.action_id if success else "recovery_failed",
            retry_recommended=not success and escalation < EscalationLevel.ABORT,
        )
        self._record_result(result)
        return result

    def get_status(self) -> dict[str, Any]:
        """Return current recovery status summary."""
        total = len(self._recovery_history)
        successes = sum(1 for r in self._recovery_history if r.success)
        return {
            "total_recoveries": total,
            "successful": successes,
            "success_rate": successes / total if total > 0 else 1.0,
            "consecutive_failures": {k.value: v for k, v in self._consecutive_failures.items()},
            "categories_recovered": list({
                r.category.value for r in self._recovery_history if r.success
            }),
        }

    def reset_consecutive(self, category: RecoveryCategory) -> None:
        """Reset consecutive failure counter for a category."""
        self._consecutive_failures.pop(category, None)

    @staticmethod
    def _severity_to_escalation(severity: RecoverySeverity) -> EscalationLevel:
        mapping = {
            RecoverySeverity.TRIVIAL: EscalationLevel.AUTO,
            RecoverySeverity.MINOR: EscalationLevel.AUTO,
            RecoverySeverity.MODERATE: EscalationLevel.AUTO,
            RecoverySeverity.MAJOR: EscalationLevel.ASSISTED,
            RecoverySeverity.CRITICAL: EscalationLevel.MANUAL,
        }
        return mapping.get(severity, EscalationLevel.AUTO)

    def _find_recovery_action(self, event: RecoveryEvent) -> RecoveryAction | None:
        """Find the best recovery action for the event."""
        # Check event context for specific failure type
        failure_type = event.context.get("failure_type", event.description)

        # Try exact match first
        action = _ALL_RECOVERY_ACTIONS.get(failure_type)
        if action is not None:
            return action

        # Try category-level matching
        category = event.category
        category_actions = {
            RecoveryCategory.COMBAT: _COMBAT_RECOVERY_ACTIONS,
            RecoveryCategory.NAVIGATION: _NAVIGATION_RECOVERY_ACTIONS,
            RecoveryCategory.QUEST: _QUEST_RECOVERY_ACTIONS,
            RecoveryCategory.UI: _UI_RECOVERY_ACTIONS,
            RecoveryCategory.ENVIRONMENT: _ENVIRONMENT_RECOVERY_ACTIONS,
            RecoveryCategory.SYSTEM: _SYSTEM_RECOVERY_ACTIONS,
            RecoveryCategory.RESOURCE: _RESOURCE_RECOVERY_ACTIONS,
        }
        actions = category_actions.get(category, {})
        if actions:
            # Return first action for the category
            return next(iter(actions.values()))

        return None

    def _record_result(self, result: RecoveryResult) -> None:
        self._recovery_history.append(result)
        if result.success:
            self._consecutive_failures.pop(result.category, None)
        else:
            self._consecutive_failures[result.category] = (
                self._consecutive_failures.get(result.category, 0) + 1
            )
        self._last_recovery_time = time.perf_counter()
        # Keep history bounded
        if len(self._recovery_history) > 100:
            self._recovery_history = self._recovery_history[-50:]

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))
