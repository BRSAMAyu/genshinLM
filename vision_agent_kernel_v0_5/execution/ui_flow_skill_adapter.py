from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.state_bus import StateBus
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from interaction.ui_flow_engine import UIFlow, UIFlowExecutor
from interaction.ui_flows import ALL_FLOWS, get_flow

log = logging.getLogger(__name__)


PrimitiveHandler = Callable[[str, dict[str, Any]], bool]


@dataclass(frozen=True, slots=True)
class UIFlowSkillAdapterConfig:
    """Configuration for the semantic-to-UIFlow adapter.

    The default backend is ConsoleInputBackend, so this adapter is safe to use
    as the AutonomousTaskBrain executor in tests and QA sandboxes.
    """

    wait_chunk_ms: int = 50
    semantic_aliases: dict[str, str] = field(default_factory=dict)
    default_wait_sec: float = 0.5


class UIFlowSkillAdapter:
    """Bridge high-level semantic actions to declarative UIFlow execution.

    This closes the TaskBrain ``execute_semantic`` gap without requiring a live
    client. Callers can inject any InputWorker-compatible backend; absent that,
    a dry-run ConsoleInputBackend is used.
    """

    _DEFAULT_ALIASES: dict[str, str] = {
        "open_menu": "open_character_menu",
        "open_character": "open_character_menu",
        "open_character_menu": "open_character_menu",
        "open_backpack": "open_backpack",
        "open_inventory": "open_backpack",
        "open_map": "open_map",
        "navigate_map": "open_map",
        "open_quest_menu": "open_quest_menu",
        "open_quests": "open_quest_menu",
        "open_party_setup": "open_party_setup",
        "open_wish": "open_wish",
        "close_menu": "close_menu",
        "go_back": "close_menu",
        "character_level_up": "character_level_up",
        "level_up_character": "character_level_up",
        "level_up_full": "character_level_up_full",
        "character_ascend": "character_ascend",
        "character_talent_upgrade": "character_talent_upgrade",
        "weapon_equip": "weapon_equip",
        "weapon_enhance": "weapon_enhance",
        "artifact_equip": "artifact_equip",
        "artifact_enhance": "artifact_enhance",
        "party_quick_config": "party_quick_config",
        "teleport": "teleport",
        "domain_enter_and_claim": "domain_enter_and_claim",
        "wish_ten_pull": "wish_ten_pull",
        "shop_open_paimon_bargains": "shop_open_paimon_bargains",
        "shop_buy_monthly_fates": "shop_buy_monthly_fates",
        "crafting_bench_interact": "crafting_bench_interact",
        "cooking_interact": "cooking_interact",
        "cooking_auto_cook": "cooking_auto_cook",
        "handbook_track_enemy": "handbook_track_enemy",
        "time_adjust": "time_adjust",
        "food_use_from_backpack": "food_use_from_backpack",
        "statue_offer_oculi": "statue_offer_oculi",
        "forging_interact": "forging_interact",
        "forging_forge_item": "forging_forge_item",
        "npc_shop_interact": "npc_shop_interact",
        "npc_shop_buy_item": "npc_shop_buy_item",
        "combat_food_revive": "combat_food_revive",
        "statue_element_resonance": "statue_element_resonance",
    }

    def __init__(
        self,
        *,
        state_bus: StateBus | None = None,
        input_worker: InputWorker | None = None,
        executor: UIFlowExecutor | None = None,
        config: UIFlowSkillAdapterConfig | None = None,
        quest_follower: Any = None,  # QuestMarkerFollower for navigate_walk
        somatic_supervisor: Any = None,  # SomaticStateSupervisor for stamina/HP monitoring
    ) -> None:
        self._bus = state_bus or StateBus()
        self._config = config or UIFlowSkillAdapterConfig()
        self._quest_follower = quest_follower
        self._somatic_supervisor = somatic_supervisor
        if executor is not None:
            self._executor = executor
            self._worker = input_worker
        else:
            self._worker = input_worker or InputWorker(
                backend=ConsoleInputBackend(),
                state_bus=self._bus,
            )
            self._executor = UIFlowExecutor(
                state_bus=self._bus,
                input_worker=self._worker,
                wait_chunk_ms=self._config.wait_chunk_ms,
            )
        self._aliases = dict(self._DEFAULT_ALIASES)
        self._aliases.update(self._config.semantic_aliases)
        self._primitive_handlers: dict[str, PrimitiveHandler] = {
            "observe": self._handle_wait,
            "wait": self._handle_wait,
            "wait_for_loading": self._handle_wait,
            "confirm": self._handle_confirm,
            "advance_dialog": self._handle_confirm,
            "interact": self._handle_interact,
            "interact_npc": self._handle_interact,
            "open_chest": self._handle_interact,
            "use_statue": self._handle_interact,
            "click_button": self._handle_confirm,
            "heal": self._handle_confirm,
            "revive_char": self._handle_confirm,
            "skip": self._handle_confirm,
            "skip_cutscene": self._handle_confirm,
            "dismiss_notification": self._handle_confirm,
            "use_food": self._handle_confirm,
            "claim_reward": self._handle_confirm,
            "claim_all": self._handle_confirm,
            "buy_item": self._handle_confirm,
            "use_item": self._handle_confirm,
            "use_waypoint": self._handle_confirm,
            "select_option": self._handle_select_option,
            "select_dialog_option": self._handle_select_option,
            "select_quest": self._handle_select_option,
            "select_waypoint": self._handle_select_option,
            "select_item": self._handle_select_option,
            "select_tab": self._handle_select_option,
            "move": self._handle_action_intent,
            "look": self._handle_action_intent,
            "navigate_to": self._handle_action_intent,
            "navigate_walk": self._handle_action_intent,
            "move_forward": self._handle_action_intent,
            "sprint": self._handle_action_intent,
            "swim": self._handle_action_intent,
            "climb": self._handle_action_intent,
            "glide": self._handle_action_intent,
            "dash": self._handle_action_intent,
            "jump": self._handle_action_intent,
            "attack": self._handle_action_intent,
            "basic_attack": self._handle_action_intent,
            "use_skill": self._handle_action_intent,
            "use_burst": self._handle_action_intent,
            "use_ultimate": self._handle_action_intent,
            "dodge": self._handle_action_intent,
            "switch_char": self._handle_action_intent,
            "toggle_auto": self._handle_action_intent,
            "track_quest": self._handle_action_intent,
            "sort": self._handle_action_intent,
            "scroll_down": self._handle_action_intent,
            "scroll_up": self._handle_action_intent,
            "open_quest_log": self._handle_open_menu_alias,
            "open_character_screen": self._handle_open_menu_alias,
        }

    @property
    def flow_names(self) -> tuple[str, ...]:
        return tuple(sorted(ALL_FLOWS))

    def can_handle(self, action: str) -> bool:
        return self._resolve_flow_name(action) is not None or action in self._primitive_handlers

    def execute_semantic(self, action: str, target: str = "", context: dict[str, Any] | None = None) -> bool:
        context = context or {}

        # Gap 8 fix: check somatic state before movement actions
        if self._somatic_supervisor is not None and action in (
            "move", "move_forward", "sprint", "swim", "climb", "glide", "dash", "jump",
            "navigate_walk", "navigate_to",
        ):
            obs = self._bus.latest_observation.get()
            if obs and obs.image is not None:
                state, intercepted = self._somatic_supervisor.monitor_and_intercept(
                    backend=self._backend(),
                    frame=obs.image,
                    frame_id=obs.frame_id if hasattr(obs, "frame_id") else 0,
                )
                if intercepted and state.recovery_mode:
                    log.info("[UIFlowSkillAdapter] somatic interception active, blocking %s", action)
                    return False

        flow_name = self._resolve_flow_name(action)
        if flow_name is not None:
            return self.execute_flow_as_semantic(flow_name, context)

        handler = self._primitive_handlers.get(action)
        if handler is None:
            log.warning("[UIFlowSkillAdapter] unknown semantic action: %s target=%s", action, target)
            return False
        context.setdefault("semantic_action", action)
        return handler(target, context)

    def is_target_focused(self) -> bool:
        backend = self._backend()
        if hasattr(backend, "is_target_focused"):
            try:
                return bool(backend.is_target_focused())
            except Exception:
                return False
        return True

    def execute_flow_as_semantic(self, flow_or_name: str | UIFlow, context: dict[str, Any] | None = None) -> bool:
        del context
        self._ensure_worker_started()
        flow = get_flow(flow_or_name) if isinstance(flow_or_name, str) else flow_or_name
        log.info("[UIFlowSkillAdapter] route semantic action to UIFlow: %s", flow.name)
        result = self._executor.execute(flow)
        return result.status == "SUCCESS"

    def _ensure_worker_started(self) -> None:
        if self._worker is None:
            return
        if hasattr(self._worker, "is_alive") and hasattr(self._worker, "start"):
            try:
                if not self._worker.is_alive:
                    self._worker.start()
            except Exception:
                log.debug("[UIFlowSkillAdapter] input worker auto-start skipped", exc_info=True)

    def _resolve_flow_name(self, action: str) -> str | None:
        if action in ALL_FLOWS:
            return action
        alias = self._aliases.get(action)
        if alias in ALL_FLOWS:
            return alias
        return None

    def _backend(self) -> Any:
        if self._worker is not None:
            return self._worker.backend
        return getattr(self._executor, "_worker").backend

    def _handle_wait(self, target: str, context: dict[str, Any]) -> bool:
        wait_sec = context.get("wait_sec", context.get("duration_sec", target))
        try:
            seconds = float(wait_sec) if wait_sec not in ("", None) else self._config.default_wait_sec
        except (TypeError, ValueError):
            seconds = self._config.default_wait_sec
        self._chunked_sleep(max(0.0, min(seconds, 5.0)))
        return True

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))

    def _handle_confirm(self, target: str, context: dict[str, Any]) -> bool:
        del target, context
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent("confirm", reason="semantic_confirm")
            return True
        try:
            backend.key_down("enter", reason="semantic_confirm")
            backend.key_up("enter", reason="semantic_confirm_done")
            return True
        except Exception as exc:
            log.warning("[UIFlowSkillAdapter] confirm failed: %s", exc)
            return False

    def _handle_interact(self, target: str, context: dict[str, Any]) -> bool:
        del target, context
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent("interact", reason="semantic_interact")
            return True
        try:
            backend.key_down("f", reason="semantic_interact")
            backend.key_up("f", reason="semantic_interact_done")
            return True
        except Exception as exc:
            log.warning("[UIFlowSkillAdapter] interact failed: %s", exc)
            return False

    def _handle_select_option(self, target: str, context: dict[str, Any]) -> bool:
        del context
        backend = self._backend()
        option = target or "1"
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"select_option:{option}", reason="semantic_select_option")
            return True
        try:
            backend.key_down(option, reason="semantic_select_option")
            backend.key_up(option, reason="semantic_select_option_done")
            return True
        except Exception as exc:
            log.warning("[UIFlowSkillAdapter] select option failed: %s", exc)
            return False

    def _handle_action_intent(self, target: str, context: dict[str, Any]) -> bool:
        action = str(context.get("semantic_action") or context.get("action") or "action")
        if action == "action":
            action = str(context.get("node_type") or "action")
        if target:
            action = f"{action}:{target}"

        # Gap 3 fix: wire QuestMarkerFollower into navigate_walk
        if action in ("navigate_walk", "follow_quest_marker") and self._quest_follower is not None:
            log.info("[UIFlowSkillAdapter] navigate_walk: activating QuestMarkerFollower")
            try:
                def frame_source():
                    obs = self._bus.latest_observation.get()
                    return obs.image if obs else None
                return self._quest_follower.navigate_to_marker(
                    frame_source=frame_source,
                    max_steps=500,
                    shutdown_event=getattr(self._quest_follower, "_shutdown", None),
                )
            except Exception as exc:
                log.warning("[UIFlowSkillAdapter] QuestMarkerFollower failed: %s", exc)

        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent(action, reason="semantic_action_intent")
            return True
        log.info("[UIFlowSkillAdapter] primitive action intent accepted: %s", action)
        return True

    def _handle_open_menu_alias(self, target: str, context: dict[str, Any]) -> bool:
        action = str(context.get("semantic_action", ""))
        key_map: dict[str, str] = {
            "open_quest_log": "j",
            "open_character_screen": "c",
        }
        key = key_map.get(action, "escape")
        backend = self._backend()
        try:
            backend.key_press(key, reason=f"semantic_{action}")
            return True
        except Exception as exc:
            log.warning("[UIFlowSkillAdapter] open menu failed for %s: %s", action, exc)
            return False
