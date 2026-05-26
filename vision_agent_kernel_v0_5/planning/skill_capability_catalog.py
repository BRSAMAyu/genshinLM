from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol

from capsules.capsule_protocol import CapsuleManifest


class SkillLike(Protocol):
    skill_id: str
    name: str
    type: str
    capsule_id: str
    capabilities: list[str]
    resources: list[dict[str, object]]
    verifier_contracts: list[dict[str, object]]
    planner: dict[str, object]


@dataclass(frozen=True, slots=True)
class SkillCatalogEntry:
    """Planner-facing row that decouples framework skills from game packages."""

    skill_id: str
    capsule_id: str
    source: str
    kind: str
    capabilities: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    planner_tags: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    capabilities_required: list[str] = field(default_factory=list)
    capabilities_provided: list[str] = field(default_factory=list)
    failure_modes: list[dict] = field(default_factory=list)
    recovery_policy: dict = field(default_factory=dict)


class SkillCapabilityCatalog:
    """Unified catalog for planner selection across core skills and installed capsules."""

    def __init__(self, entries: Iterable[SkillCatalogEntry] = ()) -> None:
        import threading
        self._entries = list(entries)
        self._lock = threading.Lock()

    @classmethod
    def from_sources(
        cls,
        skills: Iterable[SkillLike] = (),
        manifests: Iterable[CapsuleManifest] = (),
    ) -> SkillCapabilityCatalog:
        entries_by_id: dict[str, SkillCatalogEntry] = {}

        for skill in skills:
            planner = skill.planner or {}
            caps = list(skill.capabilities)
            caps_prov = list(planner.get("capabilities_provided", caps))
            entry = SkillCatalogEntry(
                skill_id=skill.skill_id,
                capsule_id=skill.capsule_id,
                source="skill_store",
                kind=skill.type,
                capabilities=caps,
                resources=[
                    str(resource.get("resource_id") or resource.get("uri") or resource.get("path"))
                    for resource in skill.resources
                ],
                verifiers=[
                    str(contract.get("verifier_id"))
                    for contract in skill.verifier_contracts
                    if contract.get("verifier_id")
                ],
                planner_tags=list(planner.get("tags", [])),
                risk_level=str(planner.get("risk_level", "medium")),
                capabilities_required=list(planner.get("capabilities_required", [])),
                capabilities_provided=caps_prov,
                failure_modes=list(planner.get("failure_modes", [])),
                recovery_policy=dict(planner.get("recovery_policy", {})),
            )
            entries_by_id[entry.skill_id] = entry

        for manifest in manifests:
            for spec in manifest.skills:
                caps_prov = list(spec.capabilities_provided)
                if not caps_prov:
                    caps_prov = list(spec.capabilities)
                entry = SkillCatalogEntry(
                    skill_id=spec.skill_id,
                    capsule_id=manifest.capsule_id,
                    source="capsule_manifest",
                    kind=spec.kind,
                    capabilities=list(spec.capabilities),
                    resources=list(spec.resources),
                    verifiers=list(spec.verifiers),
                    planner_tags=list(spec.planner_tags),
                    risk_level=spec.risk_level,
                    capabilities_required=list(spec.capabilities_required),
                    capabilities_provided=caps_prov,
                    failure_modes=list(spec.failure_modes),
                    recovery_policy=dict(spec.recovery_policy),
                )
                entries_by_id[entry.skill_id] = entry

        return cls(entries_by_id.values())

    def entries(self) -> list[SkillCatalogEntry]:
        with self._lock:
            return list(self._entries)

    def by_capability(self, capability: str) -> list[SkillCatalogEntry]:
        with self._lock:
            return [
                entry
                for entry in self._entries
                if capability in set(entry.capabilities) | set(entry.capabilities_provided)
            ]

    def by_capsule(self, capsule_id: str) -> list[SkillCatalogEntry]:
        with self._lock:
            return [entry for entry in self._entries if entry.capsule_id == capsule_id]

    def missing_capabilities(self, required: Iterable[str]) -> list[str]:
        with self._lock:
            available = {
                capability
                for entry in self._entries
                for capability in set(entry.capabilities) | set(entry.capabilities_provided)
            }
            return [capability for capability in required if capability not in available]

    def register_induced_skill(self, entry: SkillCatalogEntry) -> None:
        """Dynamically add or update a skill in the catalog at runtime."""
        with self._lock:
            for i, existing in enumerate(self._entries):
                if existing.skill_id == entry.skill_id:
                    self._entries[i] = entry
                    return
            self._entries.append(entry)

