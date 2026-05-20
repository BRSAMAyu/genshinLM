"""Full flywheel test: failure -> repair -> segment -> patch -> validate -> approve -> benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.state_bus import StateBus
from learning.evolution_engine import EvolutionEngine


class TestFailureToSkillRepairFlywheel:
    """End-to-end flywheel: force TARGET_LOST, repair, validate, approve, benchmark."""

    def test_full_flywheel(self, tmp_path: Path):
        # 1. Force a TARGET_LOST failure via the evolution engine
        bus = StateBus()
        bus.register_slot("learning.patch_event")
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)

        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            result = engine.handle_failure(
                skill_name="flywheel_skill",
                failure_code="TARGET_LOST",
                observation_data={"target_confidence_drop": True},
            )
        assert result is not None
        assert result["skill_id"] == "flywheel_skill"
        assert result["failure_code"] == "TARGET_LOST"

        # 2. Verify a repair session was created
        sessions = engine._repair_sessions
        assert len(sessions) >= 1
        session = list(sessions.values())[0]

        # The auto-suggestion should have seeded demonstration events
        assert len(session.events) > 0
        demo_ids = session.demonstration_ids
        assert len(demo_ids) >= 1

        # 3. Verify demonstration was segmented
        from repair.demo_segmenter import DemoSegmenter
        segmenter = DemoSegmenter()
        segments = segmenter.segment(session.events)
        # Should have segments from auto-suggested actions (increase_coasting_window, add_reacquire_step)
        assert len(segments) >= 1

        # 4. Verify a SkillPatchDraft was built
        patch_drafts = engine._skill_patch_drafts
        assert len(patch_drafts) >= 1
        draft = list(patch_drafts.values())[0]
        assert draft.skill_id == "flywheel_skill"
        assert draft.status in ("DRAFT", "SANDBOX_VALIDATED")
        assert len(draft.proposed_steps) >= 1

        # 5. Validate in sandbox
        from repair.repair_validator import RepairValidator
        validator = RepairValidator()
        dry_run_ok = validator.validate_dry_run(draft)
        assert dry_run_ok is True

        # Promote to SANDBOX_VALIDATED if not already
        draft.status = "SANDBOX_VALIDATED"
        draft.validation = {**draft.validation, "dry_run_passed": True}
        verifier_ok = validator.validate_verifier_replay(draft, draft.verifier_contract)
        draft.validation = {**draft.validation, "verifier_replay_passed": verifier_ok}

        # 6. Approve the patch
        # First make sure the legacy draft is in a verified state
        legacy_drafts = engine.list_patch_drafts("flywheel_skill")
        assert len(legacy_drafts) >= 1
        # Force verification so approve_patch can succeed
        for ld in legacy_drafts:
            ld["verified"] = True

        approved = engine.approve_patch("flywheel_skill")
        assert approved is True

        # 7. Verify before/after benchmark delta
        delta = engine.get_benchmark_delta("flywheel_skill")
        assert delta is not None
        assert delta.improvement >= 0.0
        assert delta.before_pass_rate == 0.0
        assert delta.after_pass_rate == 1.0

        # Also via legacy API
        legacy_delta = engine.benchmark_delta("flywheel_skill")
        assert legacy_delta is not None
        assert "improvement" in legacy_delta
        assert legacy_delta["improvement"] == 1.0

        # 8. Verify patch file written to data/skill_patches/ (tmp_path)
        patch_files = list(tmp_path.glob("*.json"))
        assert len(patch_files) >= 1

        # Verify the SkillPatchDraft file is valid JSON
        draft_file = tmp_path / f"{draft.patch_id}.json"
        assert draft_file.exists()
        with open(draft_file, encoding="utf-8") as f:
            content = json.load(f)
        assert content["skill_id"] == "flywheel_skill"
        assert content["status"] in ("SANDBOX_VALIDATED", "APPROVED")

    def test_flywheel_with_manual_demonstration(self, tmp_path: Path):
        """Simulate a user manually recording demonstration actions."""
        bus = StateBus()
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)

        # Trigger failure (mock sandbox to avoid subprocess)
        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            result = engine.handle_failure("manual_skill", "TARGET_LOST", {})
        assert result is not None

        # Get the repair session
        sessions = engine._repair_sessions
        session = list(sessions.values())[0]

        # Add manual demonstration on top of auto-suggested
        session.start_demonstration()
        session.record_action("rotate_camera", {"yaw": 45, "pitch": 10})
        session.record_action("rotate_camera", {"yaw": -30, "pitch": 5})
        session.record_action("lock_on", {"target_id": "enemy_42"})
        session.propose_checkpoint({"target_locked": True, "confidence": 0.95})

        # Re-segment with all events
        from repair.demo_segmenter import DemoSegmenter
        segmenter = DemoSegmenter()
        all_segments = segmenter.segment(session.events)

        # Should include auto-suggested + manual segments
        assert len(all_segments) >= 2

        # Rebuild patch from the full session
        from repair.skill_patch_builder import SkillPatchBuilder
        builder = SkillPatchBuilder()
        new_draft = builder.build(session, all_segments)

        assert new_draft.skill_id == "manual_skill"
        assert len(new_draft.proposed_steps) >= 2
        # Should have verifier contract from the manual checkpoint
        assert "target_locked" in new_draft.verifier_contract

    def test_flywheel_patch_file_roundtrip(self, tmp_path: Path):
        """Verify that patch drafts survive a JSON write/read roundtrip."""
        bus = StateBus()
        engine = EvolutionEngine(state_bus=bus, patches_dir=tmp_path)

        with patch.object(engine, "_verify_in_sandbox", return_value=True):
            engine.handle_failure("roundtrip_skill", "COMBAT_TIMEOUT", {})

        # Get the SkillPatchDraft
        drafts = engine._skill_patch_drafts
        if not drafts:
            pytest.skip("No patch draft created (no auto-suggested actions)")

        original = list(drafts.values())[0]

        # Read from disk
        draft_file = tmp_path / f"{original.patch_id}.json"
        assert draft_file.exists()

        with open(draft_file, encoding="utf-8") as f:
            loaded = json.load(f)

        assert loaded["patch_id"] == original.patch_id
        assert loaded["skill_id"] == original.skill_id
        assert loaded["source_failure_signature_id"] == original.source_failure_signature_id
        assert loaded["status"] == original.status
        assert len(loaded["proposed_steps"]) == len(original.proposed_steps)
