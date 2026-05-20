from __future__ import annotations

from pathlib import Path
from typing import Any

from app_service.skill_manager import SkillStore
from llm.glm_provider import GLMProvider
from llm.minimax_provider import MiniMaxProvider
from llm.mock_provider import MockProvider
from llm.provider_base import PlannerProposal
from llm.request_guard import LLMRequestGuard


class Planner:
    def __init__(self, root: Path, skill_store: SkillStore, guard: LLMRequestGuard | None = None) -> None:
        self._root = root
        self._skill_store = skill_store
        self._guard = guard or LLMRequestGuard()
        self._mock = MockProvider()
        self._providers = {
            "mock": self._mock,
            "glm": GLMProvider(),
            "minimax": MiniMaxProvider(),
        }

    def plan(self, goal: str, provider: str = "mock", persona_id: str = "default_companion") -> PlannerProposal:
        self._guard.reset_task()
        selected = self._providers.get(provider, self._mock)
        skills = self._skill_store.list_skills().get("skills", [])
        if selected.name == "mock":
            proposal = selected.plan(goal, skills, persona_id)
            return PlannerProposal(
                proposal.provider,
                proposal.task_spec,
                proposal.skill_chain,
                proposal.risks,
                usage={**proposal.usage, "guard": self._guard.snapshot()},
            )
        try:
            self._guard.check(estimated_tokens=1400)
            proposal = selected.plan(goal, skills, persona_id)
            return PlannerProposal(
                proposal.provider,
                proposal.task_spec,
                proposal.skill_chain,
                proposal.risks,
                usage={**proposal.usage, "guard": self._guard.snapshot()},
            )
        except Exception as exc:
            fallback = self._mock.plan(goal, skills, persona_id)
            return PlannerProposal(
                provider="mock",
                task_spec=fallback.task_spec,
                skill_chain=fallback.skill_chain,
                risks=[f"{selected.name} unavailable; fell back to mock planner: {exc}", *fallback.risks],
                usage={"guard": self._guard.snapshot(), "failover": selected.name},
                provider_error=str(exc),
            )

    def explain_failure(self, summary: dict[str, Any], provider: str = "mock") -> dict[str, Any]:
        selected = self._providers.get(provider, self._mock)
        if selected.name == "mock":
            return selected.explain_failure(summary)
        try:
            self._guard.check(estimated_tokens=900)
            payload = selected.explain_failure(summary)
            return _normalize_explanation(payload)
        except Exception as exc:
            fallback = self._mock.explain_failure({**summary, "provider_error": str(exc)})
            fallback["provider_error"] = str(exc)
            fallback["provider"] = "mock"
            return fallback

    def plan_combat(self, goal: str, team_profile: str = "default_team", provider: str = "mock") -> dict[str, Any]:
        proposal = self.plan(goal=f"combat:{goal}", provider=provider)
        return {
            "playbook_id": "mock_combat_playbook",
            "goal": goal,
            "team_profile": team_profile,
            "nodes": [
                {"node_id": "maintain_lock", "type": "condition", "priority": 10, "guards": ["target_visible"]},
                {"node_id": "target_visible_checkpoint", "type": "checkpoint", "priority": 15, "guards": ["target_visible"]},
                {"node_id": "attack_if_safe", "type": "action", "priority": 30, "guards": ["danger_score < 0.45"]},
                {"node_id": "burst_if_safe", "type": "branch", "priority": 35, "guards": ["danger_score < 0.35", "cooldown_ready"]},
                {"node_id": "heal_if_low_hp", "type": "branch", "priority": 60, "guards": ["hp_ratio < 0.35"]},
                {"node_id": "dodge_if_danger", "type": "reflex", "priority": 100, "guards": ["danger_score >= 0.8"]},
                {"node_id": "fallback_basic_loop", "type": "fallback", "priority": 1, "guards": ["recoverable"]},
                {"node_id": "verify_complete", "type": "verification", "priority": 5, "guards": ["target_resolved"]},
            ],
            "edges": [
                ["maintain_lock", "target_visible_checkpoint"],
                ["target_visible_checkpoint", "attack_if_safe"],
                ["attack_if_safe", "burst_if_safe"],
                ["burst_if_safe", "verify_complete"],
                ["attack_if_safe", "dodge_if_danger"],
                ["burst_if_safe", "dodge_if_danger"],
                ["heal_if_low_hp", "maintain_lock"],
                ["dodge_if_danger", "maintain_lock"],
                ["fallback_basic_loop", "maintain_lock"],
            ],
            "fallback": "fallback_basic_loop",
            "retry": {"max_retries": 2},
            "source_task": proposal.task_spec["task_id"],
        }


def _normalize_explanation(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_friendly_summary": str(payload.get("user_friendly_summary") or payload.get("user_friendly") or "The run failed, but the planner did not provide a user summary."),
        "technical_summary": str(payload.get("technical_summary") or payload.get("technical") or payload),
        "suggested_next_steps": list(payload.get("suggested_next_steps") or payload.get("next_steps") or []),
        "possible_skill_patch": payload.get("possible_skill_patch") or {"requires_user_confirmation": True, "suggestion": "No automatic patch."},
        **({"provider": payload["provider"]} if "provider" in payload else {}),
        **({"provider_error": payload["provider_error"]} if "provider_error" in payload else {}),
    }
