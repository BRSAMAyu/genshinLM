from __future__ import annotations

import time
import uuid

from core.events import Interrupt
from core.state_bus import StateBus
from core.types import Observation
from evidence.evidence_store import EvidenceStore
from evidence.evidence_nodes import (
    NODE_TYPE_INTERRUPT,
    NODE_TYPE_PRECONDITION,
    NODE_TYPE_VERIFIER_RESULT,
    EDGE_AUTHORIZES,
    EDGE_VERIFIED_BY,
)
from reflex.danger_clear_verifier import DangerClearVerifier
from reflex.preemption_token import PreemptionToken
from reflex.resume_contract import ResumeContract
from execution.verifier_base import VerifierContext


class ReflexScheduler:
    """Core reflex scheduler that monitors danger levels and orchestrates the
    Verified Reflex Resume Gauntlet.

    Workflow:
    1. :meth:`check_danger` reads the danger score from the latest observation.
       If it exceeds the threshold (and cooldown has elapsed), a
       :class:`PreemptionToken` is created and a ``DODGE_REFLEX`` interrupt is
       published to the :class:`StateBus`.
    2. After the dodge maneuver, :meth:`verify_danger_cleared` runs the
       :class:`DangerClearVerifier`. If the danger is verified clear, a
       :class:`ResumeContract` is created and marked ``SATISFIED``.
    """

    def __init__(
        self,
        state_bus: StateBus,
        evidence_store: EvidenceStore | None = None,
        danger_threshold: float = 0.7,
        cooldown_seconds: float = 1.0,
    ) -> None:
        self._state_bus = state_bus
        self._evidence_store = evidence_store
        self._danger_threshold = danger_threshold
        self._cooldown_seconds = cooldown_seconds
        self._last_interrupt_time: float = 0.0
        self._active_token: PreemptionToken | None = None
        self._verifier = DangerClearVerifier(danger_threshold=0.15)

    # -- public API -----------------------------------------------------------

    def check_danger(self, observation: Observation) -> PreemptionToken | None:
        """Check if danger threshold is crossed.

        Returns a :class:`PreemptionToken` if a new interrupt was published,
        or ``None`` if no action is needed (danger below threshold, within
        cooldown, or an active preemption is already in flight).
        """
        now = time.perf_counter()

        # Cooldown guard
        if now - self._last_interrupt_time < self._cooldown_seconds:
            return None

        # Already have an active preemption — do not re-issue
        if self._active_token is not None:
            return None

        danger_score = self._read_danger_score(observation)
        if danger_score is None:
            return None

        if danger_score < self._danger_threshold:
            return None

        # --- Danger detected: create preemption token and publish interrupt ---
        interrupt_id = uuid.uuid4().hex
        token_id = uuid.uuid4().hex

        token = PreemptionToken(
            token_id=token_id,
            interrupted_action_id=None,
            interrupted_skill_id=None,
            checkpoint_id=None,
            reason="DANGER_DETECTED",
            interrupt_id=interrupt_id,
            created_at=now,
            expires_at=now + 5.0,
        )
        self._active_token = token

        interrupt = Interrupt(
            priority=20,  # P2 — tracking priority level for dodge reflex
            timestamp=now,
            code="DODGE_REFLEX",
            source="reflex_scheduler",
            frame_id=observation.frame_id,
            payload={
                "danger_score": danger_score,
                "token_id": token_id,
            },
            recoverable=True,
            requires_input_release=True,
        )

        self._state_bus.publish_interrupt(interrupt)
        self._last_interrupt_time = now

        # Record evidence
        if self._evidence_store is not None:
            int_node = self._evidence_store.record_node(
                NODE_TYPE_INTERRUPT,
                {
                    "interrupt_id": interrupt_id,
                    "code": "DODGE_REFLEX",
                    "danger_score": danger_score,
                    "frame_id": observation.frame_id,
                },
            )
            pre_node = self._evidence_store.record_node(
                NODE_TYPE_PRECONDITION,
                {
                    "token_id": token_id,
                    "reason": "DANGER_DETECTED",
                    "danger_score": danger_score,
                    "threshold": self._danger_threshold,
                },
            )
            self._evidence_store.record_edge(
                pre_node.node_id, int_node.node_id, EDGE_AUTHORIZES
            )

        return token

    def verify_danger_cleared(self, observation: Observation) -> ResumeContract | None:
        """After a dodge maneuver, verify that danger has cleared.

        Returns a :class:`ResumeContract` if the danger is verified cleared
        and the active preemption token is consumed. Returns ``None`` if danger
        persists or there is no active preemption.
        """
        if self._active_token is None:
            return None

        # Build verifier context from the observation
        ctx = VerifierContext(
            state={},
            observation=observation,
        )

        result = self._verifier.verify(ctx)

        # Record verifier result as evidence
        if self._evidence_store is not None:
            vr_node = self._evidence_store.record_node(
                NODE_TYPE_VERIFIER_RESULT,
                {
                    "verifier_id": result.verifier_id,
                    "ok": result.ok,
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "evidence": result.evidence,
                    "frame_id": result.frame_id,
                },
            )
            # Link to active token's precondition
            # Find the latest precondition node for the token
            pre_nodes = [
                n
                for n in self._evidence_store.query().all_nodes()
                if n.node_type == NODE_TYPE_PRECONDITION
                and n.payload.get("token_id") == self._active_token.token_id
            ]
            if pre_nodes:
                self._evidence_store.record_edge(
                    vr_node.node_id, pre_nodes[-1].node_id, EDGE_VERIFIED_BY
                )

        if not result.ok:
            return None

        # Danger cleared — create satisfied resume contract
        now = time.perf_counter()
        contract = ResumeContract(
            contract_id=uuid.uuid4().hex,
            preemption_token_id=self._active_token.token_id,
            checkpoint_id=self._active_token.checkpoint_id,
            required_evidence_ids=[],
            reacquire_required=True,
            max_resume_delay_ms=2000,
            status="SATISFIED",
            satisfied_at=now,
        )

        # Clear active token so new dangers can be detected
        self._active_token = None

        return contract

    def expire_token(self) -> PreemptionToken | None:
        """Force-expire the active preemption token (e.g. on timeout).

        Returns the expired token, or ``None`` if no active token exists.
        """
        token = self._active_token
        if token is not None:
            self._active_token = None
        return token

    @property
    def active_token(self) -> PreemptionToken | None:
        return self._active_token

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _read_danger_score(observation: Observation) -> float | None:
        """Extract danger score from observation extensions."""
        raw = observation.extensions.get("danger_score")
        if raw is not None:
            return float(raw)
        return None
