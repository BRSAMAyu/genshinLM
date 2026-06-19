"""Dual-model coordinator — GLM-5.2 reasons, MiniMax M3 perceives.

GLM-5.2 has the stronger deep-thinking/reasoning; MiniMax M3 is natively
multimodal (image + video). This module routes each call to the model that's best
at it, and chains them on tasks that need both — M3 turns pixels into structured
visual facts, then GLM-5.2 reasons over those facts to decide strategy. That
"perceive → reason" split is where the two complement each other most.

Both halves are offline-testable (each provider accepts an injected transport).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm.glm_provider import GLMProvider
from llm.minimax_provider import MiniMaxProvider
from llm.provider_base import PlannerProposal
from llm.vision_provider import ImageInput, ScreenStateResult, UIGroundingResult, VisionResult


@dataclass(frozen=True, slots=True)
class VisualFacts:
    """Structured perception output produced by MiniMax M3."""

    screen_state: str
    confidence: float
    description: str
    candidates: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class DiagnosedFailure:
    """M3-grounded visual evidence + GLM-5.2 reasoned attribution."""

    user_friendly_summary: str
    technical_summary: str
    suggested_next_steps: list[str]
    visual_evidence: VisualFacts
    reasoning_provider: str
    vision_provider: str


class DualModelCoordinator:
    """Route calls by capability and chain the two models where they combine.

    - vision / multimodal → MiniMax M3 (``describe_image`` / ``classify_screen`` /
      ``ground_ui``)
    - reasoning / planning → GLM-5.2 (``plan`` / ``reason`` / ``reason_json``)
    - perceive → reason pipelines → both (``perceive_and_plan`` / ``diagnose_failure``)
    """

    def __init__(
        self,
        *,
        vision: MiniMaxProvider | None = None,
        reasoner: GLMProvider | None = None,
    ) -> None:
        self.vision = vision or MiniMaxProvider()
        self.reasoner = reasoner or GLMProvider()

    # -- capability routing: vision → M3 -----------------------------------

    def describe_image(self, image: ImageInput, prompt: str) -> VisionResult:
        return self.vision.describe_image(image, prompt)

    def classify_screen(self, image: ImageInput, candidates: list[str]) -> ScreenStateResult:
        return self.vision.classify_screen(image, candidates)

    def ground_ui(self, image: ImageInput, query: str) -> UIGroundingResult:
        return self.vision.ground_ui(image, query)

    def perceive(self, image: ImageInput, *, candidates: list[str] | None = None,
                 describe_prompt: str = "Describe the screen: game state, the player's situation, visible UI, nearby threats, and any objective marker.") -> VisualFacts:
        """M3 turns the screenshot into structured visual facts for the reasoner."""
        states = candidates or [
            "overworld", "combat", "turn_based_combat", "dialog", "menu", "map",
            "inventory", "boss_fight", "cutscene", "loading", "reward_screen", "unknown",
        ]
        classified = self.vision.classify_screen(image, states)
        described = self.vision.describe_image(image, describe_prompt)
        return VisualFacts(
            screen_state=classified.screen_state,
            confidence=classified.confidence,
            description=described.text,
            candidates=[],
        )

    # -- capability routing: reasoning → GLM-5.2 ---------------------------

    def plan(self, goal: str, skills: list[dict], persona_id: str) -> PlannerProposal:
        return self.reasoner.plan(goal, skills, persona_id)

    def reason(self, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
        return self.reasoner.reason(system_prompt, user_prompt)

    def reason_json(self, system_prompt: str, user_prompt: str) -> tuple[dict, dict]:
        return self.reasoner.reason_json(system_prompt, user_prompt)

    # -- complementary pipelines: M3 perceives → GLM-5.2 reasons -----------

    def perceive_and_plan(
        self,
        image: ImageInput,
        goal: str,
        skills: list[dict],
        persona_id: str = "default_companion",
        *,
        facts: VisualFacts | None = None,
    ) -> PlannerProposal:
        """M3 reads the screen into facts; GLM-5.2 reasons a plan over them.

        Without vision, planning is blind to current state. Here the planner gets
        a concise, M3-produced picture of the world, so GLM-5.2 can choose a
        skill chain that actually fits the moment (e.g. don't pick navigation
        when a boss is mid-attack).
        """
        visual = facts if facts is not None else self.perceive(image)
        augmented_goal = json.dumps({
            "goal": goal,
            "current_screen_state": visual.screen_state,
            "perceived_situation": visual.description,
        }, ensure_ascii=False)
        return self.reasoner.plan(augmented_goal, skills, persona_id)

    def diagnose_failure(
        self,
        image: ImageInput,
        summary: dict[str, Any],
        *,
        facts: VisualFacts | None = None,
    ) -> DiagnosedFailure:
        """Ground the failure in what's actually on screen, then reason the cause.

        M3 supplies the visual evidence (what does the screen show at failure?);
        GLM-5.2 attributes *why* and proposes recovery — the strongest reasoning
        applied to the most accurate, current visual facts.
        """
        visual = facts if facts is not None else self.perceive(image)
        system = (
            "You are diagnosing why an autonomous game-agent action failed. Use the "
            "provided visual evidence (what is on screen) plus the failure summary to "
            "attribute the most likely cause and propose concrete recovery. Return strict "
            "JSON: user_friendly_summary, technical_summary, suggested_next_steps."
        )
        payload, _usage = self.reasoner.reason_json(
            system,
            json.dumps({"summary": summary, "visual_evidence": {
                "screen_state": visual.screen_state,
                "description": visual.description,
            }}, ensure_ascii=False),
            temperature=0.2,
            max_tokens=1200,
        )
        return DiagnosedFailure(
            user_friendly_summary=str(payload.get("user_friendly_summary", "")),
            technical_summary=str(payload.get("technical_summary", "")),
            suggested_next_steps=list(payload.get("suggested_next_steps", [])),
            visual_evidence=visual,
            reasoning_provider=self.reasoner.name,
            vision_provider=self.vision.name,
        )

    def plan_combat_strategy(
        self,
        image: ImageInput,
        goal: str,
        team: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """M3 reads the enemy/team state; GLM-5.2 reasons the combat strategy.

        Combat is exactly where strong reasoning pays off (reaction chains, burst
        windows, target priority) AND where you must see the enemy's aura/shield —
        so this routes the picture to M3 and the decision to GLM-5.2.
        """
        visual = self.perceive(
            image,
            describe_prompt=(
                "Combat scene: describe enemy count, enemy element/aura/shield, "
                "player active character, HP bars, and any incoming-attack telegraph."
            ),
        )
        payload, _usage = self.reasoner.reason_json(
            "You are a combat strategist. Given the perceived combat scene and goal, "
            "return strict JSON: active_character_to_switch, rotation "
            "(list of {step, action, reason}), reaction_target_element, "
            "burst_when (condition), risks.",
            json.dumps({"goal": goal, "team": team or {}, "scene": {
                "screen_state": visual.screen_state, "description": visual.description,
            }}, ensure_ascii=False),
            temperature=0.2,
            max_tokens=1400,
        )
        return payload
