from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from perception.observation_graph import ObservationGraph
from planning.mission_queue import MissionQueue


@dataclass(frozen=True, slots=True)
class RunSummary:
    mission_id: str
    current_node: str
    completed_nodes: list[str]
    active_goal: dict[str, Any]
    verified_facts: list[str]
    unresolved_risks: list[str]
    last_failure: dict[str, Any] | None
    recovery_attempts: int
    next_allowed_actions: list[str]
    evidence_refs: list[str]
    hot_context: dict[str, Any] = field(default_factory=dict)
    warm_context: dict[str, Any] = field(default_factory=dict)
    cold_context_refs: list[str] = field(default_factory=list)
    claim_status: dict[str, str] = field(default_factory=dict)


class ContextCompactor:
    """Turn long-running traces into bounded LLM context projections."""

    def compact(
        self,
        mission: MissionQueue,
        current_node: str,
        observation_graph: ObservationGraph | None = None,
        completed_nodes: list[str] | None = None,
        verifier_results: list[dict[str, Any]] | None = None,
        failures: list[dict[str, Any]] | None = None,
        recovery_attempts: int = 0,
        cold_refs: list[str] | None = None,
        claim_status: dict[str, str] | None = None,
    ) -> RunSummary:
        verified_facts = [
            str(result.get("fact") or result.get("verifier_id") or result.get("reason"))
            for result in (verifier_results or [])
            if result.get("ok") is True
        ]
        last_failure = failures[-1] if failures else None
        unresolved_risks = []
        if last_failure:
            unresolved_risks.append(str(last_failure.get("failure_code", "unresolved_failure")))
        if observation_graph and observation_graph.screen_state() == "unknown":
            unresolved_risks.append("unknown_screen_state")

        next_allowed = self._next_allowed_actions(mission, current_node, completed_nodes or [])
        return RunSummary(
            mission_id=mission.mission_id,
            current_node=current_node,
            completed_nodes=completed_nodes or [],
            active_goal=asdict(mission.goal),
            verified_facts=verified_facts,
            unresolved_risks=unresolved_risks,
            last_failure=last_failure,
            recovery_attempts=recovery_attempts,
            next_allowed_actions=next_allowed,
            evidence_refs=[observation_graph.graph_id] if observation_graph else [],
            hot_context={
                "current_node": current_node,
                "observation": observation_graph.evidence_summary() if observation_graph else None,
                "last_failure": last_failure,
            },
            warm_context={
                "completed_nodes": completed_nodes or [],
                "recent_verified_facts": verified_facts[-8:],
                "recovery_attempts": recovery_attempts,
            },
            cold_context_refs=cold_refs or [],
            claim_status=claim_status or {},
        )

    def _next_allowed_actions(
        self,
        mission: MissionQueue,
        current_node: str,
        completed_nodes: list[str],
    ) -> list[str]:
        if current_node not in {node.id for node in mission.nodes}:
            return [mission.nodes[0].id] if mission.nodes else []
        current_seen = False
        for node in mission.nodes:
            if node.id == current_node:
                current_seen = True
                continue
            if current_seen and node.id not in completed_nodes:
                return [node.id]
        return []


@dataclass(frozen=True, slots=True)
class SummaryValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


class RunSummaryValidator:
    """Guard against silent context-compaction corruption."""

    def validate(self, mission: MissionQueue, summary: RunSummary) -> SummaryValidationResult:
        errors: list[str] = []
        node_ids = {node.id for node in mission.nodes}
        if summary.mission_id != mission.mission_id:
            errors.append("mission_id_mismatch")
        if summary.current_node and summary.current_node not in node_ids:
            errors.append("unknown_current_node")
        for node_id in summary.completed_nodes:
            if node_id not in node_ids:
                errors.append(f"unknown_completed_node:{node_id}")
        for node_id in summary.next_allowed_actions:
            if node_id not in node_ids:
                errors.append(f"unknown_next_action:{node_id}")
        if summary.verified_facts and not summary.evidence_refs:
            errors.append("verified_facts_without_evidence")
        if len(set(summary.completed_nodes)) != len(summary.completed_nodes):
            errors.append("duplicate_completed_nodes")
        return SummaryValidationResult(ok=not errors, errors=errors)
