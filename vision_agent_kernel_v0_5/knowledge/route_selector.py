from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from knowledge.resource_db import ResourceDB
from knowledge.world_graph import WaypointGraph


class RouteSelector:
    def __init__(self, db: ResourceDB | None = None) -> None:
        self._db = db or ResourceDB()
        self._graph = WaypointGraph(self._db.pack.waypoints, self._db.pack.edges)
        self._sources = {item.source_id: item for item in self._db.pack.sources}

    def rank_routes(self, resource_id: str, start_waypoint: str = "safe_anchor") -> dict[str, Any]:
        resource = self._db.resolve_resource(resource_id)
        if resource is None:
            return {"ok": False, "routes": [], "message": "unknown resource"}
        ranked = []
        for route in self._db.pack.routes:
            if not any(ref.source_id in route.targets for ref in resource.sources):
                continue
            costs = []
            path = [start_waypoint]
            current = start_waypoint
            valid = True
            for target in route.targets:
                source = self._sources.get(target)
                waypoint = self._graph.nearest_waypoint(source) if source else None
                if waypoint is None:
                    valid = False
                    break
                result = self._graph.shortest_path(current, waypoint)
                if not result.ok:
                    valid = False
                    break
                costs.append(result.cost)
                path.extend(result.path[1:])
                current = waypoint
            if valid:
                ranked.append(replace(route, traversal_cost=sum(costs), waypoint_path=path))
        ranked.sort(key=lambda item: (item.traversal_cost, item.estimated_time_sec))
        return {"ok": True, "routes": [asdict(item) for item in ranked], "message": "ranked by waypoint traversal cost"}
