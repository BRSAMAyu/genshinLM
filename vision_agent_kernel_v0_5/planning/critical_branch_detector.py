"""Q-34: Critical branch detector.

Detects critical decision points in quests where choosing wrong
can break quest progression or lead to bad endings.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class BranchType(str, Enum):
    DIALOG_CHOICE = "dialog_choice"      # Dialogue option selection
    TASK_SELECTION = "task_selection"    # Multiple task options
    ITEM_CHOICE = "item_choice"         # Choose item to use
    TARGET_SELECTION = "target_selection"  # Select target/entity


@dataclass(frozen=True, slots=True)
class BranchOption:
    """A single branch option."""
    option_id: str
    display_text: str
    is_safe: bool          # Known to be safe
    is_critical: bool      # Critical path option
    is_locked: bool         # Not yet available
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class CriticalBranch:
    """Detected critical branch point."""
    branch_id: str
    branch_type: BranchType
    options: list[BranchOption]
    default_option: str | None  # Recommended option ID
    is_time_limited: bool
    time_remaining: float | None
    confidence: float


@dataclass(frozen=True, slots=True)
class BranchDecision:
    """Recorded branch decision."""
    branch_id: str
    selected_option: str
    timestamp: float
    was_correct: bool | None  # None if outcome unknown


class CriticalBranchDetector:
    """Detect and handle critical quest branch points."""

    _REF_W = 1920
    _REF_H = 1080

    # Dialog choice indicator
    _DIALOG_CHOICE_LOW = np.array([0, 0, 100], dtype=np.uint8)
    _DIALOG_CHOICE_HIGH = np.array([180, 20, 255], dtype=np.uint8)

    # Critical/warning colors
    _WARNING_RED_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _WARNING_RED_HIGH = np.array([10, 255, 255], dtype=np.uint8)

    def __init__(
        self,
        on_critical_branch: Any = None,
        on_branch_decided: Any = None,
    ) -> None:
        self._on_critical_branch = on_critical_branch
        self._on_branch_decided = on_branch_decided

        # Known critical branches
        self._known_branches: dict[str, dict[str, Any]] = {}
        # Branch knowledge base
        self._branch_knowledge: dict[str, BranchDecision] = {}
        # Current active branch
        self._active_branch: CriticalBranch | None = None

    def register_branch(
        self,
        branch_id: str,
        branch_type: BranchType,
        options: list[dict[str, Any]],
        default_option: str | None = None,
        is_critical: bool = True,
    ) -> None:
        """Register a known critical branch.

        Args:
            branch_id: Unique branch identifier
            branch_type: Type of branch
            options: List of option specs
            default_option: Recommended option ID
            is_critical: Whether this branch is critical
        """
        self._known_branches[branch_id] = {
            "branch_type": branch_type,
            "options": options,
            "default_option": default_option,
            "is_critical": is_critical,
        }
        log.info("[CriticalBranch] Registered branch: %s (%s)", branch_id, branch_type.value)

    def detect_branch(self, frame: np.ndarray, frame_id: int = 0) -> CriticalBranch | None:
        """Detect if currently at a branch point.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            CriticalBranch if at branch point, None otherwise
        """
        if cv2 is None:
            return None

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check for dialog choices
        choice_mask = cv2.inRange(hsv, self._DIALOG_CHOICE_LOW, self._DIALOG_CHOICE_HIGH)
        choice_pixels = cv2.countNonZero(choice_mask)
        has_choices = choice_pixels > 2000

        # Check for warning indicators
        warning_mask = cv2.inRange(hsv, self._WARNING_RED_LOW, self._WARNING_RED_HIGH)
        warning_pixels = cv2.countNonZero(warning_mask)
        has_warning = warning_pixels > 500

        if not has_choices:
            self._active_branch = None
            return None

        # Build options from detected UI elements
        # In production, use OCR to read option text
        options = self._parse_options_from_frame(frame)

        # Determine if critical
        is_critical = has_warning or self._is_known_critical_branch(options)

        branch_type = BranchType.DIALOG_CHOICE

        # Determine default based on knowledge
        default = self._get_recommended_option(options)

        branch = CriticalBranch(
            branch_id=f"branch_{frame_id}",
            branch_type=branch_type,
            options=options,
            default_option=default,
            is_time_limited=False,
            time_remaining=None,
            confidence=0.7 if has_choices else 0.4,
        )

        self._active_branch = branch

        if is_critical and self._on_critical_branch:
            try:
                self._on_critical_branch(branch)
            except Exception as exc:
                log.warning("[CriticalBranch] Critical branch callback failed: %s", exc)

        return branch

    def _parse_options_from_frame(self, frame: np.ndarray) -> list[BranchOption]:
        """Parse branch options from frame UI."""
        # Placeholder - would use OCR to read dialog choices
        return []

    def _is_known_critical_branch(self, options: list[BranchOption]) -> bool:
        """Check if this matches a known critical branch."""
        # Check option texts against known critical options
        for opt in options:
            if opt.is_critical:
                return True
        return False

    def _get_recommended_option(self, options: list[BranchOption]) -> str | None:
        """Get recommended option based on knowledge."""
        for opt in options:
            if opt.is_safe:
                return opt.option_id
            if opt.is_critical:
                return opt.option_id
        return None

    def record_decision(
        self,
        branch_id: str,
        selected_option: str,
    ) -> None:
        """Record a branch decision.

        Args:
            branch_id: Branch that was decided
            selected_option: Selected option ID
        """
        decision = BranchDecision(
            branch_id=branch_id,
            selected_option=selected_option,
            timestamp=time.perf_counter(),
            was_correct=None,
        )

        key = f"{branch_id}:{selected_option}"
        self._branch_knowledge[key] = decision

        log.info("[CriticalBranch] Decision recorded: %s -> %s", branch_id, selected_option)

    def mark_decision_outcome(
        self,
        branch_id: str,
        selected_option: str,
        was_correct: bool,
    ) -> None:
        """Mark the outcome of a decision.

        Args:
            branch_id: Branch that was decided
            selected_option: Selected option ID
            was_correct: Whether the decision was correct
        """
        key = f"{branch_id}:{selected_option}"
        if key in self._branch_knowledge:
            decision = self._branch_knowledge[key]
            self._branch_knowledge[key] = BranchDecision(
                branch_id=decision.branch_id,
                selected_option=decision.selected_option,
                timestamp=decision.timestamp,
                was_correct=was_correct,
            )

            if self._on_branch_decided:
                try:
                    self._on_branch_decided(branch_id, selected_option, was_correct)
                except Exception as exc:
                    log.warning("[CriticalBranch] Branch decided callback failed: %s", exc)

    def get_known_safe_options(self, branch_id: str) -> list[str]:
        """Get list of known safe options for a branch."""
        safe = []
        for key, decision in self._branch_knowledge.items():
            if decision.branch_id == branch_id and decision.was_correct:
                safe.append(decision.selected_option)
        return safe

    def get_decision_guidance(self, branch: CriticalBranch) -> str | None:
        """Get guidance for making decision at branch."""
        if not branch.options:
            return None

        # Check knowledge base
        safe_options = self.get_known_safe_options(branch.branch_id)
        if safe_options:
            return f"Safe options from experience: {', '.join(safe_options)}"

        # Use default recommendation
        if branch.default_option:
            return f"Recommended: {branch.default_option}"

        return "No guidance available - choose carefully"

    def is_decision_made(self, branch: CriticalBranch) -> bool:
        """Check if decision has been made for this branch."""
        key = f"{branch.branch_id}:*"
        return any(
            d.branch_id == branch.branch_id
            for d in self._branch_knowledge.values()
        )

    def reset(self) -> None:
        """Reset handler state."""
        self._active_branch = None
        log.info("[CriticalBranchDetector] Detector reset")