"""Integration test: ClosedLoopRunner × UIFlowSkillAdapter for all 9 UI scenarios.

Proves the full chain wiring for every UI capability:
  companion text → TaskSpec → SkillRecipe → UIFlowSkillAdapter → execute → verify

This is the code-level proof that the autonomy closed loop works for all
UI operations defined in docs/GENSHIN_UI_OPERATION_SCENARIOS.md.
"""
from __future__ import annotations

from typing import Any

import pytest

from execution.closed_loop_runner import (
    ClosedLoopResult,
    ClosedLoopRunner,
    SimpleSkillRecipeLookup,
    SimpleTaskSpecResolver,
    VerificationResult,
    ScreenClaimResult,
    TaskSpecResult,
)
from execution.ui_flow_skill_adapter import UIFlowSkillAdapter


class _TrackerVerificationProvider:
    """Verification provider that records which capabilities were verified."""
    def __init__(self) -> None:
        self.verified_capabilities: list[str] = []

    def verify(self, task: TaskSpecResult, screen: ScreenClaimResult) -> VerificationResult:
        self.verified_capabilities.append(task.capability)
        return VerificationResult(verified=True, confidence=0.85, method="vlm", details="mock_pass")


class _TrackingAdapter:
    """Adapter that records all execute_semantic calls."""
    def __init__(self, succeed: bool = True) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self._succeed = succeed

    def execute_semantic(
        self,
        action: str,
        target: str = "",
        context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return self._succeed


# All 9 UI scenarios with their Chinese triggers and expected skill IDs
UI_SCENARIOS = [
    {
        "capability": "character_level_up",
        "text": "升级胡桃到90级",
        "skill_id": "character_level_up_full",
    },
    {
        "capability": "character_ascend",
        "text": "突破甘雨",
        "skill_id": "character_ascend_full",
    },
    {
        "capability": "talent_upgrade",
        "text": "天赋升级",
        "skill_id": "character_talent_upgrade_full",
    },
    {
        "capability": "weapon_equip",
        "text": "装备武器",
        "skill_id": "weapon_equip_full",
    },
    {
        "capability": "weapon_enhance",
        "text": "强化武器",
        "skill_id": "weapon_enhance_full",
    },
    {
        "capability": "weapon_refine",
        "text": "精炼武器",
        "skill_id": "weapon_refine_full",
    },
    {
        "capability": "artifact_equip",
        "text": "圣遗物装备",
        "skill_id": "artifact_equip_full",
    },
    {
        "capability": "artifact_enhance",
        "text": "圣遗物强化",
        "skill_id": "artifact_enhance_full",
    },
    {
        "capability": "wish_pull",
        "text": "祈愿十连",
        "skill_id": "wish_ten_pull_full",
    },
]


class TestUI9ScenarioIntegration:
    """Run the closed loop for all 9 UI scenarios."""

    @pytest.fixture
    def runner(self) -> tuple[ClosedLoopRunner, _TrackingAdapter, _TrackerVerificationProvider]:
        adapter = _TrackingAdapter(succeed=True)
        verifier = _TrackerVerificationProvider()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = ClosedLoopRunner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=verifier,
        )
        return runner, adapter, verifier

    @pytest.mark.parametrize("scenario", UI_SCENARIOS, ids=lambda s: s["capability"])
    def test_scenario_succeeds(self, runner, scenario) -> None:
        r, adapter, verifier = runner
        result = r.run(scenario["text"])
        assert result.success is True, (
            f"{scenario['capability']}: loop failed, steps="
            f"{[(s.step, s.success, s.details) for s in result.steps]}"
        )
        assert len(adapter.calls) == 1
        assert adapter.calls[0][0] == scenario["skill_id"]

    def test_all_9_succeed_sequentially(self, runner) -> None:
        """Run all 9 scenarios in sequence, proving no state leakage."""
        r, adapter, verifier = runner
        results: list[ClosedLoopResult] = []

        for scenario in UI_SCENARIOS:
            result = r.run(scenario["text"])
            results.append(result)
            assert result.success is True, f"{scenario['capability']} failed"

        # Verify all 9 ran
        assert len(results) == 9
        assert all(r.success for r in results)

        # Verify adapter received all 9 skill IDs
        assert len(adapter.calls) == 9
        skill_ids = [c[0] for c in adapter.calls]
        expected = [s["skill_id"] for s in UI_SCENARIOS]
        assert skill_ids == expected

    def test_claim_graph_accumulates_across_runs(self, runner) -> None:
        """Claim graph should grow as more scenarios run."""
        r, _, _ = runner
        for scenario in UI_SCENARIOS:
            r.run(scenario["text"])

        graph = r.claim_graph
        assert graph.observation_count >= 9, f"expected >=9 observations, got {graph.observation_count}"
        assert graph.claim_count >= 9, f"expected >=9 claims, got {graph.claim_count}"

    def test_timing_all_under_1s(self, runner) -> None:
        """Each closed loop iteration should complete in under 1 second."""
        r, _, _ = runner
        for scenario in UI_SCENARIOS:
            result = r.run(scenario["text"])
            assert result.total_duration_ms < 1000, (
                f"{scenario['capability']}: took {result.total_duration_ms:.1f}ms"
            )

    def test_real_adapter_dry_run_all_9(self) -> None:
        """Full chain with real UIFlowSkillAdapter (ConsoleInputBackend dry-run).

        Without a live game the UIFlow screen validation won't pass, but this
        proves the chain wiring is correct for all 9 capabilities.
        """
        adapter = UIFlowSkillAdapter()
        verifier = _TrackerVerificationProvider()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = ClosedLoopRunner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=verifier,
        )

        completed = 0
        for scenario in UI_SCENARIOS:
            result = runner.run(scenario["text"])
            assert isinstance(result, ClosedLoopResult)
            step_names = [s.step for s in result.steps]
            assert "resolve_task" in step_names
            assert "lookup_skill" in step_names
            assert "execute" in step_names
            completed += 1

        assert completed == 9
        assert runner.claim_graph.observation_count >= 9

    def test_verification_provider_called_for_each(self, runner) -> None:
        """Verification provider should be invoked for every scenario."""
        r, _, verifier = runner
        for scenario in UI_SCENARIOS:
            r.run(scenario["text"])

        assert len(verifier.verified_capabilities) == 9
        caps = verifier.verified_capabilities
        expected_caps = [s["capability"] for s in UI_SCENARIOS]
        assert caps == expected_caps


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
