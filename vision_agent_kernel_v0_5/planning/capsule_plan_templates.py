from __future__ import annotations

from execution.semantic_action import click_anchor_action
from planning.mission_graph import MissionGraph, MissionGraphEdge, MissionGraphNode
from planning.mission_queue import MissionGoal


class CapsulePlanTemplateLibrary:
    """Deterministic plan templates for capsule-owned common flows.

    These templates are intentionally dry-run/testbed friendly. They provide a
    stable executable graph shape while each capsule supplies concrete anchors,
    skills, verifiers, and resources.
    """

    def hsr_daily_flow(self, mission_id: str = "hsr_daily_flow") -> MissionGraph:
        goal = MissionGoal(type="daily", resource_id="hsr_daily")
        nodes = [
            MissionGraphNode(
                node_id="open_hsr_menu",
                node_type="ui_interact",
                skill_binding="hsr_navigation",
                verifier="screen_state_menu",
                action_contracts=[click_anchor_action("open_hsr_menu_action", "hsr_menu_button")],
                failure_policy={"max_retries": 1, "on_failed": "recalibrate_or_fallback_agent"},
            ),
            MissionGraphNode(
                node_id="progress_dialog",
                node_type="dialog",
                skill_binding="hsr_dialog",
                verifier="dialog_progressed",
                action_contracts=[click_anchor_action("continue_dialog_action", "hsr_dialog_continue")],
                failure_policy={"max_retries": 2, "on_failed": "fallback_agent_with_confirmation"},
            ),
            MissionGraphNode(
                node_id="claim_reward",
                node_type="claim_reward",
                skill_binding="hsr_claim_rewards",
                verifier="reward_claimed",
                action_contracts=[click_anchor_action("claim_reward_action", "hsr_claim_reward_button")],
                failure_policy={"max_retries": 1, "on_failed": "record_anchor_click_no_effect"},
                requires_user_confirmation=True,
            ),
        ]
        return MissionGraph(
            mission_id=mission_id,
            goal=goal,
            nodes=nodes,
            edges=[
                MissionGraphEdge("open_hsr_menu", "progress_dialog"),
                MissionGraphEdge("progress_dialog", "claim_reward"),
            ],
            capsule_id="hsr",
            explanation="HSR UI-first daily flow: menu -> dialog -> claim reward, all via UIAnchor contracts.",
        )

    def genshin_material_flow(self, mission_id: str = "genshin_material_flow") -> MissionGraph:
        goal = MissionGoal(type="collect", resource_id="genshin_material")
        nodes = [
            MissionGraphNode(
                node_id="open_map",
                node_type="ui_interact",
                skill_binding="genshin_navigation",
                verifier="map_opened",
                action_contracts=[click_anchor_action("open_map_action", "genshin_map_button")],
                failure_policy={"max_retries": 1, "on_failed": "recalibrate_or_fallback_agent"},
            ),
            MissionGraphNode(
                node_id="confirm_teleport",
                node_type="ui_interact",
                skill_binding="genshin_navigation",
                verifier="teleport_started",
                action_contracts=[click_anchor_action("teleport_confirm_action", "genshin_teleport_confirm")],
                failure_policy={"max_retries": 1, "on_failed": "ask_user_or_reselect_waypoint"},
                requires_user_confirmation=True,
            ),
            MissionGraphNode(
                node_id="navigate_to_material",
                node_type="navigate",
                skill_binding="genshin_navigation",
                verifier="navigation_progress",
                failure_policy={"max_retries": 2, "on_failed": "local_recovery_then_replan"},
            ),
            MissionGraphNode(
                node_id="collect_material",
                node_type="collect",
                skill_binding="genshin_collect",
                verifier="collection_verified",
                failure_policy={"max_retries": 1, "on_failed": "repair_skill_or_abort_safely"},
            ),
        ]
        return MissionGraph(
            mission_id=mission_id,
            goal=goal,
            nodes=nodes,
            edges=[
                MissionGraphEdge("open_map", "confirm_teleport"),
                MissionGraphEdge("confirm_teleport", "navigate_to_material"),
                MissionGraphEdge("navigate_to_material", "collect_material"),
            ],
            capsule_id="genshin",
            explanation="Genshin hard-embodied material flow: UI teleport, segment navigation, verified collection.",
        )
