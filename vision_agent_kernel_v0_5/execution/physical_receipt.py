from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from core.types import InputLease


PhysicalActionStatus = Literal["accepted", "rejected", "executed", "released", "blocked", "dry_run"]


@dataclass(frozen=True, slots=True)
class PhysicalActionReceipt:
    """Auditable receipt for any low-level physical or dry-run actuation."""

    receipt_id: str
    lease_id: str
    owner: str
    action_family: str
    status: PhysicalActionStatus
    backend: str
    created_at: float = field(default_factory=time.time)
    release_at: float | None = None
    focus_state: str = "unknown"
    window_id: str = ""
    reason: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_lease(
        cls,
        lease: InputLease,
        *,
        status: PhysicalActionStatus,
        backend: str,
        action_family: str,
        focus_state: str = "unknown",
        window_id: str = "",
        evidence_ids: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> PhysicalActionReceipt:
        return cls(
            receipt_id=f"receipt:{lease.lease_id}",
            lease_id=lease.lease_id,
            owner=lease.owner,
            action_family=action_family,
            status=status,
            backend=backend,
            created_at=lease.created_at,
            release_at=lease.expires_at,
            focus_state=focus_state,
            window_id=window_id,
            reason=lease.reason,
            evidence_ids=evidence_ids or [],
            metadata=metadata or {},
        )

    @property
    def bounded(self) -> bool:
        return self.release_at is not None and self.release_at >= self.created_at
