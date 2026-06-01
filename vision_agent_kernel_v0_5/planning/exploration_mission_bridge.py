"""Bridge ExplorationEngine targets to MissionGraphV4 executable nodes.

Converts exploration plans (waypoint sweep, oculus collection, region
progression) into claim-gated MissionNodeV4 nodes that the MainlineRunner
can execute through SkillRegistry → ExplorationSkillAdapter.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planning.exploration_engine import ExplorationEngine

from planning.mainline.mission_graph_v4 import (
    ClaimContract,
    FallbackDecl,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
    NodeBudget,
)
from runtime.claim_runtime import RiskLevel

log = logging.getLogger(__name__)

# ExplorationObjective value -> skill candidates for SkillRegistry routing
_OBJECTIVE_SKILLS: dict[str, tuple[str, ...]] = {
    "waypoint_unlock": ("explore_activate_waypoint",),
    "chest_open": ("explore_open_chest",),
    "oculus_collect": ("explore_collect_oculus",),
    "statue_activate": ("explore_activate_waypoint",),
    "puzzle_solve": ("explore_puzzle_monument",),
    "domain_unlock": ("explore_interact",),
    "challenge_complete": ("explore_timed_challenge",),
}

# Risk level per objective type
_OBJECTIVE_RISK: dict[str, RiskLevel] = {
    "puzzle_solve": "high",
    "challenge_complete": "high",
    "oculus_collect": "medium",
    "domain_unlock": "medium",
}


def build_exploration_graph(
    engine: ExplorationEngine,
    current_region: str = "mondstadt",
    current_ar: int = 1,
    mission_id: str = "exploration",
    time_budget_min: float = 30.0,
    max_targets: int = 20,
) -> MissionGraphV4:
    """Build a MissionGraphV4 from ExplorationEngine plan.

    Uses ``engine.plan_session()`` to get prioritized targets, then converts
    each ``ExplorationTarget`` into a claim-gated ``MissionNodeV4``.
    """
    from planning.exploration_engine import ExplorationEngine as _EE
    from planning.exploration_engine import Region

    graph = MissionGraphV4(mission_id=mission_id)

    # Resolve Region enum from string
    region = _resolve_region(current_region)

    plan = engine.plan_session(
        current_region=region,
        current_ar=current_ar,
        time_budget_min=time_budget_min,
    )

    targets = plan.targets[:max_targets]

    if not targets:
        log.info("[ExplorationBridge] no targets to build graph for")
        return graph

    prev_node_id: str | None = None

    for idx, target in enumerate(targets):
        obj_value = target.objective.value
        skills = _OBJECTIVE_SKILLS.get(obj_value, ("explore_interact",))
        risk = _OBJECTIVE_RISK.get(obj_value, "low")

        node = MissionNodeV4(
            node_id=f"exploration_{idx}_{target.target_id}",
            node_type=f"exploration_{obj_value}",
            risk_level=risk,
            skill_candidates=skills,
            input_claims=(
                ClaimContract(
                    claim_type="screen_state",
                    target="overworld",
                    required_status="verified",
                    claim_role="informational",
                ),
            ),
            output_claims=(
                ClaimContract(
                    claim_type="exploration_completion",
                    target=target.target_id,
                    required_status="completed",
                    claim_role="terminal",
                ),
            ),
            fallbacks=(
                FallbackDecl(
                    recovery_recipe="retry_approach",
                    replan_policy="skip_and_continue",
                ),
            ),
            budgets=NodeBudget(
                max_retries=3,
                max_duration_sec=max(60.0, target.estimated_time_sec * 3),
            ),
            metadata={
                "target_id": target.target_id,
                "objective": obj_value,
                "region": target.region.value,
                "priority": target.priority,
            },
        )

        graph.add_node(node)

        # Chain nodes sequentially
        if prev_node_id is not None:
            graph.add_edge(MissionEdgeV4(
                from_node=prev_node_id,
                to_node=node.node_id,
                condition="previous_completed",
            ))

        prev_node_id = node.node_id

    log.info(
        "[ExplorationBridge] built graph with %d exploration nodes for mission %s",
        len(targets), mission_id,
    )
    return graph


def _resolve_region(region_str: str):
    """Resolve a region string to a Region enum value."""
    from planning.exploration_engine import Region

    try:
        return Region(region_str)
    except ValueError:
        return Region.MONDSTADT
