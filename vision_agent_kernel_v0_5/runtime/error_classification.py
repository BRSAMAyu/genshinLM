"""Unified error classification and severity system.

Implements the 7-category × 4-severity error taxonomy from
GENSHIN_ERROR_RECOVERY_ARCHITECTURE.md, providing:
- ErrorCategory enum (7 categories)
- ErrorSeverity enum (P0-P3)
- ErrorEvent dataclass for classified error instances
- classify_error() heuristic function
- RecoveryStateMachine for NORMAL→ANOMALY→DIAGNOSE→PLAN→RECOVER flow
"""
from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


class ErrorCategory(enum.Enum):
    PERCEPTION = "perception"
    NAVIGATION = "navigation"
    COMBAT = "combat"
    UI = "ui"
    INPUT = "input"
    SYSTEM = "system"
    ENVIRONMENT = "environment"


class ErrorSeverity(enum.Enum):
    P0_CRITICAL = 0
    P1_SEVERE = 10
    P2_MODERATE = 20
    P3_MINOR = 40


class RecoveryPhase(enum.Enum):
    NORMAL = "normal"
    ANOMALY = "anomaly"
    DIAGNOSE = "diagnose"
    PLAN = "plan"
    RECOVER = "recover"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    category: ErrorCategory
    severity: ErrorSeverity
    code: str
    source: str
    message: str = ""
    confidence: float = 0.5
    recoverable: bool = True
    requires_input_release: bool = False
    context: dict[str, float | str | bool] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.perf_counter())

    @property
    def priority(self) -> int:
        return self.severity.value


# ---------------------------------------------------------------------------
# Error classification heuristics
# ---------------------------------------------------------------------------

_CODE_CATEGORY_MAP: dict[str, ErrorCategory] = {
    # Perception
    "LOW_CONFIDENCE": ErrorCategory.PERCEPTION,
    "TRACKER_DIVERGED": ErrorCategory.PERCEPTION,
    "OCR_MISREAD": ErrorCategory.PERCEPTION,
    "VLM_TIMEOUT": ErrorCategory.PERCEPTION,
    "SCREEN_CLASSIFY_LOW": ErrorCategory.PERCEPTION,
    # Navigation
    "STUCK": ErrorCategory.NAVIGATION,
    "TARGET_LOST": ErrorCategory.NAVIGATION,
    "PATH_FAILED": ErrorCategory.NAVIGATION,
    "TELEPORT_FAILED": ErrorCategory.NAVIGATION,
    "WAYPOINT_NOT_FOUND": ErrorCategory.NAVIGATION,
    # Combat
    "CHARACTER_DIED": ErrorCategory.COMBAT,
    "TEAM_WIPE": ErrorCategory.COMBAT,
    "COMBO_INTERRUPTED": ErrorCategory.COMBAT,
    "REACTION_ERROR": ErrorCategory.COMBAT,
    "BOSS_MECHANIC_FAILED": ErrorCategory.COMBAT,
    "RESIN_EMPTY": ErrorCategory.COMBAT,
    # UI
    "BUTTON_NOT_FOUND": ErrorCategory.UI,
    "UNKNOWN_POPUP": ErrorCategory.UI,
    "UI_DEPTH_MISMATCH": ErrorCategory.UI,
    "INPUT_TIMEOUT": ErrorCategory.UI,
    "BLOCKING_NOTIFICATION": ErrorCategory.UI,
    "LOADING_STUCK": ErrorCategory.UI,
    # Input
    "FOCUS_LOST": ErrorCategory.INPUT,
    "LEASE_EXPIRED": ErrorCategory.INPUT,
    "DEADLOCK": ErrorCategory.INPUT,
    "INPUT_QUEUE_FULL": ErrorCategory.INPUT,
    # System
    "GAME_CRASHED": ErrorCategory.SYSTEM,
    "GPU_FAILURE": ErrorCategory.SYSTEM,
    "NETWORK_DISCONNECT": ErrorCategory.SYSTEM,
    "OOM": ErrorCategory.SYSTEM,
    "VERSION_UPDATE": ErrorCategory.SYSTEM,
    # Environment
    "STAMINA_DEPLETED": ErrorCategory.ENVIRONMENT,
    "HAZARD_DANGER": ErrorCategory.ENVIRONMENT,
    "DROWNING": ErrorCategory.ENVIRONMENT,
    "TERRAIN_SHIFT": ErrorCategory.ENVIRONMENT,
    "WEATHER_LOW_VIS": ErrorCategory.ENVIRONMENT,
}

_CRITICAL_CODES = frozenset({
    "FOCUS_LOST", "GAME_CRASHED", "GPU_FAILURE", "DEADLOCK",
})
_SEVERE_CODES = frozenset({
    "TEAM_WIPE", "LOADING_STUCK", "NETWORK_DISCONNECT", "OOM",
    "DROWNING", "LEASE_EXPIRED",
})


def classify_error(code: str, source: str = "", **ctx: float | str | bool) -> ErrorEvent:
    """Classify an error code into category + severity."""
    category = _CODE_CATEGORY_MAP.get(code, ErrorCategory.SYSTEM)

    if code in _CRITICAL_CODES:
        severity = ErrorSeverity.P0_CRITICAL
        recoverable = False
        requires_release = True
    elif code in _SEVERE_CODES:
        severity = ErrorSeverity.P1_SEVERE
        recoverable = True
        requires_release = code == "TEAM_WIPE"
    elif category in (ErrorCategory.PERCEPTION, ErrorCategory.NAVIGATION):
        severity = ErrorSeverity.P2_MODERATE
        recoverable = True
        requires_release = False
    else:
        severity = ErrorSeverity.P3_MINOR
        recoverable = True
        requires_release = False

    return ErrorEvent(
        category=category,
        severity=severity,
        code=code,
        source=source,
        recoverable=recoverable,
        requires_input_release=requires_release,
        context=dict(ctx),
    )


# ---------------------------------------------------------------------------
# Recovery state machine
# ---------------------------------------------------------------------------

_TRANSITIONS: dict[tuple[RecoveryPhase, str], RecoveryPhase] = {
    (RecoveryPhase.NORMAL, "anomaly_detected"): RecoveryPhase.ANOMALY,
    (RecoveryPhase.NORMAL, "interrupt_received"): RecoveryPhase.ANOMALY,
    (RecoveryPhase.ANOMALY, "diagnosis_complete"): RecoveryPhase.DIAGNOSE,
    (RecoveryPhase.DIAGNOSE, "strategy_selected"): RecoveryPhase.PLAN,
    (RecoveryPhase.PLAN, "recovery_executed"): RecoveryPhase.RECOVER,
    (RecoveryPhase.RECOVER, "verification_success"): RecoveryPhase.NORMAL,
    (RecoveryPhase.RECOVER, "verification_failed"): RecoveryPhase.ESCALATE,
    (RecoveryPhase.RECOVER, "budget_exhausted"): RecoveryPhase.ESCALATE,
    (RecoveryPhase.ESCALATE, "manual_intervention"): RecoveryPhase.NORMAL,
}

# Transitions that reset the escalation counter (successful recovery only)
_RESET_ESCALATION_TRANSITIONS: frozenset[str] = frozenset({"verification_success"})


@dataclass(slots=True)
class RecoveryStateMachine:
    """Enforce the 6-state recovery flow: NORMAL→ANOMALY→DIAGNOSE→PLAN→RECOVER→(NORMAL|ESCALATE)."""
    phase: RecoveryPhase = RecoveryPhase.NORMAL
    error_history: list[ErrorEvent] = field(default_factory=list)
    escalation_count: int = 0
    max_escalations: int = 3
    last_transition_at: float = 0.0

    def __post_init__(self) -> None:
        if self.last_transition_at == 0.0:
            self.last_transition_at = time.perf_counter()

    def transition(self, event: str) -> RecoveryPhase:
        key = (self.phase, event)
        next_phase = _TRANSITIONS.get(key)
        if next_phase is None:
            log.warning("[RecoverySM] invalid transition %s in phase %s", event, self.phase.value)
            return self.phase
        log.info("[RecoverySM] %s → %s (event: %s)", self.phase.value, next_phase.value, event)
        self.phase = next_phase
        self.last_transition_at = time.perf_counter()
        if next_phase == RecoveryPhase.ESCALATE:
            self.escalation_count += 1
        if next_phase == RecoveryPhase.NORMAL and event in _RESET_ESCALATION_TRANSITIONS:
            self.escalation_count = 0
        return next_phase

    def accept_error(self, error: ErrorEvent) -> RecoveryPhase:
        """Accept an error and drive the state machine."""
        self.error_history.append(error)
        if len(self.error_history) > 100:
            self.error_history = self.error_history[-50:]

        if self.phase == RecoveryPhase.NORMAL:
            if error.severity in (ErrorSeverity.P0_CRITICAL, ErrorSeverity.P1_SEVERE):
                return self.transition("interrupt_received")
            return self.transition("anomaly_detected")

        return self.phase

    @property
    def is_recovering(self) -> bool:
        return self.phase not in (RecoveryPhase.NORMAL, RecoveryPhase.ESCALATE)

    @property
    def should_abort(self) -> bool:
        return self.escalation_count >= self.max_escalations

    @property
    def duration_in_phase_sec(self) -> float:
        return time.perf_counter() - self.last_transition_at
