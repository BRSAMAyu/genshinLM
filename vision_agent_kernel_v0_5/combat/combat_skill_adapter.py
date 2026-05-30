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
        self._active_playbook_id: str | None = None

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
        self._active_playbook_id = playbook.playbook_id
        log.info(
            "[CombatSkill] playbook=%s rotation=%d steps chain=%s",
            playbook.playbook_id,
            len(playbook.default_rotation),
            playbook.elemental_chain,
        )

        steps = self._rotation_to_steps(playbook.default_rotation)
        obs_stream = self._make_obs_stream()

        for attempt in range(self._config.max_retries + 1):
            if attempt > 0:
                log.info("[CombatSkill] retry attempt %d/%d", attempt, self._config.max_retries)
            result = self._actuator.execute_combat_loop(
                playbook_steps=steps,
                obs_stream=obs_stream,
                duration_limit_sec=duration,
            )
            if result:
                self._active_playbook_id = None
                return True

        self._active_playbook_id = None
        log.warning("[CombatSkill] combat failed after %d attempts", self._config.max_retries + 1)
        return False

    def execute_boss_combat(
        self,
        team_elements: list[str],
        team_characters: list[str],
        boss_profile: Any | None = None,
        duration_sec: float = 30.0,
    ) -> bool:
        """Execute a boss encounter with boss-aware playbook."""
        playbook, _team_plan = self._planner.generate_boss_playbook(
            team_elements=team_elements,
            team_characters=team_characters,
            boss_profile=boss_profile,
        )
        self._active_playbook_id = playbook.playbook_id
        log.info(
            "[CombatSkill] boss playbook=%s triggers=%d",
            playbook.playbook_id,
            len(playbook.priority_triggers),
        )

        steps = self._rotation_to_steps(playbook.default_rotation)
        obs_stream = self._make_obs_stream()

        result = self._actuator.execute_combat_loop(
            playbook_steps=steps,
            obs_stream=obs_stream,
            duration_limit_sec=duration_sec,
        )
        self._active_playbook_id = None
        return result

    def execute_basic_attack(self, duration_sec: float = 2.0) -> bool:
        """Execute a simple auto-attack sequence for easy encounters."""
        steps = [
            {"type": "attack", "duration": duration_sec},
        ]
        obs_stream = self._make_obs_stream()
        return self._actuator.execute_combat_loop(
            playbook_steps=steps,
            obs_stream=obs_stream,
            duration_limit_sec=duration_sec + 1.0,
        )

    def get_combat_context(self) -> CombatContext:
        """Read current combat state from StateBus."""
        if self._bus is None:
            return CombatContext()
        obs = self._bus.latest_observation.get()
        if obs is None:
            return CombatContext()
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
        steps: list[dict[str, Any]] = []
        for action in rotation:
            if action.action in ("normal_attack", "attack"):
                steps.append({"type": "attack", "duration": 0.5 * action.repeat})
            elif action.action in ("e_skill", "use_skill", "skill"):
                steps.append({"type": "skill_e"})
            elif action.action in ("q_burst", "use_burst", "burst"):
                steps.append({"type": "burst_q"})
            elif action.action == "switch":
                steps.append({"type": "switch", "character": action.character})
        return steps

    def _make_obs_stream(self) -> Callable[[], dict[str, Any] | None]:
        """Create an observation stream callable for LiveCombatActuator."""
        def _stream() -> dict[str, Any] | None:
            if self._bus is None:
                return None
            obs = self._bus.latest_observation.get()
            if obs is None:
                return None
            return {
                "hp_ratio": getattr(obs, "hp_ratio", 1.0),
                "target_offset_x": getattr(obs, "target_offset_x", 0.0),
                "signals": getattr(obs, "signals", {}),
            }
        return _stream
