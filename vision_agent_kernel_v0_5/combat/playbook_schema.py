from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PlaybookNode:
    node_id: str
    type: str
    priority: int
    guards: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CombatPlaybook:
    playbook_id: str
    goal: str
    team_profile: str
    nodes: list[PlaybookNode]
    edges: list[tuple[str, str]]
    fallback: str
    retry: dict[str, Any]
