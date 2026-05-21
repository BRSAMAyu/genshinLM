from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from combat.boss_schema import BossProfile


@dataclass(frozen=True, slots=True)
class CharacterCapability:
    character_id: str
    slot: int
    element: str
    role: str
    cooldowns: dict[str, int] = field(default_factory=dict)
    energy_requirement: int = 0
    survival_tools: list[str] = field(default_factory=list)
    reaction_tags: list[str] = field(default_factory=list)
    known: bool = True


@dataclass(frozen=True, slots=True)
class TeamProfile:
    characters: list[CharacterCapability]

    @property
    def elements(self) -> list[str]:
        return [c.element for c in self.characters if c.element]

    @property
    def has_healer(self) -> bool:
        return any("heal" in c.survival_tools or c.role == "healer" for c in self.characters)

    @property
    def has_shielder(self) -> bool:
        return any("shield" in c.survival_tools or c.role == "shielder" or "shield" in c.role for c in self.characters)

    @property
    def primary_dps_slot(self) -> int:
        for role in ("on_field_dps", "burst_dps"):
            for character in self.characters:
                if character.role == role:
                    return character.slot
        return self.characters[0].slot if self.characters else 1


@dataclass(frozen=True, slots=True)
class TeamCombatPlan:
    main_chain: list[str]
    survival_chain: list[str]
    low_resource_chain: list[str]
    fallback_chain: list[str]
    conservative_level: int
    reason: str


class TeamCapabilityAnalyzer:
    """Compile user team composition into reusable combat capabilities."""

    def __init__(self, character_db: dict[str, dict[str, Any]] | None = None) -> None:
        self._character_db = character_db or {}

    @classmethod
    def from_yaml(cls, path: str | Path) -> TeamCapabilityAnalyzer:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        character_db = {str(item["character_id"]): item for item in raw.get("characters", []) if "character_id" in item}
        return cls(character_db)

    def analyze(self, team_characters: list[str], team_elements: list[str] | None = None) -> TeamProfile:
        elements = team_elements or []
        characters: list[CharacterCapability] = []
        for index, character_id in enumerate(team_characters):
            raw = self._character_db.get(character_id, {})
            element = str(raw.get("element") or (elements[index] if index < len(elements) else "unknown"))
            role = self._normalize_role(str(raw.get("role") or raw.get("behavior_preference") or "unknown"))
            survival_tools = self._survival_tools(raw, role)
            characters.append(
                CharacterCapability(
                    character_id=character_id,
                    slot=index + 1,
                    element=element,
                    role=role,
                    cooldowns={"e_skill": int(raw.get("e_skill_cd_ms", 0)), "q_burst": int(raw.get("q_duration_ms", 0))},
                    energy_requirement=int(raw.get("q_energy_cost", 0)),
                    survival_tools=survival_tools,
                    reaction_tags=[element] if element != "unknown" else [],
                    known=bool(raw),
                )
            )
        if not characters and elements:
            for index, element in enumerate(elements):
                characters.append(
                    CharacterCapability(
                        character_id=f"unknown_{element}_{index + 1}",
                        slot=index + 1,
                        element=element,
                        role="unknown",
                        known=False,
                    )
                )
        return TeamProfile(characters)

    def compile_plan(self, profile: TeamProfile, boss: BossProfile) -> TeamCombatPlan:
        main_chain = self._main_chain(profile, boss)
        survival_chain: list[str] = []
        conservative = 0
        if profile.has_shielder:
            survival_chain.append("shield_before_punish_window")
        if profile.has_healer:
            survival_chain.append("heal_on_soft_threshold")
        if not survival_chain:
            survival_chain.extend(["dodge_more_often", "retreat_on_hard_threshold"])
            conservative += 2
        if any(not c.known for c in profile.characters):
            conservative += 1
        if boss.mobility_profile in {"high", "teleporting"}:
            conservative += 1
        low_resource = ["skip_burst_if_energy_low", "use_e_skill_then_normal_attack", "preserve_stamina"]
        fallback = ["re_acquire_target", "reset_tactic", "safe_abort_after_repeated_failure"]
        return TeamCombatPlan(
            main_chain=main_chain,
            survival_chain=survival_chain,
            low_resource_chain=low_resource,
            fallback_chain=fallback,
            conservative_level=conservative,
            reason=self._reason(profile, boss, conservative),
        )

    def _main_chain(self, profile: TeamProfile, boss: BossProfile) -> list[str]:
        chain = list(boss.recommended_reactions)
        elements = set(profile.elements)
        if not chain:
            if {"pyro", "hydro"} <= elements:
                chain.append("Vaporize")
            if {"cryo", "hydro"} <= elements:
                chain.append("Frozen")
            if {"dendro", "electro"} <= elements:
                chain.append("Quicken")
        if not chain:
            chain.append("safe_basic_loop")
        resisted = {k for k, value in boss.elemental_resistance.items() if float(value) >= 0.6}
        if resisted:
            chain = [name for name in chain if not any(elem in name.lower() for elem in resisted)] or ["safe_basic_loop"]
        return chain

    def _reason(self, profile: TeamProfile, boss: BossProfile, conservative: int) -> str:
        survival = "healer" if profile.has_healer else "shielder" if profile.has_shielder else "no_survival"
        return f"team={survival}; boss={boss.boss_id}; conservative_level={conservative}"

    @staticmethod
    def _normalize_role(role: str) -> str:
        if "heal" in role:
            return "healer"
        if "shield" in role:
            return "shielder"
        return role

    @staticmethod
    def _survival_tools(raw: dict[str, Any], role: str) -> list[str]:
        tools = list(raw.get("survival_tools", []))
        if role == "healer" and "heal" not in tools:
            tools.append("heal")
        if role == "shielder" and "shield" not in tools:
            tools.append("shield")
        name = str(raw.get("name_en", "")).lower()
        if name in {"bennett", "jean", "kokomi", "kuki shinobu", "barbara", "qiqi"} and "heal" not in tools:
            tools.append("heal")
        if name in {"zhongli", "layla", "diona", "kirara", "noelle"} and "shield" not in tools:
            tools.append("shield")
        return tools
