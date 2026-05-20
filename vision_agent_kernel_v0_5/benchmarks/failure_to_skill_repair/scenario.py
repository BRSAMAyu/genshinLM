"""Scenarios for the failure-to-skill-repair benchmark suite."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RepairScenario:
    """A failure scenario to feed into the EvolutionEngine repair flywheel."""

    name: str
    description: str
    skill_name: str
    failure_code: str
    observation_data: dict[str, object]
    expect_patch_created: bool = True
    expect_patch_approved: bool = True
    expect_benchmark_delta: bool = True


SCENARIOS: list[RepairScenario] = [
    RepairScenario(
        name="target_lost_repair",
        description="Target lost failure triggers patch creation and approval",
        skill_name="safe_combat_v1",
        failure_code="TARGET_LOST",
        observation_data={"target_confidence_drop": True},
        expect_patch_created=True,
        expect_patch_approved=True,
        expect_benchmark_delta=True,
    ),
    RepairScenario(
        name="visual_pollution_repair",
        description="Visual pollution triggers ROI/threshold patch",
        skill_name="safe_combat_v1",
        failure_code="VISUAL_POLLUTION",
        observation_data={"visual_pollution_high": True},
        expect_patch_created=True,
        expect_patch_approved=True,
        expect_benchmark_delta=True,
    ),
    RepairScenario(
        name="timeout_recovery_repair",
        description="Combat timeout triggers timeout recovery patch",
        skill_name="combat_rotation_v2",
        failure_code="COMBAT_TIMEOUT",
        observation_data={},
        expect_patch_created=True,
        expect_patch_approved=True,
        expect_benchmark_delta=True,
    ),
    RepairScenario(
        name="combined_failure_repair",
        description="Multiple failure signals combined trigger comprehensive patch",
        skill_name="exploration_v1",
        failure_code="NAVIGATION_FAILED",
        observation_data={"target_confidence_drop": True, "visual_pollution_high": True},
        expect_patch_created=True,
        expect_patch_approved=True,
        expect_benchmark_delta=True,
    ),
]
