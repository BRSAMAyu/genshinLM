"""Build a SkillPatchDraft from a repair session and demonstration segments."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from repair.demo_segmenter import DemoSegment
from repair.repair_session import RepairSession


@dataclass(slots=True)
class SkillPatchDraft:
    """A draft patch for a skill, derived from repair demonstration."""

    patch_id: str
    skill_id: str
    source_failure_signature_id: str
    source_run_id: str | None
    demonstration_segment_ids: list[str]
    proposed_steps: list[dict[str, object]]
    verifier_contract: dict[str, object]
    safety: dict[str, object]
    validation: dict[str, object]
    status: str  # DRAFT, SANDBOX_VALIDATED, REJECTED, APPROVED, APPLIED, ROLLED_BACK
    created_at: float

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "patch_id": self.patch_id,
            "skill_id": self.skill_id,
            "source_failure_signature_id": self.source_failure_signature_id,
            "source_run_id": self.source_run_id,
            "demonstration_segment_ids": self.demonstration_segment_ids,
            "proposed_steps": self.proposed_steps,
            "verifier_contract": self.verifier_contract,
            "safety": self.safety,
            "validation": self.validation,
            "status": self.status,
            "created_at": self.created_at,
        }


class SkillPatchBuilder:
    """Constructs a SkillPatchDraft from a repair session and its segments."""

    def build(self, session: RepairSession, segments: list[DemoSegment]) -> SkillPatchDraft:
        """Build a SkillPatchDraft from session events and segments."""
        # Collect verifier contracts from checkpoint events
        verifier_contracts: list[dict[str, object]] = []
        for event in session.events:
            if event.event_type == "checkpoint_proposed":
                contract = event.payload.get("verifier_contract")
                if isinstance(contract, dict):
                    verifier_contracts.append(contract)

        # Merge all verifier contracts into one
        merged_contract: dict[str, object] = {}
        for contract in verifier_contracts:
            merged_contract.update(contract)

        # Build proposed steps from segments
        proposed_steps: list[dict[str, object]] = []
        for seg in segments:
            proposed_steps.append({
                "segment_id": seg.segment_id,
                "action_type": seg.action_type,
                "params": seg.params,
            })

        # Collect demonstration segment IDs
        segment_ids = [seg.segment_id for seg in segments]

        # Build safety defaults
        safety: dict[str, object] = {
            "requires_user_approval": True,
            "dry_run_required": True,
            "safe_window_required": False,
        }

        # Build validation defaults (all false until verified)
        validation: dict[str, object] = {
            "dry_run_passed": False,
            "verifier_replay_passed": False,
            "benchmark_before": None,
            "benchmark_after": None,
        }

        return SkillPatchDraft(
            patch_id=str(uuid.uuid4()),
            skill_id=session.skill_id,
            source_failure_signature_id=session.failure_signature_id,
            source_run_id=None,
            demonstration_segment_ids=segment_ids,
            proposed_steps=proposed_steps,
            verifier_contract=merged_contract,
            safety=safety,
            validation=validation,
            status="DRAFT",
            created_at=time.perf_counter(),
        )
