"""CerebrumAgentImpl — concrete L7-L8 CerebrumAgent.

Implements strategic planning, failure diagnosis, and visual puzzle solving
as defined in the ADR L7-L8 layer.

L7-L8 runs at 0.1-0.2Hz (cloud-first with offline fallback), providing:
- Mission compilation: goal → MissionGraph (plan DAG)
- Failure diagnosis: failed node + screenshot → RepairPatch
- Visual puzzle solving: image → action sequence
"""
from __future__ import annotations

import logging
import uuid

from agent_kernel.protocols import CerebrumAgent as CerebrumAgentProtocol
from agent_kernel.types import (
    AgentGoal,
    MissionGraph,
    MissionNode,
    RepairPatch,
)

log = logging.getLogger(__name__)


class CerebrumAgentImpl(CerebrumAgentProtocol):
    """Concrete L7-L8 CerebrumAgent.

    Provides rule-based strategic planning with LLM/VLM fallback.
    In production, the cloud-first path uses a remote API.
    This implementation provides the offline fallback: keyword-based
    goal decomposition and pattern-based failure diagnosis.

    Usage:
        agent = CerebrumAgentImpl()
        graph = agent.compile_mission(goal)
        patch = agent.diagnose_failure(node, screenshot, error)
        actions = agent.solve_visual_puzzle(image, description)
    """

    # Goal → skill intent mapping for mission compilation
    _GOAL_SKILL_MAP: dict[str, list[str]] = {
        "character_level_up": ["open_character_menu", "select_character", "click_level_up", "confirm_materials", "verify_level"],
        "character_ascend": ["open_character_menu", "select_character", "click_ascend", "confirm_materials", "wait_animation"],
        "weapon_manage": ["open_backpack", "select_weapon", "equip_weapon", "close_menu"],
        "artifact_manage": ["open_backpack", "select_artifact", "equip_artifact", "close_menu"],
        "talent_upgrade": ["open_character_menu", "select_talents", "select_talent", "click_upgrade", "confirm"],
        "wish_pull": ["open_wish", "select_banner", "pull", "wait_animation", "verify_result"],
        "combat": ["approach_enemy", "enter_combat", "execute_rotation", "verify_victory"],
        "explore": ["navigate_to_area", "scan_for_items", "collect_items"],
        "quest": ["open_quest_log", "select_quest", "follow_marker", "complete_objective"],
        "teleport": ["open_map", "select_waypoint", "confirm_teleport", "wait_loading"],
        "daily": ["open_adventure_handbook", "complete_daily", "claim_rewards"],
        "mainline": ["follow_quest_marker", "handle_dialog", "complete_objective"],
    }

    # Failure pattern → repair mapping
    _FAILURE_PATTERNS: dict[str, RepairPatch] = {
        "timeout": RepairPatch(
            replan_required=True,
            inject_skills=("return_to_safe_anchor_v1",),
            explanation="Timeout suggests navigation stuck — return to anchor and retry",
        ),
        "element not found": RepairPatch(
            replan_required=False,
            runtime_overrides=(("retry_count", "3"),),
            explanation="Element not found — retry with re-sampling",
        ),
        "loading_stuck": RepairPatch(
            inject_skills=("return_to_safe_anchor_v1",),
            explanation="Loading screen stuck — teleport to safe anchor",
        ),
        "combat_death": RepairPatch(
            replan_required=True,
            inject_skills=("return_to_safe_anchor_v1", "heal_team"),
            explanation="Character died — retreat, heal, and replan approach",
        ),
    }

    def compile_mission(self, goal: AgentGoal) -> MissionGraph:
        """Compile a goal into a MissionGraph (plan DAG)."""
        skill_intents = self._GOAL_SKILL_MAP.get(goal.goal_id, ["approach", "interact", "verify"])
        nodes = tuple(
            MissionNode(
                node_id=f"n{i}",
                skill_intent=intent,
                preconditions=(f"n{i-1}" if i > 0 else "",),
                expected_state=f"after_{intent}",
                risk_level="medium" if "combat" in intent else "low",
            )
            for i, intent in enumerate(skill_intents)
        )
        edges = tuple(
            (f"n{i}", f"n{i+1}")
            for i in range(len(nodes) - 1)
        )
        return MissionGraph(
            graph_id=f"mission_{uuid.uuid4().hex[:8]}",
            nodes=nodes,
            edges=edges,
            current_node_index=0,
        )

    def diagnose_failure(
        self,
        failed_node: MissionNode,
        screenshot: object,
        error_trace: str,
    ) -> RepairPatch:
        """Diagnose why a mission node failed. Returns a repair patch."""
        error_lower = error_trace.lower()

        for pattern, patch in self._FAILURE_PATTERNS.items():
            if pattern in error_lower:
                log.info("[L7-L8] Diagnosed failure as '%s' for node %s", pattern, failed_node.node_id)
                return patch

        # Generic fallback
        return RepairPatch(
            replan_required=True,
            explanation=f"Unknown failure at {failed_node.node_id}: {error_trace[:200]}",
        )

    def solve_visual_puzzle(
        self,
        puzzle_image: object,
        scene_description: str,
    ) -> tuple[str, ...]:
        """Solve a visual puzzle using multi-modal reasoning.

        Returns a tuple of action descriptions to execute.
        In production, this calls VLM. Offline fallback returns
        generic exploration actions.
        """
        log.info("[L7-L8] Visual puzzle solving requested: %s", scene_description[:100])
        # Offline fallback: return generic exploration actions
        return (
            "observe_puzzle_elements",
            "identify_interactable_objects",
            "try_interact_with_nearest",
        )
