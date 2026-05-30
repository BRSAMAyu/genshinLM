from __future__ import annotations

from bagel.evidence_matrix import EvidenceMatrix, EvidenceSignal, ThresholdGatedFusion
from bagel.fig_schema import ActionNode, BeliefNode, FalsifiableInterventionGraph
from bagel.lazy_evaluation import LazyEvaluationBudget, assess_fig_overhead, should_trigger_high_order_audit
from bagel.metrics import AttributionMetrics, BagelThreeLayerMetrics, RepairMetrics, RevisionMetrics
from bagel.proxy_intervention import ProxyInterventionContract, mutate_for_attribution, mutate_for_repair
from bagel.safe_revision import SafeRevisionEngine


def _belief(belief_id: str) -> BeliefNode:
    return BeliefNode(
        belief_id=belief_id,
        target_object="objective",
        causal_role="localization",
        hypothesis="objective is dialogue",
        falsification_condition="dialogue verifier fails",
    )


def test_exploratory_probe_cannot_enter_hard_falsification() -> None:
    matrix = EvidenceMatrix()
    matrix.add_signal(EvidenceSignal(
        signal_id="s1",
        belief_id="b1",
        polarity="refute",
        weight=1.0,
        is_core_probe=True,
        subtype="exploratory",
        hard_falsification=True,
    ))
    score = matrix.score_belief("b1")
    assert score.score < 0
    assert not score.core_contradiction


def test_claim_falsifying_probe_can_be_decisive() -> None:
    matrix = EvidenceMatrix(core_probe_veto_threshold=0.8)
    matrix.add_signal(EvidenceSignal(
        signal_id="s1",
        belief_id="b1",
        polarity="refute",
        weight=0.9,
        is_core_probe=True,
        subtype="claim_falsifying",
        hard_falsification=True,
    ))
    score = matrix.score_belief("b1")
    assert score.core_contradiction
    assert ThresholdGatedFusion().state(score.score) == "decisive"


def test_attribution_rank_is_separate_from_repair_priority() -> None:
    matrix = EvidenceMatrix()
    matrix.add_signal(EvidenceSignal("s1", "b1", "refute", weight=0.8, subtype="discriminative"))
    score = matrix.score_belief("b1")
    rank = matrix.attribution_rank()[0]
    priority = matrix.repair_priority(score, residual_risk=0.4, estimated_cost=2.0, reversibility=0.8)

    assert rank.belief_id == "b1"
    assert rank.score == score.score
    assert priority.belief_id == "b1"
    assert priority.priority < max(0.0, -score.score)


def test_proxy_intervention_splits_attribution_and_repair_modes() -> None:
    attribution = ProxyInterventionContract(
        belief_id="b1",
        replacement_hypothesis="objective is combat",
        frozen_context_ref="fig:v1",
        allowed_scope=("mission_node:n1",),
        mutation_mode="attribution",
        max_scope_delta=0,
    )
    accepted = mutate_for_attribution(attribution, ("mission_node:n1",), feedback_shift=0.5)
    rejected = mutate_for_attribution(attribution, ("mission_node:n1", "mission_node:n2"), feedback_shift=0.5)
    assert accepted.accepted
    assert not rejected.accepted

    repair = ProxyInterventionContract(
        belief_id="b1",
        replacement_hypothesis="objective is combat",
        frozen_context_ref="fig:v2",
        allowed_scope=("skill:approach",),
        mutation_mode="repair",
    )
    assert mutate_for_repair(repair, ("skill:approach",)).accepted


def test_safe_revision_uses_verification_adjusted_residual_risk() -> None:
    fig = FalsifiableInterventionGraph()
    fig.commit_belief(_belief("hub"))
    for i in range(8):
        fig.propose_action(ActionNode(f"a{i}", ("hub",), "gui_action", claim_id=f"claim_{i}"))

    weak = SafeRevisionEngine(kappa=0.5, max_impact=10, verification_quality_default=0.1)
    strong = SafeRevisionEngine(kappa=0.5, max_impact=10, verification_quality_default=0.9)
    weak_report = weak.assess_cascade(fig, "hub")
    strong_report = strong.assess_cascade(fig, "hub")

    assert strong_report.cascade_risk == weak_report.cascade_risk
    assert strong_report.residual_risk < weak_report.residual_risk


def test_lazy_evaluation_budget_blocks_high_order_audit_until_shift_is_significant() -> None:
    budget = LazyEvaluationBudget(active_frontier_max=2, high_order_audit_min_shift=0.4)
    assert not should_trigger_high_order_audit(0.39, budget=budget)
    assert should_trigger_high_order_audit(0.4, budget=budget)

    report = assess_fig_overhead(active_nodes=2, frontier_nodes=3, total_nodes=10, budget=budget)
    assert report.gamma_fig == 0.5
    assert not report.within_budget


def test_metrics_keep_attribution_revision_and_repair_disjoint() -> None:
    metrics = BagelThreeLayerMetrics(
        attribution=AttributionMetrics(top1_attribution_accuracy=1.0),
        revision=RevisionMetrics(safe_revision_rate=0.5),
        repair=RepairMetrics(final_repair_success_rate=0.25),
    )
    assert metrics.attribution.top1_attribution_accuracy == 1.0
    assert metrics.revision.safe_revision_rate == 0.5
    assert metrics.repair.final_repair_success_rate == 0.25
