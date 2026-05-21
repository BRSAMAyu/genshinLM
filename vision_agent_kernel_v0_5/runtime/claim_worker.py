from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from runtime.claim_adjudicator import AdjudicationResult, ClaimAdjudicator
from runtime.claim_events import ClaimEvent, ClaimEventPublisher, ClaimGraphState
from runtime.claim_runtime import AdjudicationEvent, ClaimGraph, ObservationClaim, StateDeltaClaim


ClaimGraphCommandType = Literal["add_claim", "add_observation", "adjudicate", "demote", "stop"]


@dataclass(frozen=True, slots=True)
class ClaimGraphCommand:
    command_type: ClaimGraphCommandType
    claim: StateDeltaClaim | None = None
    observation: ObservationClaim | None = None
    claim_id: str = ""
    reason: str = ""
    inferred_dependencies: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ClaimGraphCommandResult:
    ok: bool
    command_type: ClaimGraphCommandType
    snapshot: dict[str, Any]
    adjudication: AdjudicationResult | None = None
    error: str = ""


@dataclass(slots=True)
class _Envelope:
    command: ClaimGraphCommand
    done: threading.Event = field(default_factory=threading.Event)
    result: ClaimGraphCommandResult | None = None


class ClaimGraphWorker:
    """Single-writer runtime for ClaimGraph.

    ClaimGraph remains a simple domain object. This worker is the concurrency
    boundary: execution, verifier, audit, and orchestration threads submit
    commands, and one event loop mutates the graph in order.
    """

    def __init__(
        self,
        *,
        graph: ClaimGraph | None = None,
        adjudicator: ClaimAdjudicator | None = None,
        publisher: ClaimEventPublisher | None = None,
        graph_id: str = "",
        mission_id: str = "",
    ) -> None:
        self.graph = graph or ClaimGraph()
        self.adjudicator = adjudicator or ClaimAdjudicator()
        self.publisher = publisher
        self.graph_id = graph_id or f"claim_graph:{uuid.uuid4()}"
        self.mission_id = mission_id
        self._queue: queue.Queue[_Envelope] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, name="ClaimGraphWorker", daemon=True)
        self._thread.start()
        self._started.wait(timeout=2.0)

    def stop(self, timeout: float = 2.0) -> None:
        if not self._thread:
            return
        self.submit(ClaimGraphCommand("stop"), timeout=timeout)
        self._thread.join(timeout=timeout)

    def submit(self, command: ClaimGraphCommand, timeout: float = 5.0) -> ClaimGraphCommandResult:
        if self._thread is None or not self._thread.is_alive():
            self.start()
        env = _Envelope(command)
        self._queue.put(env)
        if not env.done.wait(timeout=timeout):
            return ClaimGraphCommandResult(False, command.command_type, self.graph.snapshot(), error="claim_worker_timeout")
        assert env.result is not None
        return env.result

    def snapshot(self) -> dict[str, Any]:
        return dict(self.graph.snapshot())

    def _run(self) -> None:
        self._started.set()
        while True:
            env = self._queue.get()
            try:
                result = self._apply(env.command)
            except Exception as exc:  # keep worker alive, surface event.
                result = ClaimGraphCommandResult(
                    False,
                    env.command.command_type,
                    self.graph.snapshot(),
                    error=f"{exc.__class__.__name__}:{exc}",
                )
                self._publish_event("claim_adjudication_error", env.command.claim_id, "error", {"error": result.error})
            env.result = result
            env.done.set()
            if env.command.command_type == "stop":
                self._stopped.set()
                return

    def _apply(self, command: ClaimGraphCommand) -> ClaimGraphCommandResult:
        if command.command_type == "stop":
            return ClaimGraphCommandResult(True, "stop", self.graph.snapshot())
        if command.command_type == "add_claim":
            if command.claim is None:
                raise ValueError("add_claim requires claim")
            self.graph.add_claim(command.claim, inferred_dependencies=command.inferred_dependencies)
            self._publish_event("claim_event", command.claim.claim_id, command.claim.status, {"action": "add_claim"})
            self._publish_state(command.claim.claim_id)
            return ClaimGraphCommandResult(True, command.command_type, self.graph.snapshot())
        if command.command_type == "add_observation":
            if command.observation is None:
                raise ValueError("add_observation requires observation")
            self.graph.add_observation(command.observation)
            self._publish_event(
                "claim_event",
                command.observation.claim_id,
                "",
                {"action": "add_observation", "observation_id": command.observation.observation_id},
            )
            self._publish_state(command.observation.claim_id)
            return ClaimGraphCommandResult(True, command.command_type, self.graph.snapshot())
        if command.command_type == "adjudicate":
            claim_id = command.claim_id
            claim = self.graph.get(claim_id)
            observations = self.graph.get_observations_for(claim_id)
            adjudication = self.adjudicator.adjudicate(claim, observations)
            updated = replace(
                claim,
                status=adjudication.status,
                confidence=adjudication.confidence,
                evidence_refs=[obs.observation_id for obs in observations],
                metadata={**claim.metadata, "adjudication_reason": adjudication.reason},
            )
            self.graph.update_claim(updated)
            event = AdjudicationEvent(
                adjudication_id=f"adj:{claim_id}:{uuid.uuid4()}",
                claim_id=claim_id,
                old_status=claim.status,
                new_status=adjudication.status,
                reason=adjudication.reason,
                confidence=adjudication.confidence,
                evidence_votes_summary={
                    "support_score": adjudication.support_score,
                    "refute_score": adjudication.refute_score,
                    "family_coverage": adjudication.family_coverage,
                    "next_action": adjudication.next_action,
                },
                created_at=time.time(),
            )
            self.graph.add_adjudication(event)
            self._publish_event("claim_adjudicated", claim_id, adjudication.status, event.evidence_votes_summary)
            self._publish_state(claim_id)
            return ClaimGraphCommandResult(True, command.command_type, self.graph.snapshot(), adjudication=adjudication)
        if command.command_type == "demote":
            report = self.graph.demote(command.claim_id, command.reason or "worker_demote")
            self._publish_event("claim_cascade", command.claim_id, "demoted", {"affected_claims": report.affected_claims})
            self._publish_state(command.claim_id)
            return ClaimGraphCommandResult(True, command.command_type, self.graph.snapshot())
        raise ValueError(f"unsupported claim command: {command.command_type}")

    def _publish_event(self, event_type: str, claim_id: str, status: str, payload: dict[str, Any]) -> None:
        if self.publisher is None:
            return
        self.publisher.publish_event(
            ClaimEvent(
                event_type=event_type,  # type: ignore[arg-type]
                mission_id=self.mission_id,
                graph_id=self.graph_id,
                claim_id=claim_id,
                status=status,
                payload=payload,
            )
        )

    def _publish_state(self, latest_claim_id: str = "") -> None:
        if self.publisher is None:
            return
        snapshot = dict(self.graph.snapshot())
        if latest_claim_id:
            snapshot["latest_claim_id"] = latest_claim_id
        self.publisher.publish_state(
            ClaimGraphState.from_snapshot(
                mission_id=self.mission_id,
                graph_id=self.graph_id,
                snapshot=snapshot,
            )
        )
