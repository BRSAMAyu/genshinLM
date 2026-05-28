"""MissionGraph v4 Validator — structural and semantic validation.

Validation rules:
1. Terminal nodes (no successors) must have output_claims
2. High-risk and critical nodes must have fallbacks
3. Graph must be acyclic
4. All edge references must point to existing nodes
5. All belief_templates must have target_object and causal_role
6. Node IDs must be unique
7. Graph must be deterministic-serializable (round-trip to_dict/from_dict)
8. risk_level must be a valid literal value
"""
from __future__ import annotations

from dataclasses import dataclass

from planning.mainline.mission_graph_v4 import (
    MissionGraphV4,
    _VALID_CLAIM_ROLES,
    _VALID_RISK_LEVELS,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    node_id: str
    rule: str
    message: str
    severity: str  # error, warning


class MissionGraphValidatorV4:
    """Validates a MissionGraphV4 for structural correctness and safety."""

    def validate(self, graph: MissionGraphV4) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        self._check_unique_ids(graph, issues)
        self._check_risk_levels(graph, issues)
        self._check_terminal_output_claims(graph, issues)
        self._check_high_risk_fallbacks(graph, issues)
        self._check_cycle(graph, issues)
        self._check_edge_references(graph, issues)
        self._check_belief_templates(graph, issues)
        self._check_required_belief_templates(graph, issues)
        self._check_deterministic_serialization(graph, issues)

        return issues

    def is_valid(self, graph: MissionGraphV4) -> bool:
        return all(i.severity != "error" for i in self.validate(graph))

    def _check_unique_ids(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        seen: set[str] = set()
        for nid in graph.node_ids:
            if nid in seen:
                issues.append(ValidationIssue(nid, "unique_id", f"Duplicate node_id: {nid!r}", "error"))
            seen.add(nid)

    def _check_risk_levels(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        for nid in graph.node_ids:
            node = graph.get_node(nid)
            if node is None:
                continue
            if node.risk_level not in _VALID_RISK_LEVELS:
                issues.append(ValidationIssue(
                    nid, "invalid_risk_level",
                    f"Node {nid!r} has invalid risk_level {node.risk_level!r}", "error",
                ))
            for ic in node.input_claims:
                if ic.claim_role not in _VALID_CLAIM_ROLES:
                    issues.append(ValidationIssue(
                        nid, "invalid_claim_role",
                        f"Input claim in {nid!r} has invalid claim_role {ic.claim_role!r}", "error",
                    ))
            for oc in node.output_claims:
                if oc.claim_role not in _VALID_CLAIM_ROLES:
                    issues.append(ValidationIssue(
                        nid, "invalid_claim_role",
                        f"Output claim in {nid!r} has invalid claim_role {oc.claim_role!r}", "error",
                    ))

    def _check_terminal_output_claims(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        for nid in graph.terminal_nodes():
            node = graph.get_node(nid)
            if node is None:
                continue
            if not node.output_claims:
                issues.append(ValidationIssue(
                    nid, "terminal_output_claim",
                    f"Terminal node {nid!r} must have at least one output_claim", "error",
                ))

    def _check_high_risk_fallbacks(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        for nid in graph.node_ids:
            node = graph.get_node(nid)
            if node is None:
                continue
            if node.risk_level in ("high", "critical") and not node.fallbacks:
                issues.append(ValidationIssue(
                    nid, "high_risk_fallback",
                    f"{node.risk_level}-risk node {nid!r} must have at least one fallback", "error",
                ))

    def _check_cycle(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        if graph.has_cycle():
            issues.append(ValidationIssue(
                "", "acyclic", "Graph contains a cycle", "error",
            ))

    def _check_edge_references(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        reported: set[tuple[str, str]] = set()
        for nid in graph.node_ids:
            for succ in graph.successors(nid):
                if succ not in graph.nodes and (nid, succ) not in reported:
                    reported.add((nid, succ))
                    issues.append(ValidationIssue(
                        nid, "edge_reference",
                        f"Edge from {nid!r} to unknown node {succ!r}", "error",
                    ))

    def _check_belief_templates(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        for nid in graph.node_ids:
            node = graph.get_node(nid)
            if node is None:
                continue
            for bt in node.belief_templates:
                if not bt.target_object:
                    issues.append(ValidationIssue(
                        nid, "belief_template_target",
                        f"Belief template in node {nid!r} missing target_object", "warning",
                    ))
                if not bt.causal_role:
                    issues.append(ValidationIssue(
                        nid, "belief_template_role",
                        f"Belief template in node {nid!r} missing causal_role", "warning",
                    ))

    def _check_required_belief_templates(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        for nid in graph.node_ids:
            node = graph.get_node(nid)
            if node is None:
                continue
            if node.metadata.get("requires_bagel_belief") and not node.belief_templates:
                issues.append(ValidationIssue(
                    nid, "required_belief_template",
                    f"Node {nid!r} requires at least one BAGEL belief template", "error",
                ))

    def _check_deterministic_serialization(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
        try:
            data = graph.to_dict()
            reconstructed = MissionGraphV4.from_dict(data)
            roundtrip = reconstructed.to_dict()

            if data["nodes"] != roundtrip["nodes"]:
                issues.append(ValidationIssue(
                    "", "serialization",
                    "Round-trip serialization failed: nodes mismatch", "error",
                ))
            if data["edges"] != roundtrip["edges"]:
                issues.append(ValidationIssue(
                    "", "serialization",
                    "Round-trip serialization failed: edges mismatch", "error",
                ))
        except Exception as exc:
            issues.append(ValidationIssue(
                "", "serialization",
                f"Serialization failed: {exc}", "error",
            ))
