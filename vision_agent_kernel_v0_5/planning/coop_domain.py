"""Cooperative domain system: automated co-op domain completion.

Covers S-34: Automatically complete multiplayer domain runs.
Manages co-op domain matching, team coordination, and reward claiming
for co-op domain challenges.

Integrates with:
- perception/coop_mode_detector.py for co-op state detection
- planning/resource_manager.py for resin tracking
- execution/crash_recovery.py for session recovery
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

class DomainType(str, Enum):
    TALENT_DOMAIN = "talent_domain"
    WEAPON_DOMAIN = "weapon_domain"
    ARTIFACT_DOMAIN = "artifact_domain"
    BOSS_DOMAIN = "boss_domain"
    LEY_LINE = "ley_line"


# ---------------------------------------------------------------------------
# Co-op domain state
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CoOpDomainSession:
    """Active co-op domain session."""
    session_id: str
    domain_name: str
    domain_type: DomainType
    is_host: bool = True
    partner_count: int = 0
    difficulty: str = "normal"
    started_at: float = 0.0
    expected_duration_min: float = 5.0
    is_complete: bool = False
    rewards_claimed: bool = False


@dataclass(slots=True)
class CoOpDomain:
    """A domain that can be completed in co-op."""
    domain_id: str
    name: str
    domain_type: DomainType
    region: str
    recommended_level: int = 0
    element_focus: tuple[str, ...] = field(default_factory=())
    coop_recommended: bool = False
    estimated_time_min: float = 3.0


# ---------------------------------------------------------------------------
# Co-op domain database
# ---------------------------------------------------------------------------

COOP_DOMAINS: dict[str, CoOpDomain] = {
    "valleyball": CoOpDomain(
        domain_id="valleyball",
        name="Valleyball",
        domain_type=DomainType.TALENT_DOMAIN,
        region="Mondstadt",
        recommended_level=30,
        element_focus=("anemo", "geo"),
        coop_recommended=True,
    ),
    "cecilia_garden": CoOpDomain(
        domain_id="cecilia_garden",
        name="Cecilia Garden",
        domain_type=DomainType.TALENT_DOMAIN,
        region="Mondstadt",
        recommended_level=30,
        element_focus=("anemo",),
        coop_recommended=False,
    ),
    "hidden_treasure": CoOpDomain(
        domain_id="hidden_treasure",
        name="Hidden Palace of Zhou Formula",
        domain_type=DomainType.WEAPON_DOMAIN,
        region="Liyue",
        recommended_level=35,
        element_focus=("geo",),
        coop_recommended=True,
    ),
    "court_of_justice": CoOpDomain(
        domain_id="court_of_justice",
        name="Court of Justice",
        domain_type=DomainType.TALENT_DOMAIN,
        region="Inazuma",
        recommended_level=55,
        element_focus=("electro",),
        coop_recommended=True,
    ),
    "tower_of_tranquility": CoOpDomain(
        domain_id="tower_of_tranquility",
        name="Tower of Abjection",
        domain_type=DomainType.BOSS_DOMAIN,
        region="Sumeru",
        recommended_level=60,
        element_focus=("dendro",),
        coop_recommended=True,
    ),
}


# ---------------------------------------------------------------------------
# Co-op domain manager
# ---------------------------------------------------------------------------

class CoOpDomainManager:
    """Manages co-op domain completion.

    Handles:
    1. Identifying domains suitable for co-op
    2. Initiating co-op matching
    3. Coordinating domain completion
    4. Tracking rewards
    """

    MATCH_TIMEOUT_SEC = 90.0
    DOMAIN_COMPLETION_TIMEOUT_SEC = 600.0

    def __init__(self) -> None:
        self._active_session: CoOpDomainSession | None = None
        self._completed_domains: set[str] = set()

    def is_coop_recommended(self, domain_id: str) -> bool:
        """Check if domain is recommended for co-op."""
        domain = COOP_DOMAINS.get(domain_id)
        return domain.coop_recommended if domain else False

    def start_coop_domain(
        self,
        domain_id: str,
        is_host: bool = True,
    ) -> CoOpDomainSession | None:
        """Start a co-op domain session.

        Returns None if domain doesn't exist or already in session.
        """
        if self._active_session is not None:
            log.warning("[CoOpDomain] already in session %s", self._active_session.session_id)
            return None

        domain = COOP_DOMAINS.get(domain_id)
        if domain is None:
            log.warning("[CoOpDomain] unknown domain %s", domain_id)
            return None

        session = CoOpDomainSession(
            session_id=f"coop_domain_{domain_id}_{self._get_timestamp()}",
            domain_name=domain.name,
            domain_type=domain.domain_type,
            is_host=is_host,
            started_at=0.0,
        )
        self._active_session = session
        log.info("[CoOpDomain] started domain session %s for %s",
                 session.session_id, domain_id)
        return session

    def complete_domain(
        self,
        rewards_claimed: bool = False,
    ) -> dict[str, Any]:
        """Mark domain as complete and claim rewards."""
        if self._active_session is None:
            return {"success": False, "error": "No active session"}

        domain_id = self._active_session.domain_name
        self._active_session.is_complete = True
        self._active_session.rewards_claimed = rewards_claimed

        self._completed_domains.add(domain_id)
        log.info("[CoOpDomain] completed domain %s", domain_id)

        result = {
            "success": True,
            "domain_name": domain_id,
            "rewards_claimed": rewards_claimed,
            "session_id": self._active_session.session_id,
        }

        # Clear session
        self._active_session = None
        return result

    def cancel_session(self) -> dict[str, Any]:
        """Cancel current co-op domain session."""
        if self._active_session:
            session_id = self._active_session.session_id
            self._active_session = None
            log.info("[CoOpDomain] cancelled session %s", session_id)
            return {"success": True, "session_id": session_id, "cancelled": True}
        return {"success": False, "error": "No active session"}

    def get_session_status(self) -> dict[str, Any]:
        """Get current domain session status."""
        if self._active_session is None:
            return {"status": "no_session"}

        session = self._active_session
        return {
            "status": "active",
            "session_id": session.session_id,
            "domain_name": session.domain_name,
            "domain_type": session.domain_type.value,
            "is_host": session.is_host,
            "is_complete": session.is_complete,
            "rewards_claimed": session.rewards_claimed,
        }

    def get_domain_recommendation(
        self,
        domain_type: DomainType,
        current_ar: int,
    ) -> list[CoOpDomain]:
        """Get recommended co-op domains for current AR."""
        recommendations = []
        for domain in COOP_DOMAINS.values():
            if domain.domain_type != domain_type:
                continue
            if domain.recommended_level <= current_ar + 10:
                recommendations.append(domain)
        return recommendations

    def _get_timestamp(self) -> str:
        """Generate timestamp string."""
        import time
        return str(int(time.perf_counter() * 1000))


# ---------------------------------------------------------------------------
# Co-op domain flow
# ---------------------------------------------------------------------------

class CoOpDomainFlow:
    """Predefined flow for co-op domain completion."""

    COOP_DOMAIN_ENTRY_FLOW = (
        "navigate_to_domain",
        "interact_domain",
        "click:0.50,0.85",  # Click "Start Challenge"
        "wait_state:coop_invite",
        "click:0.65,0.85",  # Accept co-op invite
        "wait_state:coop_loading",
        "wait_state:domain_combat",
    )

    COOP_DOMAIN_COMPLETION_FLOW = (
        "complete_domain_objective",
        "wait_state:domain_complete",
        "click:0.50,0.50",  # Claim rewards
        "click:0.65,0.85",  # Confirm
        "wait_state:world",
    )

    def get_flow(self, flow_type: str) -> tuple[str, ...]:
        """Get predefined co-op domain flow."""
        if flow_type == "entry":
            return self.COOP_DOMAIN_ENTRY_FLOW
        if flow_type == "completion":
            return self.COOP_DOMAIN_COMPLETION_FLOW
        return ()


# ---------------------------------------------------------------------------
# Co-op domain strategy
# ---------------------------------------------------------------------------

class CoOpDomainStrategy:
    """Strategy optimization for co-op domains."""

    def get_role_assignment(
        self,
        team_elements: list[str],
        partner_elements: list[str],
        domain_type: DomainType,
    ) -> dict[str, str]:
        """Assign roles for co-op domain based on elements.

        Returns dict of character -> role.
        """
        roles: dict[str, str] = {}

        # Basic role assignment based on element
        element_roles = {
            "pyro": "damage",
            "hydro": "support",
            "cryo": "freeze",
            "electro": "battery",
            "anemo": "crowd_control",
            "geo": "shield",
            "dendro": "reaction",
        }

        all_elements = team_elements + partner_elements
        for i, elem in enumerate(all_elements):
            role = element_roles.get(elem, "support")
            roles[f"char_{i}"] = role

        return roles

    def recommend_support_actions(
        self,
        domain_type: DomainType,
        is_host: bool,
    ) -> list[str]:
        """Recommend support actions during co-op domain.

        Args:
            domain_type: Type of domain being run
            is_host: Whether we are the host player

        Returns:
            List of recommended actions
        """
        actions = []

        if is_host:
            actions.extend([
                "Lead navigation to objectives",
                "Mark enemies for partner",
                "Initiate elemental reactions",
            ])
        else:
            actions.extend([
                "Follow host's lead",
                "Focus on support role",
                "Provide elemental reactions",
            ])

        if domain_type == DomainType.ARTIFACT_DOMAIN:
            actions.append("Prioritize damage for faster clear")
        elif domain_type == DomainType.TALENT_DOMAIN:
            actions.append("Balance damage and energy generation")

        return actions