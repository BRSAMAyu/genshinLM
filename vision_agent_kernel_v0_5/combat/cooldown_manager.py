from __future__ import annotations

import time
from dataclasses import dataclass

from combat.combat_action_state import CooldownState


@dataclass(slots=True)
class SkillCooldownConfig:
    skill_id: str
    base_cooldown_ms: int


class CooldownManager:
    def __init__(self, configs: list[SkillCooldownConfig] | None = None) -> None:
        self._configs = {item.skill_id: item for item in configs or []}
        self._last_used: dict[str, float] = {}

    def mark_used(self, skill_id: str) -> None:
        self._last_used[skill_id] = time.perf_counter()

    def update_from_ocr(self, skill_id: str, text: str, confidence: float = 0.8) -> CooldownState:
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return CooldownState(False, -1, confidence * 0.3)
        remaining_ms = int(digits) * 1000
        cap = self._configs.get(skill_id, SkillCooldownConfig(skill_id, 60000)).base_cooldown_ms
        remaining_ms = min(remaining_ms, max(60000, cap))
        return CooldownState(remaining_ms <= 0, remaining_ms, confidence)

    def update_from_template(self, skill_id: str, is_grey: bool, confidence: float = 0.7) -> CooldownState:
        if not is_grey:
            return CooldownState(True, 0, confidence)
        estimate = self.estimate(skill_id)
        return CooldownState(False, estimate.remaining_ms or self._configs.get(skill_id, SkillCooldownConfig(skill_id, 1000)).base_cooldown_ms, confidence)

    def estimate(self, skill_id: str) -> CooldownState:
        config = self._configs.get(skill_id, SkillCooldownConfig(skill_id, 0))
        elapsed_ms = int((time.perf_counter() - self._last_used.get(skill_id, 0.0)) * 1000)
        remaining = max(0, config.base_cooldown_ms - elapsed_ms)
        return CooldownState(remaining == 0, remaining, 0.55)

