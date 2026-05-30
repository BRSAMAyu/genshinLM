"""SkillRegistry: route composite semantic actions to specialized adapters.

Bridges the gap between AutonomousTaskBrain's flat ``execute_semantic`` and the
5 specialized adapters (Combat, Exploration, Quest, DailyRoutine,
CharacterProgression).  Composite actions like ``"run_daily_deep"`` are resolved
here and delegated to the appropriate adapter method.

Lazy instantiation: adapters are created on first use so the registry is cheap
to construct and only pulls in heavy dependencies when actually needed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


class BackendProvider(Protocol):
    """Minimal protocol for input backends."""

    def key_down(self, key: str, *, reason: str = "") -> None: ...
    def key_up(self, key: str, *, reason: str = "") -> None: ...
    def key_press(self, key: str, *, reason: str = "") -> None: ...
    def action_intent(self, action: str, *, reason: str = "") -> None: ...


class SemanticExecutor(Protocol):
    """Unified protocol matching UIFlowSkillAdapter.execute_semantic."""

    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Composite action routing table
# ---------------------------------------------------------------------------

_COMPOSITE_ROUTES: dict[str, tuple[str, str]] = {
    # Daily routine 3-layer composites
    "run_daily_quick": ("daily_routine", "execute_layer1"),
    "run_daily_standard": ("daily_routine", "execute_layer2"),
    "run_daily_deep": ("daily_routine", "execute_layer3"),
    # Character progression chain
    "character_progression_full": ("progression", "run_full_chain"),
    "character_progression_level_up": ("progression", "stage1_level_up"),
    "character_progression_ascend": ("progression", "stage2_ascend"),
    "character_progression_weapon": ("progression", "stage3_weapon"),
    "character_progression_artifact": ("progression", "stage4_artifact"),
    "character_progression_talent": ("progression", "stage5_talent"),
    "character_progression_team": ("progression", "stage6_team_config"),
    # Combat composites
    "combat_encounter": ("combat", "execute_combat"),
    "combat_boss": ("combat", "execute_boss_combat"),
    "combat_basic_attack": ("combat", "execute_basic_attack"),
    # Exploration composites
    "explore_activate_waypoint": ("exploration", "activate_waypoint"),
    "explore_open_chest": ("exploration", "open_chest"),
    "explore_collect_oculus": ("exploration", "collect_oculus"),
    "explore_interact": ("exploration", "interact_with_object"),
    # Exploration scenario routing
    "explore_scenario": ("exploration_scenario", "execute_scenario"),
    # Quest composites
    "quest_drive_dialog": ("quest", "drive_dialog"),
    "quest_skip_cutscene": ("quest", "skip_cutscene"),
    "quest_follow_marker": ("quest", "follow_quest_marker"),
    "quest_advance": ("quest", "advance_quest"),
    "quest_check_prerequisites": ("quest", "check_prerequisites"),
    # Mainline progression
    "mainline_full_progression": ("mainline", "run_full_progression"),
    "mainline_execute_chapter": ("mainline", "execute_chapter"),
}

_ADAPTER_METHOD_EXTRA_ARGS: dict[str, list[str]] = {
    "combat.execute_combat": ["team_elements", "team_characters"],
    "combat.execute_boss_combat": ["team_elements", "team_characters"],
    "combat.execute_basic_attack": [],
    "progression.run_full_chain": ["character"],
    "progression.stage1_level_up": ["character"],
    "progression.stage2_ascend": ["character"],
    "progression.stage3_weapon": ["character"],
    "progression.stage4_artifact": ["character"],
    "progression.stage5_talent": ["character"],
    "progression.stage6_team_config": ["character"],
    "daily_routine.execute_layer1": ["context"],
    "daily_routine.execute_layer2": ["context"],
    "daily_routine.execute_layer3": ["context"],
    "exploration.activate_waypoint": [],
    "exploration.open_chest": [],
    "exploration.collect_oculus": [],
    "exploration.interact_with_object": ["object_type"],
    "exploration_scenario.execute_scenario": ["scenario"],
    "quest.drive_dialog": ["choice_selector"],
    "quest.skip_cutscene": ["timeout_sec"],
    "quest.follow_quest_marker": ["navigate_fn"],
    "quest.advance_quest": ["evidence"],
    "quest.check_prerequisites": ["current_ar"],
    "mainline.run_full_progression": ["current_ar"],
    "mainline.execute_chapter": ["chapter_id"],
    # Exploration scenario routing
    "explore_scenario": ["scenario"],
}


@dataclass(frozen=True, slots=True)
class SkillRegistryConfig:
    combat_max_retries: int = 2
    combat_default_duration_sec: float = 10.0
    daily_max_commissions: int = 4
    progression_max_level: int = 90


class SkillRegistry:
    """Route composite semantic actions to the correct specialized adapter.

    Usage::

        registry = SkillRegistry(
            skill_executor=ui_flow_adapter,
            state_bus=bus,
        )
        # Composite action — delegated to DailyRoutineSkillAdapter
        registry.execute("run_daily_deep", context={"resin_priority": "artifact"})
        # Simple action — forwarded to UIFlowSkillAdapter
        registry.execute("open_menu")
    """

    def __init__(
        self,
        *,
        skill_executor: SemanticExecutor,
        state_bus: Any | None = None,
        config: SkillRegistryConfig | None = None,
    ) -> None:
        self._executor = skill_executor
        self._bus = state_bus
        self._config = config or SkillRegistryConfig()
        self._adapters: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_handle(self, action: str) -> bool:
        """Return True if this action is a known composite route."""
        return action in _COMPOSITE_ROUTES

    def execute(
        self,
        action: str,
        target: str = "",
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Execute a composite action via the appropriate adapter.

        Returns False for unknown actions (caller should fallback).
        """
        route = _COMPOSITE_ROUTES.get(action)
        if route is None:
            return False

        adapter_key, method_name = route
        context = context or {}

        adapter = self._get_adapter(adapter_key)
        if adapter is None:
            log.warning("[SkillRegistry] adapter '%s' not available for action '%s'", adapter_key, action)
            return False

        method = getattr(adapter, method_name, None)
        if method is None:
            log.warning("[SkillRegistry] method '%s' missing on adapter '%s'", method_name, adapter_key)
            return False

        args = self._build_method_args(adapter_key, method_name, target, context)
        try:
            result = method(**args)
        except Exception as exc:
            log.warning("[SkillRegistry] %s.%s failed: %s", adapter_key, method_name, exc)
            return False

        # Adapters return bool, list[ProgressionResult], or dataclass with .success
        if isinstance(result, bool):
            return result
        if isinstance(result, list):
            return all(getattr(r, "success", False) for r in result)
        # Dataclass results: check .success field
        success = getattr(result, "success", None)
        if success is not None:
            return bool(success)
        return True

    @property
    def composite_actions(self) -> tuple[str, ...]:
        return tuple(sorted(_COMPOSITE_ROUTES))

    # ------------------------------------------------------------------
    # Adapter lazy instantiation
    # ------------------------------------------------------------------

    def _get_adapter(self, key: str) -> Any:
        if key in self._adapters:
            return self._adapters[key]
        adapter = self._create_adapter(key)
        if adapter is not None:
            self._adapters[key] = adapter
        return adapter

    def _create_adapter(self, key: str) -> Any:
        try:
            if key == "combat":
                return self._create_combat_adapter()
            if key == "exploration":
                return self._create_exploration_adapter()
            if key == "quest":
                return self._create_quest_adapter()
            if key == "daily_routine":
                return self._create_daily_routine_adapter()
            if key == "progression":
                return self._create_progression_adapter()
            if key == "mainline":
                return self._create_mainline_adapter()
            if key == "exploration_scenario":
                return self._create_exploration_scenario_adapter()
        except Exception as exc:
            log.warning("[SkillRegistry] failed to create adapter '%s': %s", key, exc)
        return None

    def _get_backend(self) -> Any:
        """Extract backend from skill_executor if available."""
        executor = self._executor
        # UIFlowSkillAdapter exposes _worker.backend
        worker = getattr(executor, "_worker", None)
        if worker is not None:
            return getattr(worker, "backend", None)
        # Fallback: check if executor itself acts as backend
        if hasattr(executor, "key_down") and hasattr(executor, "key_up"):
            return executor
        return None

    def _create_combat_adapter(self) -> Any:
        from combat.combat_skill_adapter import CombatSkillAdapter, CombatSkillAdapterConfig

        backend = self._get_backend()
        if backend is None:
            return None
        config = CombatSkillAdapterConfig(
            max_retries=self._config.combat_max_retries,
            default_combat_duration_sec=self._config.combat_default_duration_sec,
        )
        return CombatSkillAdapter(backend=backend, state_bus=self._bus, config=config)

    def _create_exploration_adapter(self) -> Any:
        from exploration.exploration_skill_adapter import ExplorationSkillAdapter

        backend = self._get_backend()
        if backend is None:
            return None
        return ExplorationSkillAdapter(
            backend=backend,
            state_bus=self._bus,
            skill_adapter=self._executor,
        )

    def _create_quest_adapter(self) -> Any:
        from planning.quest_skill_adapter import QuestSkillAdapter

        backend = self._get_backend()
        if backend is None:
            return None
        return QuestSkillAdapter(backend=backend, state_bus=self._bus)

    def _create_daily_routine_adapter(self) -> Any:
        from orchestration.daily_routine_skill_adapter import DailyRoutineSkillAdapter, DailyRoutineConfig

        config = DailyRoutineConfig(max_commissions=self._config.daily_max_commissions)
        return DailyRoutineSkillAdapter(skill_executor=self._executor, config=config)

    def _create_progression_adapter(self) -> Any:
        from planning.character_progression_adapter import CharacterProgressionAdapter, CharacterProgressionConfig

        config = CharacterProgressionConfig(max_level=self._config.progression_max_level)
        return CharacterProgressionAdapter(skill_executor=self._executor, config=config)

    def _create_mainline_adapter(self) -> Any:
        from planning.mainline.mainline_progression_adapter import MainlineProgressionAdapter, MainlineProgressionConfig

        config = MainlineProgressionConfig()
        return MainlineProgressionAdapter(
            skill_executor=self._executor,
            config=config,
            skill_registry=self,
        )

    def _create_exploration_scenario_adapter(self) -> Any:
        from exploration.exploration_scenario_router import ExplorationScenarioRouter

        return ExplorationScenarioRouter(skill_executor=self._executor)

    # ------------------------------------------------------------------
    # Argument building
    # ------------------------------------------------------------------

    def _build_method_args(
        self,
        adapter_key: str,
        method_name: str,
        target: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        route_key = f"{adapter_key}.{method_name}"
        param_names = _ADAPTER_METHOD_EXTRA_ARGS.get(route_key, [])
        args: dict[str, Any] = {}

        for param in param_names:
            if param in context:
                args[param] = context[param]
            elif target and param in ("character", "object_type", "evidence", "chapter_id"):
                args[param] = target
            # Provide safe defaults for missing params
            elif param == "team_elements":
                args[param] = context.get("team_elements", ["pyro", "hydro", "cryo", "anemo"])
            elif param == "team_characters":
                args[param] = context.get("team_characters", ["amber", "kaeya", "lisa", "traveler"])
            elif param == "navigate_fn":
                args[param] = context.get("navigate_fn", lambda: True)
            elif param == "choice_selector":
                args[param] = context.get("choice_selector", lambda choices: 0)
            elif param == "timeout_sec":
                args[param] = context.get("timeout_sec", 30.0)
            elif param == "current_ar":
                args[param] = context.get("current_ar", 0)
            elif param == "context":
                args[param] = context

        return args
