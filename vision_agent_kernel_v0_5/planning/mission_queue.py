from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MissionGoal:
    type: str
    resource_id: str
    target_count: int = 1


@dataclass(frozen=True, slots=True)
class MissionNode:
    id: str
    type: str
    skill_binding: str | None
    verifier: str
    failure_policy: dict[str, Any]
    route_id: str | None = None
    playbook: str | None = None


@dataclass(frozen=True, slots=True)
class MissionLoop:
    until: dict[str, Any]
    max_iterations: int


@dataclass(frozen=True, slots=True)
class MissionQueue:
    mission_id: str
    goal: MissionGoal
    nodes: list[MissionNode]
    loop: MissionLoop | None = None
    failure_policy: dict[str, Any] = field(default_factory=lambda: {"max_retries_per_node": 3, "on_node_failed": "recover_or_skip"})
    requires_user_confirmation: bool = True


def mission_to_dict(queue: MissionQueue) -> dict[str, Any]:
    return {
        "mission_id": queue.mission_id,
        "goal": asdict(queue.goal),
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "skill_binding": node.skill_binding,
                "verifier": node.verifier,
                "failure_policy": node.failure_policy,
                "route_id": node.route_id,
                "playbook": node.playbook,
            }
            for node in queue.nodes
        ],
        "loop": None if queue.loop is None else {"until": queue.loop.until, "max_iterations": queue.loop.max_iterations},
        "failure_policy": queue.failure_policy,
        "requires_user_confirmation": queue.requires_user_confirmation,
    }
