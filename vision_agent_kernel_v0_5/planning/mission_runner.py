from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.types import SkillResult
from execution.combat_verifier import CombatVerifier
from execution.collection_verifier import CollectionVerifier
from execution.mission_node_executor import MissionNodeExecutor, MissionNodeExecutionResult
from execution.verifier_base import VerifierContext
from persistence.hot_resume import HotResume
from persistence.mission_checkpoint import MissionCheckpoint
from planning.mission_queue import MissionQueue


SkillRunner = Callable[[str, object, VerifierContext], tuple[SkillResult, VerifierContext]]


@dataclass(slots=True)
class MissionRunResult:
    ok: bool
    node_results: list[MissionNodeExecutionResult] = field(default_factory=list)
    resumed: bool = False


class MissionRunner:
    def __init__(self, root: Path, executor: MissionNodeExecutor | None = None) -> None:
        self._executor = executor or MissionNodeExecutor()
        self._resume = HotResume(root)

    def run(
        self,
        queue: MissionQueue,
        available_skills: list[dict],
        initial_context: VerifierContext,
        skill_runner: SkillRunner,
        resume: bool = False,
    ) -> MissionRunResult:
        completed: list[str] = []
        failed: list[str] = []
        node_results: list[MissionNodeExecutionResult] = []
        if resume:
            latest = self._resume.latest()
            completed = list(latest.get("completed_nodes", [])) if latest else []
        context = initial_context
        for node in queue.nodes:
            if node.id in completed:
                continue
            verifier = CollectionVerifier() if node.type in {"collect", "verify_collection"} else CombatVerifier() if node.type == "combat" else _PassVerifier()
            result = self._executor.execute(node, available_skills, verifier, context, skill_runner=skill_runner)
            node_results.append(result)
            if result.status == "SUCCESS":
                completed.append(node.id)
            else:
                failed.append(node.id)
                if result.status == "FAILED":
                    self._save(queue, node.id, completed, failed)
                    return MissionRunResult(False, node_results, resumed=resume)
            self._save(queue, node.id, completed, failed)
        return MissionRunResult(True, node_results, resumed=resume)

    def _save(self, queue: MissionQueue, current_node: str, completed: list[str], failed: list[str]) -> None:
        self._resume.save(
            MissionCheckpoint(
                mission_id=queue.mission_id,
                current_node=current_node,
                completed_nodes=completed,
                failed_nodes=failed,
                profile_id="default_1920x1080",
                skill_id=None,
                playbook_id=None,
            )
        )


class _PassVerifier:
    verifier_id = "pass_verifier"

    def verify(self, context: VerifierContext | dict) -> object:
        from execution.verifier_base import VerifierResult

        return VerifierResult(True, self.verifier_id, 1.0, "pass")
