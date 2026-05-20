"""Tests for the repair session, demo segmenter, skill patch builder, and benchmark runner."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.state_bus import StateBus
from repair.repair_session import RepairEvent, RepairSession
from repair.demo_segmenter import DemoSegment, DemoSegmenter
from repair.skill_patch_builder import SkillPatchBuilder, SkillPatchDraft
from repair.repair_validator import RepairValidator
from repair.repair_benchmark_runner import BenchmarkDelta, RepairBenchmarkRunner
from learning.evolution_engine import EvolutionEngine


# ---------------------------------------------------------------------------
# RepairSession
# ---------------------------------------------------------------------------

class TestRepairSession:
    def test_records_demonstration_events(self):
        session = RepairSession(failure_signature_id="fs_001", skill_id="combat_strike")
        demo_id = session.start_demonstration()
        action_id = session.record_action("move_to_target", {"x": 100, "y": 200})
        checkpoint_id = session.propose_checkpoint({"target_visible": True})
        complete_event = session.complete_repair()

        events = session.events
        assert len(events) == 4
        assert events[0].event_type == "demonstration_start"
        assert events[0].event_id == demo_id
        assert events[1].event_type == "action_recorded"
        assert events[1].event_id == action_id
        assert events[2].event_type == "checkpoint_proposed"
        assert events[2].event_id == checkpoint_id
        assert events[3].event_type == "repair_complete"
        assert events[3].event_id == complete_event.event_id

    def test_demonstration_ids(self):
        session = RepairSession(failure_signature_id="fs_002", skill_id="dodge_roll")
        session.start_demonstration()
        session.start_demonstration()
        session.start_demonstration()

        assert len(session.demonstration_ids) == 3
        for did in session.demonstration_ids:
            assert isinstance(did, str) and len(did) > 0

    def test_session_has_unique_ids(self):
        s1 = RepairSession(failure_signature_id="fs_a", skill_id="a")
        s2 = RepairSession(failure_signature_id="fs_b", skill_id="b")
        assert s1.session_id != s2.session_id

    def test_events_property_returns_copy(self):
        session = RepairSession(failure_signature_id="fs_003", skill_id="k")
        session.start_demonstration()
        events_ref = session.events
        events_ref.clear()
        assert len(session.events) == 1  # original not affected


# ---------------------------------------------------------------------------
# DemoSegmenter
# ---------------------------------------------------------------------------

class TestDemoSegmenter:
    def _make_action_event(self, action_type: str, params: dict) -> RepairEvent:
        return RepairEvent(
            event_id=f"evt_{action_type}",
            session_id="sess_1",
            event_type="action_recorded",
            payload={"action_type": action_type, "params": params},
            created_at=0.0,
        )

    def test_segments_events_into_demo_segments(self):
        session = RepairSession(failure_signature_id="fs_010", skill_id="combat")
        session.start_demonstration()
        session.record_action("aim", {"target_x": 50})
        session.record_action("aim", {"target_x": 60})
        session.record_action("fire", {"weapon": "bow"})
        session.complete_repair()

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)

        assert len(segments) == 2
        assert segments[0].action_type == "aim"
        assert segments[1].action_type == "fire"

    def test_empty_events_produce_no_segments(self):
        session = RepairSession(failure_signature_id="fs_011", skill_id="noop")
        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        assert segments == []

    def test_single_action_type_produces_one_segment(self):
        events = [
            self._make_action_event("move", {"dx": 10}),
            self._make_action_event("move", {"dx": 20}),
            self._make_action_event("move", {"dx": 30}),
        ]
        segmenter = DemoSegmenter()
        segments = segmenter.segment(events)
        assert len(segments) == 1
        assert segments[0].action_type == "move"
        # Params should be merged
        assert segments[0].params.get("dx") == 30  # last write wins in merge


# ---------------------------------------------------------------------------
# SkillPatchBuilder
# ---------------------------------------------------------------------------

class TestSkillPatchBuilder:
    def test_builds_draft_from_session_with_demonstration(self):
        session = RepairSession(failure_signature_id="fs_020", skill_id="heal_skill")
        session.start_demonstration()
        session.record_action("cast_spell", {"spell": "heal"})
        session.record_action("move", {"target": "ally"})
        session.propose_checkpoint({"hp_restored": True})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)

        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        assert draft.skill_id == "heal_skill"
        assert draft.source_failure_signature_id == "fs_020"
        assert draft.status == "DRAFT"
        assert len(draft.proposed_steps) == 2
        assert draft.safety["requires_user_approval"] is True

    def test_draft_has_correct_fields(self):
        session = RepairSession(failure_signature_id="fs_021", skill_id="skill_x")
        session.start_demonstration()
        session.record_action("jump", {"height": 5})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        assert isinstance(draft.patch_id, str) and len(draft.patch_id) > 0
        assert isinstance(draft.created_at, float)
        assert isinstance(draft.demonstration_segment_ids, list)
        assert isinstance(draft.proposed_steps, list)
        assert isinstance(draft.verifier_contract, dict)
        assert isinstance(draft.safety, dict)
        assert isinstance(draft.validation, dict)

    def test_draft_json_serializable(self):
        session = RepairSession(failure_signature_id="fs_022", skill_id="skill_y")
        session.start_demonstration()
        session.record_action("dash", {"direction": "forward"})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        serialized = json.dumps(draft.to_dict())
        assert isinstance(serialized, str)
        deserialized = json.loads(serialized)
        assert deserialized["skill_id"] == "skill_y"
        assert deserialized["status"] == "DRAFT"


# ---------------------------------------------------------------------------
# Draft status lifecycle
# ---------------------------------------------------------------------------

class TestDraftLifecycle:
    def test_draft_status_lifecycle(self):
        """DRAFT -> SANDBOX_VALIDATED -> APPROVED."""
        session = RepairSession(failure_signature_id="fs_030", skill_id="lifecycle_skill")
        session.start_demonstration()
        session.record_action("attack", {"target": "enemy"})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        assert draft.status == "DRAFT"

        # Validate dry-run
        validator = RepairValidator()
        assert validator.validate_dry_run(draft) is True
        draft.status = "SANDBOX_VALIDATED"

        assert draft.status == "SANDBOX_VALIDATED"

        # Approve
        draft.status = "APPROVED"
        assert draft.status == "APPROVED"

    def test_draft_cannot_be_applied_without_approval(self):
        """Only APPROVED drafts should be considered applied."""
        session = RepairSession(failure_signature_id="fs_031", skill_id="approval_skill")
        session.start_demonstration()
        session.record_action("wait", {"duration_ms": 500})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)

        # Draft is DRAFT, not APPROVED or APPLIED
        assert draft.status == "DRAFT"
        assert draft.status not in ("APPROVED", "APPLIED")

        # Even after validation, it's not approved
        draft.status = "SANDBOX_VALIDATED"
        assert draft.status not in ("APPROVED", "APPLIED")

    def test_benchmark_delta_computed_from_before_after(self):
        runner = RepairBenchmarkRunner()
        before = runner.run_before("combat_skill")
        assert before["pass_rate"] == 0.0
        assert before["failure_count"] == 1

        # Create a validated patch
        session = RepairSession(failure_signature_id="fs_032", skill_id="combat_skill")
        session.start_demonstration()
        session.record_action("attack", {"target": "enemy"})

        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        builder = SkillPatchBuilder()
        draft = builder.build(session, segments)
        draft.status = "SANDBOX_VALIDATED"

        after = runner.run_after("combat_skill", draft)
        assert after["pass_rate"] == 1.0
        assert after["failure_count"] == 0

        delta = runner.compute_delta("combat_skill", draft)
        assert isinstance(delta, BenchmarkDelta)
        assert delta.improvement == 1.0  # 1.0 - 0.0
        assert delta.before_pass_rate == 0.0
        assert delta.after_pass_rate == 1.0


# ---------------------------------------------------------------------------
# EvolutionEngine integration (backward compatibility)
# ---------------------------------------------------------------------------

class TestEvolutionEngineBackwardCompat:
    def test_handle_failure_still_returns_legacy_dict(self, tmp_path: Path):
        bus = StateBus()
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            result = engine.handle_failure("test_skill", "TARGET_LOST", {})
        assert result is not None
        assert "patch_id" in result
        assert result["skill_id"] == "test_skill"
        assert result["failure_code"] == "TARGET_LOST"
        assert result["verified"] is True

    def test_approve_patch(self, tmp_path: Path):
        bus = StateBus()
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            engine.handle_failure("approve_skill", "COMBAT_TIMEOUT", {})
        approved = engine.approve_patch("approve_skill")
        assert isinstance(approved, bool)

    def test_list_patch_drafts(self, tmp_path: Path):
        bus = StateBus()
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            engine.handle_failure("list_skill", "HP_DEPLETED", {})
        drafts = engine.list_patch_drafts("list_skill")
        assert len(drafts) >= 1
        assert all(d["skill_id"] == "list_skill" for d in drafts)

    def test_evolution_engine_has_repair_session(self, tmp_path: Path):
        bus = StateBus()
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            engine.handle_failure("repair_skill", "TARGET_LOST", {})
        sessions = engine._repair_sessions
        assert len(sessions) >= 1

    def test_evolution_engine_has_skill_patch_draft(self, tmp_path: Path):
        bus = StateBus()
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            engine.handle_failure("patch_skill", "TARGET_LOST", {"target_confidence_drop": True})
        drafts = engine._skill_patch_drafts
        assert len(drafts) >= 1
        for pd in drafts.values():
            assert pd.status in ("DRAFT", "SANDBOX_VALIDATED")
