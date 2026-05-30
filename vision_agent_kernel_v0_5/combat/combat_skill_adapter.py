"""Bridge semantic combat actions to the GenshinCombatPlanner + LiveCombatActuator pipeline.

Provides a high-level ``execute_combat`` method that:
1. Builds a combat playbook via ``GenshinCombatPlanner``
2. Executes it via ``LiveCombatActuator`` with StateBus observation
3. Falls back to primitive attack/skill/burst when no playbook is available
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from combat.combat_context import CombatContext
from combat.genshin_combat_planner import GenshinCombatPlanner
from combat.live_combat_actuator import LiveCombatActuator

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CombatSkillAdapterConfig:
    default_combat_duration_sec: float = 10.0
    max_retries: int = 2
    hp_threshold_retreat: float = 0.20
    target_offset_threshold: float = 0.15


class CombatSkillAdapter:
    """Orchestrate combat from semantic action to playbook execution.

    Integrates with StateBus for observation and UIFlowSkillAdapter for
    primitive combat actions (attack, skill, burst, dodge).
    """

    def __init__(
        self,
        *,
        backend: Any,
        state_bus: Any | None = None,
        planner: GenshinCombatPlanner | None = None,
        config: CombatSkillAdapterConfig | None = None,
    ) -> None:
        self._backend = backend
        self._bus = state_bus
        self._config = config or CombatSkillAdapterConfig()
        self._planner = planner or GenshinCombatPlanner()
        self._actuator = LiveCombatActuator(backend=backend)

    def execute_combat(
        self,
        team_elements: list[str],
        team_characters: list[str],
        enemy_id: str = "unknown",
        enemy_weaknesses: list[str] | None = None,
        duration_sec: float | None = None,
    ) -> bool:
        """Execute a full combat encounter using generated playbook."""
        duration = duration_sec or self._config.default_combat_duration_sec

        playbook = self._planner.generate_playbook(
            team_elements=team_elements,
            team_characters=team_characters,
            enemy_id=enemy_id,
            enemy_weaknesses=enemy_weaknesses,
        )
        log.info(
            "[CombatSkill] playbook=%s rotation=%d steps chain=%s",
            playbook.playbook_id,
            len(playbook.default_rotation),
            playbook.elemental_chain,
        )

        steps = self._rotation_to_steps(playbook.default_rotation)
        obs_stream = self._make_obs_stream_with_triggers(playbook.priority_triggers)

        for attempt in range(self._config.max_retries + 1):
            if attempt > 0:
                log.info("[CombatSkill] retry attempt %d/%d", attempt, self._config.max_retries)
            result = self._actuator.execute_combat_loop(
                playbook_steps=steps,
                obs_stream=obs_stream,
                duration_limit_sec=duration,
            )
            if result:
                return True

        log.warning("[CombatSkill] combat failed after %d attempts", self._config.max_retries + 1)
        return False

    def execute_boss_combat(
        self,
        team_elements: list[str],
        team_characters: list[str],
        boss_profile: Any | None = None,
        duration_sec: float = 30.0,
    ) -> bool:
        """Execute a boss encounter with boss-aware playbook and retry."""
        playbook, _team_plan = self._planner.generate_boss_playbook(
            team_elements=team_elements,
            team_characters=team_characters,
            boss_profile=boss_profile,
        )
        log.info(
            "[CombatSkill] boss playbook=%s triggers=%d",
            playbook.playbook_id,
            len(playbook.priority_triggers),
        )

        steps = self._rotation_to_steps(playbook.default_rotation)
        obs_stream = self._make_obs_stream_with_triggers(playbook.priority_triggers)

        for attempt in range(self._config.max_retries + 1):
            if attempt > 0:
                log.info("[CombatSkill] boss retry attempt %d/%d", attempt, self._config.max_retries)
            result = self._actuator.execute_combat_loop(
                playbook_steps=steps,
                obs_stream=obs_stream,
                duration_limit_sec=duration_sec,
            )
            if result:
                return True

        log.warning("[CombatSkill] boss combat failed after %d attempts", self._config.max_retries + 1)
        return False

    def execute_basic_attack(self, duration_sec: float = 2.0) -> bool:
        """Execute a simple auto-attack sequence for easy encounters."""
        steps = [
            {"type": "attack", "duration": duration_sec},
        ]
        obs_stream = self._make_obs_stream_with_triggers([])
        return self._actuator.execute_combat_loop(
            playbook_steps=steps,
            obs_stream=obs_stream,
            duration_limit_sec=duration_sec + 1.0,
        )

    def get_combat_context(self) -> CombatContext:
        """Read current combat state from StateBus."""
        if self._bus is None:
            return CombatContext(target_visible=False)
        obs = self._bus.latest_observation.get()
        if obs is None:
            return CombatContext(target_visible=False)
        hp_ratio = getattr(obs, "hp_ratio", 1.0)
        target_visible = getattr(obs, "target_visible", False)
        stamina = getattr(obs, "stamina_ratio", 1.0)
        danger = getattr(obs, "danger_priority", 0.0)
        return CombatContext(
            target_visible=target_visible,
            hp_ratio=hp_ratio,
            stamina_ratio=stamina,
            danger_priority=danger,
        )

    @staticmethod
    def _rotation_to_steps(rotation: list[Any]) -> list[dict[str, Any]]:
        """Convert CombatAction list to LiveCombatActuator step dicts."""
        _ACTION_MAP: dict[str, str] = {
            "normal_attack": "attack",
            "attack": "attack",
            "e_skill": "skill_e",
            "use_skill": "skill_e",
            "skill": "skill_e",
            "q_burst": "burst_q",
            "use_burst": "burst_q",
            "burst": "burst_q",
            "switch": "switch",
            "dodge": "dodge",
            "charge_attack": "attack",
            "dash": "dodge",
            "heal": "skill_e",
            "shield": "skill_e",
            "retreat": "dodge",
        }
        steps: list[dict[str, Any]] = []
        for action in rotation:
            step_type = _ACTION_MAP.get(action.action)
            if step_type == "attack":
                steps.append({"type": "attack", "duration": 0.5 * action.repeat})
            elif step_type == "switch":
                steps.append({"type": "switch", "character": action.character})
            elif step_type is not None:
                steps.append({"type": step_type})
        return steps

    def _make_obs_stream_with_triggers(
        self,
        triggers: list[Any],
    ) -> Callable[[], dict[str, Any] | None]:
        """Create an observation stream that evaluates priority triggers."""
        def _stream() -> dict[str, Any] | None:
            if self._bus is None:
                return None
            obs = self._bus.latest_observation.get()
            if obs is None:
                return None
            data: dict[str, Any] = {
                "hp_ratio": getattr(obs, "hp_ratio", 1.0),
                "target_offset_x": getattr(obs, "target_offset_x", 0.0),
                "signals": dict(getattr(obs, "signals", {})),
            }
            # Evaluate priority triggers — inject interrupt signals
            hp = data["hp_ratio"]
            for trigger in triggers:
                cond = trigger.condition.lower().replace(" ", "")
                # Parse structured conditions: "hp<0.2", "stamina<0.3"
                if cond.startswith("hp") and "<" in cond:
                    try:
                        threshold = float(cond.split("<", 1)[1])
                    except (ValueError, IndexError):
                        threshold = self._config.hp_threshold_retreat
                    if hp < threshold:
                        data["signals"]["attack_incoming"] = 1.0
                        break
                elif cond.startswith("stamina") and "<" in cond:
                    stamina_val = data.get("stamina_ratio", 1.0)
                    if stamina_val not in data:
                        data["stamina_ratio"] = stamina_val
                    try:
                        threshold = float(cond.split("<", 1)[1])
                    except (ValueError, IndexError):
                        threshold = 0.2
                    if stamina_val < threshold:
                        data["signals"]["stamina_low"] = 1.0
                        break
            return data
        return _stream
