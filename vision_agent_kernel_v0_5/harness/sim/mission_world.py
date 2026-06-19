"""Chapter-scale mission world — Phase 5 dogfood.

A composite :class:`~mission.mission_orchestrator.NodeExecutor` that dispatches
each graph node to the matching primitive sub-environment + sub-controller built
in Phases 0-4 (nav / combat / interaction / puzzle), run to completion via the
harness ScenarioRunner. So a passing mission means the whole stack composes into
multi-step chapter completion with claim-gating and failure recovery.

Includes a generator for chapter DAGs: a branching main-story-shaped graph
(talk -> travel -> combat -> puzzle -> travel -> boss -> turn-in -> reward) with
one node injected as initially-failing-then-recoverable, exercising the
orchestrator's retry/attribution path.
"""
from __future__ import annotations

import math
import random

from harness.core import Scenario
from harness.runner import ScenarioRunner
from harness.sim.combat_world import CombatPolicy, CombatWorldEnv
from harness.sim.interaction_world import InteractionEnv, InteractionPolicy
from harness.sim.nav_world import NavStackPolicy, NavWorldEnv
from harness.sim.puzzle_world import PuzzlePolicy, PuzzleWorldEnv
from mission.mission_graph import MissionGraph, MissionNode, QuestContext
from mission.mission_orchestrator import NodeOutcome


def _run_primitive(kind: str, setup: dict[str, object], objective: str) -> tuple[bool, str]:
    """Run one primitive sub-scenario to completion; return (success, failure_code)."""
    if kind == "nav":
        result = ScenarioRunner(NavWorldEnv(), NavStackPolicy()).run(
            Scenario(scenario_id=objective, objective=objective, setup=setup,
                     max_steps=400, timeout_sec=40.0, tags=("nav",)))
    elif kind == "combat":
        result = ScenarioRunner(CombatWorldEnv(), CombatPolicy()).run(
            Scenario(scenario_id=objective, objective=objective, setup=setup,
                     max_steps=300, timeout_sec=30.0, tags=("combat",)))
    elif kind == "interaction":
        result = ScenarioRunner(InteractionEnv(), InteractionPolicy()).run(
            Scenario(scenario_id=objective, objective=objective, setup=setup,
                     max_steps=40, timeout_sec=20.0, tags=("interaction",)))
    elif kind == "puzzle":
        result = ScenarioRunner(PuzzleWorldEnv(), PuzzlePolicy()).run(
            Scenario(scenario_id=objective, objective=objective, setup=setup,
                     max_steps=50, timeout_sec=15.0, tags=("puzzle",)))
    else:
        # system nodes (teleport, wait, save) succeed trivially offline.
        return True, ""
    return result.passed, result.failure_code or ""


class ChapterNodeExecutor:
    """NodeExecutor over the primitive sub-environments.

    ``flaky_nodes`` maps node_id -> set of attempt numbers that should fail before
    succeeding, to deterministically exercise the retry/recovery path without a
    real adversarial game.
    """

    def __init__(self, flaky_nodes: dict[str, set[int]] | None = None) -> None:
        self._flaky = flaky_nodes or {}
        self._attempts: dict[str, int] = {}

    def execute(self, node: MissionNode, ctx: QuestContext) -> NodeOutcome:
        attempts = self._attempts.get(node.node_id, 0) + 1
        self._attempts[node.node_id] = attempts

        flaky = self._flaky.get(node.node_id, set())
        if attempts in flaky:
            return NodeOutcome(success=False, failure_code="transient_fault",
                               reason=f"injected transient fault (attempt {attempts})")

        success, code = _run_primitive(node.kind, node.setup, node.node_id)
        updates: dict[str, object] = {}
        if success and node.kind == "interaction":
            # propagate quest flags so downstream claim-gates can depend on them
            updates[f"done_{node.node_id}"] = True
        return NodeOutcome(success=success, failure_code=code, context_updates=updates,
                           reason="ok" if success else code)


def make_chapter_graph(seed: int = 0, *, flaky: bool = True) -> MissionGraph:
    """Build a main-story-shaped chapter DAG."""
    rng = random.Random(seed)
    elements = ["pyro", "hydro", "electro", "cryo"]
    e1 = rng.choice(elements)

    ang = rng.uniform(0, 360)
    dist = rng.uniform(10.0, 18.0)
    tx, ty = dist * math.sin(math.radians(ang)), dist * math.cos(math.radians(ang))

    graph = MissionGraph(objective="clear chapter")
    graph.add(MissionNode(
        node_id="talk_start", kind="interaction",
        setup={"script": [
            {"kind": "prompt", "prompt": "Talk to NPC", "goal": "talk"},
            {"kind": "dialogue", "goal": "advance"},
            {"kind": "choice", "goal": "accept the quest",
             "choices": ["Accept the quest", "Decline"], "correct": 0},
        ]},
    ))
    graph.add(MissionNode(
        node_id="travel_site", kind="nav", dependencies=("talk_start",),
        setup={"start": [0.0, 0.0], "heading": rng.uniform(0, 360), "target": [tx, ty],
               "arrival_radius": 2.5, "speed": 5.0, "flow_noise": 0.03, "heading_noise": 4.0,
               "bounds": 200.0, "seed": rng.randint(0, 1_000_000)},
    ))
    graph.add(MissionNode(
        node_id="clear_camp", kind="combat", dependencies=("travel_site",),
        setup={"team": [{"name": "dps", "element": e1, "role": "dps", "hp": 1000.0, "atk": 70.0,
                         "skill_cd": 6, "skill_mult": 3.5, "burst_cost": 30.0, "burst_mult": 7.0}],
               "enemy": {"hp": 800.0, "atk": 70.0, "aura": rng.choice(["", "hydro"]),
                         "attack_interval": 6, "telegraph_lead": 1}, "max_ticks": 300},
    ))
    graph.add(MissionNode(
        node_id="solve_seal", kind="puzzle", dependencies=("clear_camp",),
        setup={"start": [rng.uniform(-30, 30), rng.uniform(-30, 30)],
               "target": [rng.uniform(-30, 30), rng.uniform(-30, 30)],
               "tolerance": 1.5, "noise": 2.0, "max_attempts": 50,
               "seed": rng.randint(0, 1_000_000)},
    ))
    graph.add(MissionNode(
        node_id="travel_boss", kind="nav", dependencies=("solve_seal",),
        setup={"start": [tx, ty], "heading": rng.uniform(0, 360),
               "target": [-tx, -ty], "arrival_radius": 2.5, "speed": 5.0,
               "flow_noise": 0.03, "heading_noise": 4.0, "bounds": 200.0,
               "seed": rng.randint(0, 1_000_000)},
    ))
    graph.add(MissionNode(
        node_id="boss_fight", kind="combat", dependencies=("travel_boss",),
        setup={"team": [{"name": "dps", "element": e1, "role": "dps", "hp": 1000.0, "atk": 75.0,
                         "skill_cd": 6, "skill_mult": 3.5, "burst_cost": 30.0, "burst_mult": 7.0}],
               "enemy": {"hp": 1400.0, "atk": 95.0, "aura": "", "attack_interval": 5,
                         "telegraph_lead": 1}, "max_ticks": 300},
        max_retries=2,
    ))
    graph.add(MissionNode(
        node_id="turn_in", kind="interaction", dependencies=("boss_fight",),
        setup={"script": [
            {"kind": "prompt", "prompt": "Talk to NPC", "goal": "talk"},
            {"kind": "dialogue", "goal": "advance"},
            {"kind": "choice", "goal": "turn in the report",
             "choices": ["Turn in the report", "Not yet"], "correct": 0},
        ]},
    ))
    graph.add(MissionNode(
        node_id="claim_reward", kind="interaction", dependencies=("turn_in",),
        setup={"script": [{"kind": "reward", "goal": "claim reward"}]},
    ))

    # Inject one transient fault to exercise retry/attribution.
    if flaky:
        # (executor config carries the flaky map; graph nodes carry retry budget.)
        graph.nodes["boss_fight"].max_retries = 2
    return graph


def flaky_map_for(graph: MissionGraph) -> dict[str, set[int]]:
    """Flaky config: the boss fails once then succeeds (tests retry path)."""
    return {"boss_fight": {1}} if "boss_fight" in graph.nodes else {}
