from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


SurvivalDecisionKind = Literal["none", "dodge", "shield", "heal", "retreat", "food_ui", "safe_abort"]


@dataclass(frozen=True, slots=True)
class SurvivalState:
    active_hp: float
    team_hp: list[float]
    shield_active: bool = False
    shielder_available: bool = False
    healer_available: bool = False
    food_available: bool = False
    burst_iframes_available: bool = False
    stamina: float = 1.0
    recent_damage_rate: float = 0.0
    death_risk: float = 0.0
    danger_score: float = 0.0
    ui_profile_ready: bool = False


@dataclass(frozen=True, slots=True)
class SurvivalPolicy:
    soft_hp_threshold: float = 0.55
    hard_hp_threshold: float = 0.35
    emergency_threshold: float = 0.18
    prefer_shield: bool = True
    prefer_heal: bool = True
    allow_food_ui: bool = True
    allow_retreat: bool = True
    danger_ui_block_threshold: float = 0.45


@dataclass(frozen=True, slots=True)
class SurvivalDecision:
    kind: SurvivalDecisionKind
    action: str
    interrupt: bool
    priority: int
    reason: str
    verifier: str = ""
    failure_code: str = ""
    evidence_requirements: list[str] = field(default_factory=list)


class SurvivalPolicyEngine:
    """Decide survival actions before the rotation greedily spends inputs."""

    def __init__(self, policy: SurvivalPolicy | None = None) -> None:
        self.policy = policy or SurvivalPolicy()

    def decide(self, state: SurvivalState) -> SurvivalDecision:
        p = self.policy
        if state.danger_score >= 0.7:
            return SurvivalDecision("dodge", "dodge_reflex", True, 0, "danger_imminent", "danger_cleared", evidence_requirements=["danger_frame"])
        if state.active_hp <= p.emergency_threshold:
            if state.danger_score >= p.danger_ui_block_threshold:
                return SurvivalDecision("dodge", "dodge_reflex", True, 0, "emergency_hp_but_ui_unsafe", "danger_cleared", evidence_requirements=["danger_frame"])
            if p.allow_food_ui and state.food_available:
                if not state.ui_profile_ready:
                    return SurvivalDecision("safe_abort", "release_all", True, 0, "food_ui_profile_missing", "input_released", "HEAL_PROFILE_NOT_READY")
                return SurvivalDecision("food_ui", "open_inventory_use_food", True, 1, "emergency_food_heal", "hp_increased", evidence_requirements=["hp_before", "hp_after"])
            if p.allow_retreat:
                return SurvivalDecision("retreat", "retreat_and_keep_distance", True, 1, "emergency_retreat", "distance_increased")
            return SurvivalDecision("safe_abort", "release_all", True, 0, "emergency_no_survival_path", "input_released", "NO_SURVIVAL_PATH")
        if state.active_hp <= p.hard_hp_threshold:
            if p.prefer_shield and state.shielder_available and not state.shield_active:
                return SurvivalDecision("shield", "use_shield_skill", True, 2, "hard_hp_shield", "shield_active")
            if p.prefer_heal and state.healer_available:
                return SurvivalDecision("heal", "use_heal_skill", True, 2, "hard_hp_heal", "hp_increased", evidence_requirements=["hp_before", "hp_after"])
            if p.allow_retreat:
                return SurvivalDecision("retreat", "retreat_and_keep_distance", True, 2, "hard_hp_retreat", "distance_increased")
        if state.active_hp <= p.soft_hp_threshold:
            if p.prefer_shield and state.shielder_available and not state.shield_active:
                return SurvivalDecision("shield", "use_shield_skill", False, 5, "soft_hp_shield", "shield_active")
            if p.prefer_heal and state.healer_available:
                return SurvivalDecision("heal", "use_heal_skill", False, 5, "soft_hp_heal", "hp_increased", evidence_requirements=["hp_before", "hp_after"])
        return SurvivalDecision("none", "continue_rotation", False, 99, "safe")


class SurvivalStateTracker:
    def from_runtime(
        self,
        *,
        hp_ratios: list[float],
        danger_score: float,
        shield_active: bool = False,
        healer_available: bool = False,
        shielder_available: bool = False,
        food_available: bool = False,
        stamina: float = 1.0,
        ui_profile_ready: bool = False,
    ) -> SurvivalState:
        active_hp = hp_ratios[0] if hp_ratios else 1.0
        death_risk = max(0.0, min(1.0, (0.4 - active_hp) + danger_score * 0.6))
        return SurvivalState(
            active_hp=active_hp,
            team_hp=list(hp_ratios),
            shield_active=shield_active,
            shielder_available=shielder_available,
            healer_available=healer_available,
            food_available=food_available,
            stamina=stamina,
            death_risk=death_risk,
            danger_score=danger_score,
            ui_profile_ready=ui_profile_ready,
        )
