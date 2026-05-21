from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ClaimRole = Literal["informational", "local", "dependency", "terminal"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True, slots=True)
class ProducedClaimDecl:
    claim_type: str
    target: str = ""
    delta: int | float | str = 0
    claim_role: ClaimRole = "local"
    stabilization_window_ms: int = 1000
    verifier_recipe: str = ""
    delayed_audit_type: str = ""
    delayed_audit_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InputClaimDecl:
    claim_type: str
    target: str = ""
    expected: str = ""
    required_status: str = "verified"


@dataclass(frozen=True, slots=True)
class FailureModeDecl:
    code: str
    policy: str = ""


@dataclass(frozen=True, slots=True)
class SkillClaimDeclaration:
    skill_id: str
    capsule_id: str = ""
    version: int = 1
    risk_level: RiskLevel = "medium"
    capabilities_provided: list[str] = field(default_factory=list)

    input_claims: list[InputClaimDecl] = field(default_factory=list)
    required_world_facts: list[dict[str, Any]] = field(default_factory=list)
    produced_claims: list[ProducedClaimDecl] = field(default_factory=list)

    semantic_actions: list[dict[str, str]] = field(default_factory=list)
    failure_modes: list[FailureModeDecl] = field(default_factory=list)

    def produced_claim_types(self) -> list[str]:
        return [pc.claim_type for pc in self.produced_claims]

    def terminal_claims(self) -> list[ProducedClaimDecl]:
        return [pc for pc in self.produced_claims if pc.claim_role == "terminal"]

    def dependency_claim_types(self) -> list[str]:
        return [ic.claim_type for ic in self.input_claims]


_REGISTRY: dict[str, SkillClaimDeclaration] = {}


def register_skill_declaration(decl: SkillClaimDeclaration) -> None:
    _REGISTRY[decl.skill_id] = decl


def get_skill_declaration(skill_id: str) -> SkillClaimDeclaration | None:
    return _REGISTRY.get(skill_id)


def all_declarations() -> dict[str, SkillClaimDeclaration]:
    return dict(_REGISTRY)


def clear_registry() -> None:
    _REGISTRY.clear()
