from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from runtime.claim_runtime import (
    AuditSnapshot,
    RiskLevel,
    _clamp,
)


AuditType = Literal["post_node", "mission_terminal", "low_activity"]
AuditRecordStatus = Literal["pending", "completed", "contaminated", "unverifiable", "expired"]


@dataclass(frozen=True, slots=True)
class AuditRecord:
    audit_id: str
    claim_id: str
    skill_id: str
    claim_type: str
    audit_type: AuditType
    due_at: float
    deadline_at: float
    snapshot_ref: str
    expected_delta: dict[str, Any]
    status: AuditRecordStatus = "pending"
    observed_delta: dict[str, Any] = field(default_factory=dict)
    contamination_reasons: list[str] = field(default_factory=list)
    retry_count: int = 0
    result: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None


@dataclass(frozen=True, slots=True)
class AuditScheduleConfig:
    post_node_delay_ms: int = 1500
    mission_terminal_delay_ms: int = 5000
    low_activity_idle_s: float = 30.0
    deadline_extension_ms: int = 300000  # 5 minutes
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class AuditCompletion:
    audit_id: str
    claim_id: str
    matched: bool
    contaminated: bool
    unverifiable: bool


class DelayedAuditScheduler:
    """Persistent audit queue with JSONL event log (Section 16.2, 17.7).

    Three trigger types:
      post_node: After MissionNode completion, short delay
      mission_terminal: After Mission reaches terminal node
      low_activity: During 30+ second idle periods

    Dual-track scheduling:
      Track A: Node-completion trigger → immediate after stabilization window
      Track B: Background idle monitor → scans pending queue every 60s
    """

    def __init__(
        self,
        config: AuditScheduleConfig | None = None,
        persistence_path: str = "",
    ) -> None:
        self.config = config or AuditScheduleConfig()
        self._persistence_path = persistence_path
        self._pending: dict[str, AuditRecord] = {}
        self._completed: dict[str, AuditRecord] = {}
        self._low_activity_queue: list[str] = []
        self._retry_counts: dict[str, int] = defaultdict(int)
        if persistence_path:
            self._load_from_jsonl()

    def schedule(
        self,
        *,
        audit_id: str,
        claim_id: str,
        skill_id: str,
        claim_type: str,
        audit_type: AuditType,
        snapshot: AuditSnapshot,
        expected_delta: dict[str, Any],
        stabilization_window_ms: int = 1000,
    ) -> AuditRecord:
        now = time.time()
        if audit_type == "post_node":
            due_at = now + (max(stabilization_window_ms, self.config.post_node_delay_ms) / 1000.0)
        elif audit_type == "mission_terminal":
            due_at = now + (self.config.mission_terminal_delay_ms / 1000.0)
        else:
            due_at = now + self.config.low_activity_idle_s

        deadline_at = due_at + (self.config.deadline_extension_ms / 1000.0)
        record = AuditRecord(
            audit_id=audit_id,
            claim_id=claim_id,
            skill_id=skill_id,
            claim_type=claim_type,
            audit_type=audit_type,
            due_at=due_at,
            deadline_at=deadline_at,
            snapshot_ref=snapshot.metadata.get("snapshot_ref", audit_id),
            expected_delta=expected_delta,
        )
        self._pending[audit_id] = record
        if audit_type == "low_activity":
            self._low_activity_queue.append(audit_id)
        self._persist_record("scheduled", record)
        return record

    def check_due(self, current_time: float | None = None) -> list[AuditRecord]:
        now = current_time or time.time()
        due: list[AuditRecord] = []
        expired: list[str] = []
        for audit_id, record in self._pending.items():
            if now > record.deadline_at:
                expired.append(audit_id)
            elif now >= record.due_at:
                due.append(record)
        for audit_id in expired:
            record = self._pending.pop(audit_id)
            self._completed[audit_id] = replace(record, status="expired", completed_at=now)
            self._persist_record("expired", self._completed[audit_id])
        return due

    def complete(
        self,
        audit_id: str,
        observed_delta: dict[str, Any],
        contamination_reasons: list[str] | None = None,
        current_time: float | None = None,
    ) -> AuditCompletion:
        record = self._pending.pop(audit_id, None)
        if record is None:
            return AuditCompletion(audit_id, "", False, False, True)
        now = current_time or time.time()
        contamination = contamination_reasons or []
        if contamination:
            status: AuditRecordStatus = "contaminated"
            matched = False
            contaminated = True
            unverifiable = False
        elif observed_delta == record.expected_delta:
            status = "completed"
            matched = True
            contaminated = False
            unverifiable = False
        else:
            status = "completed"
            matched = False
            contaminated = False
            unverifiable = False
        completed = replace(
            record,
            status=status,
            observed_delta=observed_delta,
            contamination_reasons=contamination,
            completed_at=now,
            result="matched" if matched else ("contaminated" if contaminated else "mismatch"),
        )
        self._completed[audit_id] = completed
        self._persist_record("completed", completed)
        return AuditCompletion(audit_id, record.claim_id, matched, contaminated, unverifiable)

    def mark_unverifiable(self, audit_id: str, reason: str = "", current_time: float | None = None) -> AuditCompletion:
        record = self._pending.pop(audit_id, None)
        if record is None:
            return AuditCompletion(audit_id, "", False, False, True)
        now = current_time or time.time()
        completed = replace(
            record, status="unverifiable", completed_at=now,
            result=f"unverifiable:{reason}",
        )
        self._completed[audit_id] = completed
        self._persist_record("unverifiable", completed)
        return AuditCompletion(audit_id, record.claim_id, False, False, True)

    def retry(self, audit_id: str, current_time: float | None = None) -> AuditRecord | None:
        record = self._pending.get(audit_id)
        if record is None:
            return None
        retry_count = self._retry_counts[audit_id] + 1
        if retry_count > self.config.max_retries:
            self.mark_unverifiable(audit_id, "max_retries_exceeded", current_time)
            return None
        self._retry_counts[audit_id] = retry_count
        now = current_time or time.time()
        new_due = now + self.config.post_node_delay_ms / 1000.0
        record = replace(record, due_at=new_due, retry_count=retry_count)
        self._pending[audit_id] = record
        return record

    def get_pending(self) -> list[AuditRecord]:
        return list(self._pending.values())

    def get_completed(self) -> list[AuditRecord]:
        return list(self._completed.values())

    def get_low_activity_pending(self) -> list[AuditRecord]:
        return [self._pending[aid] for aid in self._low_activity_queue if aid in self._pending]

    def pending_count(self) -> int:
        return len(self._pending)

    def completed_count(self) -> int:
        return len(self._completed)

    def _persist_record(self, event_type: str, record: AuditRecord) -> None:
        if not self._persistence_path:
            return
        data = {
            "event": event_type,
            "audit_id": record.audit_id,
            "claim_id": record.claim_id,
            "skill_id": record.skill_id,
            "claim_type": record.claim_type,
            "audit_type": record.audit_type,
            "status": record.status,
            "expected_delta": record.expected_delta,
            "observed_delta": record.observed_delta,
            "contamination_reasons": record.contamination_reasons,
            "result": record.result,
            "due_at": record.due_at,
            "deadline_at": record.deadline_at,
            "retry_count": record.retry_count,
            "created_at": record.created_at,
            "completed_at": record.completed_at,
        }
        try:
            with open(self._persistence_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _load_from_jsonl(self) -> None:
        if not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._replay_record(data)
        except OSError:
            pass

    def _replay_record(self, data: dict[str, Any]) -> None:
        event = data.get("event")
        record = AuditRecord(
            audit_id=data.get("audit_id", ""),
            claim_id=data.get("claim_id", ""),
            skill_id=data.get("skill_id", ""),
            claim_type=data.get("claim_type", ""),
            audit_type=data.get("audit_type", "post_node"),
            due_at=data.get("due_at", 0.0),
            deadline_at=data.get("deadline_at", 0.0),
            snapshot_ref=data.get("audit_id", ""),
            expected_delta=data.get("expected_delta", {}),
            status=data.get("status", "pending"),
            observed_delta=data.get("observed_delta", {}),
            contamination_reasons=data.get("contamination_reasons", []),
            retry_count=data.get("retry_count", 0),
            result=data.get("result", ""),
            created_at=data.get("created_at", 0.0),
            completed_at=data.get("completed_at"),
        )
        if event in ("completed", "expired", "unverifiable"):
            self._pending.pop(record.audit_id, None)
            self._completed[record.audit_id] = record
        else:
            self._pending[record.audit_id] = record
            if record.audit_type == "low_activity":
                self._low_activity_queue.append(record.audit_id)
