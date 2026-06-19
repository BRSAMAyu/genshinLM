from __future__ import annotations

import pytest

from bagel.runtime import BagelRuntime
from planning.mainline.mainline_runner import MainlineRunner
from planning.mainline.mainline_skill_executor import MainlineSkillExecutor
from planning.mainline.mission_graph_v4 import (
    BeliefTemplate,
    ClaimContract,
    MissionEdgeV4,
    MissionGraphV4,
    MissionNodeV4,
)
from runtime.claim_worker import ClaimGraphWorker


class _Executor:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def execute_semantic(self, action: str, target: str, context: dict[str, object]) -> bool:
        self.calls.append((action, target, context))
        return self.ok

    def is_target_focused(self) -> bool:
        return True


def _node(node_id: str = "n1") -> MissionNodeV4:
    return MissionNodeV4(
        node_id=node_id,
        node_type="menu_step",
        skill_candidates=("open_map",),
        output_claims=(ClaimContract("screen_state_match", target="map"),),
        belief_templates=(
            BeliefTemplate(
                target_object="map_screen",
                causal_role="screen_state_hypothesis",
                hypothesis="opening the map should produce a map screen",
                falsification_condition="map screen is not visible after execution",
            ),
        ),
        metadata={"target": "map"},
    )


def test_mainline_skill_executor_records_success_in_bagel_and_claim_graph() -> None:
    semantic = _Executor(ok=True)
    bagel = BagelRuntime()
    claim_worker = ClaimGraphWorker(mission_id="test")
    skill_executor = MainlineSkillExecutor(
        semantic,
        bagel_runtime=bagel,
        claim_worker=claim_worker,
        mission_id="test",
    )

    data = skill_executor.execute_node_skill(_node())

    assert data["execution_success"] is True
    assert semantic.calls[0][0] == "open_map"
    fig = bagel.fig.snapshot()
    assert data["action_id"] in fig["actions"]
    assert f"fb_{data['action_id']}" in fig["feedbacks"]
    snapshot = claim_worker.snapshot()
    assert data["claim_id"] in snapshot["claims"]
    assert snapshot["claims"][data["claim_id"]] == "verified"


def test_mainline_skill_executor_raises_and_records_negative_feedback_on_failure() -> None:
    bagel = BagelRuntime()
    skill_executor = MainlineSkillExecutor(
        _Executor(ok=False),
        bagel_runtime=bagel,
        claim_worker=ClaimGraphWorker(mission_id="test"),
        mission_id="test",
    )

    with pytest.raises(RuntimeError):
        skill_executor.execute_node_skill(_node())

    fig = bagel.fig.snapshot()
    assert len(fig["actions"]) == 1
    assert len(fig["feedbacks"]) == 1
    feedback = next(iter(fig["feedbacks"].values()))
    assert feedback.polarity == "negative"


def test_mainline_runner_can_use_skill_executor_bridge() -> None:
    graph = MissionGraphV4(mission_id="mainline_bridge")
    graph.add_node(_node("start"))
    graph.add_node(_node("end"))
    graph.add_edge(MissionEdgeV4("start", "end"))

    semantic = _Executor(ok=True)
    bridge = MainlineSkillExecutor(
        semantic,
        bagel_runtime=BagelRuntime(),
        claim_worker=ClaimGraphWorker(mission_id="mainline_bridge"),
        mission_id="mainline_bridge",
    )
    result = MainlineRunner(skill_execute_fn=bridge.execute_node_skill).run(graph)

    assert result.success
    assert result.completed_nodes == ["start", "end"]
    assert [call[0] for call in semantic.calls] == ["open_map", "open_map"]


def test_mainline_skill_executor_default_path_is_claim_centric_without_bagel() -> None:
    semantic = _Executor(ok=True)
    skill_executor = MainlineSkillExecutor(
        semantic,
        claim_worker=ClaimGraphWorker(mission_id="claim_only"),
        mission_id="claim_only",
    )
    data = skill_executor.execute_node_skill(_node())

    assert data["execution_success"] is True
    assert data["claim_runtime_gate_allowed"] in {True, False}
    assert isinstance(data["claim_runtime_decision_memory"], dict)
