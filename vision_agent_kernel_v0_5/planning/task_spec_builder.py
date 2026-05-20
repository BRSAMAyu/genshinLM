from __future__ import annotations

from knowledge.route_selector import RouteSelector
from planning.intent_parser import ParsedIntent
from planning.mission_queue import MissionGoal, MissionLoop, MissionNode, MissionQueue


class TaskSpecBuilder:
    def __init__(self, route_selector: RouteSelector | None = None) -> None:
        self._routes = route_selector or RouteSelector()

    def build(self, intent: ParsedIntent) -> MissionQueue:
        ranked = self._routes.rank_routes(intent.resource_id)
        route = ranked["routes"][0] if ranked.get("routes") else {"route_id": None}
        failure = {"max_retries": 3, "on_failed": "recover_or_skip", "cleanup_skill": "return_to_safe_anchor_v1"}
        nodes = [
            MissionNode("enter_region", "enter_region", "enter_region_a_v1", "region_entered", failure, route_id=route.get("route_id")),
            MissionNode("acquire_target", "acquire_target", "acquire_monster_a_v1", "target_visible", failure),
            MissionNode("combat", "combat", "safe_combat_playbook_v1", "target_defeated", failure, playbook="safe_combat_v1"),
            MissionNode("verify_reward", "verify", None, "reward_seen_or_count_changed", failure),
        ]
        return MissionQueue(
            mission_id=f"mission_{intent.resource_id}",
            goal=MissionGoal(intent.goal_type, intent.resource_id, intent.target_count),
            nodes=nodes,
            loop=MissionLoop({"resource_count_delta": intent.target_count}, max_iterations=5),
        )

