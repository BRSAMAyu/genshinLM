from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Payload = dict[str, Any]


@dataclass(order=True, slots=True)
class Interrupt:
    priority: int
    timestamp: float = field(compare=False)
    code: str = field(compare=False)
    source: str = field(compare=False)
    frame_id: int | None = field(default=None, compare=False)
    payload: Payload = field(default_factory=dict, compare=False)
    recoverable: bool = field(default=True, compare=False)
    requires_input_release: bool = field(default=False, compare=False)


@dataclass(slots=True)
class ModeRequest:
    requested_mode: str
    owner: str
    priority: int
    reason: str
    timestamp: float


@dataclass(slots=True)
class KernelEvent:
    name: str
    timestamp: float
    source: str
    payload: Payload = field(default_factory=dict)
