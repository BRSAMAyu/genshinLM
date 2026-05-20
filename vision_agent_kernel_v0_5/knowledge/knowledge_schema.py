from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ResourceType = Literal["monster_drop", "collectable", "shop", "quest_reward"]
SourceType = Literal["monster", "monster_group", "collectable", "shop", "quest"]


@dataclass(frozen=True, slots=True)
class SourceRef:
    source_id: str
    source_type: SourceType
    expected_drop: bool = False
    expected_yield: int = 1


@dataclass(frozen=True, slots=True)
class Resource:
    resource_id: str
    name: str
    type: ResourceType
    sources: list[SourceRef]


@dataclass(frozen=True, slots=True)
class SourceNode:
    source_id: str
    type: SourceType
    region: str
    position: tuple[float, float, float]
    entry_skill: str
    acquire_skill: str
    execution_skill: str
    verification: str
    risk: str = "low"


@dataclass(frozen=True, slots=True)
class Waypoint:
    waypoint_id: str
    region: str
    position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TraversalEdge:
    from_waypoint: str
    to_waypoint: str
    cost: float
    bidirectional: bool = True
    constraints: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RouteNode:
    route_id: str
    entry_point: str
    targets: list[str]
    estimated_time_sec: float
    required_profiles: list[str]
    traversal_cost: float = 0.0
    waypoint_path: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class KnowledgePack:
    resources: list[Resource]
    sources: list[SourceNode]
    waypoints: list[Waypoint]
    edges: list[TraversalEdge]
    routes: list[RouteNode]


def source_ref_from_dict(data: dict[str, Any]) -> SourceRef:
    return SourceRef(
        source_id=str(data["source_id"]),
        source_type=data.get("source_type", "monster"),
        expected_drop=bool(data.get("expected_drop", False)),
        expected_yield=int(data.get("expected_yield", 1)),
    )


def resource_from_dict(data: dict[str, Any]) -> Resource:
    return Resource(
        resource_id=str(data["resource_id"]),
        name=str(data["name"]),
        type=data.get("type", "monster_drop"),
        sources=[source_ref_from_dict(item) for item in data.get("sources", [])],
    )


def source_node_from_dict(data: dict[str, Any]) -> SourceNode:
    position = data.get("position") or data.get("coords") or (0.0, 0.0, 0.0)
    return SourceNode(
        source_id=str(data["source_id"]),
        type=data.get("type", "monster_group"),
        region=str(data.get("region", "unknown")),
        position=(float(position[0]), float(position[1]), float(position[2])),
        entry_skill=str(data.get("entry_skill", "")),
        acquire_skill=str(data.get("acquire_skill", "")),
        execution_skill=str(data.get("execution_skill", "")),
        verification=str(data.get("verification", "")),
        risk=str(data.get("risk", "low")),
    )


def waypoint_from_dict(data: dict[str, Any]) -> Waypoint:
    position = data.get("position") or (0.0, 0.0, 0.0)
    return Waypoint(str(data["waypoint_id"]), str(data.get("region", "unknown")), (float(position[0]), float(position[1]), float(position[2])))


def edge_from_dict(data: dict[str, Any]) -> TraversalEdge:
    return TraversalEdge(
        from_waypoint=str(data["from"]),
        to_waypoint=str(data["to"]),
        cost=float(data.get("cost", 1.0)),
        bidirectional=bool(data.get("bidirectional", True)),
        constraints=list(data.get("constraints", [])),
    )


def route_from_dict(data: dict[str, Any]) -> RouteNode:
    return RouteNode(
        route_id=str(data["route_id"]),
        entry_point=str(data["entry_point"]),
        targets=[str(item) for item in data.get("targets", [])],
        estimated_time_sec=float(data.get("estimated_time_sec", 0.0)),
        required_profiles=[str(item) for item in data.get("required_profiles", [])],
        traversal_cost=float(data.get("traversal_cost", 0.0)),
        waypoint_path=[str(item) for item in data.get("waypoint_path", [])],
    )

