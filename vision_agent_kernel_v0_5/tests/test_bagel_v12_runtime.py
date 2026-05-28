from __future__ import annotations

import pytest

from bagel.evidence_matrix import EvidenceMatrix, EvidenceSignal
from bagel.feedback_shift import discrete_tvd, single_probe_ifs
from bagel.fig_schema import (
    ActionNode,
    BeliefNode,
    CausalBridgeNode,
    CondensedNode,
    FeedbackNode,
    FalsifiableInterventionGraph,
)
from bagel.omitted_belief import ConstrainedVerbalizer, ExtractInvariantSym
from bagel.probe_policy import ProbePolicy
from bagel.runtime import BagelRuntime


def _belief(bid: str = "b1", lifecycle: str = "committed") -> BeliefNode:
    return BeliefNode(
        belief_id=bid,
        target_object="quest objective",
        causal_role="objective_type_hypothesis",
        hypothesis="objective is dialogue",
        falsification_condition="dialogue overlay absent",
        lifecycle=lifecycle,
    )


def test_feedback_shift_single_probe_and_tvd() -> None:
    single = single_probe_ifs(
        belief_id="b1",
        before_failure="failed",
        after_failure="passed",
        signal_quality=0.8,
    )
    assert single.attributed
    assert single.ifs_score == pytest.approx(0.8)

    multi = discrete_tvd(
        belief_id="b1",
        before=["failed", "failed", "passed"],
        after=["passed", "passed", "passed"],
    )
    assert multi.tvd_score > 0


def test_bounded_evidence_bonus_does_not_explode_for_hub_belief() -> None:
    matrix = EvidenceMatrix(alpha=0.1)
    for i in range(200):
        matrix.add_signal(EvidenceSignal(f"neutral_{i}", "hub", "neutral", 1.0))
    matrix.add_signal(EvidenceSignal("refute", "hub", "refute", 0.7))
    score = matrix.score_belief("hub")
    assert score.bounded_density_bonus <= 0.1
    assert score.score < 0


def test_non_decidable_probe_degrades_probe_family_not_belief() -> None:
    policy = ProbePolicy(non_decidable_limit=2)
    probe = policy._create_probe(_belief("b_probe"))
    assert probe is not None

    first = policy.degrade_non_decidable(probe, "timeout")
    second = policy.degrade_non_decidable(probe, "timeout")

    assert first.state == "non_decidable_once"
    assert second.state == "undecidable_cluster"
    assert policy.is_probe_family_taboo(second.taboo_probe_family)


def test_runtime_delayed_feedback_bridge_and_condensation() -> None:
    runtime = BagelRuntime()
    runtime.commit_belief(_belief("b_old", lifecycle="confirmed"))
    runtime.propose_action(ActionNode("a_old", ("b_old",), "gui_action", claim_id="claim_1"))
    runtime.receive_feedback(FeedbackNode("y_late", "a_old", "negative", signal_quality=0.9))

    bridge = runtime.register_causal_bridge(CausalBridgeNode(
        bridge_id="cb_1",
        from_feedback="y_late",
        to_belief="b_old",
        bridge_type="contract_continuity",
        evidence=("same_quest_objective_contract",),
        weight=0.6,
    ))
    # Temporal decay makes score slightly < 0.6; allow margin
    assert runtime.score_delayed_feedback(bridge) == pytest.approx(0.6, abs=0.01)

    condensed = runtime.condense_stable_subgraph(("b_old",), {"summary": "stable dialog contract"})
    assert condensed is not None
    assert runtime.expand_condensed_node(condensed.condensed_id) == ("b_old",)


def test_snapshot_isolation_blocks_jit_regeneration() -> None:
    runtime = BagelRuntime()
    runtime.commit_belief(_belief("b1"))
    runtime.propose_action(ActionNode("a1", ("b1",), "gui_action", status="aborted"))
    runtime.freeze_attribution_snapshot()

    blocked = runtime.jit_regenerate_stale_action("a1")
    assert not blocked.allowed
    assert blocked.reason == "attribution_snapshot_frozen"

    runtime.commit_attribution_decision()
    runtime.enter_execution_phase()
    allowed = runtime.jit_regenerate_stale_action("a1")
    assert allowed.allowed


def test_neuro_symbolic_omitted_belief_uses_only_anchored_invariants() -> None:
    extractor = ExtractInvariantSym(max_candidates=5)
    invariants = extractor.extract([
        {
            "source": "ui_anchor",
            "anchor": "screen:dialogue.choice_1",
            "symbol": "dialogue.choice_1.visible",
            "operator": "==",
            "constraint": "true",
        },
        {
            "source": "free_llm_guess",
            "anchor": "none",
            "symbol": "invented",
            "operator": "==",
            "constraint": "true",
        },
    ])
    assert len(invariants) == 1

    candidate = ConstrainedVerbalizer().verbalize(invariants[0])
    assert candidate.belief.metadata["trace_anchor"] == "screen:dialogue.choice_1"
    assert candidate.belief.lifecycle == "challenged"
