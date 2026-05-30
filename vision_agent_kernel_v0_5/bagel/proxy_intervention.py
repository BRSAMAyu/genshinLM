"""BAGEL v2.1 context-bounded proxy intervention contracts.

The runtime cannot perform a literal causal do-intervention on an LLM. It can
only ask a model or local mutator to alter a bounded proxy slice while keeping
the rest of the context stable. This module makes that contract explicit and
keeps attribution mutation separate from repair mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MutationMode = Literal["attribution", "repair"]


@dataclass(frozen=True, slots=True)
class ProxyInterventionContract:
    belief_id: str
    replacement_hypothesis: str
    frozen_context_ref: str
    allowed_scope: tuple[str, ...]
    disallowed_scope: tuple[str, ...] = ()
    mutation_mode: MutationMode = "attribution"
    fidelity_checks: tuple[str, ...] = ()
    max_scope_delta: int = 1

    def validate(self) -> None:
        if not self.belief_id:
            raise ValueError("belief_id is required")
        if not self.replacement_hypothesis:
            raise ValueError("replacement_hypothesis is required")
        if not self.frozen_context_ref:
            raise ValueError("frozen_context_ref is required")
        if not self.allowed_scope:
            raise ValueError("allowed_scope must be non-empty")
        overlap = set(self.allowed_scope) & set(self.disallowed_scope)
        if overlap:
            raise ValueError(f"scope cannot be both allowed and disallowed: {sorted(overlap)}")
        if self.max_scope_delta < 0:
            raise ValueError("max_scope_delta must be non-negative")


@dataclass(frozen=True, slots=True)
class ProxyInterventionResult:
    belief_id: str
    mutation_mode: MutationMode
    touched_scope: tuple[str, ...]
    fidelity_ok: bool
    scope_delta: int
    feedback_shift: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.fidelity_ok and self.scope_delta >= 0


def evaluate_proxy_result(
    contract: ProxyInterventionContract,
    touched_scope: tuple[str, ...],
    *,
    feedback_shift: float = 0.0,
    diagnostics: dict[str, Any] | None = None,
) -> ProxyInterventionResult:
    """Validate a bounded proxy mutation result against its contract."""
    contract.validate()
    allowed = set(contract.allowed_scope)
    disallowed = set(contract.disallowed_scope)
    touched = set(touched_scope)
    out_of_scope = touched - allowed
    forbidden = touched & disallowed
    scope_delta = len(out_of_scope) + len(forbidden)
    fidelity_ok = scope_delta <= contract.max_scope_delta and not forbidden
    return ProxyInterventionResult(
        belief_id=contract.belief_id,
        mutation_mode=contract.mutation_mode,
        touched_scope=tuple(sorted(touched)),
        fidelity_ok=fidelity_ok,
        scope_delta=scope_delta,
        feedback_shift=feedback_shift,
        diagnostics=diagnostics or {},
    )


def mutate_for_attribution(
    contract: ProxyInterventionContract,
    touched_scope: tuple[str, ...],
    *,
    feedback_shift: float = 0.0,
) -> ProxyInterventionResult:
    if contract.mutation_mode != "attribution":
        raise ValueError("MutateForAttribution requires mutation_mode='attribution'")
    return evaluate_proxy_result(contract, touched_scope, feedback_shift=feedback_shift)


def mutate_for_repair(
    contract: ProxyInterventionContract,
    touched_scope: tuple[str, ...],
    *,
    feedback_shift: float = 0.0,
) -> ProxyInterventionResult:
    if contract.mutation_mode != "repair":
        raise ValueError("MutateForRepair requires mutation_mode='repair'")
    return evaluate_proxy_result(contract, touched_scope, feedback_shift=feedback_shift)
