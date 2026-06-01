"""R-37: Alternative weapon recommender — F2P weapon fallback selection.

When the optimal F2P weapon is unavailable, recommends the next best
alternative from F2P_BUILDS alt_weapons list. Supports partial name
matching for inventory-based lookups.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from knowledge.genshin_f2p_builds import F2P_BUILDS

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WeaponRecommendation:
    character_id: str
    best_weapon: str
    available_alternatives: tuple[str, ...]
    selected: str
    rank: int  # 0=best, 1=first alt, etc.
    reason: str


class WeaponRecommender:
    """Recommend weapons based on F2P builds with fallback alternatives."""

    def recommend(
        self,
        character_id: str,
        owned_weapons: list[str] | tuple[str, ...] | None = None,
    ) -> WeaponRecommendation:
        """Get weapon recommendation for a character.

        Args:
            character_id: Character identifier (e.g., "xiangling").
            owned_weapons: List of weapon names the player owns.
                          If None, returns the best F2P weapon.

        Returns:
            WeaponRecommendation with selected weapon and alternatives.
        """
        cid = character_id.lower().strip()
        build = F2P_BUILDS.get(cid)

        if build is None:
            return WeaponRecommendation(
                character_id=character_id,
                best_weapon="unknown",
                available_alternatives=(),
                selected="unknown",
                rank=0,
                reason=f"No build data for {character_id}",
            )

        best = build.best_weapon_f2p
        alts = build.alt_weapons

        if owned_weapons is None:
            return WeaponRecommendation(
                character_id=character_id,
                best_weapon=best,
                available_alternatives=alts,
                selected=best,
                rank=0,
                reason="Best F2P weapon",
            )

        # Normalize owned weapons for matching
        owned_norm = [w.lower().strip() for w in owned_weapons]

        # Try best weapon first
        if self._weapon_available(best, owned_norm):
            return WeaponRecommendation(
                character_id=character_id,
                best_weapon=best,
                available_alternatives=alts,
                selected=best,
                rank=0,
                reason="Best F2P weapon available",
            )

        # Try alternatives in order
        for i, alt in enumerate(alts):
            if self._weapon_available(alt, owned_norm):
                return WeaponRecommendation(
                    character_id=character_id,
                    best_weapon=best,
                    available_alternatives=alts,
                    selected=alt,
                    rank=i + 1,
                    reason=f"Alternative #{i + 1} — best weapon not available",
                )

        # Nothing available — recommend best as target
        return WeaponRecommendation(
            character_id=character_id,
            best_weapon=best,
            available_alternatives=alts,
            selected=best,
            rank=0,
            reason="No recommended weapons owned — craft or obtain the best option",
        )

    def recommend_team(
        self,
        character_ids: list[str],
        owned_weapons: list[str] | tuple[str, ...] | None = None,
    ) -> list[WeaponRecommendation]:
        """Get weapon recommendations for an entire team."""
        return [self.recommend(cid, owned_weapons) for cid in character_ids]

    @staticmethod
    def _weapon_available(weapon_name: str, owned_norm: list[str]) -> bool:
        """Check if a weapon is in the owned list (fuzzy match)."""
        target = weapon_name.lower().strip()
        for owned in owned_norm:
            if target == owned or target in owned or owned in target:
                return True
        return False
