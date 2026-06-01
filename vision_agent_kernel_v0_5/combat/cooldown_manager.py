import time
import logging
from typing import Any
from dataclasses import dataclass

from combat.combat_action_state import CooldownState

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SkillCooldownConfig:
    skill_id: str
    base_cooldown_ms: int


class CooldownManager:
    def __init__(self, configs: list[SkillCooldownConfig] | None = None, input_backend: Any = None) -> None:
        self._configs = {item.skill_id: item for item in configs or []}
        self._last_used: dict[str, float] = {}
        self.input_backend = input_backend
        
        # State Bus caching for Embodied AI character metrics
        self.char_hp: dict[int, float] = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}
        self.char_energy: dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}

    def update_character_hp(self, slot_id: int, hp_pct: float) -> None:
        """Updates internal HP cache and triggers emergency food if HP is critically low (<20%)."""
        self.char_hp[slot_id] = hp_pct
        if hp_pct < 0.2:
            log.warning(f"[CooldownManager] CRITICAL HP DETECTED in slot {slot_id} ({hp_pct*100:.1f}%)! Triggering recovery.")
            self.trigger_emergency_food_healing(slot_id)

    def update_character_energy(self, slot_id: int, energy_pct: float) -> None:
        self.char_energy[slot_id] = energy_pct

    def trigger_emergency_food_healing(self, target_slot: int) -> bool:
        """Executes inventory/backpack visual actions to feed recovery items to low HP characters."""
        if self.input_backend is None:
            log.warning("[CooldownManager] No input_backend configured for emergency healing.")
            return False
            
        import time
        log.info(f"[CooldownManager] Executing emergency food healing sequence for character slot {target_slot}...")
        
        # 1. Press B to open backpack
        if hasattr(self.input_backend, "key_press"):
            self.input_backend.key_press("b", reason="open_backpack_emergency")
        time.sleep(0.5)
        
        # 2. Click on the Food Tab
        # For simulation/mock purposes, we assume coordinates (x=450, y=80) for the food tab on standard UI
        if hasattr(self.input_backend, "mouse_move_to") and hasattr(self.input_backend, "left_click"):
            self.input_backend.mouse_move_to(450, 80, reason="backpack_food_tab")
            self.input_backend.left_click(reason="backpack_food_tab")
        time.sleep(0.3)
        
        # 3. Double-click premium recovery food (e.g., Sweet Madame at coordinates x=200, y=250)
        if hasattr(self.input_backend, "mouse_move_to") and hasattr(self.input_backend, "left_click"):
            self.input_backend.mouse_move_to(200, 250, reason="select_premium_recovery_food")
            self.input_backend.left_click(reason="select_premium_recovery_food")
            time.sleep(0.1)
            self.input_backend.left_click(reason="use_recovery_food")
        time.sleep(0.3)
        
        # 4. Select target slot and confirm feeding
        if hasattr(self.input_backend, "key_press"):
            self.input_backend.key_press(str(target_slot), reason="select_low_hp_character")
            time.sleep(0.2)
            self.input_backend.key_press("space", reason="confirm_eat_food")
        time.sleep(0.3)
        
        # 5. Exit backpack
        if hasattr(self.input_backend, "key_press"):
            self.input_backend.key_press("escape", reason="close_backpack_resume")
        time.sleep(0.2)
        return True

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

