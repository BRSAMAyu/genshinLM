"""Cooperative commission system: automated co-op commission completion.

Covers S-33: Automatically complete multiplayer commission quests.
Manages co-op matching, commission selection, and completion tracking
for co-op-only daily commissions.

Integrates with:
- perception/coop_mode_detector.py for co-op state detection
- planning/quest_tracker.py for quest tracking
- execution/crash_recovery.py for recovery during co-op
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Co-op commission types
# ---------------------------------------------------------------------------

class CoOpCommissionType(str, Enum):
    DELIVERY = "delivery"          # Deliver items to co-op partner
    COMBAT = "combat"              # Defeat enemies together
    PUZZLE = "puzzle"              # Solve puzzles together
    COLLECTION = "collection"       # Collect items together
    CUSTOM = "custom"               # Various commission types


# ---------------------------------------------------------------------------
# Co-op state tracking
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CoOpSession:
    """Active co-op session."""
    session_id: str
    commission_type: CoOpCommissionType
    is_host: bool = True
    partner_count: int = 0
    started_at: float = 0.0
    expected_duration_min: float = 5.0
    is_complete: bool = False
    rewards_claimed: bool = False


@dataclass(slots=True)
class CoOpCommission:
    """A co-op daily commission."""
    commission_id: str
    name: str
    commission_type: CoOpCommissionType
    description: str
    requirements: list[str] = field(default_factory=list)
    is_coop_only: bool = False
    estimated_time_min: float = 5.0


# ---------------------------------------------------------------------------
# Co-op commission database
# ---------------------------------------------------------------------------

# Known co-op-only commissions (require multiplayer)
COOP_ONLY_COMMISSIONS: dict[str, CoOpCommission] = {
    "a_crash_course": CoOpCommission(
        commission_id="a_crash_course",
        name="A Crash Course",
        commission_type=CoOpCommissionType.DELIVERY,
        description="Deliver materials to co-op partner",
        requirements=["Find partner in co-op", "Visit delivery point"],
        is_coop_only=True,
    ),
    "combat_company": CoOpCommission(
        commission_id="combat_company",
        name="Combat Company",
        commission_type=CoOpCommissionType.COMBAT,
        description="Defeat enemies with co-op partner",
        requirements=["Match with partner", "Clear enemy waves"],
        is_coop_only=True,
    ),
    "teatime_guerilla": CoOpCommission(
        commission_id="teatime_guerilla",
        name="Teatime Guerilla",
        commission_type=CoOpCommissionType.PUZZLE,
        description="Solve puzzles together",
        requirements=["Coordinate with partner", "Complete puzzle"],
        is_coop_only=False,  # Can be done solo but easier in co-op
    ),
}


# ---------------------------------------------------------------------------
# Co-op commission manager
# ---------------------------------------------------------------------------

class CoOpCommissionManager:
    """Manages co-op commission completion.

    Handles:
    1. Identifying co-op-only commissions
    2. Initiating co-op matching
    3. Coordinating commission completion
    4. Tracking co-op session state
    """

    # Co-op matching parameters
    MATCH_TIMEOUT_SEC = 60.0
    SESSION_TIMEOUT_SEC = 600.0  # 10 minutes max

    def __init__(self) -> None:
        self._active_session: CoOpSession | None = None
        self._completed_commissions: set[str] = set()
        self._match_start_time: float = 0.0

    def is_coop_commission(self, commission_id: str) -> bool:
        """Check if a commission requires co-op."""
        commission = COOP_ONLY_COMMISSIONS.get(commission_id)
        if commission:
            return commission.is_coop_only
        return False

    def needs_coop_matching(self, commission_id: str) -> bool:
        """Check if we need to match for this commission."""
        if self._active_session is not None:
            return False  # Already in session
        return self.is_coop_commission(commission_id)

    def start_matching(self, commission_id: str) -> dict[str, Any]:
        """Start co-op matching for a commission."""
        self._match_start_time = 0.0  # Would use time.perf_counter()
        log.info("[CoOpMgr] starting match for commission %s", commission_id)
        return {
            "status": "matching",
            "commission_id": commission_id,
            "estimated_wait_sec": self.MATCH_TIMEOUT_SEC,
        }

    def check_matching_result(self) -> dict[str, Any]:
        """Check result of co-op matching.

        In production, this would check actual match status.
        """
        # Mock: assume matching succeeds after some time
        return {
            "matched": True,
            "partner_count": 1,
            "is_host": True,
        }

    def start_session(
        self,
        commission_id: str,
        commission_type: CoOpCommissionType,
        is_host: bool = True,
    ) -> CoOpSession:
        """Start a co-op session for a commission."""
        session = CoOpSession(
            session_id=f"coop_{commission_id}_{self._get_timestamp()}",
            commission_type=commission_type,
            is_host=is_host,
            started_at=0.0,  # Would use time.perf_counter()
        )
        self._active_session = session
        log.info("[CoOpMgr] started session %s for %s (host=%s)",
                 session.session_id, commission_id, is_host)
        return session

    def complete_commission(
        self,
        commission_id: str,
        rewards_claimed: bool = False,
    ) -> dict[str, Any]:
        """Mark a co-op commission as complete."""
        if self._active_session:
            self._active_session.is_complete = True
            self._active_session.rewards_claimed = rewards_claimed

        self._completed_commissions.add(commission_id)
        log.info("[CoOpMgr] completed commission %s", commission_id)

        result = {
            "commission_id": commission_id,
            "completed": True,
            "rewards_claimed": rewards_claimed,
            "session_id": self._active_session.session_id if self._active_session else "",
        }

        # Clear session
        self._active_session = None
        return result

    def cancel_session(self) -> dict[str, Any]:
        """Cancel current co-op session."""
        if self._active_session:
            session_id = self._active_session.session_id
            self._active_session = None
            log.info("[CoOpMgr] cancelled session %s", session_id)
            return {"status": "cancelled", "session_id": session_id}
        return {"status": "no_active_session"}

    def get_pending_coop_commissions(
        self,
        all_commissions: list[str],
    ) -> list[CoOpCommission]:
        """Get list of co-op commissions from all daily commissions.

        Args:
            all_commissions: List of commission IDs from daily rotation

        Returns:
            List of CoOpCommission objects for commissions needing co-op
        """
        pending = []
        for comm_id in all_commissions:
            if comm_id in COOP_ONLY_COMMISSIONS:
                commission = COOP_ONLY_COMMISSIONS[comm_id]
                if comm_id not in self._completed_commissions:
                    pending.append(commission)
        return pending

    def get_session_status(self) -> dict[str, Any]:
        """Get current co-op session status."""
        if self._active_session is None:
            return {"status": "no_session"}
        return {
            "status": "active",
            "session_id": self._active_session.session_id,
            "commission_type": self._active_session.commission_type.value,
            "is_host": self._active_session.is_host,
            "is_complete": self._active_session.is_complete,
            "rewards_claimed": self._active_session.rewards_claimed,
        }

    def _get_timestamp(self) -> str:
        """Generate timestamp string for session ID."""
        import time
        return str(int(time.perf_counter() * 1000))


# ---------------------------------------------------------------------------
# Co-op commission flow
# ---------------------------------------------------------------------------

class CoOpCommissionFlow:
    """Predefined flow for completing co-op commissions."""

    COOP_ENTRY_FLOW = (
        # Press co-op button in quest menu
        "press_f",
        # Wait for co-op menu
        "wait_state:co-op_menu",
        # Click "Find Partners"
        "click:0.50,0.50",
        # Wait for matching
        "wait:30000",
        # Accept match
        "click:0.65,0.85",
    )

    COOP_COMPLETION_FLOW = (
        # Complete the commission objective
        "complete_objective",
        # Wait for completion notification
        "wait_state:commission_complete",
        # Claim rewards
        "click:0.50,0.50",
        # Confirm
        "click:0.65,0.85",
    )

    def get_flow(self, flow_type: str) -> tuple[str, ...]:
        """Get predefined co-op flow."""
        if flow_type == "entry":
            return self.COOP_ENTRY_FLOW
        if flow_type == "completion":
            return self.COOP_COMPLETION_FLOW
        return ()


# ---------------------------------------------------------------------------
# Co-op state detector integration
# ---------------------------------------------------------------------------

class CoOpStateDetector:
    """Detects co-op state transitions.

    Uses screen classifier to detect co-op mode states.
    """

    def detect_coop_state(self, screen_state: str) -> str:
        """Detect current co-op state from screen classification."""
        if screen_state == "co-op_menu":
            return "menu"
        if screen_state == "co-op_loading":
            return "connecting"
        if screen_state == "co-op_world":
            return "in_coop"
        return "unknown"

    def is_in_coop_mode(self, screen_state: str) -> bool:
        """Check if currently in co-op mode."""
        return "co-op" in screen_state or screen_state == "multiplayer"

    def needs_partner_confirm(self, screen_state: str) -> bool:
        """Check if waiting for partner confirmation."""
        return screen_state in ("co-op_invite_pending", "co-op_waiting_for_partner")