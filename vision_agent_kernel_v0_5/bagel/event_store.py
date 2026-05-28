"""Append-only event store for BAGEL.

Persists the complete lifecycle of beliefs, actions, feedbacks, and probes.
Events are written to JSONL files. The store can reconstruct a FIG from its
event stream.

Hard rules:
- Append-only: no mutation or deletion of past events.
- Every event has graph_version, trace_id, timestamp, snapshot_id.
- Write failure prevents further external action (via callback).
- Can reconstruct FIG from event stream.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TextIO

log = logging.getLogger(__name__)

# -- Event types ----------------------------------------------------------

EventType = Literal[
    "BeliefCommitted",
    "ActionProposed",
    "ActionMaterialized",
    "ActionExecuted",
    "FeedbackReceived",
    "AuditStarted",
    "AuditCompleted",
    "ProbeGenerated",
    "ProbeExecuted",
    "ArbiterUpdated",
    "BeliefRevised",
    "BeliefRetired",
    "BeliefStaled",
    "CausalBridgeRegistered",
    "SubgraphCondensed",
    "AttributionSnapshotFrozen",
    "AttributionDecisionCommitted",
    "ExecutionPhaseEntered",
    "JitRegenerationRequested",
    "QuestArchived",
    "QuestTransition",
]


@dataclass(frozen=True, slots=True)
class BagelEvent:
    event_type: EventType
    graph_id: str
    graph_version: int
    trace_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    snapshot_id: str = ""

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.perf_counter())
        if not self.snapshot_id:
            object.__setattr__(self, "snapshot_id", uuid.uuid4().hex[:8])

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "graph_id": self.graph_id,
            "graph_version": self.graph_version,
            "trace_id": self.trace_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "snapshot_id": self.snapshot_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BagelEvent:
        return cls(
            event_type=data["event_type"],
            graph_id=data["graph_id"],
            graph_version=data["graph_version"],
            trace_id=data["trace_id"],
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", 0.0),
            snapshot_id=data.get("snapshot_id", ""),
        )


# -- Event Store ----------------------------------------------------------

class BagelEventStore:
    """Append-only JSONL event store with thread-safe writes."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            data_dir = Path("data") / "bagel_events"
            data_dir.mkdir(parents=True, exist_ok=True)
            path = data_dir / "events.jsonl"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._write_count = 0
        self._write_failure_callback: list[Any] = []
        self._file: TextIO | None = None

    def __enter__(self) -> BagelEventStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def set_write_failure_callback(self, callback: Any) -> None:
        self._write_failure_callback.append(callback)

    def append(self, event: BagelEvent) -> bool:
        """Append an event. Returns False if write failed."""
        line = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            try:
                if self._file is None:
                    self._file = open(self._path, "a", encoding="utf-8")
                self._file.write(line + "\n")
                self._file.flush()
                self._write_count += 1
                return True
            except Exception as exc:
                log.error("[BagelEventStore] Write failed: %s", exc)
                for cb in self._write_failure_callback:
                    try:
                        cb(event, exc)
                    except Exception:
                        pass
                return False

    def append_many(self, events: list[BagelEvent]) -> int:
        """Append multiple events atomically. Returns count of successful writes."""
        success = 0
        with self._lock:
            try:
                if self._file is None:
                    self._file = open(self._path, "a", encoding="utf-8")
                for event in events:
                    line = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
                    self._file.write(line + "\n")
                    success += 1
                self._file.flush()
                self._write_count += success
            except Exception as exc:
                log.error("[BagelEventStore] Batch write failed after %d events: %s", success, exc)
                for cb in self._write_failure_callback:
                    try:
                        cb(events[-1] if events else None, exc)
                    except Exception:
                        pass
        return success

    def read_events(
        self,
        graph_id: str | None = None,
        trace_id: str | None = None,
        event_type: EventType | None = None,
    ) -> list[BagelEvent]:
        """Read events, optionally filtered."""
        events: list[BagelEvent] = []
        if not self._path.exists():
            return events
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = BagelEvent.from_dict(data)
                except (json.JSONDecodeError, KeyError):
                    continue
                if graph_id and event.graph_id != graph_id:
                    continue
                if trace_id and event.trace_id != trace_id:
                    continue
                if event_type and event.event_type != event_type:
                    continue
                events.append(event)
        return events

    def reconstruct_fig(self, graph_id: str) -> dict[str, Any]:
        """Reconstruct a FIG state from its event stream."""
        from bagel.fig_schema import FalsifiableInterventionGraph

        events = self.read_events(graph_id=graph_id)
        if not events:
            return {"graph_id": graph_id, "error": "no events found"}

        fig = FalsifiableInterventionGraph(graph_id=graph_id)

        for event in events:
            payload = event.payload
            if event.event_type == "BeliefCommitted":
                node = _dict_to_belief(payload)
                if node:
                    fig.commit_belief(node)
            elif event.event_type == "ActionProposed":
                node = _dict_to_action(payload)
                if node:
                    fig.propose_action(node)
            elif event.event_type == "FeedbackReceived":
                node = _dict_to_feedback(payload)
                if node:
                    fig.add_feedback(node)
            elif event.event_type == "ProbeGenerated":
                node = _dict_to_probe(payload)
                if node:
                    fig.add_probe(node)
            elif event.event_type == "CausalBridgeRegistered":
                node = _dict_to_bridge(payload)
                if node:
                    fig.add_bridge(node)
            elif event.event_type == "SubgraphCondensed":
                node = _dict_to_condensed(payload)
                if node:
                    fig.add_condensed_node(node)
            elif event.event_type == "AttributionSnapshotFrozen":
                fig.set_phase("attribution_frozen")
            elif event.event_type == "AttributionDecisionCommitted":
                fig.set_phase("attribution_committed")
            elif event.event_type == "ExecutionPhaseEntered":
                fig.set_phase("execution")
            elif event.event_type in ("BeliefRevised", "BeliefStaled", "BeliefRetired",
                                      "ArbiterUpdated"):
                # Lifecycle transition — apply update to existing belief
                bid = payload.get("belief_id", "")
                new_lc = payload.get("new_lifecycle") or payload.get("lifecycle")
                if bid and new_lc:
                    fig.update_belief(bid, lifecycle=new_lc)
            elif event.event_type == "ActionMaterialized":
                aid = payload.get("action_id", "")
                if aid:
                    overrides: dict = {}
                    if payload.get("status"):
                        overrides["status"] = payload["status"]
                    if payload.get("fingerprint"):
                        overrides["fingerprint"] = payload["fingerprint"]
                    if payload.get("claim_id"):
                        overrides["claim_id"] = payload["claim_id"]
                    if overrides:
                        fig.update_action(aid, **overrides)
            elif event.event_type == "ActionExecuted":
                aid = payload.get("action_id", "")
                if aid:
                    overrides = {
                        key: payload[key]
                        for key in ("status", "fingerprint", "claim_id", "metadata")
                        if key in payload
                    }
                    if overrides:
                        fig.update_action(aid, **overrides)
            elif event.event_type == "ProbeExecuted":
                pid = payload.get("probe_id", "")
                if pid:
                    probe_overrides: dict = {}
                    if payload.get("status"):
                        probe_overrides["status"] = payload["status"]
                    if payload.get("result"):
                        probe_overrides["result"] = payload["result"]
                    if probe_overrides:
                        fig.update_probe(pid, **probe_overrides)

        return fig.to_dict()

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    @property
    def write_count(self) -> int:
        with self._lock:
            return self._write_count

    @property
    def path(self) -> Path:
        return self._path


def _dict_to_belief(data: dict[str, Any]) -> Any:
    from bagel.fig_schema import BeliefIdentity, BeliefNode, StructuredValidityCondition
    try:
        identity_data = data.get("identity")
        identity = None
        if isinstance(identity_data, dict):
            identity = BeliefIdentity(
                belief_id=identity_data.get("belief_id", data["belief_id"]),
                provisional_anchor=identity_data.get("provisional_anchor", ""),
                fingerprint=identity_data.get("fingerprint", ""),
            )
        validity = []
        for item in data.get("valid_while_structured", ()) or ():
            if isinstance(item, dict):
                validity.append(StructuredValidityCondition(
                    kind=item.get("kind", ""),
                    target=item.get("target", ""),
                    expected=item.get("expected", ""),
                    on_violation=item.get("on_violation", "mark_stale"),
                ))
        return BeliefNode(
            belief_id=data["belief_id"],
            target_object=data.get("target_object", ""),
            causal_role=data.get("causal_role", "custom"),
            hypothesis=data.get("hypothesis", ""),
            falsification_condition=data.get("falsification_condition", ""),
            lifecycle=data.get("lifecycle", "provisional"),
            identity=identity,
            confidence=data.get("confidence", 0.5),
            intervenable=data.get("intervenable", True),
            risk_level=data.get("risk_level", "low"),
            valid_while_structured=tuple(validity),
            ifs_score=data.get("ifs_score", 0.0),
            tvd_score=data.get("tvd_score", 0.0),
            attribution_quality=data.get("attribution_quality", 0.0),
            condensed_from=data.get("condensed_from", ""),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )
    except (KeyError, TypeError):
        return None


def _dict_to_action(data: dict[str, Any]) -> Any:
    from bagel.fig_schema import ActionNode
    try:
        return ActionNode(
            action_id=data["action_id"],
            belief_ids=tuple(data.get("belief_ids", ())),
            action_type=data.get("action_type", ""),
            params=data.get("params", {}),
            status=data.get("status", "proposed"),
            fingerprint=data.get("fingerprint", ""),
            claim_id=data.get("claim_id", ""),
            risk_level=data.get("risk_level", "low"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )
    except (KeyError, TypeError):
        return None


def _dict_to_feedback(data: dict[str, Any]) -> Any:
    from bagel.fig_schema import FeedbackNode
    try:
        return FeedbackNode(
            feedback_id=data["feedback_id"],
            action_id=data["action_id"],
            polarity=data.get("polarity", "neutral"),
            signal_quality=data.get("signal_quality", 0.5),
            evidence_refs=tuple(data.get("evidence_refs", ())),
            claim_refs=tuple(data.get("claim_refs", ())),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", 0.0),
        )
    except (KeyError, TypeError):
        return None


def _dict_to_probe(data: dict[str, Any]) -> Any:
    from bagel.fig_schema import ProbeNode
    try:
        can_distinguish_raw = data.get("can_distinguish", ("", ""))
        can_distinguish: tuple[str, ...] = ("", "")
        if isinstance(can_distinguish_raw, list) and len(can_distinguish_raw) >= 2:
            can_distinguish = (can_distinguish_raw[0], can_distinguish_raw[1])
        elif isinstance(can_distinguish_raw, tuple) and len(can_distinguish_raw) >= 2:
            can_distinguish = (can_distinguish_raw[0], can_distinguish_raw[1])
        return ProbeNode(
            probe_id=data["probe_id"],
            belief_id=data["belief_id"],
            description=data.get("description", ""),
            failure_criteria=data.get("failure_criteria", ""),
            status=data.get("status", "generated"),
            falsification_invariant=data.get("falsification_invariant", ""),
            irreversible=data.get("irreversible", False),
            can_distinguish=can_distinguish,
            timeout_risk=data.get("timeout_risk", ""),
            noise_risk=data.get("noise_risk", ""),
            probe_cluster_id=data.get("probe_cluster_id", ""),
            non_decidable_count=data.get("non_decidable_count", 0),
            sanity_status=data.get("sanity_status", ""),
            result=data.get("result", {}),
            created_at=data.get("created_at", 0.0),
            executed_at=data.get("executed_at", 0.0),
        )
    except (KeyError, TypeError):
        return None


def _dict_to_bridge(data: dict[str, Any]) -> Any:
    from bagel.fig_schema import CausalBridgeNode
    try:
        return CausalBridgeNode(
            bridge_id=data["bridge_id"],
            from_feedback=data["from_feedback"],
            to_belief=data["to_belief"],
            bridge_type=data.get("bridge_type", "state_continuity"),
            evidence=tuple(data.get("evidence", ())),
            weight=data.get("weight", 0.5),
            created_at=data.get("created_at", 0.0),
        )
    except (KeyError, TypeError):
        return None


def _dict_to_condensed(data: dict[str, Any]) -> Any:
    from bagel.fig_schema import CondensedNode
    try:
        return CondensedNode(
            condensed_id=data["condensed_id"],
            kind=data.get("kind", "super_belief"),
            source_node_ids=tuple(data.get("source_node_ids", ())),
            interface_contract=data.get("interface_contract", {}),
            summary_belief=data.get("summary_belief", ""),
            survival_evidence=tuple(data.get("survival_evidence", ())),
            risk_summary=data.get("risk_summary", {}),
            artifact_fingerprints=tuple(data.get("artifact_fingerprints", ())),
            expand_event_ref=data.get("expand_event_ref", ""),
            created_at=data.get("created_at", 0.0),
        )
    except (KeyError, TypeError):
        return None
