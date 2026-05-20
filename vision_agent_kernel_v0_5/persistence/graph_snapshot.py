from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    mission_id: str
    nodes: list[str]
    edges: list[tuple[str, str]]
    safe_resume_node: str

