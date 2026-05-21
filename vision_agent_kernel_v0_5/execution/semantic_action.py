from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ActionKind = Literal["ui", "navigation", "combat", "system"]
RiskLevel = Literal["low", "medium", "high", "human_confirm"]


@dataclass(frozen=True, slots=True)
class SemanticAction:
    action_id: str
    kind: ActionKind
    intent: str
    target: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    requires_physical_input: bool = False


@dataclass(frozen=True, slots=True)
class ActionContract:
    action_id: str
    semantic_action: SemanticAction
    preconditions: list[str] = field(default_factory=list)
    execution_policy: dict[str, Any] = field(default_factory=dict)
    safety_policy: dict[str, Any] = field(default_factory=dict)
    expected_state_delta: dict[str, Any] = field(default_factory=dict)
    verifier_contract: dict[str, Any] = field(default_factory=dict)
    fallback_policy: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 1000
    risk_level: RiskLevel = "medium"
    evidence_links: list[str] = field(default_factory=list)

    @property
    def is_physical(self) -> bool:
        return self.semantic_action.requires_physical_input


@dataclass(frozen=True, slots=True)
class ContractValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


class ActionContractValidator:
    """Reject contracts that collapse high-level intent into unsafe raw input."""

    def validate(self, contract: ActionContract, strict_mode: bool = True) -> ContractValidationResult:
        errors: list[str] = []
        action = contract.semantic_action
        if contract.timeout_ms <= 0:
            errors.append("timeout_ms must be positive")
        if action.kind == "ui" and action.intent in {"click_anchor", "click_text", "select_list_item"} and not action.target:
            errors.append(f"{action.intent} requires a semantic target")
        if action.kind == "ui" and {"x", "y"} <= set(action.parameters) and not action.parameters.get("anchor_id"):
            errors.append("UI actions must not expose raw x/y coordinates without anchor_id")
        if action.requires_physical_input:
            if not contract.safety_policy.get("require_focus", False):
                errors.append("physical action requires safety_policy.require_focus=true")
            if not contract.safety_policy.get("input_lease_required", False):
                errors.append("physical action requires input_lease_required=true")
            if int(contract.safety_policy.get("max_lease_ms", 0)) <= 0:
                errors.append("physical action requires bounded max_lease_ms")
        if strict_mode:
            if not contract.verifier_contract.get("verifier_id"):
                errors.append("strict mode requires verifier_contract.verifier_id")
            if contract.risk_level in {"high", "human_confirm"} and not contract.fallback_policy:
                errors.append("high risk action requires fallback_policy")
        return ContractValidationResult(ok=not errors, errors=errors)


def click_anchor_action(action_id: str, anchor_id: str, timeout_ms: int = 1500) -> ActionContract:
    action = SemanticAction(
        action_id=action_id,
        kind="ui",
        intent="click_anchor",
        target=anchor_id,
        parameters={"anchor_id": anchor_id},
        requires_physical_input=True,
    )
    return ActionContract(
        action_id=action_id,
        semantic_action=action,
        safety_policy={"require_focus": True, "input_lease_required": True, "max_lease_ms": 250},
        verifier_contract={"verifier_id": f"{anchor_id}_post_click", "success_criteria": ["screen_state_changed"]},
        fallback_policy={"on_not_found": "fallback_visual_agent", "on_no_effect": "retry_once"},
        timeout_ms=timeout_ms,
        risk_level="low",
    )
