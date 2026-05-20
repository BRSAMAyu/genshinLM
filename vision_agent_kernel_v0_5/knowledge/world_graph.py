from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from knowledge.knowledge_schema import SourceNode, TraversalEdge, Waypoint


@dataclass(frozen=True, slots=True)
class PathResult:
    ok: bool
    cost: float
    path: list[str]
    reason: str = ""


class WaypointGraph:
    def __init__(self, waypoints: list[Waypoint], edges: list[TraversalEdge]) -> None:
        self._waypoints = {item.waypoint_id: item for item in waypoints}
        self._adj: dict[str, list[tuple[str, float]]] = {item.waypoint_id: [] for item in waypoints}
        for edge in edges:
            self._adj.setdefault(edge.from_waypoint, []).append((edge.to_waypoint, edge.cost))
            if edge.bidirectional:
                self._adj.setdefault(edge.to_waypoint, []).append((edge.from_waypoint, edge.cost))

    def nearest_waypoint(self, source: SourceNode) -> str | None:
        candidates = [item for item in self._waypoints.values() if item.region == source.region]
        if not candidates:
            candidates = list(self._waypoints.values())
        if not candidates:
            return None
        return min(candidates, key=lambda waypoint: _distance(waypoint.position, source.position)).waypoint_id

    def shortest_path(self, start: str, goal: str) -> PathResult:
        if start not in self._adj or goal not in self._adj:
            return PathResult(False, math.inf, [], "unknown waypoint")
        queue: list[tuple[float, str, list[str]]] = [(0.0, start, [start])]
        seen: dict[str, float] = {}
        while queue:
            cost, node, path = heapq.heappop(queue)
            if node == goal:
                return PathResult(True, cost, path)
            if node in seen and seen[node] <= cost:
                continue
            seen[node] = cost
            for nxt, edge_cost in self._adj.get(node, []):
                heapq.heappush(queue, (cost + edge_cost, nxt, [*path, nxt]))
        return PathResult(False, math.inf, [], "unreachable")


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

