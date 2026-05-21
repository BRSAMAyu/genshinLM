from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Tuple

from capsules.capsule_protocol import CapsuleManifest
from capsules.capsule_registry import CapsuleRegistry
from capsules.provider_registry import ProviderRegistry
from planning.intent_parser import ParsedIntent
from planning.skill_capability_catalog import SkillCapabilityCatalog, SkillCatalogEntry

logger = logging.getLogger("capability_planner")


@dataclass(frozen=True, slots=True)
class PlanProposal:
    """Proposal compiled by the capability planner."""
    selected_skills: List[SkillCatalogEntry]
    missing_capabilities: List[str]
    rejected_candidates: List[Tuple[SkillCatalogEntry, str]]  # (entry, reason)
    verifier_coverage: float
    capsule_id: str
    requires_user_confirmation: bool = False

    @property
    def selected_skill_ids(self) -> List[str]:
        return [entry.skill_id for entry in self.selected_skills]


class CapabilityPlanner:
    """Deterministic planner to resolve capabilities into a PlanProposal."""

    def __init__(
        self,
        catalog: SkillCapabilityCatalog,
        provider_registry: ProviderRegistry | None = None,
        registry: CapsuleRegistry | None = None,
    ) -> None:
        self.catalog = catalog
        self.provider_registry = provider_registry
        self.registry = registry

    def plan(
        self,
        intent: ParsedIntent | str,
        active_capsule_id: str,
        strict_mode: bool = False,
        required_capabilities: List[str] | None = None,
    ) -> PlanProposal:
        """Resolve required capabilities to candidate skills, ranking them and compiling a DAG."""
        # 1. Resolve required capabilities
        if required_capabilities is not None:
            caps = list(required_capabilities)
        else:
            caps = self._infer_capabilities(intent, active_capsule_id)

        selected: List[SkillCatalogEntry] = []
        missing: List[str] = []
        rejected: List[Tuple[SkillCatalogEntry, str]] = []

        # Load manifest to check resources if registry is available
        manifest: CapsuleManifest | None = None
        manifest_path: Path | None = None
        if self.registry:
            manifest = self.registry.manifest(active_capsule_id)
            if manifest and hasattr(self.registry, "_manifest_paths"):
                manifest_path = self.registry._manifest_paths.get(active_capsule_id)

        # 2. For each required capability, find the best matching skill
        for cap in caps:
            candidates = self.catalog.by_capability(cap)
            if not candidates:
                missing.append(cap)
                continue

            scored_candidates: List[Tuple[float, SkillCatalogEntry]] = []
            for entry in candidates:
                # Filter by active capsule
                if entry.capsule_id != active_capsule_id and entry.capsule_id != "core":
                    rejected.append((entry, f"capsule_mismatch: active capsule is {active_capsule_id}"))
                    continue

                # Filter/check resource availability
                resources_ok = True
                missing_res = []
                if manifest and entry.resources:
                    for res_id in entry.resources:
                        # Find resource in manifest
                        res_spec = next((r for r in manifest.resources if r.resource_id == res_id), None)
                        if res_spec and not res_spec.optional:
                            # Resolve path
                            if manifest_path:
                                paths_dict = manifest.resource_paths(manifest_path)
                                r_path = paths_dict.get(res_id)
                                if r_path and not r_path.exists():
                                    resources_ok = False
                                    missing_res.append(res_id)
                            else:
                                # Fallback if manifest_path is missing but path is specified
                                if res_spec.path and not Path(res_spec.path).exists():
                                    resources_ok = False
                                    missing_res.append(res_id)

                if not resources_ok:
                    rejected.append((entry, f"missing_resources: {', '.join(missing_res)}"))
                    continue

                # Strict mode check: high risk without verifiers
                has_verifiers = len(entry.verifiers) > 0
                is_high_risk = entry.risk_level in ("high", "human_confirm")
                if strict_mode and is_high_risk and not has_verifiers:
                    rejected.append((entry, "strict_mode: high_risk_without_verifier"))
                    continue

                # Calculate score
                # score = capability_match * 50 + verifier_count * 10 + resource_available * 10 - risk_level * 10
                risk_map = {"low": 1, "medium": 2, "high": 3, "human_confirm": 4}
                risk_val = risk_map.get(entry.risk_level, 2)
                
                score = (
                    1.0 * 50
                    + len(entry.verifiers) * 10
                    + (1.0 if resources_ok else 0.0) * 10
                    - risk_val * 10
                )
                scored_candidates.append((score, entry))

            if not scored_candidates:
                missing.append(cap)
                continue

            # Sort by score descending
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_entry = scored_candidates[0][1]
            selected.append(best_entry)

        # 3. Check for human_confirm or high risk in selected skills
        requires_user_confirm = any(entry.risk_level == "human_confirm" for entry in selected)

        # 4. Verifier coverage
        if selected:
            skills_with_verifiers = [entry for entry in selected if entry.verifiers]
            coverage = len(skills_with_verifiers) / len(selected)
        else:
            coverage = 1.0

        return PlanProposal(
            selected_skills=selected,
            missing_capabilities=missing,
            rejected_candidates=rejected,
            verifier_coverage=coverage,
            capsule_id=active_capsule_id,
            requires_user_confirmation=requires_user_confirm,
        )

    def _infer_capabilities(self, intent: ParsedIntent | str, active_capsule_id: str) -> List[str]:
        """Infer required capabilities based on intent and active capsule."""
        lowered = ""
        goal_type = ""
        preference = ""

        if isinstance(intent, ParsedIntent):
            lowered = intent.resource_id.lower()
            goal_type = intent.goal_type
            preference = intent.preference
        else:
            lowered = intent.lower()

        caps: List[str] = []
        if active_capsule_id == "hsr":
            if "combat" in lowered or "fight" in lowered or preference == "combat_first" or goal_type == "combat":
                caps.append("hsr_turn_based_combat")
            if "nav" in lowered or "navigate" in lowered or "go" in lowered or "move" in lowered:
                caps.append("hsr_navigation")
            if "reward" in lowered or "claim" in lowered:
                caps.append("hsr_reward_claim")
            if "dialog" in lowered or "talk" in lowered or "progression" in lowered:
                caps.append("hsr_dialog_progression")
            # Default fallback if empty
            if not caps:
                caps.append("hsr_navigation")
        elif active_capsule_id == "genshin":
            if "combat" in lowered or "fight" in lowered or preference == "combat_first":
                caps.append("arpg_combat")
            if "nav" in lowered or "navigate" in lowered or "go" in lowered or "move" in lowered:
                caps.append("navigation")
            # Default fallback if empty
            if not caps:
                caps.append("navigation")
        return caps
