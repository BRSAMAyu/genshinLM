from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EvidenceNode:
    """A single node in the evidence graph, representing a discrete piece of evidence."""

    node_id: str
    node_type: str  # one of NODE_TYPE_* constants
    created_at: float
    payload: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Node type constants
# ---------------------------------------------------------------------------
NODE_TYPE_FRAME = "frame"
NODE_TYPE_OBSERVATION = "observation"
NODE_TYPE_TARGET_TRACK = "target_track"
NODE_TYPE_ROI_EVIDENCE = "roi_evidence"
NODE_TYPE_PRECONDITION = "precondition"
NODE_TYPE_ACTION_INTENT = "action_intent"
NODE_TYPE_INPUT_LEASE = "input_lease"
NODE_TYPE_ACTUATION_RESULT = "actuation_result"
NODE_TYPE_VERIFIER_CONTRACT = "verifier_contract"
NODE_TYPE_VERIFIER_RESULT = "verifier_result"
NODE_TYPE_INTERRUPT = "interrupt"
NODE_TYPE_RECOVERY = "recovery"
NODE_TYPE_SKILL_RESULT = "skill_result"
NODE_TYPE_MISSION_NODE_RESULT = "mission_node_result"
NODE_TYPE_FAILURE_SIGNATURE = "failure_signature"
NODE_TYPE_PATCH_PROPOSAL = "patch_proposal"
NODE_TYPE_BENCHMARK_RESULT = "benchmark_result"

# ---------------------------------------------------------------------------
# Edge type constants
# ---------------------------------------------------------------------------
EDGE_DERIVED_FROM = "DERIVED_FROM"
EDGE_SATISFIES = "SATISFIES"
EDGE_AUTHORIZES = "AUTHORIZES"
EDGE_LEASED_AS = "LEASED_AS"
EDGE_RESULTED_IN = "RESULTED_IN"
EDGE_VERIFIED_BY = "VERIFIED_BY"
EDGE_FAILED_WITH = "FAILED_WITH"
EDGE_RECOVERED_BY = "RECOVERED_BY"
EDGE_PATCHED_BY = "PATCHED_BY"
EDGE_BENCHMARKED_BY = "BENCHMARKED_BY"

# ---------------------------------------------------------------------------
# Aggregate lists for quick membership checks
# ---------------------------------------------------------------------------
ALL_NODE_TYPES: list[str] = [v for k, v in sorted(globals().items()) if k.startswith("NODE_TYPE_")]
ALL_EDGE_TYPES: list[str] = [v for k, v in sorted(globals().items()) if k.startswith("EDGE_")]
