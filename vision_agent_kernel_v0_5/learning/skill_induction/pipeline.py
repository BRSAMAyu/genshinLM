"""Induction pipeline — end-to-end trace → SkillDef → registry.

Orchestrates: TraceRecorder → EpisodeSegmenter → AnchorBinder → PromotionGate → SkillRegistry
"""
from __future__ import annotations

from dataclasses import dataclass, field

from learning.skill_induction.trace_recorder import TraceRecorder, TraceSession
from learning.skill_induction.episode_segmenter import EpisodeSegmenter
from learning.skill_induction.anchor_binder import AnchorBinder, BindingResult
from learning.skill_induction.promotion_gate import PromotionGate
from skills.registry import SkillRegistry
from skills.schema import SkillDef


@dataclass(frozen=True, slots=True)
class InductionResult:
    """Result of a full induction pipeline run."""
    skills_produced: int
    coordinate_only_rejected: int
    promotion_results: tuple[tuple[str, bool, str], ...]


class InductionPipeline:
    """Full pipeline from trace session to registered skills."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.recorder = TraceRecorder()
        self.segmenter = EpisodeSegmenter()
        self.binder = AnchorBinder()
        self.registry = registry or SkillRegistry()
        self.gate = PromotionGate(self.registry)

    def process_session(
        self,
        session: TraceSession,
        target_tier: str = "draft",
    ) -> InductionResult:
        """Process a completed trace session into skills.

        Steps:
        1. Segment into episodes
        2. Bind anchors for each episode
        3. Register produced skills
        4. Attempt promotion
        """
        if not session.success:
            return InductionResult(0, 0, ())

        episodes = self.segmenter.segment(session)
        skills_produced = 0
        coordinate_only = 0
        promotion_results: list[tuple[str, bool, str]] = []

        for episode in episodes:
            result = self.binder.bind(episode)
            if result.skill is None:
                continue

            if result.coordinate_only:
                coordinate_only += 1
                # Still register as raw_trace for storage
                self.registry.register(result.skill)
                continue

            self.registry.register(result.skill)

            # Try promotion if target tier is above draft
            if target_tier not in ("raw_trace", "draft"):
                from skills.promotion import PromotionTier
                promo = self.gate.try_promote(
                    result.skill, target_tier,  # type: ignore
                )
                promotion_results.append((result.skill.skill_id, promo.success, promo.reason))
                if promo.success:
                    skills_produced += 1
            else:
                skills_produced += 1

        return InductionResult(
            skills_produced=skills_produced,
            coordinate_only_rejected=coordinate_only,
            promotion_results=tuple(promotion_results),
        )
