from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlannerProposal:
    provider: str
    task_spec: dict
    skill_chain: list[str]
    risks: list[str]
    usage: dict = field(default_factory=dict)
    provider_error: str | None = None


class ProviderUnavailable(RuntimeError):
    pass


class ProviderRequestError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def plan(self, goal: str, skills: list[dict], persona_id: str) -> PlannerProposal:
        ...

    def explain_failure(self, summary: dict) -> dict:
        ...
