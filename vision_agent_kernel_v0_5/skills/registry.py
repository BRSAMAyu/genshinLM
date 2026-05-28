"""Skill OS Registry — thread-safe skill lookup and indexing.

Supports lookup by:
- skill_id (exact match)
- screen_state (applicability matching)
- capability (produced claim types)
- tier (promotion level filtering)
"""
from __future__ import annotations

import threading
from typing import Sequence

from skills.promotion import tier_index
from skills.schema import PromotionTier, SkillDef


class SkillRegistry:
    """Thread-safe registry for SkillDef objects."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDef] = {}
        self._lock = threading.Lock()

    def register(self, skill: SkillDef) -> None:
        with self._lock:
            self._skills[skill.skill_id] = skill

    def unregister(self, skill_id: str) -> None:
        with self._lock:
            self._skills.pop(skill_id, None)

    def get(self, skill_id: str) -> SkillDef | None:
        with self._lock:
            return self._skills.get(skill_id)

    def all_skills(self) -> list[SkillDef]:
        with self._lock:
            return list(self._skills.values())

    def find_by_screen_state(self, screen_state: str) -> list[SkillDef]:
        """Find skills applicable to a given screen state."""
        with self._lock:
            return [
                s for s in self._skills.values()
                if not s.applicability.screen_states
                or screen_state in s.applicability.screen_states
            ]

    def find_by_capability(self, claim_type: str) -> list[SkillDef]:
        """Find skills that produce a given claim type."""
        with self._lock:
            return [
                s for s in self._skills.values()
                if any(c.claim_type == claim_type for c in s.produced_claims)
            ]

    def find_by_tier(self, min_tier: PromotionTier) -> list[SkillDef]:
        """Find skills at or above a promotion tier."""
        min_idx = tier_index(min_tier)
        with self._lock:
            return [
                s for s in self._skills.values()
                if tier_index(s.tier) >= min_idx
            ]

    def find_applicable(
        self,
        screen_state: str,
        available_claims: set[str] | None = None,
        min_tier: PromotionTier = "candidate",
    ) -> list[SkillDef]:
        """Find skills applicable to current context.

        Filters by screen state, required claims satisfaction, and minimum tier.
        """
        available = available_claims or set()
        min_idx = tier_index(min_tier)

        with self._lock:
            results: list[SkillDef] = []
            for s in self._skills.values():
                if tier_index(s.tier) < min_idx:
                    continue
                if s.applicability.screen_states and screen_state not in s.applicability.screen_states:
                    continue
                if s.applicability.required_claims:
                    required = set(s.applicability.required_claims)
                    if not required.issubset(available):
                        continue
                results.append(s)
            return results

    def clear(self) -> None:
        with self._lock:
            self._skills.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._skills)
