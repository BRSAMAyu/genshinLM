"""Tests for Skill Induction v2 pipeline."""
from __future__ import annotations

import pytest

from learning.skill_induction.trace_recorder import (
    RecordedAction,
    TraceRecorder,
    TraceSession,
)
from learning.skill_induction.episode_segmenter import EpisodeSegmenter, Episode
from learning.skill_induction.anchor_binder import AnchorBinder, BindingResult
from learning.skill_induction.promotion_gate import PromotionGate, PromotionResult
from learning.skill_induction.pipeline import InductionPipeline, InductionResult
from skills.registry import SkillRegistry
from skills.schema import SkillDef, SkillProducedClaim


# -- Helpers --

def _action(
    action_type: str = "click_anchor",
    target: str = "btn",
    screen_state: str = "dialogue",
    anchor_id: str = "",
    x: float = 0.0,
    y: float = 0.0,
) -> RecordedAction:
    return RecordedAction(
        action_id=f"act_{action_type}",
        action_type=action_type,
        target=target,
        screen_state=screen_state,
        timestamp=0.0,
        anchor_id=anchor_id,
        x=x,
        y=y,
    )


def _successful_session(anchor: bool = True) -> TraceSession:
    """Build a session with 3 dialogue actions."""
    recorder = TraceRecorder()
    session = recorder.start_session("dialogue_advance", screen_state="dialogue")
    recorder.record_action(session, "click_anchor", "dialogue_continue",
                           screen_state="dialogue",
                           anchor_id="dialogue_continue" if anchor else "")
    if not anchor:
        # Add coordinate fallback
        session.actions[-1] = _action("click", "btn", "dialogue", x=0.5, y=0.7)
    recorder.record_action(session, "click_anchor", "dialogue_continue",
                           screen_state="dialogue",
                           anchor_id="dialogue_continue" if anchor else "")
    recorder.end_session(session, success=True)
    return session


# -- TraceRecorder tests --

class TestTraceRecorder:
    def test_start_and_end_session(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("test_goal", screen_state="world")
        assert session.goal == "test_goal"
        recorder.end_session(session, success=True)
        assert session.success
        assert session.duration >= 0

    def test_record_actions(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("test")
        recorder.record_action(session, "click_anchor", "btn", anchor_id="btn")
        recorder.record_action(session, "press_key", "esc")
        assert len(session.actions) == 2
        assert session.actions[0].anchor_id == "btn"

    def test_completed_sessions(self) -> None:
        recorder = TraceRecorder()
        s1 = recorder.start_session("a")
        recorder.end_session(s1, success=True)
        s2 = recorder.start_session("b")
        recorder.end_session(s2, success=False)
        assert len(recorder.completed_sessions()) == 1

    def test_has_semantic_anchors(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("test")
        recorder.record_action(session, "click_anchor", "btn", anchor_id="btn")
        assert session.has_semantic_anchors

    def test_no_anchors(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("test")
        recorder.record_action(session, "click", "btn", x=0.5, y=0.5)
        assert not session.has_semantic_anchors


# -- EpisodeSegmenter tests --

class TestEpisodeSegmenter:
    def test_single_episode(self) -> None:
        session = _successful_session()
        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        assert len(episodes) == 1
        assert episodes[0].screen_state == "dialogue"

    def test_split_on_state_change(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("test")
        recorder.record_action(session, "click", "a", screen_state="world")
        recorder.record_action(session, "click", "b", screen_state="world")
        recorder.record_action(session, "click", "c", screen_state="dialogue")
        recorder.record_action(session, "click", "d", screen_state="dialogue")
        recorder.end_session(session, success=True)

        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        assert len(episodes) == 2
        assert episodes[0].screen_state == "world"
        assert episodes[1].screen_state == "dialogue"

    def test_empty_session(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("empty")
        recorder.end_session(session, success=True)
        segmenter = EpisodeSegmenter()
        assert segmenter.segment(session) == []

    def test_episode_has_anchors(self) -> None:
        session = _successful_session(anchor=True)
        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        assert episodes[0].has_anchors

    def test_episode_no_anchors(self) -> None:
        session = _successful_session(anchor=False)
        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        assert not episodes[0].has_anchors


# -- AnchorBinder tests --

class TestAnchorBinder:
    def test_bind_with_anchors(self) -> None:
        session = _successful_session(anchor=True)
        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        binder = AnchorBinder()
        result = binder.bind(episodes[0])
        assert result.skill is not None
        assert not result.coordinate_only
        assert result.bound_anchor_count > 0
        assert result.skill.tier == "draft"

    def test_bind_coordinate_only(self) -> None:
        session = _successful_session(anchor=False)
        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        binder = AnchorBinder()
        result = binder.bind(episodes[0])
        assert result.skill is not None
        assert result.coordinate_only
        assert result.skill.tier == "raw_trace"

    def test_bind_empty_episode(self) -> None:
        binder = AnchorBinder()
        empty = Episode("ep1", "test", "world", ())
        result = binder.bind(empty)
        assert result.skill is None

    def test_inferred_claim_for_dialogue(self) -> None:
        session = _successful_session(anchor=True)
        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        binder = AnchorBinder()
        result = binder.bind(episodes[0])
        assert result.skill is not None
        assert len(result.skill.produced_claims) >= 1
        assert result.skill.produced_claims[0].claim_type == "dialogue_advanced"

    def test_required_anchors_populated(self) -> None:
        session = _successful_session(anchor=True)
        segmenter = EpisodeSegmenter()
        episodes = segmenter.segment(session)
        binder = AnchorBinder()
        result = binder.bind(episodes[0])
        assert result.skill is not None
        assert "dialogue_continue" in result.skill.applicability.required_anchors


# -- PromotionGate tests --

class TestPromotionGate:
    def test_promote_draft_to_experimental(self) -> None:
        registry = SkillRegistry()
        gate = PromotionGate(registry)
        skill = SkillDef(
            skill_id="test_skill", tier="draft",
            steps=(SkillDef.from_dict({"skill_id": "x", "steps": [{"action": "click_anchor", "target": "btn"}]}).steps[0],),
            produced_claims=(SkillProducedClaim("test_claim"),),
        )
        result = gate.try_promote(skill, "experimental")
        assert result.success
        assert registry.get("test_skill").tier == "experimental"

    def test_raw_trace_cannot_promote(self) -> None:
        registry = SkillRegistry()
        gate = PromotionGate(registry)
        # raw_trace with no steps → blocked by can_promote_to
        skill = SkillDef(skill_id="raw", tier="raw_trace")
        result = gate.try_promote(skill, "draft")
        assert not result.success

    def test_raw_trace_with_semantic_steps_can_be_promoted(self) -> None:
        """Promotion is blocked by coordinate-only evidence, not by tier label alone."""
        registry = SkillRegistry()
        gate = PromotionGate(registry)
        skill = SkillDef(
            skill_id="raw_with_steps", tier="raw_trace",
            steps=(SkillDef.from_dict({"skill_id": "x", "steps": [{"action": "click_anchor", "target": "btn"}]}).steps[0],),
        )
        result = gate.try_promote(skill, "draft")
        assert result.success

    def test_evaluate_next_tier(self) -> None:
        registry = SkillRegistry()
        gate = PromotionGate(registry)
        skill = SkillDef(
            skill_id="test", tier="draft",
            produced_claims=(SkillProducedClaim("x"),),
        )
        target = gate.evaluate(skill)
        assert target == "experimental"

    def test_evaluate_coordinate_only_raw_trace_returns_none(self) -> None:
        registry = SkillRegistry()
        gate = PromotionGate(registry)
        skill = SkillDef(
            skill_id="raw_with_steps", tier="raw_trace",
            steps=(SkillDef.from_dict({"skill_id": "x", "steps": [{"action": "click_anchor", "target": "btn"}]}).steps[0],),
            metadata={"coordinate_only": True},
        )
        assert gate.evaluate(skill) is None

    def test_evaluate_candidate_reachable(self) -> None:
        registry = SkillRegistry()
        gate = PromotionGate(registry)
        skill = SkillDef(
            skill_id="test", tier="experimental",
            produced_claims=(SkillProducedClaim("x", verifier_recipe="verify_x"),),
        )
        target = gate.evaluate(skill)
        assert target == "candidate"


# -- Full pipeline tests --

class TestInductionPipeline:
    def test_process_successful_session(self) -> None:
        registry = SkillRegistry()
        pipeline = InductionPipeline(registry)
        session = _successful_session(anchor=True)
        result = pipeline.process_session(session)
        assert result.skills_produced >= 1
        assert result.coordinate_only_rejected == 0

    def test_process_coordinate_only(self) -> None:
        registry = SkillRegistry()
        pipeline = InductionPipeline(registry)
        session = _successful_session(anchor=False)
        result = pipeline.process_session(session)
        assert result.coordinate_only_rejected >= 1
        # Raw trace should still be stored
        assert registry.size >= 1

    def test_process_failed_session(self) -> None:
        pipeline = InductionPipeline()
        recorder = TraceRecorder()
        session = recorder.start_session("fail")
        recorder.end_session(session, success=False)
        result = pipeline.process_session(session)
        assert result.skills_produced == 0

    def test_process_multi_episode(self) -> None:
        registry = SkillRegistry()
        pipeline = InductionPipeline(registry)
        recorder = TraceRecorder()
        session = recorder.start_session("multi", screen_state="world")
        recorder.record_action(session, "click_anchor", "npc",
                               screen_state="world", anchor_id="npc_marker")
        recorder.record_action(session, "click_anchor", "continue",
                               screen_state="dialogue", anchor_id="dialogue_continue")
        recorder.end_session(session, success=True)
        result = pipeline.process_session(session)
        # Should produce 2 episodes
        assert result.skills_produced >= 1

    def test_process_session_can_iteratively_promote_to_candidate(self) -> None:
        registry = SkillRegistry()
        pipeline = InductionPipeline(registry)
        session = _successful_session(anchor=True)
        result = pipeline.process_session(session, target_tier="candidate")
        assert result.skills_produced == 1
        skill = registry.all_skills()[0]
        assert skill.tier == "candidate"

    def test_empty_action_screen_state_inherits_session_state(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("dialogue_advance", screen_state="dialogue")
        recorder.record_action(session, "click_anchor", "continue", screen_state="", anchor_id="dialogue_continue")
        recorder.end_session(session, success=True)
        episodes = EpisodeSegmenter().segment(session)
        assert episodes[0].screen_state == "dialogue"

    def test_draft_with_coordinate_only_metadata_cannot_promote(self) -> None:
        registry = SkillRegistry()
        gate = PromotionGate(registry)
        skill = SkillDef(
            skill_id="bad_draft",
            tier="draft",
            steps=(SkillDef.from_dict({"skill_id": "x", "steps": [{"action": "click_anchor", "target": ""}]}).steps[0],),
            metadata={"coordinate_only": True},
        )
        result = gate.try_promote(skill, "experimental")
        assert not result.success
        assert "coordinate" in result.reason
