from __future__ import annotations

from planning.mainline.active_quest_context import ActiveQuestContext
from planning.mainline.mainline_runner import MainlineAutonomyLoop
from planning.mainline.mission_graph_v4 import (
    BeliefTemplate,
    ClaimContract,
    FallbackDecl,
    MissionGraphV4,
    MissionNodeV4,
)
from planning.mainline.mission_graph_validator_v4 import MissionGraphValidatorV4
from skills.applicability import ReliabilitySample, SkillReliabilityGate, wilson_lower_bound


def _context() -> ActiveQuestContext:
    return ActiveQuestContext(
        quest_id="quest_demo",
        quest_title="Demo",
        objective_text="Talk to Amber",
        objective_type="dialog",
        confidence=0.9,
    )


def _graph() -> MissionGraphV4:
    graph = MissionGraphV4(mission_id="quest_demo")
    graph.add_node(MissionNodeV4(
        node_id="talk",
        node_type="dialog",
        risk_level="medium",
        output_claims=(ClaimContract("quest_objective_changed", "active_quest.objective_text"),),
        fallbacks=(FallbackDecl("UI_LOST_RECOVERY"),),
        belief_templates=(BeliefTemplate(
            "quest objective",
            "objective_type_hypothesis",
            "objective requires dialogue",
            "objective text does not change after dialogue",
        ),),
        expected_verifier_bundle="quest_objective_delta.default",
        metadata={"requires_bagel_belief": True},
    ))
    return graph


def test_required_bagel_belief_template_validation() -> None:
    graph = MissionGraphV4()
    graph.add_node(MissionNodeV4(
        node_id="bad",
        node_type="dialog",
        output_claims=(ClaimContract("quest_objective_changed"),),
        metadata={"requires_bagel_belief": True},
    ))
    issues = MissionGraphValidatorV4().validate(graph)
    assert any(i.rule == "required_belief_template" and i.severity == "error" for i in issues)


def test_mainline_autonomy_loop_commits_beliefs_and_checkpoints() -> None:
    loop = MainlineAutonomyLoop()
    result = loop.run_once(initial_context=_context(), graph=_graph())
    assert result.success
    assert result.phase == "completed"
    assert result.checkpoint.completed_nodes == ("talk",)
    assert "talk_belief_0" in loop.bagel.fig.snapshot()["beliefs"]


def test_reliability_gate_degrades_low_wilson_bound() -> None:
    gate = SkillReliabilityGate(min_lower_bound=0.70)
    route, lower = gate.decide(ReliabilitySample(successes=1, attempts=5), risk_level="high")
    assert lower == wilson_lower_bound(1, 5)
    assert route in {"exploration", "human-review-needed"}
