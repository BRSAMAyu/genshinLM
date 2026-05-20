from __future__ import annotations

from dataclasses import dataclass, field

from evidence.evidence_graph import EvidenceGraph
from evidence.evidence_nodes import NODE_TYPE_INPUT_LEASE, NODE_TYPE_VERIFIER_RESULT


@dataclass(slots=True)
class StrictModeConfig:
    """Toggle flags for strict-mode validation checks."""

    enabled: bool = True
    require_terminal_verifier: bool = True
    require_visual_evidence: bool = True
    require_lease_for_physical_action: bool = True
    require_patch_benchmark_delta: bool = True


class StrictModeValidator:
    """Validates evidence-chain integrity for actions, verifier results, and
    mission-terminal outcomes.

    Uses generic ``getattr``/``hasattr`` access so it never imports domain types
    directly.
    """

    def __init__(self, config: StrictModeConfig | None = None) -> None:
        self._config = config or StrictModeConfig()

    @property
    def config(self) -> StrictModeConfig:
        return self._config

    # -- validators ---------------------------------------------------------

    def validate_action(self, action: object, graph: EvidenceGraph) -> list[str]:
        """Return a list of violation strings.  Empty means *valid*."""
        if not self._config.enabled:
            return []

        violations: list[str] = []
        status = getattr(action, "status", "")
        is_physical = bool(getattr(action, "is_physical", False))

        # A VERIFIED_SUCCESS action must have a verifier_result_id that is
        # present in the graph.
        if status == "VERIFIED_SUCCESS":
            vr_id = getattr(action, "verifier_result_id", None)
            if vr_id is None:
                violations.append(
                    "Action with status=VERIFIED_SUCCESS has no verifier_result_id"
                )
            elif graph.get_node(str(vr_id)) is None:
                violations.append(
                    f"verifier_result_id '{vr_id}' not found in evidence graph"
                )

        # Physical actions must have an InputLease node linked.
        if is_physical and self._config.require_lease_for_physical_action:
            lease_id = getattr(action, "input_lease_id", None)
            if lease_id is None:
                violations.append(
                    "Physical action has no input_lease_id"
                )
            else:
                lease_node = graph.get_node(str(lease_id))
                if lease_node is None:
                    violations.append(
                        f"input_lease_id '{lease_id}' not found in evidence graph"
                    )
                elif lease_node.node_type != NODE_TYPE_INPUT_LEASE:
                    violations.append(
                        f"Node '{lease_id}' is not an InputLease node "
                        f"(got '{lease_node.node_type}')"
                    )

        # Precondition evidence IDs must exist in the graph.
        precond_ids = getattr(action, "precondition_evidence_ids", None)
        if precond_ids is not None:
            for pid in precond_ids:
                if graph.get_node(str(pid)) is None:
                    violations.append(
                        f"precondition_evidence_id '{pid}' not found in evidence graph"
                    )

        return violations

    def validate_verifier_result(
        self,
        verifier_result: object,
        graph: EvidenceGraph,
    ) -> list[str]:
        """Validate a verifier result has proper evidence linkage."""
        if not self._config.enabled:
            return []

        violations: list[str] = []
        ok = getattr(verifier_result, "ok", False)

        # Collect evidence ids from various possible attributes.
        evidence_ids: list[str] = []
        for attr in ("evidence_ids", "frame_id", "observation_id"):
            val = getattr(verifier_result, attr, None)
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                evidence_ids.extend(str(v) for v in val)
            else:
                evidence_ids.append(str(val))

        has_evidence_link = False
        for eid in evidence_ids:
            node = graph.get_node(eid)
            if node is not None:
                has_evidence_link = True
            else:
                violations.append(
                    f"Evidence id '{eid}' referenced by verifier not found in graph"
                )

        if ok and self._config.require_visual_evidence and not has_evidence_link:
            violations.append(
                "Verifier result with ok=True has no evidence nodes in graph"
            )

        return violations

    def validate_mission_terminal_success(
        self,
        mission_result: object,
        graph: EvidenceGraph,
    ) -> list[str]:
        """Validate a mission-node terminal success has a complete evidence chain."""
        if not self._config.enabled:
            return []

        violations: list[str] = []

        vr_id = getattr(mission_result, "verifier_result_id", None)
        if vr_id is None:
            violations.append(
                "Mission terminal result has no verifier_result_id"
            )
            return violations

        vr_node = graph.get_node(str(vr_id))
        if vr_node is None:
            violations.append(
                f"verifier_result_id '{vr_id}' not found in evidence graph"
            )
            return violations

        if vr_node.node_type != NODE_TYPE_VERIFIER_RESULT:
            violations.append(
                f"Node '{vr_id}' is not a verifier_result "
                f"(got '{vr_node.node_type}')"
            )

        # The verifier result must report ok=True.
        vr_ok = vr_node.payload.get("ok")
        if vr_ok is not True:
            violations.append(
                f"Verifier result '{vr_id}' does not have ok=True "
                f"(payload.ok={vr_ok!r})"
            )

        # The verifier result must have at least one evidence node linked.
        if self._config.require_terminal_verifier:
            edges_to = graph.get_edges_to(str(vr_id))
            if not edges_to:
                violations.append(
                    f"Verifier result '{vr_id}' has no evidence edges linked to it"
                )

        return violations
