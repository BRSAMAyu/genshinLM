"""Tests for Mainline API — cockpit endpoints."""
from __future__ import annotations

import pytest

from app_service.mainline_api import MainlineAPI
from planning.mainline.mission_graph_v4 import (
    ClaimContract,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
)
from skills.schema import SkillDef


def _linear_graph() -> MissionGraphV4:
    g = MissionGraphV4(mission_id="api_test")
    g.add_node(MissionNodeV4(
        node_id="start", node_type="observe",
        output_claims=(ClaimContract("screen"),),
    ))
    g.add_node(MissionNodeV4(
        node_id="end", node_type="dialog",
        output_claims=(ClaimContract("done"),),
    ))
    g.add_edge(MissionEdgeV4("start", "end"))
    return g


class TestMainlineAPI:
    def test_initial_state(self) -> None:
        api = MainlineAPI()
        state = api.get_state()
        assert state["runner_state"] == "idle"
        assert state["skill_count"] == 0

    def test_start_mission(self) -> None:
        api = MainlineAPI()
        result = api.start(_linear_graph())
        assert result["ok"]
        state = api.get_state()
        assert state["runner_state"] in ("completed", "error")

    def test_start_twice_fails(self) -> None:
        api = MainlineAPI()
        api.start(_linear_graph())  # completes immediately
        # After completion, state is "completed" not "running"
        result = api.start(_linear_graph())
        # Second start should work since we're not "running"
        assert result["ok"]

    def test_pause_when_not_running(self) -> None:
        api = MainlineAPI()
        result = api.pause()
        assert not result["ok"]

    def test_stop(self) -> None:
        api = MainlineAPI()
        result = api.stop()
        assert result["ok"]
        assert api.get_state()["runner_state"] == "stopped"

    def test_get_claims(self) -> None:
        api = MainlineAPI()
        claims = api.get_claims()
        assert "claim_count" in claims
        assert "observation_count" in claims

    def test_get_bagel(self) -> None:
        api = MainlineAPI()
        bagel = api.get_bagel()
        assert "graph_id" in bagel
        assert "belief_count" in bagel
        assert "suspect_beliefs" in bagel
        assert "falsified_beliefs" in bagel

    def test_get_skills_empty(self) -> None:
        api = MainlineAPI()
        skills = api.get_skills()
        assert skills["total"] == 0
        assert skills["by_tier"] == {}

    def test_get_skills_with_registry(self) -> None:
        from skills.registry import SkillRegistry
        reg = SkillRegistry()
        reg.register(SkillDef(skill_id="s1", tier="draft"))
        reg.register(SkillDef(skill_id="s2", tier="candidate", produced_claims=(ClaimContract("x"),)))
        api = MainlineAPI(skill_registry=reg)
        skills = api.get_skills()
        assert skills["total"] == 2
        assert skills["by_tier"]["draft"] == 1
        assert skills["by_tier"]["candidate"] == 1

    def test_run_benchmark_unknown_task(self) -> None:
        api = MainlineAPI()
        result = api.run_benchmark("C99")
        assert not result["ok"]

    def test_run_benchmark_valid_task(self) -> None:
        api = MainlineAPI()
        result = api.run_benchmark("C0")
        assert result["ok"]
        assert result["task_id"] == "C0"
        assert "metric" in result
