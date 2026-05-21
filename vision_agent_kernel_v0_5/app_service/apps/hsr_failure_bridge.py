from __future__ import annotations

from core.state_bus import StateBus
from core.types import SkillResult
from learning.genshin_failure_analyzer import (
    FailureCategory,
    GenshinFailureAnalyzer,
    make_failure_signature,
)

_HSR_FAILURE_CODE_MAP: dict[str, FailureCategory] = {
    "COMBAT_TIMEOUT": FailureCategory.COMBAT_TIMEOUT,
    "TARGET_LOST": FailureCategory.TARGET_LOST,
    "HP_DEPLETED": FailureCategory.HP_DEPLETED,
    "SKILL_MISS": FailureCategory.SKILL_MISS,
    "NAVIGATION_FAILED": FailureCategory.NAVIGATION_FAILED,
    "COLLECTION_FAILED": FailureCategory.COLLECTION_FAILED,
    "SP_EXHAUSTED": FailureCategory.STAMINA_EXHAUSTED,
    "WEAKNESS_NOT_EXPLOITED": FailureCategory.ELEMENT_MISMATCH,
    "WAVE_WIPE_FAILED": FailureCategory.COMBAT_TIMEOUT,
    "ULTIMATE_MISSED": FailureCategory.SKILL_MISS,
}


class HSRFailureBridge:
    """Bridges Orchestrator failures to HSR failure analysis."""

    def __init__(self, state_bus: StateBus) -> None:
        self._state_bus = state_bus
        self._analyzer = GenshinFailureAnalyzer()
        self._failure_slot = state_bus.register_slot("hsr.failure_state")

    def on_skill_result(self, result: SkillResult) -> None:
        if result.status != "FAILED":
            return

        category = _HSR_FAILURE_CODE_MAP.get(
            result.failure_code or "", FailureCategory.COMBAT_TIMEOUT
        )
        signature = make_failure_signature(
            category=category,
            playbook_id="",
            step_index=0,
            enemy_id="",
            team_composition=[],
            region="",
            duration_ms=0,
            context={"failure_code": result.failure_code, "skill": result.skill_name},
        )
        self._analyzer.record_failure(signature)
        patterns = self._analyzer.analyze_patterns()
        self._failure_slot.put({
            "failure_id": signature.failure_id,
            "patterns": [
                {"category": p.category.value, "count": p.occurrence_count} for p in patterns
            ],
            "suggestions": self._analyzer.get_suggestions(),
        })
