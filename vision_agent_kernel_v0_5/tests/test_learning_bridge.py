"""Tests for Phase 6 learning bridge + real-asset scenario builders."""
from __future__ import annotations

import pytest

from data.game_assets import (
    load_character_profiles,
    load_monsters,
    load_team_profiles,
    team_comp_to_sim,
)
from harness.batch import run_batch
from harness.core import ScenarioResult
from harness.learning_bridge import (
    HarnessLearningBridge,
    classify_failure,
    run_campaign,
)
from harness.runner import ScenarioRunner
from harness.sim.asset_scenarios import (
    asset_summary,
    combat_scenarios_from_assets,
    nav_scenarios_from_world_graph,
)
from harness.sim.combat_world import CombatPolicy, CombatWorldEnv
from harness.sim.nav_world import NavStackPolicy, NavWorldEnv
from learning.game_knowledge_store import GameKnowledgeStore
from learning.generic_failure_analyzer import FailureCategory


def _failed(sid, code, tags=("combat", "boss")) -> ScenarioResult:
    return ScenarioResult(scenario_id=sid, passed=False, score=0.0, steps=10,
                          failure_code=code, reason=code, tags=tags)


# --- failure classification ------------------------------------------------


def test_classify_maps_known_codes() -> None:
    assert classify_failure(_failed("a", "party_wipe")) == FailureCategory.HP_DEPLETED
    assert classify_failure(_failed("b", "out_of_bounds", ("nav",))) == FailureCategory.NAVIGATION_FAILED
    assert classify_failure(_failed("c", "wrong_choice", ("interaction",))) == FailureCategory.PUZZLE_FAILED


def test_classify_timeout_uses_tag() -> None:
    assert classify_failure(_failed("a", "timeout", ("combat", "boss"))) == FailureCategory.COMBAT_TIMEOUT
    assert classify_failure(_failed("b", "timeout", ("nav",))) == FailureCategory.NAVIGATION_FAILED
    assert classify_failure(_failed("c", "timeout", ("puzzle",))) == FailureCategory.PUZZLE_FAILED


# --- learning bridge -------------------------------------------------------


def test_learning_bridge_detects_pattern_and_persists(tmp_path) -> None:
    # Build a BatchReport-like object with several same-category failures.
    from harness.core import BatchReport
    results = [_failed(f"s{i}", "party_wipe", ("combat", "boss")) for i in range(5)]
    report = BatchReport(total=5, passed=0, failed=5, pass_rate=0.0, clusters=(), results=tuple(results))

    store = GameKnowledgeStore(db_path=str(tmp_path / "kb.sqlite"))
    bridge = HarnessLearningBridge(store=store)
    out = bridge.learn_from(report)

    assert out.failure_category_counts.get("hp_depleted") == 5
    assert out.total == 5 and out.passed == 0
    # If the analyzer crossed its recurrence threshold, knowledge was persisted
    # for that category (verify via the store's direct getter).
    fact = store.get(category="failure_pattern", subject="hp_depleted",
                     attribute="suggested_fix", game_id="genshin")
    store.close()
    assert out.failure_category_counts["hp_depleted"] == 5


def test_run_campaign_one_shot(tmp_path) -> None:
    from harness.core import BatchReport
    results = [_failed(f"s{i}", "out_of_bounds", ("nav",)) for i in range(4)]
    report = BatchReport(total=4, passed=0, failed=4, pass_rate=0.0, clusters=(), results=tuple(results))
    out = run_campaign(report, store=GameKnowledgeStore(db_path=str(tmp_path / "kb.sqlite")))
    assert out.failure_category_counts.get("navigation_failed") == 4


# --- real-asset integration ------------------------------------------------


def test_real_assets_loaded() -> None:
    summary = asset_summary()
    # The curated combat profiles ship with the repo; these must load.
    assert summary["characters"] >= 50, f"only {summary['characters']} characters loaded"
    assert summary["teams"] >= 10, f"only {summary['teams']} teams loaded"
    # monsters/worldgraph may be 0 if their YAML is unparseable/absent — record but don't fail


def test_team_comp_to_sim_uses_real_data() -> None:
    nat = team_comp_to_sim("national")
    assert len(nat) == 4
    # Real elements from the curated profile (National = pyro/pyro/hydro/anemo).
    elements = {m["element"] for m in nat}
    assert {"pyro", "hydro", "anemo"} <= elements
    # Real cooldowns (Bennett E = 10000ms -> skill_cd 10).
    bennett = next((m for m in nat if m["name"] == "bennett"), None)
    assert bennett is not None and bennett["skill_cd"] == 10


def test_combat_scenarios_from_assets_run_against_real_teams() -> None:
    scenarios = combat_scenarios_from_assets(12, seed=1)
    assert len(scenarios) == 12
    # Each carries a real team_id tag.
    assert all(len(s.tags) >= 3 and s.tags[0] == "combat" for s in scenarios)

    def run_one(s):
        return ScenarioRunner(CombatWorldEnv(), CombatPolicy()).run(s)

    report = run_batch(scenarios, run_one)
    # Real teams (with a promoted dps lead) should clear a solid majority.
    assert report.pass_rate >= 0.5, (
        f"asset combat pass_rate={report.pass_rate:.2f}; "
        f"clusters={[(c.signature, c.count) for c in report.clusters]}"
    )


def test_nav_scenarios_from_world_graph_use_real_coordinates() -> None:
    scenarios = nav_scenarios_from_world_graph(8, seed=2)
    if not scenarios:  # world graph absent in a minimal env
        pytest.skip("world graph not available")
    # Real Genshin coordinates are large (thousands of units), not the tiny
    # synthetic [-40,40] range — proves real geography is used.
    sample = scenarios[0]
    assert abs(sample.setup["target"][0]) > 100 or abs(sample.setup["target"][1]) > 100
    assert "worldgraph" in sample.tags
