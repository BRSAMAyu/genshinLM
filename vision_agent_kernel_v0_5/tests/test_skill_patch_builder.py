"""Tests for SkillPatchBuilder — draft construction and serialization."""

from __future__ import annotations

import json

import pytest

from repair.repair_session import RepairSession
from repair.demo_segmenter import DemoSegmenter
from repair.skill_patch_builder import SkillPatchBuilder, SkillPatchDraft


class TestSkillPatchBuilderConstruction:
    def test_build_draft_from_session_with_demonstration_events(self):
        session = RepairSession(failure_signature_id="fs_100", skill_id="attack_combo")
        session.start_demonstration()
        session.record_action("aim", {"target": "enemy_1"})
        session.record_action("aim", {"target": "enemy_2"})
        session.record_action("fire", {"weapon": "sword"})
        session.propose_checkpoint({"target_eliminated": True})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        assert len(segments) == 2  # "aim" group + "fire" group

        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        assert draft.skill_id == "attack_combo"
        assert draft.source_failure_signature_id == "fs_100"
        assert len(draft.proposed_steps) == 2
        assert draft.proposed_steps[0]["action_type"] == "aim"
        assert draft.proposed_steps[1]["action_type"] == "fire"
        assert draft.status == "DRAFT"
        assert len(draft.demonstration_segment_ids) == 2

    def test_draft_has_correct_fields(self):
        session = RepairSession(failure_signature_id="fs_101", skill_id="defend")
        session.start_demonstration()
        session.record_action("block", {"direction": "forward"})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        # Required fields exist
        assert isinstance(draft.patch_id, str) and len(draft.patch_id) > 0
        assert isinstance(draft.skill_id, str) and draft.skill_id == "defend"
        assert isinstance(draft.source_failure_signature_id, str)
        assert isinstance(draft.source_run_id, (str, type(None)))
        assert isinstance(draft.demonstration_segment_ids, list)
        assert isinstance(draft.proposed_steps, list)
        assert isinstance(draft.verifier_contract, dict)
        assert isinstance(draft.safety, dict)
        assert isinstance(draft.validation, dict)
        assert draft.status == "DRAFT"
        assert isinstance(draft.created_at, float)

        # Safety defaults
        assert draft.safety["requires_user_approval"] is True
        assert draft.safety["dry_run_required"] is True
        assert draft.safety["safe_window_required"] is False

        # Validation defaults
        assert draft.validation["dry_run_passed"] is False
        assert draft.validation["verifier_replay_passed"] is False
        assert draft.validation["benchmark_before"] is None
        assert draft.validation["benchmark_after"] is None

    def test_draft_json_serializable(self):
        session = RepairSession(failure_signature_id="fs_102", skill_id="dodge")
        session.start_demonstration()
        session.record_action("dodge", {"direction": "left", "distance": 5})
        session.record_action("dodge", {"direction": "right", "distance": 3})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        # Serialize via to_dict
        as_dict = draft.to_dict()
        serialized = json.dumps(as_dict, ensure_ascii=False)
        assert isinstance(serialized, str)

        # Deserialize and verify roundtrip
        deserialized = json.loads(serialized)
        assert deserialized["patch_id"] == draft.patch_id
        assert deserialized["skill_id"] == "dodge"
        assert deserialized["status"] == "DRAFT"
        assert len(deserialized["proposed_steps"]) == 1  # all dodge actions merged into one segment
        assert deserialized["proposed_steps"][0]["action_type"] == "dodge"

    def test_build_with_empty_segments(self):
        """Builder should still produce a valid draft with empty segments."""
        session = RepairSession(failure_signature_id="fs_103", skill_id="empty_skill")
        # No demonstration events
        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        assert segments == []

        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        assert draft.skill_id == "empty_skill"
        assert draft.proposed_steps == []
        assert draft.demonstration_segment_ids == []
        assert draft.status == "DRAFT"

    def test_build_with_multiple_demonstrations(self):
        session = RepairSession(failure_signature_id="fs_104", skill_id="multi_demo")
        session.start_demonstration()
        session.record_action("scan", {"area": "north"})
        session.start_demonstration()
        session.record_action("scan", {"area": "south"})
        session.record_action("attack", {"target": "enemy"})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)

        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        assert len(draft.proposed_steps) == 2  # "scan" + "attack"
        assert draft.verifier_contract == {}  # no checkpoints proposed
