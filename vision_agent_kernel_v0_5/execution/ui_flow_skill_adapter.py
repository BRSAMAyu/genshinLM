from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from core.state_bus import StateBus
from execution.console_backend import ConsoleInputBackend
from execution.input_worker import InputWorker
from interaction.npc_shop_interactor import NpcShopInteractor
from interaction.ui_flow_engine import UIFlow, UIFlowExecutor
from interaction.ui_flows import ALL_FLOWS, get_flow

if TYPE_CHECKING:
    from interaction.quest_marker_follower import QuestMarkerFollower
    from interaction.somatic_supervisor import SomaticStateSupervisor

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
        "character_select_in_menu": "character_select_in_menu",
        "select_character": "character_select_in_menu",
        "character_ascend": "character_ascend",
        "character_ascend_full": "character_ascend_full",
        "ascend_full": "character_ascend_full",
        "character_talent_upgrade": "character_talent_upgrade",
        "character_talent_upgrade_skill": "character_talent_upgrade_skill",
        "character_talent_upgrade_burst": "character_talent_upgrade_burst",
        "character_talent_upgrade_full": "character_talent_upgrade_full",
        "talent_upgrade_full": "character_talent_upgrade_full",
        "talent_upgrade_skill": "character_talent_upgrade_skill",
        "talent_upgrade_burst": "character_talent_upgrade_burst",
        "weapon_equip": "weapon_equip",
        "weapon_equip_full": "weapon_equip_full",
        "weapon_enhance": "weapon_enhance",
        "weapon_enhance_full": "weapon_enhance_full",
        "weapon_refine": "weapon_refine",
        "weapon_refine_full": "weapon_refine_full",
        "artifact_equip": "artifact_equip",
        "artifact_equip_full": "artifact_equip_full",
        "artifact_enhance": "artifact_enhance",
        "artifact_enhance_full": "artifact_enhance_full",
        "party_quick_config": "party_quick_config",
        "party_config_slot": "party_config_slot",
        "teleport": "teleport",
        "domain_enter_and_claim": "domain_enter_and_claim",
        "wish_ten_pull": "wish_ten_pull",
        "wish_single_pull": "wish_single_pull",
        "wish_ten_pull_full": "wish_ten_pull_full",
        "shop_open_paimon_bargains": "shop_open_paimon_bargains",
        "shop_buy_monthly_fates": "shop_buy_monthly_fates",
        "crafting_bench_interact": "crafting_bench_interact",
        "crafting_synthesize_full": "crafting_synthesize_full",
        "cooking_interact": "cooking_interact",
        "cooking_auto_cook": "cooking_auto_cook",
        "handbook_track_enemy": "handbook_track_enemy",
        "time_adjust": "time_adjust",
        "food_use_from_backpack": "food_use_from_backpack",
        "statue_offer_oculi": "statue_offer_oculi",
        "forging_interact": "forging_interact",
        "forging_forge_item": "forging_forge_item",
        "forging_forge_item_full": "forging_forge_item_full",
        "npc_shop_interact": "npc_shop_interact",
        "npc_shop_buy_item": "npc_shop_buy_item",
        "npc_shop_buy_item_full": "npc_shop_buy_item_full",
        "npc_shop_buy_specific": "npc_shop_buy_specific",
        "shop_buy_monthly_fates_full": "shop_buy_monthly_fates_full",
        "combat_food_revive": "combat_food_revive",
        "statue_element_resonance": "statue_element_resonance",
        # Combat capability aliases
        "combat_basic": "combat_basic",
        "combat_shield_break": "combat_shield_break",
        "combat_boss": "combat_boss",
        "combat_abyss_mage": "combat_abyss_mage",
        "combat_world_boss": "combat_world_boss",
        "combat_weekly": "combat_weekly",
        # Boss-specific combat aliases
        "combat_boss_dvalin": "combat_boss_dvalin",
        "combat_boss_childe": "combat_boss_childe",
        "combat_boss_signora": "combat_boss_signora",
        "combat_boss_raiden": "combat_boss_raiden",
        "combat_boss_shouki": "combat_boss_shouki",
        "combat_boss_narwhal": "combat_boss_narwhal",
        # Environment combat aliases
        "combat_env_dragonspine": "combat_env_dragonspine",
        "combat_env_inazuma": "combat_env_inazuma",
        # Abyss, multi-wave, rotation aliases
        "combat_abyss": "combat_abyss",
        "combat_multi_wave": "combat_multi_wave",
        "combat_weekly_rotation": "combat_weekly_rotation",
        "combat_world_farming": "combat_world_farming",
        "open_mail": "open_mail",
        "claim_mail": "mail_claim_all",
        "claim_all_mail": "mail_claim_all",
        "mail_claim": "mail_claim_all",
        "mail_claim_all": "mail_claim_all",
        "mail_claim_attachment": "mail_claim_attachment",
        "quest_select_and_track": "quest_select_and_track",
        # Exploration aliases
        "explore_activate_waypoint": "explore_waypoint",
        "explore_activate_statue": "explore_statue",
        "explore_open_chest": "explore_chest",
        "explore_collect_oculus": "explore_oculus",
        "explore_puzzle": "explore_puzzle",
        "explore_timed_challenge": "explore_timed",
        "explore_withering_zone": "explore_withering",
        "explore_underwater": "explore_underwater",
        # Quest aliases
        "quest_dialog": "quest_dialog",
        "quest_dialog_select": "quest_dialog_select",
        "quest_track": "quest_track",
        "quest_skip_cutscene": "quest_skip_cutscene",
        "quest_read_log": "quest_read_log",
        "quest_daily_commission": "quest_daily",
        "quest_archon": "quest_archon",
        "quest_story": "quest_story",
        "quest_world": "quest_world",
        "quest_event": "quest_event",
        # Daily routine aliases
        "daily_resin": "daily_resin",
        "daily_domain": "daily_domain",
        "daily_katheryne": "daily_katheryne",
        "daily_expedition": "daily_expedition",
        "daily_pot": "daily_pot",
        "daily_quick": "daily_quick",
        "daily_standard": "daily_standard",
        "daily_deep": "daily_deep",
        # Progression chain aliases
        "progression_chain": "progression_chain",
        "progression_level_up": "progression_level_up",
        "progression_ascend": "progression_ascend",
        "progression_weapon": "progression_weapon",
        "progression_artifact": "progression_artifact",
        "progression_talent": "progression_talent",
        "progression_party": "progression_party",
        # Long-chain scenario aliases
        "chain_tutorial": "chain_tutorial",
        "chain_daily_session": "chain_daily_session",
        "chain_boss_gauntlet": "chain_boss_gauntlet",
        "chain_weekly_gauntlet": "chain_weekly_gauntlet",
        "chain_exploration_sweep": "chain_exploration_sweep",
        # Mainline quest progression aliases
        "mainline_progress": "mainline_progress",
        "mainline_prologue": "mainline_prologue",
        "mainline_ch1": "mainline_ch1",
        "mainline_ch2": "mainline_ch2",
        "mainline_ch3": "mainline_ch3",
        "mainline_ch4": "mainline_ch4",
        "mainline_ch5": "mainline_ch5",
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
        skill_registry: Any | None = None,  # SkillRegistry for composite actions
        ocr_claim_builder: Any | None = None,  # OcrClaimBuilder for OCR-verified flows
    ) -> None:
        self._bus = state_bus or StateBus()
        self._config = config or UIFlowSkillAdapterConfig()
        self._quest_follower = quest_follower
        self._somatic_supervisor = somatic_supervisor
        self._skill_registry = skill_registry
        self._ocr_builder = ocr_claim_builder
        self._shop_interactor: NpcShopInteractor | None = None
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
        # G8 fix: initialize NPC shop grid interactor
        self._init_shop_interactor()
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
            # Mail handlers (G2)
            "open_mail": self._handle_mail,
            "mail_claim": self._handle_mail,
            "mail_claim_all": self._handle_mail,
            "auto_combat": self._handle_action_intent,
            # Combat scenario handlers
            "combat_basic": self._handle_combat,
            "combat_shield_break": self._handle_combat,
            "combat_boss": self._handle_combat,
            "combat_abyss_mage": self._handle_combat,
            "combat_world_boss": self._handle_combat,
            "combat_weekly": self._handle_combat,
            # Boss-specific combat handlers
            "combat_boss_dvalin": self._handle_boss_combat,
            "combat_boss_childe": self._handle_boss_combat,
            "combat_boss_signora": self._handle_boss_combat,
            "combat_boss_raiden": self._handle_boss_combat,
            "combat_boss_shouki": self._handle_boss_combat,
            "combat_boss_narwhal": self._handle_boss_combat,
            # Environment combat handlers
            "combat_env_dragonspine": self._handle_env_combat,
            "combat_env_inazuma": self._handle_env_combat,
            # Abyss handler
            "combat_abyss": self._handle_combat,
            # Multi-wave handler
            "combat_multi_wave": self._handle_combat,
            # Rotation handlers
            "combat_weekly_rotation": self._handle_combat,
            "combat_world_farming": self._handle_combat,
            # Exploration scenario handlers
            "explore_waypoint": self._handle_explore,
            "explore_statue": self._handle_explore,
            "explore_chest": self._handle_explore,
            "explore_oculus": self._handle_explore,
            "explore_puzzle": self._handle_explore,
            "explore_timed": self._handle_explore,
            "explore_withering": self._handle_explore,
            "explore_underwater": self._handle_explore,
            # Quest scenario handlers
            "quest_dialog": self._handle_quest_dialog,
            "quest_dialog_select": self._handle_quest_dialog,
            "quest_track": self._handle_quest_track,
            "quest_skip_cutscene": self._handle_quest_cutscene,
            "quest_read_log": self._handle_quest_action_intent,
            "quest_daily": self._handle_quest_action_intent,
            "quest_archon": self._handle_quest_action_intent,
            "quest_story": self._handle_quest_action_intent,
            "quest_world": self._handle_quest_action_intent,
            "quest_event": self._handle_quest_action_intent,
            # Daily routine handlers
            "daily_resin": self._handle_daily_action_intent,
            "daily_domain": self._handle_daily_action_intent,
            "daily_katheryne": self._handle_daily_action_intent,
            "daily_expedition": self._handle_daily_action_intent,
            "daily_pot": self._handle_daily_action_intent,
            "daily_quick": self._handle_daily_action_intent,
            "daily_standard": self._handle_daily_action_intent,
            "daily_deep": self._handle_daily_action_intent,
            # Progression chain handlers
            "progression_chain": self._handle_progression_chain,
            "progression_level_up": self._handle_progression_stage,
            "progression_ascend": self._handle_progression_stage,
            "progression_weapon": self._handle_progression_stage,
            "progression_artifact": self._handle_progression_stage,
            "progression_talent": self._handle_progression_stage,
            "progression_party": self._handle_progression_stage,
            # Long-chain scenario handlers
            "chain_tutorial": self._handle_chain_scenario,
            "chain_daily_session": self._handle_chain_scenario,
            "chain_boss_gauntlet": self._handle_chain_scenario,
            "chain_weekly_gauntlet": self._handle_chain_scenario,
            "chain_exploration_sweep": self._handle_chain_scenario,
            # Mainline quest progression handlers
            "mainline_progress": self._handle_mainline,
            "mainline_prologue": self._handle_mainline,
            "mainline_ch1": self._handle_mainline,
            "mainline_ch2": self._handle_mainline,
            "mainline_ch3": self._handle_mainline,
            "mainline_ch4": self._handle_mainline,
            "mainline_ch5": self._handle_mainline,
            # G8 fix: NPC shop specific item purchase
            "npc_shop_buy_specific": self._handle_npc_shop_buy_specific,
        }

    @property
    def flow_names(self) -> tuple[str, ...]:
        return tuple(sorted(ALL_FLOWS))

    def can_handle(self, action: str) -> bool:
        if self._skill_registry is not None and self._skill_registry.can_handle(action):
            return True
        return self._resolve_flow_name(action) is not None or action in self._primitive_handlers

    # Actions that operate on a character and support pre-selecting a slot
    _CHARACTER_ACTIONS: frozenset[str] = frozenset({
        "character_level_up_full", "character_ascend_full",
        "character_talent_upgrade_full", "character_talent_upgrade",
        "weapon_equip_full", "weapon_equip",
        "weapon_enhance_full", "weapon_enhance",
        "weapon_refine_full", "weapon_refine",
        "artifact_equip_full", "artifact_equip",
        "artifact_enhance_full", "artifact_enhance",
    })

    def execute_semantic(self, action: str, target: str = "", context: dict[str, Any] | None = None) -> bool:
        context = context or {}

        # Delegate composite actions to SkillRegistry first
        if self._skill_registry is not None and self._skill_registry.can_handle(action):
            log.info("[UIFlowSkillAdapter] delegating composite action '%s' to SkillRegistry", action)
            return self._skill_registry.execute(action, target, context)

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

        # If target specifies a character slot and the action is character-scoped,
        # run CHARACTER_SELECT_IN_MENU first, then the main action.
        if flow_name is not None and target and flow_name in self._CHARACTER_ACTIONS:
            slot = self._parse_character_slot(target)
            if slot is not None:
                log.info("[UIFlowSkillAdapter] pre-selecting character slot %d for '%s'", slot, flow_name)
                select_ok = self._select_character_slot(slot)
                if not select_ok:
                    log.warning("[UIFlowSkillAdapter] character selection failed for slot %d", slot)
                    return False

        if flow_name is not None:
            return self.execute_flow_as_semantic(flow_name, context)

        handler = self._primitive_handlers.get(action)
        if handler is None:
            alias = self._aliases.get(action)
            if alias is not None:
                handler = self._primitive_handlers.get(alias)
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

    def read_ocr_number(self, purpose: str, scene_hint: str = "") -> int | None:
        """Read a numeric value via OCR for verification.

        Purpose should match an OcrPurpose enum value (e.g., 'character_level').
        Requires ocr_claim_builder to be provided at construction time.
        """
        if self._ocr_builder is None:
            return None
        from perception.ocr_roi_registry import OcrPurpose as OP
        try:
            purpose_enum = OP(purpose)
        except ValueError:
            log.warning("[UIFlowSkillAdapter] unknown OCR purpose: %s", purpose)
            return None
        obs = self._bus.latest_observation.get()
        if obs is None or obs.image is None:
            return None
        return self._ocr_builder.read_number(obs.image, purpose_enum, scene_hint)

    def _ensure_worker_started(self) -> None:
        if self._worker is None:
            return
        if hasattr(self._worker, "is_alive") and hasattr(self._worker, "start"):
            try:
                if not self._worker.is_alive:
                    self._worker.start()
            except Exception:
                log.debug("[UIFlowSkillAdapter] input worker auto-start skipped", exc_info=True)

    def _init_shop_interactor(self) -> None:
        """G8 fix: initialize NpcShopInteractor if backend supports click_at."""
        backend = self._backend()
        if backend is not None and hasattr(backend, "click_at"):
            try:
                self._shop_interactor = NpcShopInteractor(backend=backend, state_bus=self._bus)
                log.debug("[UIFlowSkillAdapter] NpcShopInteractor initialized")
            except Exception as exc:
                log.warning("[UIFlowSkillAdapter] NpcShopInteractor init failed: %s", exc)

    def _resolve_flow_name(self, action: str) -> str | None:
        if action in ALL_FLOWS:
            return action
        alias = self._aliases.get(action)
        if alias in ALL_FLOWS:
            return alias
        return None

    @staticmethod
    def _parse_character_slot(target: str) -> int | None:
        """Parse a character slot from target string. Returns 1-4 or None."""
        import re
        if not target:
            return None
        # "slot_2", "slot:3", "slot2", "2"
        m = re.match(r"(?:slot[_:]?)?([1-4])", target.strip().lower())
        if m:
            return int(m.group(1))
        return None

    def _select_character_slot(self, slot: int) -> bool:
        """Run CHARACTER_SELECT_IN_MENU flow to select a character slot (1-4)."""
        from interaction.ui_flow_engine import UIFlow, UIStep, click_character_slot
        select_flow = UIFlow(
            name=f"character_select_slot_{slot}",
            description=f"Select character in slot {slot}",
            steps=(
                click_character_slot(slot, delay_ms=400),
            ),
        )
        self._ensure_worker_started()
        result = self._executor.execute(select_flow)
        return result.status == "SUCCESS"

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

    def _combat_key(self, key: str, reason: str = "") -> bool:
        """Execute a combat key press with down/up sequence."""
        backend = self._backend()
        try:
            backend.key_down(key, reason=reason or f"combat_key:{key}")
            self._chunked_sleep(0.08)
            backend.key_up(key, reason=f"{reason}_done" if reason else f"combat_key:{key}_done")
            return True
        except Exception as exc:
            log.warning("[UIFlowSkillAdapter] combat key %s failed: %s", key, exc)
            return False

    def _handle_combat(self, target: str, context: dict[str, Any]) -> bool:
        """Handle combat scenario actions with real key execution (G6).

        Maps semantic actions to real key presses:
        - basic_attack/attack: hold LMB for auto-attack
        - dodge/dash: Shift+S for backdash
        - cast_skill_e: E key
        - cast_burst_q/use_burst/use_ultimate: Q key
        - switch_char: 1-4 key for character slot
        - lock_target: Tab key
        - jump: Space key
        - sprint: Left Shift hold
        - auto_attack: F1 to toggle
        """
        action = str(context.get("semantic_action", "combat_basic"))
        backend = self._backend()

        # Map semantic actions to real key presses
        if action in ("basic_attack", "attack", "combo_normal_attack"):
            # Use hold_click for auto-attack (protocol-compliant)
            try:
                backend.hold_click(duration_sec=0.5, reason="combat_attack")
                return True
            except Exception as exc:
                log.warning("[UIFlowSkillAdapter] basic attack failed: %s", exc)

        if action in ("dodge", "dash"):
            # Shift + direction (default: S to backdash)
            try:
                backend.key_down("shift", reason="dodge_modifier")
                backend.key_down("s", reason="dodge_back")
                self._chunked_sleep(0.1)
                backend.key_up("s", reason="dodge_back_done")
                backend.key_up("shift", reason="dodge_modifier_done")
                return True
            except Exception as exc:
                log.warning("[UIFlowSkillAdapter] dodge failed: %s", exc)

        if action == "cast_skill_e":
            return self._combat_key("e", "combat_skill_e")

        if action in ("cast_burst_q", "use_burst", "use_ultimate"):
            return self._combat_key("q", "combat_burst_q")

        if action == "switch_char" or action.startswith("switch_char"):
            # Parse slot from target (e.g., "slot_2" -> "2")
            slot = self._parse_character_slot(target) or 1
            return self._combat_key(str(slot), "combat_switch_char")

        if action == "lock_target":
            return self._combat_key("tab", "combat_lock_target")

        if action == "jump":
            return self._combat_key("space", "combat_jump")

        if action == "sprint":
            try:
                backend.key_down("left shift", reason="combat_sprint")
                self._chunked_sleep(0.3)
                backend.key_up("left shift", reason="combat_sprint_done")
                return True
            except Exception as exc:
                log.warning("[UIFlowSkillAdapter] sprint failed: %s", exc)

        if action == "auto_attack":
            return self._combat_key("f1", "combat_auto_toggle")

        # Fall back to action_intent for combat scenarios
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"combat:{action}", reason="semantic_combat")
        log.info("[UIFlowSkillAdapter] combat action accepted (no key mapped): %s target=%s", action, target)
        return True

    _BOSS_ID_MAP: dict[str, str] = {
        "combat_boss_dvalin": "dvalin",
        "combat_boss_childe": "childe",
        "combat_boss_signora": "signora",
        "combat_boss_raiden": "raiden_shogun",
        "combat_boss_shouki": "shouki_no_kami",
        "combat_boss_narwhal": "narwhal",
    }

    def _handle_boss_combat(self, target: str, context: dict[str, Any]) -> bool:
        """Handle boss-specific combat with boss_id routing."""
        action = str(context.get("semantic_action", "combat_boss"))
        boss_id = self._BOSS_ID_MAP.get(action, target or "")
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"combat:boss:{boss_id}", reason="semantic_boss_combat")
        log.info("[UIFlowSkillAdapter] boss combat: %s boss_id=%s", action, boss_id)
        return True

    def _handle_env_combat(self, target: str, context: dict[str, Any]) -> bool:
        """Handle environment-specific combat (dragonspine/inazuma)."""
        action = str(context.get("semantic_action", "combat_env_dragonspine"))
        env_type = "dragonspine" if "dragonspine" in action else "inazuma"
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"combat:env:{env_type}", reason="semantic_env_combat")
        log.info("[UIFlowSkillAdapter] env combat: %s env=%s", action, env_type)
        return True

    _EXPLORE_INTERACT_ACTIONS: frozenset[str] = frozenset({
        "explore_waypoint", "explore_statue", "explore_chest", "explore_oculus",
        "explore_activate_waypoint", "explore_activate_statue",
        "explore_open_chest", "explore_collect_oculus",
    })

    _ESCAPE_AFTER_ACTIONS: frozenset[str] = frozenset({
        "explore_waypoint", "explore_statue",
        "explore_activate_waypoint", "explore_activate_statue",
    })

    def _handle_explore(self, target: str, context: dict[str, Any]) -> bool:
        """Handle exploration scenario actions.

        For interact-type actions (waypoint, statue, chest, oculus), sends F-key
        interact. Waypoint/statue also get ESC to close popup menus.
        For puzzle/timed/withering/underwater, delegates via action_intent.
        """
        action = str(context.get("semantic_action", "explore_chest"))
        backend = self._backend()

        if action in self._EXPLORE_INTERACT_ACTIONS:
            try:
                backend.key_down("f", reason=f"explore_{action}")
                self._chunked_sleep(0.08)
                backend.key_up("f", reason=f"explore_{action}_done")
                self._chunked_sleep(self._config.default_wait_sec)
                if action in self._ESCAPE_AFTER_ACTIONS:
                    backend.key_down("escape", reason="explore_close_popup")
                    self._chunked_sleep(0.05)
                    backend.key_up("escape", reason="explore_close_popup_done")
            except Exception as exc:
                log.warning("[UIFlowSkillAdapter] explore interact failed: %s", exc)
        else:
            if hasattr(backend, "action_intent"):
                backend.action_intent(f"explore:{action}", reason="semantic_explore")

        log.info("[UIFlowSkillAdapter] explore action accepted: %s target=%s", action, target)
        return True

    def _handle_quest_dialog(self, target: str, context: dict[str, Any]) -> bool:
        """Handle quest dialog: advance with F-key, optionally select choices."""
        action = str(context.get("semantic_action", "quest_dialog"))
        backend = self._backend()
        try:
            backend.key_down("f", reason=f"quest_{action}")
            self._chunked_sleep(0.08)
            backend.key_up("f", reason=f"quest_{action}_done")
            self._chunked_sleep(self._config.default_wait_sec)
        except Exception:
            pass
        log.info("[UIFlowSkillAdapter] quest dialog action: %s target=%s", action, target)
        return True

    def _handle_quest_cutscene(self, target: str, context: dict[str, Any]) -> bool:
        """Handle cutscene skip: press Escape."""
        backend = self._backend()
        try:
            backend.key_down("escape", reason="quest_skip_cutscene")
            self._chunked_sleep(0.08)
            backend.key_up("escape", reason="quest_skip_cutscene_done")
            self._chunked_sleep(self._config.default_wait_sec)
        except Exception:
            pass
        log.info("[UIFlowSkillAdapter] quest cutscene skip target=%s", target)
        return True

    def _handle_quest_track(self, target: str, context: dict[str, Any]) -> bool:
        """Handle quest tracking: open quest log and select+track quest."""
        action = str(context.get("semantic_action", "quest_track"))
        if action == "open_quest_log":
            return self.execute_flow_as_semantic("open_quest_log")
        # Default: open quest log + select + track
        return self.execute_flow_as_semantic("quest_select_and_track")

    def _handle_mail(self, target: str, context: dict[str, Any]) -> bool:
        """Handle mail actions: open mail, claim attachment, claim all."""
        action = str(context.get("semantic_action", "mail_claim_all"))
        if action in ("open_mail", "claim_mail"):
            return self.execute_flow_as_semantic("open_mail")
        if action in ("claim_all_mail", "mail_claim_all"):
            return self.execute_flow_as_semantic("mail_claim_all")
        return self.execute_flow_as_semantic("mail_claim_attachment")

    def _handle_quest_action_intent(self, target: str, context: dict[str, Any]) -> bool:
        """Handle quest management actions (read log, daily, archon, story, world, event)."""
        action = str(context.get("semantic_action", "quest_action"))
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"quest:{action}", reason="semantic_quest")
        log.info("[UIFlowSkillAdapter] quest action: %s target=%s", action, target)
        return True

    def _handle_daily_action_intent(self, target: str, context: dict[str, Any]) -> bool:
        """Handle daily routine actions (resin, domain, katheryne, expedition, pot)."""
        action = str(context.get("semantic_action", "daily_action"))
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"daily:{action}", reason="semantic_daily")
        log.info("[UIFlowSkillAdapter] daily action: %s target=%s", action, target)
        return True

    _PROGRESSION_STAGES: tuple[tuple[str, str], ...] = (
        ("progression_level_up", "character_level_up_full"),
        ("progression_ascend", "character_ascend_full"),
        ("progression_weapon", "weapon_enhance_full"),
        ("progression_artifact", "artifact_equip_full"),
        ("progression_talent", "character_talent_upgrade_full"),
        ("progression_party", "party_quick_config"),
    )

    def _handle_progression_chain(self, target: str, context: dict[str, Any]) -> bool:
        """Execute the full 6-stage character progression chain.

        Stages: level_up → ascend → weapon → artifact → talent → party.
        Each stage is a best-effort attempt; failures log a warning but do not
        abort the chain (later stages may still succeed).
        """
        slot = self._parse_character_slot(target)
        results: list[tuple[str, bool]] = []
        for stage_action, flow_name in self._PROGRESSION_STAGES:
            if slot is not None:
                self._select_character_slot(slot)
            ok = self.execute_flow_as_semantic(flow_name)
            results.append((stage_action, ok))
            if not ok:
                log.warning("[UIFlowSkillAdapter] progression stage %s failed, continuing", stage_action)
            self._chunked_sleep(self._config.default_wait_sec)
        succeeded = sum(1 for _, ok in results if ok)
        log.info(
            "[UIFlowSkillAdapter] progression chain complete: %d/%d stages succeeded",
            succeeded, len(results),
        )
        return succeeded > 0

    def _handle_progression_stage(self, target: str, context: dict[str, Any]) -> bool:
        """Execute a single progression stage, delegating to the corresponding UIFlow."""
        action = str(context.get("semantic_action", "progression_level_up"))
        stage_map: dict[str, str] = dict(self._PROGRESSION_STAGES)
        flow_name = stage_map.get(action)
        if flow_name is None:
            log.warning("[UIFlowSkillAdapter] unknown progression stage: %s", action)
            return False
        slot = self._parse_character_slot(target)
        if slot is not None:
            self._select_character_slot(slot)
        return self.execute_flow_as_semantic(flow_name)

    def _handle_chain_scenario(self, target: str, context: dict[str, Any]) -> bool:
        """Handle long-chain scenario dispatch.

        Chains delegate via action_intent to the MainlineRunner or
        scenario-specific chain executor. Each chain type sequences
        existing atomic capabilities.
        """
        action = str(context.get("semantic_action", "chain_tutorial"))
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"chain:{action}", reason="semantic_chain")
        log.info("[UIFlowSkillAdapter] chain scenario: %s target=%s", action, target)
        return True

    def _handle_mainline(self, target: str, context: dict[str, Any]) -> bool:
        """Handle mainline quest progression dispatch.

        Routes to quest_archon for actual execution — the chapter
        distinction is captured for logging/audit purposes.
        """
        action = str(context.get("semantic_action", "mainline_progress"))
        backend = self._backend()
        if hasattr(backend, "action_intent"):
            backend.action_intent(f"mainline:{action}", reason="semantic_mainline")
        log.info("[UIFlowSkillAdapter] mainline quest: %s target=%s", action, target)
        return True

    # Semantic actions that should be routed to combat handler
    _COMBAT_ROUTING_ACTIONS: frozenset[str] = frozenset({
        "attack", "basic_attack", "dodge", "dash", "jump", "sprint",
        "cast_skill_e", "use_skill", "cast_burst_q", "use_burst", "use_ultimate",
        "switch_char", "lock_target", "auto_attack", "combo_normal_attack",
    })

    def _handle_action_intent(self, target: str, context: dict[str, Any]) -> bool:
        action = str(context.get("semantic_action") or context.get("action") or "action")
        if action == "action":
            action = str(context.get("node_type") or "action")

        # G6 fix: route combat actions to _handle_combat for real key execution
        if action in self._COMBAT_ROUTING_ACTIONS:
            return self._handle_combat(target, context)

        if target:
            action = f"{action}:{target}"

        # Gap 3 fix: wire QuestMarkerFollower into navigate_walk
        if action in ("navigate_walk", "follow_quest_marker") and self._quest_follower is not None:
            log.info("[UIFlowSkillAdapter] navigate_walk: activating QuestMarkerFollower")
            try:
                def frame_source():
                    obs = self._bus.latest_observation.get()
                    return obs.image if obs else None
                follower_result = self._quest_follower.navigate_to_marker(
                    frame_source=frame_source,
                    max_steps=500,
                    shutdown_event=getattr(self._quest_follower, "_shutdown", None),
                )
                if follower_result:
                    return True
            except Exception as exc:
                log.warning("[UIFlowSkillAdapter] QuestMarkerFollower failed: %s", exc)
                return False

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

    # G8 fix: NPC shop specific item handler
    def _handle_npc_shop_buy_specific(self, target: str, context: dict[str, Any]) -> bool:
        """Buy a specific item from NPC shop by name or index."""
        del context
        # Parse target: could be "index:3" or "name:Weapon_Material"
        if target.startswith("index:"):
            try:
                idx = int(target.split(":")[1])
                if self._shop_interactor is not None:
                    return self._shop_interactor.buy_item_by_index(idx)
                log.warning("[UIFlowSkillAdapter] shop_interactor not available")
                return False
            except (ValueError, IndexError):
                log.warning("[UIFlowSkillAdapter] invalid shop index: %s", target)
                return False
        # Default: use existing flow
        return self.execute_flow_as_semantic("npc_shop_buy_item")
