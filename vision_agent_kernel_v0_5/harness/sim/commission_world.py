"""Daily-commission cycle — Phase 3 exit-gate composite environment.

Sequences the full loop the north-star must run end to end:
accept (interaction) → travel (navigation) → task (combat) → turn-in
(interaction) → reward (interaction). It delegates each stage to the real
sub-environment + sub-controller built in Phases 0–3, so a passing batch means
the whole chain works together — and previews the Phase 5 orchestration layer.
"""
from __future__ import annotations

import random

from harness.core import JsonDict, Scenario
from harness.sim.combat_world import CombatPolicy, CombatWorldEnv
from harness.sim.interaction_world import InteractionEnv, InteractionPolicy
from harness.sim.nav_world import NavStackPolicy, NavWorldEnv


def _build_stages(setup: JsonDict) -> list[tuple[str, Scenario]]:
    """Build the (kind, sub-scenario) sequence from a commission setup.

    Shared by the env (which holds sub-envs) and the policy (which resets
    sub-policies), so both agree on the stage plan.
    """
    accept = Scenario(
        scenario_id="accept", objective="accept commission",
        setup={"script": [
            {"kind": "prompt", "prompt": "Talk to commission board", "goal": "talk"},
            {"kind": "dialogue", "goal": "advance"},
            {"kind": "choice", "goal": "accept the commission",
             "choices": ["Accept the commission", "Decline"], "correct": 0},
        ]},
        max_steps=20, tags=("interaction",),
    )
    travel = Scenario(
        scenario_id="travel", objective="travel to site",
        setup=setup["travel"], max_steps=300, tags=("nav",),
    )
    task = Scenario(
        scenario_id="task", objective="clear the task",
        setup=setup["task"], max_steps=300, tags=("combat",),
    )
    turnin = Scenario(
        scenario_id="turnin", objective="turn in",
        setup={"script": [
            {"kind": "prompt", "prompt": "Talk to NPC", "goal": "talk"},
            {"kind": "dialogue", "goal": "advance"},
            {"kind": "choice", "goal": "turn in the report",
             "choices": ["Turn in the report", "Not yet"], "correct": 0},
        ]},
        max_steps=20, tags=("interaction",),
    )
    reward = Scenario(
        scenario_id="reward", objective="claim reward",
        setup={"script": [{"kind": "reward", "goal": "claim reward"}]},
        max_steps=10, tags=("interaction",),
    )
    return [("interaction", accept), ("nav", travel), ("combat", task),
            ("interaction", turnin), ("interaction", reward)]


class DailyCommissionEnv:
    """Composite environment sequencing the daily-commission stages."""

    def __init__(self) -> None:
        self._stages: list[tuple[str, Scenario]] = []
        self._envs = {
            "interaction": InteractionEnv(),
            "nav": NavWorldEnv(),
            "combat": CombatWorldEnv(),
        }
        self._stage = 0

    def reset(self, scenario: Scenario) -> JsonDict:
        self._stages = _build_stages(scenario.setup)
        self._stage = 0
        kind, scn = self._stages[0]
        sub_obs = self._envs[kind].reset(scn)
        return self._wrap(sub_obs, kind)

    def step(self, action: JsonDict) -> tuple[JsonDict, bool, JsonDict]:
        kind, _scn = self._stages[self._stage]
        sub_obs, sub_done, sub_info = self._envs[kind].step(action)
        n = len(self._stages)

        if sub_done and not sub_info.get("success", False):
            info = {
                "success": False,
                "failure_code": f"{kind}:{sub_info.get('failure_code', 'failed')}",
                "reason": f"stage {self._stage} ({kind}) failed",
                "progress": self._stage / n,
            }
            return self._wrap(sub_obs, kind), True, info

        if sub_done and sub_info.get("success", False):
            self._stage += 1
            if self._stage >= n:
                return self._wrap(sub_obs, kind), True, {
                    "success": True, "failure_code": None,
                    "reason": "commission complete", "progress": 1.0,
                }
            nkind, nscn = self._stages[self._stage]
            nobs = self._envs[nkind].reset(nscn)
            return self._wrap(nobs, nkind), False, {
                "success": False, "failure_code": None,
                "reason": f"advanced to stage {self._stage} ({nkind})",
                "progress": self._stage / n,
            }

        # stage still in progress
        return self._wrap(sub_obs, kind), False, {
            "success": False, "failure_code": None, "reason": f"stage {self._stage} ({kind})",
            "progress": (self._stage + float(sub_info.get("progress", 0.0))) / n,
        }

    def _wrap(self, sub_obs: JsonDict, kind: str) -> JsonDict:
        return {"stage_kind": kind, "stage_index": self._stage, "inner": sub_obs}


class CommissionPolicy:
    """Routes each stage's observation to the matching sub-controller."""

    def __init__(self) -> None:
        self._pol = {
            "interaction": InteractionPolicy(),
            "nav": NavStackPolicy(),
            "combat": CombatPolicy(),
        }

    def reset(self, scenario: Scenario) -> None:
        for kind, scn in _build_stages(scenario.setup):
            self._pol[kind].reset(scn)  # nav needs its travel scenario; others no-op

    def act(self, obs: JsonDict) -> JsonDict:
        kind = obs["stage_kind"]
        return self._pol[kind].act(obs["inner"])


def make_commission_scenarios(n: int, *, seed: int = 0) -> list[Scenario]:
    """Generate deterministic daily-commission scenarios."""
    rng = random.Random(seed)
    elements = ["pyro", "hydro", "electro", "cryo"]
    scenarios: list[Scenario] = []
    for i in range(n):
        # short travel leg
        ang = rng.uniform(0, 360)
        dist = rng.uniform(10.0, 20.0)
        import math
        tx, ty = dist * math.sin(math.radians(ang)), dist * math.cos(math.radians(ang))
        travel = {
            "start": [0.0, 0.0], "heading": rng.uniform(0, 360), "target": [tx, ty],
            "arrival_radius": 2.5, "speed": 5.0, "flow_noise": 0.03, "heading_noise": 4.0,
            "bounds": 200.0, "seed": rng.randint(0, 1_000_000),
        }
        e1 = rng.choice(elements)
        task = {
            "team": [{"name": "dps", "element": e1, "role": "dps", "hp": 1000.0, "atk": 70.0,
                      "skill_cd": 6, "skill_mult": 3.5, "burst_cost": 30.0, "burst_mult": 7.0}],
            "enemy": {"hp": 800.0, "atk": 70.0, "aura": rng.choice(["", "hydro"]),
                      "attack_interval": 6, "telegraph_lead": 1},
            "max_ticks": 300,
        }
        scenarios.append(Scenario(
            scenario_id=f"comm-{seed}-{i:03d}", objective="complete daily commission",
            setup={"travel": travel, "task": task},
            max_steps=900, timeout_sec=60.0, tags=("commission",),
        ))
    return scenarios
