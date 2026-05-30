"""BAGEL v2.1 lazy evaluation and active frontier budgeting."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LazyEvaluationBudget:
    active_frontier_max: int = 128
    high_order_audit_min_shift: float = 0.25
    entropy_stall_patience: int = 3
    max_revision_loops: int = 5
    max_regressions: int = 2

    def validate(self) -> None:
        if self.active_frontier_max <= 0:
            raise ValueError("active_frontier_max must be positive")
        if not 0.0 <= self.high_order_audit_min_shift <= 1.0:
            raise ValueError("high_order_audit_min_shift must be in [0, 1]")
        if self.entropy_stall_patience < 0 or self.max_revision_loops < 0 or self.max_regressions < 0:
            raise ValueError("budget counters must be non-negative")


@dataclass(frozen=True, slots=True)
class FigOverheadReport:
    active_nodes: int
    frontier_nodes: int
    total_nodes: int
    gamma_fig: float
    within_budget: bool


def assess_fig_overhead(
    *,
    active_nodes: int,
    frontier_nodes: int,
    total_nodes: int,
    budget: LazyEvaluationBudget | None = None,
) -> FigOverheadReport:
    b = budget or LazyEvaluationBudget()
    b.validate()
    safe_total = max(total_nodes, 1)
    gamma = (active_nodes + frontier_nodes) / safe_total
    return FigOverheadReport(
        active_nodes=active_nodes,
        frontier_nodes=frontier_nodes,
        total_nodes=total_nodes,
        gamma_fig=gamma,
        within_budget=frontier_nodes <= b.active_frontier_max,
    )


def should_trigger_high_order_audit(
    feedback_shift: float,
    *,
    budget: LazyEvaluationBudget | None = None,
) -> bool:
    b = budget or LazyEvaluationBudget()
    b.validate()
    return abs(feedback_shift) >= b.high_order_audit_min_shift
