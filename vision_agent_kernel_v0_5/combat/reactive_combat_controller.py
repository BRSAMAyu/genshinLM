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
    # Curated knowledge: the elements this enemy is weak to (from the monster DB).
    # Drives reaction-targeted rotation when present.
    enemy_weaknesses: tuple[str, ...] = ()


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
    # Score weights for weakness-aware rotation target selection.
    reaction_weight: float = 2.0   # element triggers a reaction with current aura
    weakness_weight: float = 1.5   # element is in the enemy's known weaknesses


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

        # 5. Rotation — if an off-field damage character has its skill up, switch.
        #    Target selection is weakness/reaction-aware: prefer the character
        #    whose element triggers a reaction with the current aura and/or hits a
        #    known weakness (curated monster DB), keeping skills flowing meaningfully.
        if cfg.prefer_reactions:
            other = self._best_rotation_target(chars, view)
            if other is not None:
                reason = self._rotation_reason(other, view)
                return CombatAction("switch", switch_to=other.index, reason=reason)

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

    def _best_rotation_target(
        self, chars: tuple[CombatCharView, ...], view: CombatView,
    ) -> CombatCharView | None:
        """Pick the off-field skill-ready damage char with the best element score.

        Score = reaction_weight (element != current aura, aura present) +
        weakness_weight (element in enemy weaknesses). Ties keep field order, so
        with no aura and no weakness data this degrades to "first ready other"
        (the original behaviour) — strictly a refinement, never worse.
        """
        cfg = self._cfg
        candidates = [
            c for c in chars
            if c.index != view.active_index and c.skill_ready and c.role in ("dps", "sub")
        ]
        if not candidates:
            return None
        weaknesses = {w.lower() for w in view.enemy_weaknesses}
        aura = view.enemy_aura.lower()

        def score(c: CombatCharView) -> float:
            el = c.element.lower()
            s = 0.0
            if aura and el != aura and el != "none":
                s += cfg.reaction_weight       # off-aura element -> reaction
            if el in weaknesses:
                s += cfg.weakness_weight       # hits a curated weakness
            return s

        # max by score, stable on field order (first ready other on a tie of 0).
        best = max(candidates, key=lambda c: (score(c), -c.index))
        return best

    def _rotation_reason(self, target: CombatCharView, view: CombatView) -> str:
        el = target.element.lower()
        hits_weak = el in {w.lower() for w in view.enemy_weaknesses}
        aura = view.enemy_aura.lower()
        triggers = bool(aura and el != aura and el != "none")
        if triggers and hits_weak:
            return f"rotate to {target.name}: reaction + weakness ({el})"
        if triggers:
            return f"rotate to {target.name}: trigger reaction ({el} vs {aura})"
        if hits_weak:
            return f"rotate to {target.name}: hit weakness ({el})"
        return "rotate to ready skill"
