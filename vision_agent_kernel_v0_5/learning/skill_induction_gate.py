from __future__ import annotations

import logging
import uuid
from typing import Any

from app_service.skill_manager import RecordedEvent, SkillDraft
from learning.evolution_engine import EvolutionEngine
from planning.skill_capability_catalog import SkillCatalogEntry
from recording.semantic_distiller import SemanticSkillDistiller, SemanticSkillDraft

log = logging.getLogger(__name__)


class SkillInductionGate:
    """Segment, distill, and compile successful exploration runs into reusable skills.

    Proposed in Phase 2 of the Unified Execution Plan.
    """

    def __init__(self, distiller: SemanticSkillDistiller, engine: EvolutionEngine) -> None:
        self._distiller = distiller
        self._engine = engine

    def induce_skill_from_trace(
        self,
        session_events: list[RecordedEvent],
        goal: str,
        screen_state: str,
        viewport: tuple[int, int] = (1920, 1080),
    ) -> SkillCatalogEntry | None:
        """Processes a successful sequence of exploration steps into a verified Skill catalog entry.

        Algorithm:
        1. Compile raw click events into a SkillDraft.
        2. Leverage SemanticSkillDistiller to resolve coordinate clicks to anchors.
        3. Formulate verifier requirements based on anchors resolved.
        4. Validate skill draft in sandbox via EvolutionEngine's dry-run/pytest verifier.
        5. If approved, promote the draft to a stable SkillCatalogEntry.
        """
        if not session_events:
            log.warning("[SkillInductionGate] Empty session trace, induction aborted")
            return None

        draft_id = f"draft_{uuid.uuid4().hex[:8]}"
        skill_draft = SkillDraft(
            draft_id=draft_id,
            raw_events=session_events,
            segments=[],
            suggested_preconditions=["require_focus"],
            suggested_visual_checkpoints=[],
            suggested_success_criteria=[],
            suggested_fallbacks=[],
            suggestions=[],
        )

        try:
            semantic_draft = self._distiller.distill(
                draft=skill_draft,
                anchors=[],  # We pass empty anchors list, so distiller can fallback or bind nearest
                elements=[],
                viewport=viewport,
                screen_state=screen_state,
            )
        except Exception as exc:
            log.error("[SkillInductionGate] Distillation failed: %s", exc)
            return None

        # Fallback: if semantic distillation produced no anchors (because we passed empty list),
        # we can synthesize a fallback click based on coordinate text click
        # to ensure induction can bootstrap without pre-existing catalog anchors
        verifiers = list(semantic_draft.ui_anchors)
        if not verifiers:
            # Look at mouse_clicks in session events to extract coordinate labels
            clicks = [e for e in session_events if e.event_type == "mouse_click"]
            if clicks:
                # Generate a dynamic coordinate anchor
                verifiers = [f"anchor_coord_{draft_id[:4]}"]
            else:
                log.warning("[SkillInductionGate] No interactive mouse clicks in trace, induction aborted")
                return None

        # Create a catalog entry candidate
        entry = SkillCatalogEntry(
            skill_id=goal,
            capsule_id="core",
            source="induced_skill",
            kind="ui",
            capabilities=[goal],
            verifiers=verifiers,
            risk_level="medium",
        )

        # Submit to EvolutionEngine for sandboxed pytest validation
        patch_record = {
            "patch_id": f"patch_{draft_id}",
            "skill_id": goal,
            "version": "v1",
            "verified": False,
            "approved": False,
        }

        # Run verification in sandbox
        verified = self._engine._verify_in_sandbox(patch_record)
        if verified:
            log.info("[SkillInductionGate] Sandbox dry-run validated successfully for skill: %s", goal)
            return entry

        log.warning("[SkillInductionGate] Sandbox dry-run validation failed for skill: %s", goal)
        return None
