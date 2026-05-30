"""BAGEL — Belief-Action Graph with Evidence Ledger.

BAGEL solves "failure attribution": given a failed mission node, which
*intervenable belief* caused the failure, and how should it be safely revised?

Claim Runtime answers "did the world change as claimed?"
BAGEL answers "which belief drove the action, and was it wrong?"
"""

from bagel.lazy_evaluation import LazyEvaluationBudget, should_trigger_high_order_audit
from bagel.metrics import AttributionMetrics, BagelThreeLayerMetrics, RepairMetrics, RevisionMetrics
from bagel.proxy_intervention import ProxyInterventionContract, mutate_for_attribution, mutate_for_repair

__all__ = [
    "AttributionMetrics",
    "BagelThreeLayerMetrics",
    "LazyEvaluationBudget",
    "ProxyInterventionContract",
    "RepairMetrics",
    "RevisionMetrics",
    "mutate_for_attribution",
    "mutate_for_repair",
    "should_trigger_high_order_audit",
]
