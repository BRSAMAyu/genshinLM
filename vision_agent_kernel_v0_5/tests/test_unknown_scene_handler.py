"""Tests for UnknownSceneHandler — SPARKLE §11 safe exploration loop."""
from __future__ import annotations

from agent_kernel.types import Affordance, RuntimeOverride, SceneGraph, SceneObject
from agent_kernel.unknown_scene_handler import (
    ExplorationHypothesis,
    ProbeResult,
    UnknownSceneHandler,
)


def _make_scene(
    state: str = "unknown",
    objects: tuple[SceneObject, ...] = (),
    affordances: tuple[Affordance, ...] = (),
) -> SceneGraph:
    return SceneGraph(
        timestamp=1.0,
        scene_state=state,
        objects=objects,
        affordances=affordances,
    )


class TestUnknownSceneHandler:

    def test_empty_scene_produces_wait_hypothesis(self) -> None:
        handler = UnknownSceneHandler()
        sg = _make_scene()
        hyps = handler.observe_and_hypothesize(sg)
        assert len(hyps) == 1
        assert hyps[0].test_action == "wait_and_resample"

    def test_affordance_hypotheses_sorted_by_risk(self) -> None:
        handler = UnknownSceneHandler()
        low_aff = Affordance(affordance_id="a1", verb="inspect", target_object_id="o1", risk_level="low")
        high_aff = Affordance(affordance_id="a2", verb="attack", target_object_id="o2", risk_level="high")
        sg = _make_scene(affordances=(high_aff, low_aff))
        hyps = handler.observe_and_hypothesize(sg)
        assert len(hyps) == 2
        assert hyps[0].risk_level == "low"

    def test_no_affordance_inspects_objects(self) -> None:
        handler = UnknownSceneHandler()
        obj = SceneObject(object_id="o1", kind="button", label="Btn", bbox_norm=None)
        sg = _make_scene(objects=(obj,))
        hyps = handler.observe_and_hypothesize(sg)
        assert len(hyps) == 1
        assert "inspect" in hyps[0].test_action

    def test_probe_with_target_succeeds(self) -> None:
        handler = UnknownSceneHandler()
        obj = SceneObject(object_id="o1", kind="npc", label="NPC", bbox_norm=None)
        aff = Affordance(affordance_id="a1", verb="talk", target_object_id="o1", risk_level="low")
        sg = _make_scene(objects=(obj,), affordances=(aff,))
        hyps = handler.observe_and_hypothesize(sg)
        result = handler.probe(sg, hyps[0])
        assert result.effective
        assert result.learned_override is not None

    def test_probe_without_target_still_records(self) -> None:
        handler = UnknownSceneHandler()
        aff = Affordance(affordance_id="a1", verb="talk", target_object_id="missing", risk_level="low")
        sg = _make_scene(affordances=(aff,))
        hyp = ExplorationHypothesis(
            hypothesis_id="h1",
            description="test",
            test_action="talk:missing",
            expected_state_change="x",
            risk_level="low",
            confidence=0.5,
        )
        result = handler.probe(sg, hyp)
        assert not result.effective
        assert result.learned_override is None

    def test_probe_wait_action(self) -> None:
        handler = UnknownSceneHandler()
        sg = _make_scene()
        hyp = ExplorationHypothesis(
            hypothesis_id="h1", description="wait",
            test_action="wait_and_resample",
            expected_state_change="x",
        )
        result = handler.probe(sg, hyp)
        assert result.effective

    def test_should_escalate_no_hypotheses(self) -> None:
        handler = UnknownSceneHandler()
        assert handler.should_escalate([])

    def test_should_escalate_all_high_risk(self) -> None:
        handler = UnknownSceneHandler()
        hyps = [
            ExplorationHypothesis(
                hypothesis_id=f"h{i}", description="x",
                test_action="attack", expected_state_change="x",
                risk_level="high",
            )
            for i in range(3)
        ]
        assert handler.should_escalate(hyps)

    def test_should_escalate_max_probes_no_effect(self) -> None:
        handler = UnknownSceneHandler(max_probe_attempts=3)
        sg = _make_scene()
        hyp = ExplorationHypothesis(
            hypothesis_id="h1", description="x",
            test_action="talk:missing", expected_state_change="x",
        )
        for _ in range(3):
            handler.probe(sg, hyp)
        assert handler.should_escalate([hyp])

    def test_no_escalate_when_learning(self) -> None:
        handler = UnknownSceneHandler(max_probe_attempts=3)
        obj = SceneObject(object_id="o1", kind="npc", label="NPC", bbox_norm=None)
        aff = Affordance(affordance_id="a1", verb="talk", target_object_id="o1")
        sg = _make_scene(objects=(obj,), affordances=(aff,))
        hyp = ExplorationHypothesis(
            hypothesis_id="h1", description="x",
            test_action="talk:o1", expected_state_change="x",
        )
        for _ in range(3):
            handler.probe(sg, hyp)
        assert not handler.should_escalate([hyp])

    def test_request_user_help_returns_override(self) -> None:
        handler = UnknownSceneHandler()
        sg = _make_scene(state="mysterious_puzzle")
        override = handler.request_user_help(sg)
        assert isinstance(override, RuntimeOverride)
        assert override.source == "auto"
        assert "mysterious_puzzle" in override.new_value

    def test_learned_actions_persisted(self) -> None:
        handler = UnknownSceneHandler()
        obj = SceneObject(object_id="o1", kind="item", label="Item", bbox_norm=None)
        sg = _make_scene(state="puzzle_room", objects=(obj,))
        aff = Affordance(affordance_id="a1", verb="inspect", target_object_id="o1")
        hyp = ExplorationHypothesis(
            hypothesis_id="h1", description="x",
            test_action="inspect:o1", expected_state_change="x",
        )
        handler.probe(sg, hyp)
        learned = handler.get_learned_actions()
        assert "puzzle_room" in learned
        assert learned["puzzle_room"] == "inspect:o1"

    def test_probe_count(self) -> None:
        handler = UnknownSceneHandler()
        sg = _make_scene()
        hyp = ExplorationHypothesis(
            hypothesis_id="h1", description="x",
            test_action="wait_and_resample", expected_state_change="x",
        )
        assert handler.probe_count == 0
        handler.probe(sg, hyp)
        assert handler.probe_count == 1
        handler.probe(sg, hyp)
        assert handler.probe_count == 2

    def test_max_3_hypotheses(self) -> None:
        handler = UnknownSceneHandler()
        affs = tuple(
            Affordance(affordance_id=f"a{i}", verb=f"v{i}", target_object_id=f"o{i}")
            for i in range(5)
        )
        sg = _make_scene(affordances=affs)
        hyps = handler.observe_and_hypothesize(sg)
        assert len(hyps) <= 3
