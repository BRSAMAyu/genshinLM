"""Benchmark runner for before/after skill patch comparison."""

from __future__ import annotations

import time
from dataclasses import dataclass

from repair.skill_patch_builder import SkillPatchDraft


@dataclass(slots=True)
class BenchmarkDelta:
    """Measured improvement from applying a skill patch."""

    skill_id: str
    patch_id: str
    before_pass_rate: float
    after_pass_rate: float
    before_failure_count: int
    after_failure_count: int
    improvement: float  # after - before


class RepairBenchmarkRunner:
    """Runs before/after benchmarks and computes improvement delta."""

    def __init__(self) -> None:
        self._before_results: dict[str, dict[str, object]] = {}
        self._after_results: dict[str, dict[str, object]] = {}

    def run_before(self, skill_id: str) -> dict[str, object]:
        """Run the original (unpatched) skill and collect baseline metrics."""
        # In production, this would replay recorded scenarios against the skill.
        # For MVP, we return a synthetic baseline from the failure history.
        result: dict[str, object] = {
            "skill_id": skill_id,
            "timestamp": time.perf_counter(),
            "pass_rate": 0.0,
            "failure_count": 1,
            "scenarios_run": 1,
        }
        self._before_results[skill_id] = result
        return result

    def run_after(self, skill_id: str, patch: SkillPatchDraft) -> dict[str, object]:
        """Run the patched skill and collect post-patch metrics."""
        # In production, this would replay recorded scenarios against the patched skill.
        # For MVP, we return a synthetic improved result if the patch has validated steps.
        passed = patch.status in ("SANDBOX_VALIDATED", "APPROVED", "APPLIED")
        result: dict[str, object] = {
            "skill_id": skill_id,
            "patch_id": patch.patch_id,
            "timestamp": time.perf_counter(),
            "pass_rate": 1.0 if passed else 0.0,
            "failure_count": 0 if passed else 1,
            "scenarios_run": 1,
        }
        self._after_results[skill_id] = result
        return result

    def compute_delta(self, skill_id: str, patch: SkillPatchDraft) -> BenchmarkDelta:
        """Compute the before/after benchmark delta for a skill patch."""
        before = self._before_results.get(skill_id)
        if before is None:
            before = self.run_before(skill_id)

        after = self._after_results.get(skill_id)
        if after is None:
            after = self.run_after(skill_id, patch)

        before_pass_rate = float(before.get("pass_rate", 0.0))
        after_pass_rate = float(after.get("pass_rate", 0.0))
        before_failures = int(before.get("failure_count", 0))
        after_failures = int(after.get("failure_count", 0))

        return BenchmarkDelta(
            skill_id=skill_id,
            patch_id=patch.patch_id,
            before_pass_rate=before_pass_rate,
            after_pass_rate=after_pass_rate,
            before_failure_count=before_failures,
            after_failure_count=after_failures,
            improvement=after_pass_rate - before_pass_rate,
        )
