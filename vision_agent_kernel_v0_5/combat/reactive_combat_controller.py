"""Game-agnostic reactive combat controller (ROADMAP Phase 2).

A reference decision policy over a small typed combat view. It encodes the core
combat reasoning the north-star needs — survive first, keep the team alive, spend
bursts, drive elemental reactions, and rotate characters to keep skills flowing —
without any game-specific pixel logic. A capsule feeds a real :class:`CombatView`
from perception; the sim feeds a simulated one. The decision priority is the
testable contract.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CombatCharView:
    index: int
    name: str
    element: str
    hp_ratio: float
    energy_ratio: float
    skill_ready: bool
    burst_ready: bool
    role: str = "dps"  # dps | healer | sub


@dataclass(frozen=True, slots=True)
class CombatView:
    active_index: int
    chars: tuple[CombatCharView, ...]
    enemy_hp_ratio: float
    enemy_aura: str = ""        # element currently applied on the enemy ("" = none)
    incoming_attack: bool = False  # enemy telegraph: a hit lands next tick
    can_dodge: bool = True


@dataclass(frozen=True, slots=True)
class CombatAction:
    kind: str  # attack | skill | burst | switch | dodge | heal
    switch_to: int = -1
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ReactiveCombatConfig:
    low_hp: float = 0.4            # heal threshold (any character)
    burst_min_enemy_hp: float = 0.08  # don't waste a burst on a near-dead enemy
    prefer_reactions: bool = True  # apply off-aura elements to trigger reactions


class ReactiveCombatController:
    def __init__(self, config: ReactiveCombatConfig | None = None) -> None:
        self._cfg = config or ReactiveCombatConfig()

    def decide(self, view: CombatView) -> CombatAction:
        cfg = self._cfg
        chars = view.chars
        active = chars[view.active_index]

        # 1. Survival — dodge a telegraphed hit.
        if view.incoming_attack and view.can_dodge:
            return CombatAction("dodge", reason="incoming attack")

        # 2. Keep the team alive — route to a healer when anyone is low.
        if any(c.hp_ratio < cfg.low_hp for c in chars):
            healer = self._find(chars, role="healer", skill_ready=True)
            if healer is not None:
                if healer.index != view.active_index:
                    return CombatAction("switch", switch_to=healer.index, reason="bring in healer")
                return CombatAction("heal", reason="heal team")

        # 3. Spend a burst when it's ready and worthwhile.
        if active.burst_ready and view.enemy_hp_ratio > cfg.burst_min_enemy_hp:
            return CombatAction("burst", reason="burst window")

        # 4. Use the elemental skill — damage + applies element for reactions.
        if active.skill_ready:
            return CombatAction("skill", reason="skill / apply element")

        # 5. Rotation — if a sub/dps off-field has its skill up, switch to keep
        #    skills flowing (and set up reactions) rather than dry auto-attacking.
        if cfg.prefer_reactions:
            other = self._best_skill_ready_other(chars, view.active_index)
            if other is not None:
                return CombatAction("switch", switch_to=other.index, reason="rotate to ready skill")

        # 6. Default — normal attack.
        return CombatAction("attack", reason="normal attack")

    @staticmethod
    def _find(
        chars: tuple[CombatCharView, ...], *, role: str, skill_ready: bool,
    ) -> CombatCharView | None:
        for c in chars:
            if c.role == role and (c.skill_ready or not skill_ready):
                return c
        return None

    @staticmethod
    def _best_skill_ready_other(
        chars: tuple[CombatCharView, ...], active_index: int,
    ) -> CombatCharView | None:
        # Prefer a non-active damage character whose skill is ready.
        candidates = [
            c for c in chars
            if c.index != active_index and c.skill_ready and c.role in ("dps", "sub")
        ]
        return candidates[0] if candidates else None
