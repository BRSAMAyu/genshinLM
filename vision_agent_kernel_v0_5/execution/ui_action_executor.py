from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from core.types import InputLease
from evidence.evidence_graph import EvidenceGraph
from evidence.evidence_nodes import (
    EDGE_DERIVED_FROM,
    EDGE_LEASED_AS,
    EDGE_RESULTED_IN,
    NODE_TYPE_ACTION_INTENT,
    NODE_TYPE_ACTUATION_RESULT,
    NODE_TYPE_INPUT_LEASE,
    NODE_TYPE_OBSERVATION,
    EvidenceNode,
)
from execution.input_worker import InputWorker
from execution.mouse_motor import ClickReceipt, MousePathPolicy, mouse_policy_for_action_family
from execution.physical_receipt import PhysicalActionReceipt
from interaction.ui_anchor import ClickResult, UIAnchor, UIAnchorResolver, UIElement
from perception.observation_graph import ObservationGraph
from runtime.claim_runtime import ObservationClaim, StateDeltaClaim
from runtime.claim_worker import ClaimGraphCommand, ClaimGraphCommandResult, ClaimGraphWorker


@dataclass(frozen=True, slots=True)
class UIExecutionConfig:
    dry_run: bool = True
    require_confirmation: bool = False
    max_click_lease_ms: int = 120
    owner: str = "ui_anchor_executor"
    mouse_policy: MousePathPolicy | None = None
    current_mouse_position: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class UIExecutionResult:
    click_result: ClickResult
    evidence_ids: list[str] = field(default_factory=list)
    click_receipt: ClickReceipt | None = None
    physical_receipts: list[PhysicalActionReceipt] = field(default_factory=list)
    claim_result: ClaimGraphCommandResult | None = None


class UIAnchorActionExecutor:
    """Execute UI anchor actions through dry-run or InputWorker-safe path."""

    def __init__(
        self,
        resolver: UIAnchorResolver | None = None,
        input_worker: InputWorker | None = None,
        evidence_graph: EvidenceGraph | None = None,
    ) -> None:
        self._resolver = resolver or UIAnchorResolver()
        self._input_worker = input_worker
        self._graph = evidence_graph or EvidenceGraph()

    @property
    def evidence_graph(self) -> EvidenceGraph:
        return self._graph

    def click_anchor(
        self,
        anchor: UIAnchor,
        observation_graph: ObservationGraph,
        elements: list[UIElement] | None = None,
        config: UIExecutionConfig | None = None,
    ) -> UIExecutionResult:
        cfg = config or UIExecutionConfig()
        resolved = self._resolver.resolve(
            anchor,
            elements if elements is not None else observation_graph.ui_elements(),
            observation_graph.viewport,
            screen_state=observation_graph.screen_state(),
        )
        if self._graph.get_node(observation_graph.graph_id) is None:
            self._graph.add_node(
                EvidenceNode(
                    node_id=observation_graph.graph_id,
                    node_type=NODE_TYPE_OBSERVATION,
                    created_at=observation_graph.created_at,
                    payload=observation_graph.evidence_summary(),
                )
            )
        action_id = f"action:{anchor.anchor_id}:{uuid.uuid4()}"
        action_node = EvidenceNode(
            node_id=action_id,
            node_type=NODE_TYPE_ACTION_INTENT,
            created_at=time.time(),
            payload={
                "intent": "click_anchor",
                "anchor_id": anchor.anchor_id,
                "screen_state": anchor.screen_state,
                "resolution": {
                    "ok": resolved.ok,
                    "confidence": resolved.confidence,
                    "strategy": resolved.strategy,
                    "reason": resolved.reason,
                    "click_point": resolved.click_point,
                },
            },
        )
        self._graph.add_node(action_node)
        self._graph.add_edge(observation_graph.graph_id, action_id, EDGE_DERIVED_FROM)

        if not resolved.ok or resolved.requires_confirmation or resolved.click_point is None:
            status = "BLOCKED_LOW_CONFIDENCE" if resolved.requires_confirmation else "BLOCKED_NOT_FOUND"
            return UIExecutionResult(
                ClickResult(
                    anchor_id=anchor.anchor_id,
                    status=status,
                    resolution=resolved,
                    verifier_id=anchor.post_action_verifier,
                    evidence_ids=[action_id],
                    failure_code=resolved.reason,
                ),
                [action_id],
            )

        lease_id = f"lease:{uuid.uuid4()}"
        mouse_policy = cfg.mouse_policy or mouse_policy_for_action_family("ui_click", dry_run=cfg.dry_run)
        mouse_path = mouse_policy.build_path(cfg.current_mouse_position, resolved.click_point)
        click_receipt = ClickReceipt(
            anchor_id=anchor.anchor_id,
            click_point=resolved.click_point,
            path=mouse_path,
            pre_click_frame_id=observation_graph.frame_id,
            coordinate_space="viewport_px",
            evidence_ids=[action_id],
        )
        lease_node = EvidenceNode(
            node_id=lease_id,
            node_type=NODE_TYPE_INPUT_LEASE,
            created_at=time.time(),
            payload={
                "owner": cfg.owner,
                "anchor_id": anchor.anchor_id,
                "click_point": resolved.click_point,
                "dry_run": cfg.dry_run,
                "max_click_lease_ms": cfg.max_click_lease_ms,
                "mouse_path": {
                    "mode": mouse_path.mode,
                    "points": mouse_path.points,
                    "duration_ms": mouse_path.duration_ms,
                    "coordinate_space": mouse_path.coordinate_space,
                },
            },
        )
        self._graph.add_node(lease_node)
        self._graph.add_edge(action_id, lease_id, EDGE_LEASED_AS)
        now = time.perf_counter()
        lease = InputLease(
            lease_id=lease_id,
            owner=cfg.owner,
            priority=30,
            key_states={"mouse_left": "DOWN"},
            mouse_delta=None,
            created_at=now,
            expires_at=now + cfg.max_click_lease_ms / 1000.0,
            reason=f"click_anchor:{anchor.anchor_id}",
        )
        receipt_status = "dry_run" if cfg.dry_run else "accepted"
        physical_receipt = PhysicalActionReceipt.from_lease(
            lease,
            status=receipt_status,
            backend="dry-run" if cfg.dry_run else self._input_worker.backend.__class__.__name__ if self._input_worker else "unknown",
            action_family="ui_click",
            evidence_ids=[lease_id],
            metadata={"click_point": resolved.click_point, "mouse_path_points": mouse_path.points},
        )
        if not cfg.dry_run:
            if self._input_worker is None:
                raise RuntimeError("safe-window UI execution requires InputWorker")
            self._input_worker.submit_lease(lease)

        result_id = f"actuation:{uuid.uuid4()}"
        result_node = EvidenceNode(
            node_id=result_id,
            node_type=NODE_TYPE_ACTUATION_RESULT,
            created_at=time.time(),
            payload={
                "status": "EXECUTED",
                "anchor_id": anchor.anchor_id,
                "dry_run": cfg.dry_run,
                "receipt_id": physical_receipt.receipt_id,
            },
        )
        self._graph.add_node(result_node)
        self._graph.add_edge(lease_id, result_id, EDGE_RESULTED_IN)
        evidence_ids = [action_id, lease_id, result_id]
        return UIExecutionResult(
            ClickResult(
                anchor_id=anchor.anchor_id,
                status="EXECUTED",
                resolution=resolved,
                verifier_id=anchor.post_action_verifier,
                evidence_ids=evidence_ids,
            ),
            evidence_ids,
            click_receipt,
            [physical_receipt],
        )

    def click_anchor_with_claim(
        self,
        anchor: UIAnchor,
        observation_graph: ObservationGraph,
        *,
        claim: StateDeltaClaim,
        claim_worker: ClaimGraphWorker,
        elements: list[UIElement] | None = None,
        config: UIExecutionConfig | None = None,
    ) -> UIExecutionResult:
        """Execute a UI anchor action and route its result into ClaimGraphWorker.

        The click itself is only an actuation claim. The caller must still attach
        post-action screen/inventory/navigation verifiers for terminal success.
        """
        click = self.click_anchor(anchor, observation_graph, elements=elements, config=config)
        claim_worker.submit(ClaimGraphCommand("add_claim", claim=claim))
        polarity = "support" if click.click_result.status == "EXECUTED" else "refute"
        quality = click.click_result.resolution.confidence if click.click_result.resolution else 0.0
        obs = ObservationClaim(
            observation_id=f"obs:{claim.claim_id}:ui_click",
            claim_id=claim.claim_id,
            source_family="ui_action",
            polarity=polarity,
            signal_quality=quality,
            frame_id=observation_graph.frame_id,
            graph_node_refs=click.evidence_ids,
            verifier_id="ui_anchor_action_executor",
            confidence=quality,
            metadata={
                "click_status": click.click_result.status,
                "anchor_id": anchor.anchor_id,
                "post_action_verifier": anchor.post_action_verifier,
                "freshness": 1.0,
            },
        )
        claim_worker.submit(ClaimGraphCommand("add_observation", observation=obs))
        adjudication = claim_worker.submit(ClaimGraphCommand("adjudicate", claim_id=claim.claim_id))
        return UIExecutionResult(
            click.click_result,
            click.evidence_ids,
            click.click_receipt,
            click.physical_receipts,
            adjudication,
        )
