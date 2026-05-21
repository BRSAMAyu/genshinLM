from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from execution.semantic_action import ActionContract, SemanticAction
from planning.capability_planner import PlanProposal
from planning.mission_queue import MissionGoal, MissionNode, MissionQueue


MissionNodeType = Literal[
    "observe",
    "ui_interact",
    "navigate",
    "combat",
    "collect",
    "dialog",
    "craft",
    "claim_reward",
    "verify",
    "repair",
    "fallback_agent",
]


@dataclass(frozen=True, slots=True)
class MissionGraphNode:
    node_id: str
    node_type: MissionNodeType
    skill_binding: str | None
    verifier: str
    preconditions: list[str] = field(default_factory=list)
    action_contracts: list[ActionContract] = field(default_factory=list)
    failure_policy: dict[str, Any] = field(default_factory=dict)
    checkpoint: bool = True
    requires_user_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class MissionGraphEdge:
    source: str
    target: str
    condition: str = "success"


@dataclass(frozen=True, slots=True)
class MissionGraph:
    mission_id: str
    goal: MissionGoal
    nodes: list[MissionGraphNode]
    edges: list[MissionGraphEdge]
    capsule_id: str
    explanation: str

    def to_queue(self) -> MissionQueue:
        return MissionQueue(
            mission_id=self.mission_id,
            goal=self.goal,
            nodes=[
                MissionNode(
                    id=node.node_id,
                    type=node.node_type,
                    skill_binding=node.skill_binding,
                    verifier=node.verifier,
                    failure_policy=node.failure_policy or {"max_retries": 1, "on_failed": "recover_or_escalate"},
                )
                for node in self.nodes
            ],
            requires_user_confirmation=any(node.requires_user_confirmation for node in self.nodes),
        )


class MissionDAGCompiler:
    """Compile selected skills into a verifiable sequential DAG.

    This is deliberately deterministic; LLMs may propose goals, but this compiler
    owns the executable graph shape.
    """

    def compile(
        self,
        proposal: PlanProposal,
        goal: MissionGoal,
        mission_id: str = "compiled_mission",
    ) -> MissionGraph:
        nodes: list[MissionGraphNode] = []
        edges: list[MissionGraphEdge] = []
        previous: str | None = None
        for index, skill in enumerate(proposal.selected_skills):
            node_id = f"node_{index + 1}_{skill.skill_id}"
            verifier = skill.verifiers[0] if skill.verifiers else ""
            node_type = self._node_type(skill.kind, skill.planner_tags)
            action = SemanticAction(
                action_id=f"action_{node_id}",
                kind="system",
                intent=f"run_skill:{skill.skill_id}",
                target=skill.skill_id,
                requires_physical_input=False,
            )
            contract = ActionContract(
                action_id=action.action_id,
                semantic_action=action,
                verifier_contract={"verifier_id": verifier, "success_criteria": ["skill_completed"]} if verifier else {},
                fallback_policy={"on_failed": "recover_or_escalate"},
                risk_level=skill.risk_level if skill.risk_level in {"low", "medium", "high", "human_confirm"} else "medium",
            )
            nodes.append(
                MissionGraphNode(
                    node_id=node_id,
                    node_type=node_type,
                    skill_binding=skill.skill_id,
                    verifier=verifier,
                    preconditions=list(skill.capabilities_required),
                    action_contracts=[contract],
                    failure_policy={"max_retries": 1, "on_failed": "recover_or_escalate"},
                    requires_user_confirmation=skill.risk_level == "human_confirm",
                )
            )
            if previous is not None:
                edges.append(MissionGraphEdge(previous, node_id))
            previous = node_id

        return MissionGraph(
            mission_id=mission_id,
            goal=goal,
            nodes=nodes,
            edges=edges,
            capsule_id=proposal.capsule_id,
            explanation=(
                f"Compiled {len(nodes)} node(s) from selected skills "
                f"{proposal.selected_skill_ids}; verifier coverage={proposal.verifier_coverage:.2f}"
            ),
        )

    def _node_type(self, kind: str, tags: list[str]) -> MissionNodeType:
        haystack = " ".join([kind, *tags]).lower()
        if "combat" in haystack:
            return "combat"
        if "nav" in haystack or "route" in haystack:
            return "navigate"
        if "dialog" in haystack:
            return "dialog"
        if "collection" in haystack or "reward" in haystack:
            return "claim_reward"
        if "menu" in haystack or "ui" in haystack:
            return "ui_interact"
        return "verify"
