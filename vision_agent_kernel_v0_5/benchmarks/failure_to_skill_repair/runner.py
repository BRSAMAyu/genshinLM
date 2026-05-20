"""Runner for the failure-to-skill-repair benchmark suite.

Creates an EvolutionEngine with a temp directory, mocks _verify_in_sandbox to
return True, feeds failure scenarios, and verifies the complete repair flywheel:
failure -> signature -> repair session -> patch -> validation -> benchmark delta.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from core.state_bus import StateBus
from evidence.evidence_nodes import (
    NODE_TYPE_FAILURE_SIGNATURE,
    NODE_TYPE_PATCH_PROPOSAL,
    NODE_TYPE_BENCHMARK_RESULT,
)
from evidence.evidence_store import EvidenceStore
from learning.evolution_engine import EvolutionEngine

from benchmarks.benchmark_types import BenchmarkMetrics, BenchmarkResult
from benchmarks.failure_to_skill_repair.scenario import RepairScenario, SCENARIOS


def run_scenario(scenario: RepairScenario) -> BenchmarkResult:
    """Execute a single repair scenario and return a BenchmarkResult."""
    evidence_ids: list[str] = []
    report_details: dict[str, object] = {
        "skill_name": scenario.skill_name,
        "failure_code": scenario.failure_code,
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        bus = StateBus()
        bus.register_slot("learning.patch_event")
        store = EvidenceStore(run_id=f"repair_{scenario.name}")

        engine = EvolutionEngine(
            state_bus=bus,
            patches_dir=Path(tmp_dir),
        )

        # Mock _verify_in_sandbox to return True (no real pytest)
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            # Record failure signature evidence
            failure_node = store.record_node(NODE_TYPE_FAILURE_SIGNATURE, {
                "skill_name": scenario.skill_name,
                "failure_code": scenario.failure_code,
            })
            evidence_ids.append(failure_node.node_id)

            # Feed the failure into the engine
            legacy_result = engine.handle_failure(
                skill_name=scenario.skill_name,
                failure_code=scenario.failure_code,
                observation_data=scenario.observation_data,
            )

            # Verify patch was created
            patch_created = legacy_result is not None
            report_details["patch_created"] = patch_created
            if patch_created:
                patch_id = legacy_result.get("patch_id", "unknown")  # type: ignore[union-attr]
                evidence_ids.append(f"patch_{patch_id}")

                # Record patch proposal evidence
                patch_node = store.record_node(NODE_TYPE_PATCH_PROPOSAL, {
                    "patch_id": patch_id,
                    "skill_name": scenario.skill_name,
                })
                evidence_ids.append(patch_node.node_id)
                store.record_edge(failure_node.node_id, patch_node.node_id, "PATCHED_BY")

            # Verify patch is verified (sandbox mock returns True)
            verified = legacy_result.get("verified", False) if legacy_result else False
            report_details["patch_verified"] = verified

            # Attempt approval
            approved = False
            if patch_created and verified:
                approved = engine.approve_patch(scenario.skill_name)
                report_details["patch_approved"] = approved

                if approved:
                    approval_evidence = store.record_node("patch_approved", {
                        "skill_name": scenario.skill_name,
                    })
                    evidence_ids.append(approval_evidence.node_id)

            # Check benchmark delta
            delta = engine.benchmark_delta(scenario.skill_name)
            report_details["benchmark_delta"] = delta is not None
            if delta:
                delta_node = store.record_node(NODE_TYPE_BENCHMARK_RESULT, {
                    "skill_id": scenario.skill_name,
                    "improvement": delta.get("improvement", 0.0),
                })
                evidence_ids.append(delta_node.node_id)

            # Check Stage 46 repair session was created
            repair_sessions = list(engine._repair_sessions.values())
            report_details["repair_sessions_created"] = len(repair_sessions)

            # Check Stage 46 SkillPatchDraft was created
            patch_drafts = list(engine._skill_patch_drafts.values())
            report_details["skill_patch_drafts_created"] = len(patch_drafts)
            for draft in patch_drafts:
                evidence_ids.append(f"draft_{draft.patch_id}")

    # Determine pass/fail
    passed = True
    if scenario.expect_patch_created and not patch_created:
        passed = False
    if scenario.expect_patch_approved and not approved:
        passed = False
    if scenario.expect_benchmark_delta and delta is None:
        passed = False

    # Evidence coverage: ratio of expected evidence to actual
    expected_evidence = 2  # failure signature + patch proposal at minimum
    if scenario.expect_benchmark_delta:
        expected_evidence += 1
    evidence_coverage = min(len(evidence_ids) / max(expected_evidence, 1), 1.0)

    metrics = BenchmarkMetrics(
        frame_to_observation_ms=0.0,
        observation_to_interrupt_ms=0.0,
        interrupt_to_lease_ms=0.0,
        danger_clear_time_ms=0.0,
        danger_false_clear_rate=0.0,
        resume_success_rate=1.0 if approved else 0.0,
        max_consecutive_dodges=0,
        final_task_success=passed,
        evidence_coverage=evidence_coverage,
    )

    return BenchmarkResult(
        benchmark_id=f"repair_{scenario.name}",
        run_id=uuid.uuid4().hex[:8],
        suite_name="failure_to_skill_repair",
        scenario_name=scenario.name,
        passed=passed,
        metrics=metrics,
        evidence_ids=evidence_ids,
        report=report_details,
    )


def run_all_repair() -> list[BenchmarkResult]:
    """Run all repair scenarios and return results."""
    return [run_scenario(scenario) for scenario in SCENARIOS]
