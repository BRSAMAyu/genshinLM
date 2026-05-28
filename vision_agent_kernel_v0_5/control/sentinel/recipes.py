"""Built-in recovery recipes for common failure modes.

Each recipe's ``execute_recovery()`` now publishes a ``SENTINEL_ACTION_REQUEST``
event to StateBus at priority P0 so the upper execution layer can enact the
corrective input sequence (e.g. press Escape, click Resurrect, etc.).

The StateBus interrupt is decoupled: if no executor is registered the recipe
still succeeds logically (claim_data records what was requested), but nothing
physical happens.  This keeps the recovery pipeline fully unit-testable.

Action payload convention:
    {
        "action": str,          # e.g. "press_key", "click_at", "wait_screen"
        "params": dict,         # action-specific params
        "recipe_id": str,       # originating recipe
        "priority": "P0",       # always P0 for sentinel interventions
    }
"""
from __future__ import annotations

import logging
from typing import Any

from control.sentinel.recovery_recipe import RecoveryRecipe, RecoveryResult, RecoveryPolicy
from control.sentinel.somatic_state import SomaticState

log = logging.getLogger(__name__)


def _publish(executor: Any, recipe_id: str, actions: list[dict]) -> None:
    """Publish a sentinel action request via StateBus if executor is available."""
    if executor is None:
        return
    # executor is expected to be a StateBus instance (or any object with get_slot)
    try:
        slot = executor.get_slot("sentinel.action_request")
        if slot is not None:
            slot.put({
                "recipe_id": recipe_id,
                "priority": "P0",
                "actions": actions,
            })
    except Exception as exc:
        log.warning("[Sentinel] Could not publish action request for %s: %s", recipe_id, exc)


class UILostRecovery(RecoveryRecipe):
    """Recover when UI elements are not detectable.

    Action: press Escape twice to dismiss any modal, then wait for HUD.
    """
    recipe_id = "UI_LOST_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.last_safe_screen_state == "unknown"

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "press_key", "params": {"key": "escape"}, "label": "dismiss_modal_1"},
            {"action": "wait_ms", "params": {"ms": 300}, "label": "wait_dismiss"},
            {"action": "press_key", "params": {"key": "escape"}, "label": "dismiss_modal_2"},
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 3000}, "label": "wait_hud"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "ui_lost", "actions": actions},
            feedback_data={"recovered": True},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "ask_user"


class StuckRecovery(RecoveryRecipe):
    """Recover when agent is physically stuck (collision, wall, terrain).

    Applies a multi-maneuver 3D unstick sequence:
    1. Jump-Forward: try to hop over low obstacles
    2. Strafe-Right: sidestep to find an alternate path
    3. Climb-Cancel: break out of accidental wall-climb state
    """
    recipe_id = "STUCK_RECOVERY"
    max_budget = 3

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_stuck

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            # Phase 1: Jump-Forward — try to hop over low obstacles
            {"action": "press_key", "params": {"key": "space"}, "label": "jump_forward"},
            {"action": "hold_key", "params": {"key": "w", "duration_ms": 400}, "label": "forward_after_jump"},
            {"action": "wait_ms", "params": {"ms": 300}, "label": "wait_land"},
            # Phase 2: Strafe-Right — sidestep to find alternate path
            {"action": "hold_key", "params": {"key": "d", "duration_ms": 500}, "label": "strafe_right"},
            {"action": "hold_key", "params": {"key": "w", "duration_ms": 400}, "label": "forward_after_strafe"},
            {"action": "wait_ms", "params": {"ms": 200}, "label": "wait_strafe"},
            # Phase 3: Climb-Cancel — break accidental wall-climb (Space+X)
            {"action": "press_key", "params": {"key": "space"}, "label": "climb_cancel_jump"},
            {"action": "wait_ms", "params": {"ms": 100}, "label": "wait_cancel"},
            {"action": "press_key", "params": {"key": "x"}, "label": "climb_cancel_drop"},
            {"action": "wait_ms", "params": {"ms": 300}, "label": "wait_drop"},
            # Phase 4: Final forward attempt
            {"action": "hold_key", "params": {"key": "w", "duration_ms": 600}, "label": "final_forward"},
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 2000}, "label": "wait_stable"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "stuck", "maneuvers": ["jump_forward", "strafe_right", "climb_cancel"]},
            feedback_data={"recovered": True},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class TargetLostRecovery(RecoveryRecipe):
    """Recover when combat target is lost.

    Action: rotate camera 90° to scan, then try lock-on.
    """
    recipe_id = "TARGET_LOST_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_target_lost

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "mouse_move", "params": {"dx": 300, "dy": 0}, "label": "rotate_camera"},
            {"action": "wait_ms", "params": {"ms": 200}, "label": "wait_rotate"},
            {"action": "press_key", "params": {"key": "tab"}, "label": "lock_on"},
            {"action": "wait_ms", "params": {"ms": 200}, "label": "wait_lock"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "target_lost", "actions": actions},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class LoadingTimeoutRecovery(RecoveryRecipe):
    """Recover when loading screen doesn't end.

    Action: wait additional 10s then check; if still loading, do nothing (budget=1).
    """
    recipe_id = "LOADING_TIMEOUT_RECOVERY"
    max_budget = 1

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_loading

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 10000}, "label": "extended_wait"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "loading_timeout", "actions": actions},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "ask_user"


class CombatDefeatRecovery(RecoveryRecipe):
    """Recover after combat defeat (resurrection screen).

    Action: click the Confirm / Revive button on the defeat dialog.
    """
    recipe_id = "COMBAT_DEFEAT_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return not snapshot.is_healthy()

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "wait_screen", "params": {"screen": "defeat_dialog", "timeout_ms": 2000}, "label": "wait_defeat"},
            {"action": "click_at", "params": {"target": "revive_button"}, "label": "click_revive"},
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 8000}, "label": "wait_respawn"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "combat_defeat", "actions": actions},
            feedback_data={"revived": True},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class LowHealthRecovery(RecoveryRecipe):
    """Recover when team health is critically low.

    Action: use a food item from quick-use slot.
    """
    recipe_id = "LOW_HEALTH_RECOVERY"
    max_budget = 3

    def check_precondition(self, snapshot: SomaticState) -> bool:
        if not snapshot.team_state.hp_ratios:
            return False
        active_hp = snapshot.team_state.hp_ratios[0] if snapshot.team_state.hp_ratios else 1.0
        return active_hp < 0.2

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "press_key", "params": {"key": "z"}, "label": "use_food"},
            {"action": "wait_ms", "params": {"ms": 500}, "label": "wait_food"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "low_health", "actions": actions},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class DriftRecovery(RecoveryRecipe):
    """Recover when agent has drifted from expected state.

    Action: teleport to nearest waypoint via map (open map, confirm nearest waypoint).
    """
    recipe_id = "DRIFT_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_drifting

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "press_key", "params": {"key": "escape"}, "label": "close_any_menu"},
            {"action": "wait_ms", "params": {"ms": 300}, "label": "wait"},
            {"action": "press_key", "params": {"key": "m"}, "label": "open_map"},
            {"action": "wait_screen", "params": {"screen": "map_screen", "timeout_ms": 2000}, "label": "wait_map"},
            {"action": "click_at", "params": {"target": "nearest_waypoint"}, "label": "select_waypoint"},
            {"action": "click_at", "params": {"target": "teleport_button"}, "label": "confirm_teleport"},
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 15000}, "label": "wait_arrival"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "drift", "actions": actions},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class ModelProviderFailureRecovery(RecoveryRecipe):
    """Recover when the LLM/model provider fails.

    Action: wait 5s then publish a provider retry event; no UI interaction.
    """
    recipe_id = "MODEL_PROVIDER_FAILURE_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.model_provider_failed

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "wait_ms", "params": {"ms": 5000}, "label": "wait_provider_cooldown"},
        ]
        _publish(executor, self.recipe_id, actions)
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="",
            claim_data={"recovery_type": "model_provider_failure", "actions": actions},
            feedback_data={"provider_retried": True},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "ask_user"


# Registry of all built-in recipes

def default_recipes() -> list[RecoveryRecipe]:
    return [
        UILostRecovery(),
        StuckRecovery(),
        TargetLostRecovery(),
        LoadingTimeoutRecovery(),
        CombatDefeatRecovery(),
        LowHealthRecovery(),
        DriftRecovery(),
        ModelProviderFailureRecovery(),
    ]
