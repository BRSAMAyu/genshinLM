from __future__ import annotations

import time
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any, Callable

from core.types import SkillResult
from execution.skill_binder import SkillBinder
from execution.verifier_base import SnapshotStore, Verifier, VerifierContext, VerifierResult


@dataclass(frozen=True, slots=True)
class MissionNodeExecutionResult:
    node_id: str
    status: str
    skill_result: SkillResult | None
    verifier_result: VerifierResult
    cleanup_skill_called: str | None = None
    snapshot_id: str | None = None


class MissionNodeExecutor:
    def __init__(self, binder: SkillBinder | None = None, snapshots: SnapshotStore | None = None) -> None:
        self._binder = binder or SkillBinder()
        self._snapshots = snapshots or SnapshotStore()

    def execute(
        self,
        node: Any,
        available_skills: list[dict[str, Any]],
        verifier: Verifier,
        state: dict[str, Any] | VerifierContext,
        skill_runner: Callable[[str, Any, VerifierContext], tuple[SkillResult, VerifierContext]] | None = None,
        cleanup_runner: Callable[[str, VerifierContext], SkillResult] | None = None,
    ) -> MissionNodeExecutionResult:
        context = state if isinstance(state, VerifierContext) else VerifierContext(state=state)
        policy = _field(node, "failure_policy") or {}
        node_id = _field(node, "id")
        node_type = _field(node, "type")
        high_risk = policy.get("requires_snapshot", True) or node_type in {"combat", "enter_region"}
        snapshot = self._snapshots.capture(node_id, context.state) if high_risk else None
        binding = self._binder.bind(node, available_skills)
        started = time.time()
        requested_skill = _field(node, "skill_binding")
        if binding.selected_skill is None and requested_skill is not None:
            skill_result = SkillResult("missing_skill", "FAILED", "MISSING_SKILL", started, time.time(), {"binding": asdict(binding)})
            post_context = context
        elif binding.selected_skill is None and requested_skill is None:
            skill_result = SkillResult(
                "verifier_only",
                "SUCCESS",
                "node_has_no_skill_binding",
                started,
                time.time(),
                {"binding": asdict(binding), "executed": "verifier_only"},
            )
            post_context = context
        elif skill_runner is not None:
            skill_result, post_context = skill_runner(binding.selected_skill, node, context)
        else:
            skill_result = SkillResult(binding.selected_skill, "SUCCESS", None, started, time.time(), {"binding": asdict(binding), "executed": "dry_run_noop"})
            post_context = context
        verifier_result = verifier.verify(post_context)
        if skill_result.status == "SUCCESS" and verifier_result.ok:
            return MissionNodeExecutionResult(node_id, "SUCCESS", skill_result, verifier_result, snapshot_id=snapshot.snapshot_id if snapshot else None)
        cleanup = policy.get("cleanup_skill") if policy.get("on_failed") == "recover_or_skip" or policy.get("on_node_failed") == "recover_or_skip" else None
        if cleanup and cleanup_runner is not None:
            cleanup_result = cleanup_runner(str(cleanup), post_context)
            if skill_result.metadata is not None:
                skill_result.metadata["cleanup_result"] = cleanup_result.status
        return MissionNodeExecutionResult(node_id, "SKIPPED_AFTER_CLEANUP" if cleanup else "FAILED", skill_result, verifier_result, cleanup, snapshot.snapshot_id if snapshot else None)


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
