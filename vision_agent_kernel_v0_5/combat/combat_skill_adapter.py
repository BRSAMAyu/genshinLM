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
        self._boss_router: Any | None = None

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
        boss_id: str = "",
    ) -> bool:
        """Execute a boss encounter with boss-aware playbook and retry.

        Uses BossMechanicRouter for known bosses with specific mechanics,
        falls back to generic playbook for unknown bosses.
        """
        # Route to specific boss handler if known
        if boss_id:
            router = self._get_boss_router()
            if router is not None and router.get_boss_phases(boss_id):
                log.info("[CombatSkill] routing to BossMechanicRouter for %s", boss_id)
                result = router.execute_boss_mechanics(boss_id)
                if result.success:
                    return True
                log.warning("[CombatSkill] BossMechanicRouter failed, falling back to playbook")

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
                "stamina_ratio": getattr(obs, "stamina_ratio", 1.0),
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
                    try:
                        threshold = float(cond.split("<", 1)[1])
                    except (ValueError, IndexError):
                        threshold = 0.2
                    if stamina_val < threshold:
                        data["signals"]["stamina_low"] = 1.0
                        break
            return data
        return _stream

    def _get_boss_router(self) -> Any:
        if self._boss_router is not None:
            return self._boss_router
        try:
            from combat.boss_mechanic_router import BossMechanicRouter
            self._boss_router = BossMechanicRouter(backend=self._backend)
        except Exception as exc:
            log.debug("[CombatSkill] BossMechanicRouter unavailable: %s", exc)
        return self._boss_router

    # ------------------------------------------------------------------
    # Combat rotation methods (weekly boss, world boss, multi-wave, shield)
    # ------------------------------------------------------------------

    def execute_weekly_rotation(self, context: dict[str, Any] | None = None) -> bool:
        """Cycle through weekly bosses with discount tracking."""
        from combat.combat_rotation_runners import WeeklyBossRotation
        # Build a lightweight executor that delegates to self
        executor = _CombatExecutorBridge(self)
        rotation = WeeklyBossRotation(executor=executor)
        targets = (context or {}).get("target_bosses")
        results = rotation.run_rotation(target_bosses=targets)
        return any(r.success for r in results)

    def execute_world_boss_farming(self, context: dict[str, Any] | None = None) -> bool:
        """Continuous world boss farming loop."""
        from combat.combat_rotation_runners import WorldBossFarming
        ctx = context or {}
        executor = _CombatExecutorBridge(self)
        farm = WorldBossFarming(executor=executor)
        results = farm.run(
            target_boss=ctx.get("boss_id", "hypostasis_pyro"),
            available_resin=ctx.get("resin", 160),
        )
        return any(r.success for r in results)

    def execute_multi_wave(self, context: dict[str, Any] | None = None) -> bool:
        """Multi-wave defense encounter."""
        from combat.combat_rotation_runners import MultiWaveDefense
        ctx = context or {}
        executor = _CombatExecutorBridge(self)
        defense = MultiWaveDefense(executor=executor)
        results = defense.run(total_waves=ctx.get("waves", 5))
        return all(r.success for r in results)

    def execute_shield_break(self, context: dict[str, Any] | None = None) -> bool:
        """Handle shield-bearing enemies like Mitachurls."""
        from combat.combat_rotation_runners import ShieldMitachurlStrategy
        ctx = context or {}
        executor = _CombatExecutorBridge(self)
        strategy = ShieldMitachurlStrategy(executor=executor)
        result = strategy.execute(shield_type=ctx.get("shield_type", "wood"))
        return result.success

    def execute_abyss_mage(self, context: dict[str, Any] | None = None) -> bool:
        """Handle Abyss Mage with elemental shield counter-strategy."""
        from combat.combat_rotation_runners import AbyssMageHandler
        ctx = context or {}
        executor = _CombatExecutorBridge(self)
        handler = AbyssMageHandler(executor=executor)
        result = handler.execute(mage_element=ctx.get("mage_element", "cryo"))
        return result.success

    # ------------------------------------------------------------------
    # Special boss handlers (Narwhal)
    # ------------------------------------------------------------------

    def execute_narwhal_combat(self, context: dict[str, Any] | None = None) -> bool:
        """Execute the Narwhal (All-Devouring) boss encounter."""
        # Narwhal uses the standard boss combat pipeline with narwhal boss_id
        return self.execute_boss_combat(
            team_elements=["dendro", "electro", "cryo", "anemo"],
            team_characters=["nahida", "shinobu", "zhongli", "baizhu"],
            boss_id="narwhal",
            duration_sec=(context or {}).get("timeout_sec", 300.0),
        )

    # ------------------------------------------------------------------
    # Environmental combat handlers (#12, #13)
    # ------------------------------------------------------------------

    def execute_environmental_combat(
        self,
        environment_type: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Execute environment-specific combat (Dragonspine/Inazuma)."""
        ctx = context or {}
        executor = _CombatExecutorBridge(self)
        if environment_type == "dragonspine":
            from combat.environmental_combat_handlers import DragonspineSheerColdHandler
            handler = DragonspineSheerColdHandler(executor=executor)
            result = handler.execute(
                initial_gauge=ctx.get("initial_gauge", 0.0),
                is_blizzard=ctx.get("is_blizzard", False),
                enemy_count=ctx.get("enemy_count", 3),
                has_fire_character=ctx.get("has_fire_character", True),
                has_warming_bottle=ctx.get("has_warming_bottle", False),
            )
            return result.success
        if environment_type == "inazuma_storm":
            from combat.environmental_combat_handlers import (
                InazumaThunderstormHandler,
                ThunderstormLevel,
            )
            handler = InazumaThunderstormHandler(executor=executor)
            result = handler.execute(
                storm_intensity=ThunderstormLevel(ctx.get("storm_intensity", "active")),
                enemy_count=ctx.get("enemy_count", 3),
                is_raining=ctx.get("is_raining", True),
                has_cryo_character=ctx.get("has_cryo_character", True),
                has_pyro_character=ctx.get("has_pyro_character", True),
            )
            return result.success
        log.warning("[CombatSkill] unknown environment type: %s", environment_type)
        return False

    # ------------------------------------------------------------------
    # Boss-specific combat handlers (#4-8)
    # ------------------------------------------------------------------

    def execute_boss_specific(
        self,
        boss_id: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Execute boss-specific handler for known weekly bosses."""
        executor = _CombatExecutorBridge(self)
        handlers = self._get_boss_handlers(executor)
        handler = handlers.get(boss_id)
        if handler is None:
            log.warning("[CombatSkill] no specific handler for boss: %s", boss_id)
            return False
        result = handler()
        if isinstance(result, bool):
            return result
        return result.success

    def _get_boss_handlers(self, executor: _CombatExecutorBridge) -> dict[str, Any]:
        """Lazy-load boss handler functions keyed by boss_id."""
        return {
            "dvalin": self._make_boss_handler("dvalin", executor),
            "stormterror_dvalin": self._make_boss_handler("dvalin", executor),
            "childe": self._make_boss_handler("childe", executor),
            "tartaglia": self._make_boss_handler("childe", executor),
            "signora": self._make_boss_handler("signora", executor),
            "la_signora": self._make_boss_handler("signora", executor),
            "raiden_shogun": self._make_boss_handler("raiden_shogun", executor),
            "shouki_no_kami": self._make_boss_handler("shouki_no_kami", executor),
            "scaramouche": self._make_boss_handler("shouki_no_kami", executor),
            "narwhal": self._make_boss_handler("narwhal", executor),
            "all_devouring_narwhal": self._make_boss_handler("narwhal", executor),
        }

    def _make_boss_handler(self, boss_key: str, executor: _CombatExecutorBridge) -> Any:
        """Create a lazy boss handler callable."""
        def _handler() -> Any:
            if boss_key == "dvalin":
                from combat.boss_combat_handlers import DvalinHandler
                return DvalinHandler(executor).execute()
            if boss_key == "childe":
                from combat.boss_combat_handlers import ChildeHandler
                return ChildeHandler(executor).execute()
            if boss_key == "signora":
                from combat.boss_combat_handlers import SignoraHandler
                return SignoraHandler(executor).execute()
            if boss_key == "raiden_shogun":
                from combat.boss_combat_handlers import RaidenShogunHandler
                return RaidenShogunHandler(executor).execute()
            if boss_key == "shouki_no_kami":
                from combat.boss_combat_handlers import ShoukiNoKamiHandler
                return ShoukiNoKamiHandler(executor).execute()
            if boss_key == "narwhal":
                from combat.boss_combat_handlers import NarwhalHandler
                return NarwhalHandler(executor).execute()
            return False
        return _handler


class _CombatExecutorBridge:
    """Bridge CombatSkillAdapter to SemanticExecutor protocol for rotation runners."""

    def __init__(self, adapter: CombatSkillAdapter) -> None:
        self._adapter = adapter

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        if action == "combat_boss":
            return self._adapter.execute_boss_combat(
                team_elements=["pyro", "hydro", "cryo", "anemo"],
                team_characters=["amber", "kaeya", "lisa", "traveler"],
                boss_id=target or (context or {}).get("boss_id", ""),
                duration_sec=(context or {}).get("timeout_sec", 180.0),
            )
        if action == "combat_basic_attack":
            return self._adapter.execute_basic_attack(
                duration_sec=(context or {}).get("timeout_sec", 10.0),
            )
        # For teleport/navigate/interact — log and return True (mock)
        log.debug("[CombatBridge] %s target=%s", action, target)
        return True
