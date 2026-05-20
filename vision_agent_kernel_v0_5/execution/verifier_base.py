from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from core.types import Observation, TargetTrack


@dataclass(frozen=True, slots=True)
class VerifierResult:
    ok: bool
    verifier_id: str
    confidence: float
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    frame_id: int | None = None
    roi_ids: list[str] = field(default_factory=list)
    detection_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class VerifierContext:
    state: dict[str, Any] = field(default_factory=dict)
    observation: Observation | None = None
    frame: np.ndarray | None = None
    roi_frames: dict[str, np.ndarray] = field(default_factory=dict)
    ocr_text: str = ""
    target_track: TargetTrack | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    snapshot_id: str
    created_at: float
    node_id: str
    observation_summary: dict[str, Any]
    safe_anchor: str = "safe_anchor"


class Verifier(Protocol):
    verifier_id: str

    def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
        ...


def ensure_context(context: VerifierContext | dict[str, Any]) -> VerifierContext:
    if isinstance(context, VerifierContext):
        return context
    return VerifierContext(state=context)


class SnapshotStore:
    def __init__(self) -> None:
        self._snapshots: list[StateSnapshot] = []

    def capture(self, node_id: str, observation_summary: dict[str, Any] | None = None, safe_anchor: str = "safe_anchor") -> StateSnapshot:
        snapshot = StateSnapshot(str(uuid.uuid4()), time.time(), node_id, observation_summary or {}, safe_anchor)
        self._snapshots.append(snapshot)
        return snapshot

    def latest(self) -> StateSnapshot | None:
        return self._snapshots[-1] if self._snapshots else None
