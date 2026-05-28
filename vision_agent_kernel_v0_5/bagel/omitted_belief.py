"""Neuro-symbolic omitted-belief extraction for BAGEL v1.2.

The symbolic phase extracts anchored invariants. The verbalization phase only
turns those anchors into beliefs; it does not invent new assumptions.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from bagel.fig_schema import BeliefNode


_ALLOWED_SOURCES = {
    "ui_anchor",
    "screen_state_transition",
    "quest_objective_text",
    "map_marker_continuity",
    "skill_precondition",
    "claim_verifier",
    "recovery_recipe_trigger",
}


@dataclass(frozen=True, slots=True)
class ExtractedInvariant:
    anchor: str
    symbol: str
    operator: str
    constraint: str
    source: str
    graph_distance: int = 0
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OmittedBeliefCandidate:
    belief: BeliefNode
    trace_anchor: str
    source_invariant: ExtractedInvariant


class ExtractInvariantSym:
    """Deterministic invariant extractor for GUI/mainline traces."""

    def __init__(self, max_graph_distance: int = 2, max_candidates: int = 5) -> None:
        self.max_graph_distance = max_graph_distance
        self.max_candidates = max_candidates

    def extract(self, records: Iterable[dict[str, Any]]) -> list[ExtractedInvariant]:
        invariants: list[ExtractedInvariant] = []
        for record in records:
            source = str(record.get("source", ""))
            distance = int(record.get("graph_distance", 0))
            if source not in _ALLOWED_SOURCES or distance > self.max_graph_distance:
                continue
            anchor = str(record.get("anchor", ""))
            symbol = str(record.get("symbol", ""))
            constraint = str(record.get("constraint", ""))
            if not anchor or not symbol or not constraint:
                continue
            invariants.append(ExtractedInvariant(
                anchor=anchor,
                symbol=symbol,
                operator=str(record.get("operator", "requires")),
                constraint=constraint,
                source=source,
                graph_distance=distance,
                metadata=dict(record.get("metadata", {}) or {}),
            ))
            if len(invariants) >= self.max_candidates:
                break
        return invariants


class ConstrainedVerbalizer:
    """Turns anchored invariants into BeliefNodes without free-form invention."""

    def verbalize(self, invariant: ExtractedInvariant) -> OmittedBeliefCandidate:
        digest = hashlib.sha1(
            f"{invariant.anchor}|{invariant.symbol}|{invariant.constraint}".encode("utf-8")
        ).hexdigest()[:10]
        claim = (
            f"The action assumes {invariant.symbol} {invariant.operator} "
            f"{invariant.constraint}."
        )
        belief = BeliefNode(
            belief_id=f"omitted_{digest}",
            target_object=invariant.symbol,
            causal_role="custom",
            hypothesis=claim,
            falsification_condition=f"Probe {invariant.symbol} with a value outside {invariant.constraint}.",
            lifecycle="challenged",
            risk_level="medium",
            metadata={
                "omitted": True,
                "trace_anchor": invariant.anchor,
                "source": invariant.source,
            },
        )
        return OmittedBeliefCandidate(belief, invariant.anchor, invariant)
