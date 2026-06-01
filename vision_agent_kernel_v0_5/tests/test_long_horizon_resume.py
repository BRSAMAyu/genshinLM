"""Tests for long-horizon route/fight/collect/resume gauntlet."""
from __future__ import annotations

from benchmarks.long_horizon_route_fight_collect_resume.runner import run_all_long_horizon, run_scenario
from benchmarks.long_horizon_route_fight_collect_resume.scenario import SCENARIOS


class TestLongHorizonResume:

    def test_all_scenarios_return_result(self) -> None:
        results = run_all_long_horizon()
        assert len(results) == len(SCENARIOS)

    def test_full_chain_happy_path(self) -> None:
        scenario = SCENARIOS[0]
        assert scenario.name == "full_chain_happy_path"
        result = run_scenario(scenario)
        assert result.passed
        assert result.metrics.evidence_coverage > 0.0

    def test_combat_recovery_resume(self) -> None:
        scenario = SCENARIOS[1]
        assert scenario.name == "combat_recovery_resume"
        result = run_scenario(scenario)
        assert result.passed
        report = result.report
        assert report["resume_skips_ok"] is True

    def test_double_interrupt_resume(self) -> None:
        scenario = SCENARIOS[2]
        assert scenario.name == "double_interrupt_resume"
        result = run_scenario(scenario)
        assert result.passed
        assert result.report["interrupt_count"] == 2
        assert result.report["recovery_transitions"] == 2

    def test_collect_with_danger_interleave(self) -> None:
        scenario = SCENARIOS[3]
        assert scenario.name == "collect_with_danger_interleave"
        result = run_scenario(scenario)
        assert result.passed

    def test_terminal_nodes_have_evidence(self) -> None:
        for scenario in SCENARIOS:
            result = run_scenario(scenario)
            assert result.report["terminal_evidence_ok"] is True, (
                f"{scenario.name}: terminal nodes missing evidence"
            )

    def test_evidence_coverage_high(self) -> None:
        for scenario in SCENARIOS:
            result = run_scenario(scenario)
            assert result.metrics.evidence_coverage >= 0.5, (
                f"{scenario.name}: low evidence coverage {result.metrics.evidence_coverage:.2f}"
            )

    def test_all_phases_visited(self) -> None:
        """Nodes visited (including skipped verified ones) should match scenario node count."""
        for scenario in SCENARIOS:
            result = run_scenario(scenario)
            report = result.report
            assert len(report["nodes_visited"]) == len(scenario.nodes), (
                f"{scenario.name}: visited {len(report['nodes_visited'])} != {len(scenario.nodes)} nodes"
            )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
