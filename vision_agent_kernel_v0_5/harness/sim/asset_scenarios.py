"""Scenario builders backed by the real game data assets.

Generate harness scenarios from curated data (real team comps, real world-graph
waypoints) so the dogfood benchmarks exercise actual game balance and geography
instead of purely synthetic stats. Falls back gracefully when an asset is absent
or unparseable.
"""
from __future__ import annotations

import math
import random
from typing import Any

from data.game_assets import _load_yaml, _KNOWLEDGE, load_monsters, load_team_profiles, monster_to_sim, team_comp_to_sim
from harness.core import Scenario


def combat_scenarios_from_assets(
    n: int,
    *,
    seed: int = 0,
    atk: float = 60.0,
) -> list[Scenario]:
    """Build combat scenarios from real team comps vs real monsters.

    Teams come from ``team_profiles.yaml`` (National, Raiden National, ...).
    Enemies come from ``genshin_monsters.yaml`` when it parses; otherwise a
    tiered synthetic enemy stands in. Each scenario tags its real team_id.
    """
    rng = random.Random(seed)
    teams = load_team_profiles()
    monsters = load_monsters()
    # Prefer a spread of monster tiers; fall back to synthetic tiers if the
    # monster DB didn't load.
    monster_pool = list(monsters.values()) if monsters else []
    tiers_fallback = ["mob", "elite", "boss"]

    scenarios: list[Scenario] = []
    if not teams:
        return scenarios
    for i in range(n):
        team = rng.choice(teams)
        members = team_comp_to_sim(team.team_id, atk=atk)
        if not members:
            continue
        if monster_pool:
            enemy = monster_to_sim(rng.choice(monster_pool).monster_id)
            tier = enemy.get("monster_id", "mob")
        else:
            tier = tiers_fallback[i % len(tiers_fallback)]
            hp_atk = {"mob": (800.0, 70.0), "elite": (1800.0, 130.0), "boss": (2800.0, 200.0)}
            hp, e_atk = hp_atk[tier]
            enemy = {"hp": hp, "atk": e_atk, "aura": "", "attack_interval": 6 if tier == "mob" else 4,
                     "telegraph_lead": 1, "aoe": tier == "boss"}
        scenarios.append(Scenario(
            scenario_id=f"cbt-asset-{seed}-{i:03d}",
            objective=f"clear {tier} with {team.team_id}",
            setup={"team": members, "enemy": enemy, "max_ticks": 300},
            max_steps=300, timeout_sec=30.0, tags=("combat", tier, team.team_id),
        ))
    return scenarios


def _load_waypoint_positions() -> list[tuple[str, str, tuple[float, float]]]:
    """Return [(waypoint_id, region, (x, z))] from the world graph; [] if absent."""
    data: Any = _load_yaml(_KNOWLEDGE / "genshin_world_graph.yaml")
    if not data:
        return []
    out: list[tuple[str, str, tuple[float, float]]] = []
    for wp in data.get("waypoints", []):
        pos = wp.get("position")
        wid = str(wp.get("waypoint_id", ""))
        region = str(wp.get("region", ""))
        if wid and isinstance(pos, (list, tuple)) and len(pos) >= 3:
            # Genshin world: x = east, z = south/north ground axis; y is up.
            out.append((wid, region, (float(pos[0]), float(pos[2]))))
    return out


def nav_scenarios_from_world_graph(
    n: int,
    *,
    seed: int = 0,
) -> list[Scenario]:
    """Build nav scenarios between REAL world-graph waypoint positions.

    Uses actual in-game coordinates (x, z ground plane), so the pose/nav stack is
    exercised against real geography. Falls back to nothing if the graph is absent.
    """
    rng = random.Random(seed)
    wps = _load_waypoint_positions()
    if len(wps) < 2:
        return []
    scenarios: list[Scenario] = []
    for i in range(n):
        a, b = rng.sample(wps, 2)
        # Start near waypoint a, target waypoint b (real coordinates).
        sx, sy = a[2]
        tx, ty = b[2]
        scenarios.append(Scenario(
            scenario_id=f"nav-asset-{seed}-{i:03d}",
            objective=f"travel {a[0]} -> {b[0]}",
            setup={"start": [sx, sy], "heading": rng.uniform(0, 360), "target": [tx, ty],
                   "arrival_radius": 25.0, "nav_arrival_radius": 14.0, "speed": 8.0,
                   "flow_noise": 0.03, "heading_noise": 4.0,
                   "bounds": 1.0e6, "seed": rng.randint(0, 1_000_000)},
            max_steps=400, timeout_sec=40.0, tags=("nav", "worldgraph", b[1]),
        ))
    return scenarios


def asset_summary() -> dict[str, int]:
    """Quick inventory of how many real assets loaded (for the alignment doc)."""
    from data.game_assets import load_character_profiles
    return {
        "characters": len(load_character_profiles()),
        "teams": len(load_team_profiles()),
        "monsters": len(load_monsters()),
        "worldgraph_waypoints": len(_load_waypoint_positions()),
    }
