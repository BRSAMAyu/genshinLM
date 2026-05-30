"""Human-Agent collaboration protocol: autonomy levels, control handover, safety guardrails.

Implements the 4-level autonomy system from GENSHIN_HUMAN_AGENT_COLLABORATION.md:
- Level 0 (Manual): Agent is passive advisor, no game input
- Level 1 (Assisted): Low-risk auto, high-risk requires confirmation
- Level 2 (Supervised): Full autonomy with user override capability
- Level 3 (Autonomous): Full autonomy, exception-only notifications

Plus: control handover protocol, safety guardrails, permission checks.
"""
from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


class AutonomyLevel(enum.Enum):
    MANUAL = 0       # L0: passive advisor
    ASSISTED = 1     # L1: low-risk auto, high-risk needs confirmation
    SUPERVISED = 2   # L2: full autonomy, user can override
    AUTONOMOUS = 3   # L3: full autonomy, exception-only notifications


class ActionRisk(enum.Enum):
    LOW = "low"
    HIGH = "high"
    FORBIDDEN = "forbidden"


class HandoverStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


# ---------------------------------------------------------------------------
# Permission matrix: which actions are allowed at each autonomy level
# ---------------------------------------------------------------------------

_LOW_RISK_ACTIONS: frozenset[str] = frozenset({
    "accept_commission", "complete_commission", "claim_commission_reward",
    "use_resin_domain", "use_resin_boss",
    "open_inventory", "open_character_panel", "open_map",
    "collect_material", "collect_oculus",
    "claim_expedition", "claim_mail", "claim_bp_reward", "claim_event_reward",
    "navigate_menu", "close_menu",
    "teleport", "walk_to",
    "basic_attack", "use_skill", "use_burst", "switch_character",
    "revive_character", "use_food",
})

_HIGH_RISK_ACTIONS: frozenset[str] = frozenset({
    "wish", "enter_boss_fight", "advance_main_quest", "advance_story_quest",
    "enhance_artifact", "shop_buy", "level_up_character",
    "ascend_character", "level_up_talent", "level_up_weapon",
    "forge_item", "cook_food",
    "enter_domain", "enter_spiral_abyss",
})

_FORBIDDEN_ACTIONS: frozenset[str] = frozenset({
    "delete_character", "destroy_artifact_5star",
    "spend_real_money", "link_account", "change_password",
    "modify_game_settings_graphics", "modify_game_settings_audio",
})


def classify_action_risk(action: str) -> ActionRisk:
    if action in _FORBIDDEN_ACTIONS:
        return ActionRisk.FORBIDDEN
    if action in _HIGH_RISK_ACTIONS:
        return ActionRisk.HIGH
    if action in _LOW_RISK_ACTIONS:
        return ActionRisk.LOW
    # Unknown actions default to HIGH (conservative)
    return ActionRisk.HIGH


# ---------------------------------------------------------------------------
# Autonomy-level permission check
# ---------------------------------------------------------------------------

def is_action_allowed(level: AutonomyLevel, action: str) -> tuple[bool, str]:
    """Check if an action is allowed at the given autonomy level.

    Returns (allowed, reason).
    """
    risk = classify_action_risk(action)

    if risk == ActionRisk.FORBIDDEN:
        return False, f"action '{action}' is forbidden at all levels"

    if level == AutonomyLevel.MANUAL:
        return False, "L0 Manual: no actions allowed"

    if level == AutonomyLevel.ASSISTED:
        if risk == ActionRisk.LOW:
            return True, "L1: low-risk auto-approved"
        return False, f"L1: high-risk action '{action}' requires user confirmation"

    if level in (AutonomyLevel.SUPERVISED, AutonomyLevel.AUTONOMOUS):
        return True, f"L{level.value}: action allowed"

    return False, "unknown level"


# ---------------------------------------------------------------------------
# Auto-downgrade triggers
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DowngradeTrigger:
    condition: str
    from_level: AutonomyLevel
    to_level: AutonomyLevel
    reason: str


_DOWNGRADE_TRIGGERS: list[DowngradeTrigger] = [
    DowngradeTrigger("perception_confidence_low", AutonomyLevel.SUPERVISED, AutonomyLevel.ASSISTED,
                     "perception confidence < 0.5"),
    DowngradeTrigger("perception_confidence_low", AutonomyLevel.AUTONOMOUS, AutonomyLevel.ASSISTED,
                     "perception confidence < 0.5"),
    DowngradeTrigger("consecutive_failures", AutonomyLevel.SUPERVISED, AutonomyLevel.ASSISTED,
                     "same action failed 3 times consecutively"),
    DowngradeTrigger("consecutive_failures", AutonomyLevel.AUTONOMOUS, AutonomyLevel.ASSISTED,
                     "same action failed 3 times consecutively"),
    DowngradeTrigger("puzzle_detected", AutonomyLevel.SUPERVISED, AutonomyLevel.ASSISTED,
                     "puzzle detected, requires human guidance"),
    DowngradeTrigger("window_defocus", AutonomyLevel.AUTONOMOUS, AutonomyLevel.SUPERVISED,
                     "window focus lost and restored"),
    DowngradeTrigger("user_input", AutonomyLevel.AUTONOMOUS, AutonomyLevel.MANUAL,
                     "user input detected"),
    DowngradeTrigger("user_input", AutonomyLevel.SUPERVISED, AutonomyLevel.MANUAL,
                     "user input detected"),
    DowngradeTrigger("user_input", AutonomyLevel.ASSISTED, AutonomyLevel.MANUAL,
                     "user input detected"),
]


# ---------------------------------------------------------------------------
# Control handover
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HandoverChecklist:
    game_focused: bool = False
    game_operable: bool = False
    perception_healthy: bool = False
    scene_recognized: bool = False
    task_defined: bool = False
    resource_budget_set: bool = False
    backend_ready: bool = False

    @property
    def is_ready(self) -> bool:
        return all([
            self.game_focused, self.game_operable, self.perception_healthy,
            self.scene_recognized, self.task_defined, self.resource_budget_set,
            self.backend_ready,
        ])

    @property
    def failed_items(self) -> list[str]:
        items = []
        if not self.game_focused:
            items.append("game_focused")
        if not self.game_operable:
            items.append("game_operable")
        if not self.perception_healthy:
            items.append("perception_healthy")
        if not self.scene_recognized:
            items.append("scene_recognized")
        if not self.task_defined:
            items.append("task_defined")
        if not self.resource_budget_set:
            items.append("resource_budget_set")
        if not self.backend_ready:
            items.append("backend_ready")
        return items


@dataclass(frozen=True, slots=True)
class HandoverResult:
    status: HandoverStatus
    from_level: AutonomyLevel
    to_level: AutonomyLevel
    reason: str = ""
    checklist: HandoverChecklist | None = None
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.perf_counter())


# ---------------------------------------------------------------------------
# Collaboration controller
# ---------------------------------------------------------------------------

ConfirmationCallback = Callable[[str, dict[str, Any]], bool]


@dataclass(slots=True)
class CollaborationController:
    """Manage autonomy level transitions, permission checks, and control handover.

    Usage::

        ctrl = CollaborationController()
        ctrl.set_level(AutonomyLevel.ASSISTED)
        allowed, reason = ctrl.check_permission("teleport")
        if not allowed:
            # Request confirmation for high-risk
            ...
    """

    level: AutonomyLevel = AutonomyLevel.MANUAL
    confirmation_callback: ConfirmationCallback | None = None
    consecutive_failures: dict[str, int] = field(default_factory=dict)
    max_consecutive_failures: int = 3
    perception_confidence: float = 1.0
    session_start_time: float = 0.0
    session_budget_min: float = 60.0
    primogem_budget: int = 0
    primogem_spent: int = 0
    _handover_log: list[HandoverResult] = field(default_factory=list)
    _last_rest_time: float = 0.0
    rest_interval_sec: float = 3600.0  # 60 min
    rest_duration_sec: float = 300.0   # 5 min

    def __post_init__(self) -> None:
        if self.session_start_time == 0.0:
            self.session_start_time = time.perf_counter()
        self._last_rest_time = self.session_start_time

    # ------------------------------------------------------------------
    # Autonomy level management
    # ------------------------------------------------------------------

    def set_level(self, target: AutonomyLevel, user_confirmed: bool = False) -> HandoverResult:
        """Attempt to change autonomy level. Returns handover result."""
        current = self.level

        # Downgrade: always allowed
        if target.value < current.value:
            return self._execute_downgrade(current, target, "user or auto downgrade")

        # Upgrade: requires user confirmation
        if target.value > current.value and not user_confirmed:
            result = HandoverResult(
                status=HandoverStatus.REJECTED,
                from_level=current, to_level=target,
                reason="upgrade requires user confirmation",
            )
            self._handover_log.append(result)
            return result

        # Same level: no-op
        if target == current:
            return HandoverResult(
                status=HandoverStatus.ACCEPTED,
                from_level=current, to_level=target,
                reason="already at target level",
            )

        # Upgrade with confirmation
        checklist = self._build_checklist()
        if not checklist.is_ready and target.value >= AutonomyLevel.AUTONOMOUS.value:
            result = HandoverResult(
                status=HandoverStatus.REJECTED,
                from_level=current, to_level=target,
                reason=f"checklist not ready: {checklist.failed_items}",
                checklist=checklist,
            )
            self._handover_log.append(result)
            return result

        self.level = target
        result = HandoverResult(
            status=HandoverStatus.ACCEPTED,
            from_level=current, to_level=target,
            reason="user confirmed upgrade",
            checklist=checklist,
        )
        self._handover_log.append(result)
        log.info("[Collaboration] autonomy %s → %s", current.value, target.value)
        return result

    def _execute_downgrade(self, current: AutonomyLevel, target: AutonomyLevel,
                           reason: str) -> HandoverResult:
        self.level = target
        result = HandoverResult(
            status=HandoverStatus.ACCEPTED,
            from_level=current, to_level=target,
            reason=reason,
        )
        self._handover_log.append(result)
        log.info("[Collaboration] downgrade %s → %s (%s)", current.value, target.value, reason)
        return result

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    def check_permission(self, action: str) -> tuple[bool, str]:
        """Check if action is allowed at current level."""
        allowed, reason = is_action_allowed(self.level, action)
        if not allowed and self.level == AutonomyLevel.ASSISTED:
            # In assisted mode, high-risk actions can proceed with confirmation
            risk = classify_action_risk(action)
            if risk == ActionRisk.HIGH and self.confirmation_callback is not None:
                confirmed = self.confirmation_callback(action, {})
                if confirmed:
                    return True, "user confirmed high-risk action"
        return allowed, reason

    def check_safety_limit(self) -> tuple[bool, str]:
        """Check safety limits that apply even at L3."""
        # Primogem budget
        if self.primogem_budget > 0 and self.primogem_spent >= self.primogem_budget:
            return False, f"primogem budget exhausted ({self.primogem_spent}/{self.primogem_budget})"

        # Mandatory rest interval
        elapsed = time.perf_counter() - self._last_rest_time
        if elapsed > self.rest_interval_sec:
            return False, "mandatory rest interval reached"

        return True, "within safety limits"

    # ------------------------------------------------------------------
    # Auto-downgrade triggers
    # ------------------------------------------------------------------

    def report_failure(self, action: str) -> None:
        """Report an action failure. May trigger auto-downgrade."""
        self.consecutive_failures[action] = self.consecutive_failures.get(action, 0) + 1
        if self.consecutive_failures[action] >= self.max_consecutive_failures:
            self._auto_downgrade("consecutive_failures")

    def report_success(self, action: str) -> None:
        self.consecutive_failures.pop(action, None)

    def update_perception_confidence(self, confidence: float) -> None:
        self.perception_confidence = confidence
        if confidence < 0.5 and self.level.value >= AutonomyLevel.SUPERVISED.value:
            self._auto_downgrade("perception_confidence_low")

    def report_user_input(self) -> None:
        """User input detected — immediate downgrade to MANUAL."""
        if self.level != AutonomyLevel.MANUAL:
            self._auto_downgrade("user_input")

    def report_puzzle_detected(self) -> None:
        if self.level == AutonomyLevel.SUPERVISED:
            self._auto_downgrade("puzzle_detected")

    def report_window_defocus_restored(self) -> None:
        if self.level == AutonomyLevel.AUTONOMOUS:
            self._auto_downgrade("window_defocus")

    def _auto_downgrade(self, condition: str) -> None:
        for trigger in _DOWNGRADE_TRIGGERS:
            if trigger.condition == condition and trigger.from_level == self.level:
                self._execute_downgrade(self.level, trigger.to_level, trigger.reason)
                return

    # ------------------------------------------------------------------
    # Handover checklist
    # ------------------------------------------------------------------

    def _build_checklist(self) -> HandoverChecklist:
        return HandoverChecklist(
            game_focused=True,
            game_operable=True,
            perception_healthy=self.perception_confidence >= 0.7,
            scene_recognized=self.perception_confidence >= 0.7,
            task_defined=True,
            resource_budget_set=True,
            backend_ready=True,
        )

    def attempt_handover(self, target: AutonomyLevel, checklist: HandoverChecklist) -> HandoverResult:
        """Attempt handover with explicit checklist validation."""
        if not checklist.is_ready:
            result = HandoverResult(
                status=HandoverStatus.REJECTED,
                from_level=self.level, to_level=target,
                reason=f"checklist failed: {checklist.failed_items}",
                checklist=checklist,
            )
            self._handover_log.append(result)
            return result
        return self.set_level(target, user_confirmed=True)

    @property
    def handover_history(self) -> list[HandoverResult]:
        return list(self._handover_log)

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def status_summary(self) -> dict[str, Any]:
        return {
            "level": self.level.name,
            "level_value": self.level.value,
            "perception_confidence": self.perception_confidence,
            "consecutive_failures": dict(self.consecutive_failures),
            "primogem_budget": self.primogem_budget,
            "primogem_spent": self.primogem_spent,
            "session_duration_sec": time.perf_counter() - self.session_start_time,
        }
