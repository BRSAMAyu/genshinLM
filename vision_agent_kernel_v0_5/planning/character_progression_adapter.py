"""Orchestrate the 6-stage character progression chain.

Stage 1: Level Up (1-90)
Stage 2: Ascend (level cap breakthrough)
Stage 3: Weapon Equip/Enhance/Refine
Stage 4: Artifact Equip/Enhance
Stage 5: Talent Upgrade (Normal Attack / Skill / Burst)
Stage 6: Team Configuration

Coordinates UIFlowSkillAdapter for UI operations and resource checking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)


class SkillExecutor(Protocol):
    def execute_semantic(self, action: str, target: str = "", context: dict[str, Any] | None = None) -> bool: ...


@dataclass(frozen=True, slots=True)
class CharacterProgressionConfig:
    max_level: int = 90
    max_talent_level: int = 10
    max_weapon_refine: int = 5


@dataclass(frozen=True, slots=True)
class ProgressionResult:
    stage: int
    stage_name: str
    success: bool
    details: str = ""


class CharacterProgressionAdapter:
    """Orchestrate complete character progression through 6 stages.

    Each stage delegates to UIFlowSkillAdapter via the semantic executor.
    Stages can be run individually or as a complete chain.
    """

    def __init__(
        self,
        *,
        skill_executor: SkillExecutor,
        config: CharacterProgressionConfig | None = None,
    ) -> None:
        self._executor = skill_executor
        self._config = config or CharacterProgressionConfig()

    def run_full_chain(self, character: str = "") -> list[ProgressionResult]:
        """Execute all 6 progression stages for a character."""
        results: list[ProgressionResult] = []
        log.info("[Progression] full chain for '%s'", character or "current")

        for stage_fn in (
            self.stage1_level_up,
            self.stage2_ascend,
            self.stage3_weapon,
            self.stage4_artifact,
            self.stage5_talent,
            self.stage6_team_config,
        ):
            result = stage_fn(character)
            results.append(result)
            if not result.success:
                log.warning("[Progression] stage %s failed: %s", result.stage_name, result.details)
                break

        return results

    def stage1_level_up(self, character: str = "") -> ProgressionResult:
        """Stage 1: Level up character using EXP books."""
        log.info("[Progression] Stage 1: Level Up")
        ok = self._executor.execute_semantic(
            "character_level_up_full",
            target=character,
        )
        return ProgressionResult(
            stage=1,
            stage_name="level_up",
            success=ok,
            details="open_menu → level_up → close" if ok else "level up flow failed",
        )

    def stage2_ascend(self, character: str = "") -> ProgressionResult:
        """Stage 2: Ascend character at level cap."""
        log.info("[Progression] Stage 2: Ascend")
        ok = self._executor.execute_semantic(
            "character_ascend_full",
            target=character,
        )
        return ProgressionResult(
            stage=2,
            stage_name="ascend",
            success=ok,
            details="ascension completed" if ok else "ascension failed or not at cap",
        )

    def stage3_weapon(self, character: str = "") -> ProgressionResult:
        """Stage 3: Equip and enhance weapon."""
        log.info("[Progression] Stage 3: Weapon")
        equip_ok = self._executor.execute_semantic("weapon_equip_full", target=character)
        enhance_ok = self._executor.execute_semantic("weapon_enhance_full", target=character)
        ok = equip_ok and enhance_ok
        if not ok and (equip_ok or enhance_ok):
            ok = True  # partial success — still proceed to next stage
        return ProgressionResult(
            stage=3,
            stage_name="weapon",
            success=ok,
            details=f"equip={equip_ok} enhance={enhance_ok}",
        )

    def stage4_artifact(self, character: str = "") -> ProgressionResult:
        """Stage 4: Equip and enhance artifacts."""
        log.info("[Progression] Stage 4: Artifact")
        equip_ok = self._executor.execute_semantic("artifact_equip_full", target=character)
        enhance_ok = self._executor.execute_semantic("artifact_enhance_full", target=character)
        ok = equip_ok and enhance_ok
        if not ok and (equip_ok or enhance_ok):
            ok = True  # partial success — still proceed to next stage
        return ProgressionResult(
            stage=4,
            stage_name="artifact",
            success=ok,
            details=f"equip={equip_ok} enhance={enhance_ok}",
        )

    def stage5_talent(self, character: str = "") -> ProgressionResult:
        """Stage 5: Upgrade all 3 talents."""
        log.info("[Progression] Stage 5: Talent")
        results: list[bool] = []
        for talent_flow in (
            "character_talent_upgrade_full",
            "character_talent_upgrade_skill",
            "character_talent_upgrade_burst",
        ):
            ok = self._executor.execute_semantic(talent_flow, target=character)
            results.append(ok)
        ok = any(results)
        return ProgressionResult(
            stage=5,
            stage_name="talent",
            success=ok,
            details=f"normal={results[0]} skill={results[1]} burst={results[2]}",
        )

    def stage6_team_config(self, character: str = "") -> ProgressionResult:
        """Stage 6: Configure team with this character."""
        log.info("[Progression] Stage 6: Team Config")
        ok = self._executor.execute_semantic("party_quick_config")
        return ProgressionResult(
            stage=6,
            stage_name="team_config",
            success=ok,
            details="party configured" if ok else "party config failed",
        )
