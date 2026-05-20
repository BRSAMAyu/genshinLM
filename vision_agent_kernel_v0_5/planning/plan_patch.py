from __future__ import annotations

from dataclasses import replace

from planning.mission_queue import MissionQueue


class PlanPatch:
    def set_failure_policy(self, queue: MissionQueue, policy: dict) -> MissionQueue:
        return replace(queue, failure_policy=policy)
