from __future__ import annotations

from planning.mission_queue import MissionQueue


class PlanGraphBuilder:
    def build_edges(self, queue: MissionQueue) -> list[tuple[str, str]]:
        return [(queue.nodes[index].id, queue.nodes[index + 1].id) for index in range(len(queue.nodes) - 1)]

