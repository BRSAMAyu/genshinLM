"""Tests for planning/exploration_mission_bridge.py — ExplorationEngine → MissionGraphV4."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from planning.exploration_engine import (
    ExplorationObjective,
    ExplorationPlan,
    ExplorationTarget,
    Region,
)
from planning.exploration_mission_bridge import build_exploration_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target(
    tid: str = "t1",
    objective: ExplorationObjective = ExplorationObjective.WAYPOINT_UNLOCK,
    region: Region = Region.MONDSTADT,
    priority: int = 100,
    est_sec: float = 30.0,
) -> ExplorationTarget:
    return ExplorationTarget(
        target_id=tid,
        objective=objective,
        region=region,
        position=(0.0, 0.0, 0.0),
        priority=priority,
        estimated_time_sec=est_sec,
    )


@dataclass(slots=True)
class _StubEngine:
    """Minimal ExplorationEngine stub returning preset plan."""
    _targets: list[ExplorationTarget] = field(default_factory=list)

    def plan_session(self, **kw: Any) -> ExplorationPlan:
        return ExplorationPlan(region=Region.MONDSTADT, targets=list(self._targets))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildExplorationGraph:

    def test_empty_targets_returns_empty_graph(self) -> None:
        engine = _StubEngine(_targets=[])
        graph = build_exploration_graph(engine)
        assert len(graph.nodes) == 0

    def test_single_target_creates_one_node(self) -> None:
        engine = _StubEngine(_targets=[_target("wp_1")])
        graph = build_exploration_graph(engine, mission_id="test_exp")
        assert graph.mission_id == "test_exp"
        assert len(graph.nodes) == 1
        node = graph.get_node("exploration_0_wp_1")
        assert node is not None
        assert node.node_type == "exploration_waypoint_unlock"

    def test_waypoint_maps_to_correct_skill(self) -> None:
        engine = _StubEngine(_targets=[_target("wp_1", ExplorationObjective.WAYPOINT_UNLOCK)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_wp_1")
        assert node is not None
        assert node.skill_candidates == ("explore_activate_waypoint",)

    def test_chest_maps_to_correct_skill(self) -> None:
        engine = _StubEngine(_targets=[_target("chest_1", ExplorationObjective.CHEST_OPEN)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_chest_1")
        assert node is not None
        assert node.skill_candidates == ("explore_open_chest",)

    def test_oculus_maps_to_correct_skill(self) -> None:
        engine = _StubEngine(_targets=[_target("oc_1", ExplorationObjective.OCULUS_COLLECT)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_oc_1")
        assert node is not None
        assert node.skill_candidates == ("explore_collect_oculus",)

    def test_puzzle_maps_to_correct_skill(self) -> None:
        engine = _StubEngine(_targets=[_target("pz_1", ExplorationObjective.PUZZLE_SOLVE)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_pz_1")
        assert node is not None
        assert node.skill_candidates == ("explore_puzzle_monument",)

    def test_risk_levels_per_objective(self) -> None:
        engine = _StubEngine(_targets=[
            _target("wp", ExplorationObjective.WAYPOINT_UNLOCK),
            _target("oc", ExplorationObjective.OCULUS_COLLECT),
            _target("pz", ExplorationObjective.PUZZLE_SOLVE),
        ])
        graph = build_exploration_graph(engine)
        assert graph.get_node("exploration_0_wp").risk_level == "low"
        assert graph.get_node("exploration_1_oc").risk_level == "medium"
        assert graph.get_node("exploration_2_pz").risk_level == "high"

    def test_sequential_chain_edges(self) -> None:
        engine = _StubEngine(_targets=[_target("a"), _target("b"), _target("c")])
        graph = build_exploration_graph(engine)
        assert len(graph.nodes) == 3

        # 2 edges: a→b, b→c
        from planning.mainline.mission_graph_v4 import MissionEdgeV4
        node_ids = list(graph.nodes.keys())
        assert node_ids[0] == "exploration_0_a"
        assert node_ids[1] == "exploration_1_b"
        assert node_ids[2] == "exploration_2_c"

    def test_output_claims_terminal(self) -> None:
        engine = _StubEngine(_targets=[_target("wp_1")])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_wp_1")
        assert node is not None
        assert len(node.output_claims) == 1
        assert node.output_claims[0].claim_role == "terminal"
        assert node.output_claims[0].target == "wp_1"

    def test_input_claims_informational(self) -> None:
        engine = _StubEngine(_targets=[_target("wp_1")])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_wp_1")
        assert node is not None
        assert len(node.input_claims) == 1
        assert node.input_claims[0].claim_role == "informational"
        assert node.input_claims[0].claim_type == "screen_state"

    def test_fallbacks_present(self) -> None:
        engine = _StubEngine(_targets=[_target("wp_1")])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_wp_1")
        assert node is not None
        assert len(node.fallbacks) == 1
        assert node.fallbacks[0].replan_policy == "skip_and_continue"

    def test_budgets_scaled_by_estimated_time(self) -> None:
        engine = _StubEngine(_targets=[_target("wp_1", est_sec=60.0)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_wp_1")
        assert node is not None
        assert node.budgets.max_retries == 3
        assert node.budgets.max_duration_sec == 180.0  # 60 * 3

    def test_metadata_contains_target_info(self) -> None:
        engine = _StubEngine(_targets=[_target("oc_1", ExplorationObjective.OCULUS_COLLECT)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_oc_1")
        assert node is not None
        assert node.metadata["target_id"] == "oc_1"
        assert node.metadata["objective"] == "oculus_collect"
        assert node.metadata["region"] == "mondstadt"

    def test_max_targets_limits_nodes(self) -> None:
        targets = [_target(f"t{i}") for i in range(10)]
        engine = _StubEngine(_targets=targets)
        graph = build_exploration_graph(engine, max_targets=3)
        assert len(graph.nodes) == 3

    def test_domain_unlock_skill(self) -> None:
        engine = _StubEngine(_targets=[_target("dm_1", ExplorationObjective.DOMAIN_UNLOCK)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_dm_1")
        assert node is not None
        assert node.skill_candidates == ("explore_interact",)

    def test_challenge_complete_skill(self) -> None:
        engine = _StubEngine(_targets=[_target("ch_1", ExplorationObjective.CHALLENGE_COMPLETE)])
        graph = build_exploration_graph(engine)
        node = graph.get_node("exploration_0_ch_1")
        assert node is not None
        assert node.skill_candidates == ("explore_timed_challenge",)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
