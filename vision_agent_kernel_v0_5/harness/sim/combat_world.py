"""Deterministic combat world — Phase 2 dogfood environment.

A tick-based team-vs-enemy model exercising the mechanics the north-star combat
must handle: elemental reactions (reward switching elements), skill/burst cooldown
& energy economy, character switching/rotation, telegraphed enemy attacks with a
limited dodge, and healer routing. The real
:class:`~combat.reactive_combat_controller.ReactiveCombatController` drives it, so
a batch yields an offline *clear rate* and surfaces combat failure clusters
(party_wipe / timeout) — the same find→fix loop as navigation.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from combat.reactive_combat_controller import (
    CombatAction,
    CombatCharView,
    CombatView,
    ReactiveCombatController,
)
from harness.core import JsonDict, Scenario

_REACTION_MULT = 2.0
_ENERGY_PER_ATTACK = 2.0
_ENERGY_PER_SKILL = 4.0
_DODGE_CD = 3  # ticks before the agent can dodge again


@dataclass(slots=True)
class SimChar:
    name: str
    element: str
    role: str
    max_hp: float
    hp: float
    atk: float
    skill_cd_max: int
    skill_cd: int
    skill_mult: float
    burst_cost: float
    burst_mult: float
    energy: float
    heal_amount: float = 0.0


@dataclass(slots=True)
class SimEnemy:
    max_hp: float
    hp: float
    aura: str
    atk: float
    attack_interval: int
    telegraph_lead: int
    aoe: bool = False  # AoE hits the whole team; dodge only spares the active char
    weaknesses: tuple[str, ...] = ()  # elements this enemy takes extra damage from


# Damage multiplier when a hit's element is in the enemy's weaknesses.
_WEAKNESS_MULT = 1.5


class CombatWorldEnv:
    """Implements the harness Environment protocol for combat."""

    def __init__(self) -> None:
        self._chars: list[SimChar] = []
        self._enemy: SimEnemy | None = None
        self._active = 0
        self._tick = 0
        self._max_ticks = 300
        self._enemy_timer = 0
        self._dodge_cd = 0

    def reset(self, scenario: Scenario) -> JsonDict:
        s = scenario.setup
        self._chars = [
            SimChar(
                name=c["name"], element=c["element"], role=c.get("role", "dps"),
                max_hp=c["hp"], hp=c["hp"], atk=c["atk"],
                skill_cd_max=c.get("skill_cd", 8), skill_cd=0,
                skill_mult=c.get("skill_mult", 3.0),
                burst_cost=c.get("burst_cost", 30.0), burst_mult=c.get("burst_mult", 6.0),
                energy=0.0, heal_amount=c.get("heal_amount", 0.0),
            )
            for c in s["team"]
        ]
        e = s["enemy"]
        self._enemy = SimEnemy(
            max_hp=e["hp"], hp=e["hp"], aura=e.get("aura", ""), atk=e["atk"],
            attack_interval=e.get("attack_interval", 5), telegraph_lead=e.get("telegraph_lead", 1),
            aoe=e.get("aoe", False),
            weaknesses=tuple(str(w).lower() for w in e.get("weaknesses", [])),
        )
        self._active = 0
        self._tick = 0
        self._max_ticks = int(s.get("max_ticks", 300))
        self._enemy_timer = self._enemy.attack_interval
        self._dodge_cd = 0
        return self._observe()

    def step(self, action: JsonDict) -> tuple[JsonDict, bool, JsonDict]:
        assert self._enemy is not None
        enemy = self._enemy
        self._tick += 1
        for c in self._chars:
            if c.skill_cd > 0:
                c.skill_cd -= 1
        if self._dodge_cd > 0:
            self._dodge_cd -= 1

        dodging = self._apply_player_action(action)

        # Enemy timing: telegraph then strike.
        self._enemy_timer -= 1
        info_extra: JsonDict = {}
        if self._enemy_timer <= 0:
            if enemy.aoe:
                # whole-team hit; dodge only softens the active char's share (40%),
                # so sustained AoE forces real healing rather than pure dodging
                for i, c in enumerate(self._chars):
                    if c.hp <= 0:
                        continue
                    c.hp -= enemy.atk * (0.4 if (i == self._active and dodging) else 1.0)
                info_extra["took_hit"] = True
            elif not dodging:
                self._chars[self._active].hp -= enemy.atk
                info_extra["took_hit"] = True
            self._enemy_timer = enemy.attack_interval

        success = enemy.hp <= 0.0
        wiped = all(c.hp <= 0.0 for c in self._chars)
        timeout = self._tick >= self._max_ticks
        done = success or wiped or timeout
        failure_code = None if success else ("party_wipe" if wiped else ("timeout" if timeout else None))
        progress = max(0.0, min(1.0, 1.0 - max(enemy.hp, 0.0) / enemy.max_hp))

        info: JsonDict = {
            "success": success,
            "failure_code": failure_code,
            "reason": "enemy defeated" if success else (failure_code or "fighting"),
            "progress": progress,
            "metrics": {"enemy_hp_ratio": max(enemy.hp, 0.0) / enemy.max_hp,
                        "team_alive": sum(1 for c in self._chars if c.hp > 0)},
            **info_extra,
        }
        return self._observe(), done, info

    # -- mechanics ----------------------------------------------------------

    def _apply_player_action(self, action: JsonDict) -> bool:
        assert self._enemy is not None
        kind = action.get("kind", "attack")
        active = self._chars[self._active]
        dodging = False

        if kind == "dodge":
            if self._dodge_cd <= 0:
                dodging = True
                self._dodge_cd = _DODGE_CD
            # if on cooldown, the dodge fails (still take the hit) — survival isn't free
        elif kind == "switch":
            idx = int(action.get("switch_to", self._active))
            if 0 <= idx < len(self._chars) and self._chars[idx].hp > 0:
                self._active = idx
        elif kind == "heal":
            if active.role == "healer" and active.skill_cd <= 0 and active.heal_amount > 0:
                for c in self._chars:
                    if c.hp > 0:
                        c.hp = min(c.max_hp, c.hp + active.heal_amount)
                active.skill_cd = active.skill_cd_max
        elif kind == "burst":
            if active.energy >= active.burst_cost:
                self._deal(active, active.atk * active.burst_mult)
                active.energy = 0.0
        elif kind == "skill":
            if active.skill_cd <= 0:
                self._deal(active, active.atk * active.skill_mult)
                active.skill_cd = active.skill_cd_max
                active.energy += _ENERGY_PER_SKILL
        else:  # attack
            self._deal(active, active.atk, physical=True)
            active.energy += _ENERGY_PER_ATTACK

        return dodging

    def _deal(self, char: SimChar, base: float, *, physical: bool = False) -> None:
        assert self._enemy is not None
        enemy = self._enemy
        dmg = base
        if not physical:
            if enemy.aura and enemy.aura != char.element:
                dmg *= _REACTION_MULT  # elemental reaction
                enemy.aura = ""        # reaction consumes the aura
            else:
                enemy.aura = char.element  # apply element
            # Curated weakness bonus: hitting a known-weak element does more.
            if char.element.lower() in enemy.weaknesses:
                dmg *= _WEAKNESS_MULT
        enemy.hp -= dmg

    def _observe(self) -> JsonDict:
        assert self._enemy is not None
        enemy = self._enemy
        incoming = self._enemy_timer <= enemy.telegraph_lead
        chars = [
            {
                "index": i, "name": c.name, "element": c.element, "role": c.role,
                "hp_ratio": max(c.hp, 0.0) / c.max_hp,
                "energy_ratio": min(1.0, c.energy / c.burst_cost) if c.burst_cost else 1.0,
                "skill_ready": c.skill_cd <= 0 and c.hp > 0,
                "burst_ready": c.energy >= c.burst_cost and c.hp > 0,
            }
            for i, c in enumerate(self._chars)
        ]
        return {
            "active_index": self._active,
            "chars": chars,
            "enemy_hp_ratio": max(enemy.hp, 0.0) / enemy.max_hp,
            "enemy_aura": enemy.aura,
            "incoming_attack": incoming,
            "can_dodge": self._dodge_cd <= 0,
            "enemy_weaknesses": list(enemy.weaknesses),
        }


class CombatPolicy:
    """Drives the real ReactiveCombatController from CombatWorldEnv observations."""

    def __init__(self, controller: ReactiveCombatController | None = None) -> None:
        self._controller = controller or ReactiveCombatController()

    def reset(self, scenario: Scenario) -> None:
        pass

    def act(self, obs: JsonDict) -> JsonDict:
        view = CombatView(
            active_index=obs["active_index"],
            chars=tuple(
                CombatCharView(
                    index=c["index"], name=c["name"], element=c["element"], role=c["role"],
                    hp_ratio=c["hp_ratio"], energy_ratio=c["energy_ratio"],
                    skill_ready=c["skill_ready"], burst_ready=c["burst_ready"],
                )
                for c in obs["chars"]
            ),
            enemy_hp_ratio=obs["enemy_hp_ratio"], enemy_aura=obs["enemy_aura"],
            incoming_attack=obs["incoming_attack"], can_dodge=obs["can_dodge"],
            enemy_weaknesses=tuple(obs.get("enemy_weaknesses", ())),
        )
        action: CombatAction = self._controller.decide(view)
        return {"kind": action.kind, "switch_to": action.switch_to}


def make_combat_scenarios(n: int, *, seed: int = 0) -> list[Scenario]:
    """Generate deterministic combat scenarios across difficulty tiers."""
    rng = random.Random(seed)
    elements = ["pyro", "hydro", "electro", "cryo", "anemo"]
    # (name, enemy hp, enemy atk, attack_interval, aoe) — bosses are hard but
    # winnable with a healer + good rotation/dodging; raw comps wipe.
    tiers = [
        ("mob", 900.0, 90.0, 5, False),
        ("elite", 2000.0, 150.0, 4, False),
        ("boss", 2800.0, 200.0, 4, True),
    ]
    scenarios: list[Scenario] = []
    for i in range(n):
        tier_name, e_hp, e_atk, e_interval, e_aoe = tiers[i % len(tiers)]
        # team: a dps, often a sub of a different element (reactions), sometimes a healer
        e1, e2 = rng.sample(elements, 2)
        team = [
            {"name": "dps", "element": e1, "role": "dps", "hp": 1000.0, "atk": 60.0,
             "skill_cd": 6, "skill_mult": 3.5, "burst_cost": 30.0, "burst_mult": 7.0},
        ]
        if rng.random() < 0.8:
            team.append({"name": "sub", "element": e2, "role": "sub", "hp": 900.0, "atk": 45.0,
                         "skill_cd": 8, "skill_mult": 3.0, "burst_cost": 40.0, "burst_mult": 6.0})
        if rng.random() < 0.55:
            team.append({"name": "healer", "element": "hydro", "role": "healer", "hp": 1100.0,
                         "atk": 30.0, "skill_cd": 6, "skill_mult": 1.5, "burst_cost": 50.0,
                         "burst_mult": 3.0, "heal_amount": 420.0})
        enemy = {
            "hp": e_hp,
            "atk": e_atk,
            "aura": rng.choice(["", e2]),
            "attack_interval": e_interval,
            "telegraph_lead": 1,
            # AoE bosses hit the whole team (attrition the dodge can't fully
            # avoid) → rewards healer comps; surfaces a real party_wipe cluster.
            "aoe": e_aoe,
        }
        scenarios.append(Scenario(
            scenario_id=f"cbt-{seed}-{i:03d}-{tier_name}", objective=f"defeat {tier_name}",
            setup={"team": team, "enemy": enemy, "max_ticks": 300},
            max_steps=300, timeout_sec=30.0, tags=("combat", tier_name),
        ))
    return scenarios
