from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from execution.physical_receipt import PhysicalActionReceipt
from execution.semantic_action import SemanticAction
from perception.observation_graph import ObservationGraph


@dataclass(frozen=True, slots=True)
class ControllerContext:
    observation_graph: ObservationGraph | None = None
    active_capsule_id: str = "core"
    profile_id: str = ""
    state: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ControllerResult:
    controller_id: str
    status: str
    action_id: str
    receipts: list[PhysicalActionReceipt] = field(default_factory=list)
    verifier_request: dict[str, object] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    recoverable: bool = True
    failure_code: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class ControllerSkip:
    controller_id: str
    reason: str = "can_handle_false"


@dataclass(frozen=True, slots=True)
class ControllerRouteTrace:
    action_id: str
    selected_controller: str
    skipped: list[ControllerSkip] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ambiguous_matches: list[str] = field(default_factory=list)


class Controller(Protocol):
    controller_id: str

    def can_handle(self, action: SemanticAction, context: ControllerContext) -> bool:
        ...

    def execute(self, action: SemanticAction, context: ControllerContext) -> ControllerResult:
        ...


class ControllerRouter:
    """Route semantic actions to controllers with deterministic skip semantics.

    `can_handle() == False` is an explicit skip, not a controller failure. A
    controller that cannot handle an action must not report failure upward; it is
    simply ignored. Router-level failure only happens when no controller accepts
    the action, or when a controller raises while being probed.
    """

    def __init__(self, controllers: list[Controller]) -> None:
        self._controllers = list(controllers)
        self.last_trace: ControllerRouteTrace | None = None

    def route(self, action: SemanticAction, context: ControllerContext) -> Controller:
        controller, trace = self.route_with_trace(action, context)
        self.last_trace = trace
        return controller

    def route_with_trace(self, action: SemanticAction, context: ControllerContext) -> tuple[Controller, ControllerRouteTrace]:
        matches: list[Controller] = []
        skipped: list[ControllerSkip] = []
        errors: list[str] = []
        for controller in self._controllers:
            controller_id = getattr(controller, "controller_id", controller.__class__.__name__)
            try:
                if controller.can_handle(action, context):
                    matches.append(controller)
                else:
                    skipped.append(ControllerSkip(controller_id))
            except Exception as exc:  # pragma: no cover - message is asserted in tests
                errors.append(f"{controller_id}:{exc.__class__.__name__}:{exc}")
        if not matches:
            detail = ", ".join([skip.controller_id for skip in skipped] + errors)
            raise LookupError(f"no controller can handle action {action.kind}:{action.intent}; probed={detail}")
        selected = matches[0]
        selected_id = getattr(selected, "controller_id", selected.__class__.__name__)
        trace = ControllerRouteTrace(
            action_id=action.action_id,
            selected_controller=selected_id,
            skipped=skipped,
            errors=errors,
            ambiguous_matches=[getattr(controller, "controller_id", controller.__class__.__name__) for controller in matches[1:]],
        )
        return selected, trace


ConfirmationReason = Literal["none", "low_confidence", "high_risk", "fallback_visual_agent", "unsafe_boundary"]


@dataclass(frozen=True, slots=True)
class ConfirmationDecision:
    required: bool
    reason: ConfirmationReason = "none"
    confidence: float = 1.0
    risk_level: str = "low"


@dataclass(frozen=True, slots=True)
class HumanConfirmationPolicy:
    """Central CP-1/CP-2 thresholds for user confirmation.

    CP-1: low confidence actions require confirmation before physical input.
    CP-2: high-risk or fallback visual-agent actions require confirmation even
    when the candidate is otherwise well formed.
    """

    low_confidence_threshold: float = 0.75
    risky_levels: frozenset[str] = frozenset({"high", "human_confirm"})

    def decide(
        self,
        *,
        confidence: float,
        risk_level: str = "low",
        is_fallback_visual_agent: bool = False,
        boundary_valid: bool = True,
    ) -> ConfirmationDecision:
        if not boundary_valid:
            return ConfirmationDecision(True, "unsafe_boundary", confidence, risk_level)
        if is_fallback_visual_agent:
            return ConfirmationDecision(True, "fallback_visual_agent", confidence, risk_level)
        if risk_level in self.risky_levels:
            return ConfirmationDecision(True, "high_risk", confidence, risk_level)
        if confidence < self.low_confidence_threshold:
            return ConfirmationDecision(True, "low_confidence", confidence, risk_level)
        return ConfirmationDecision(False, "none", confidence, risk_level)
