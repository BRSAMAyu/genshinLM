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

        bound_anchors = list(semantic_draft.ui_anchors)
        for event in session_events:
            payload_anchor = (
                event.payload.get("anchor_id")
                or event.payload.get("ui_anchor")
                or event.payload.get("target_anchor")
            )
            if isinstance(payload_anchor, str) and payload_anchor:
                bound_anchors.append(payload_anchor)

        bound_anchors = list(dict.fromkeys(bound_anchors))
        if not bound_anchors:
            # Coordinate-only traces are raw material, not reusable skills. They
            # can be stored for human review, but they must not be promoted into
            # the runtime catalog because they are not portable across
            # resolution, UI drift, or profile changes.
            log.warning(
                "[SkillInductionGate] Trace has no bound UIAnchor; coordinate-only induction rejected for %s",
                goal,
            )
            return None

        verifiers = [f"{anchor_id}_post_click" for anchor_id in bound_anchors]

        # Create a catalog entry candidate
        entry = SkillCatalogEntry(
            skill_id=goal,
            capsule_id="core",
            source="induced_skill",
            kind="ui",
            capabilities=[goal],
            resources=[f"ui_anchor:{anchor_id}" for anchor_id in bound_anchors],
            verifiers=verifiers,
            ui_anchors=bound_anchors,
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
