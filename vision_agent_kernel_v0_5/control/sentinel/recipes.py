"""Built-in recovery recipes for common failure modes.

Recipes are intentionally simple for MVP — real implementations will
integrate with the execution backend and perception pipeline.
"""
from __future__ import annotations

from typing import Any

from control.sentinel.recovery_recipe import RecoveryRecipe, RecoveryResult, RecoveryPolicy
from control.sentinel.somatic_state import SomaticState


class UILostRecovery(RecoveryRecipe):
    """Recover when UI elements are not detectable."""
    recipe_id = "UI_LOST_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.last_safe_screen_state == "unknown"

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "ui_lost"},
            feedback_data={"recovered": True},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "ask_user"


class StuckRecovery(RecoveryRecipe):
    """Recover when agent is stuck (no progress for extended time)."""
    recipe_id = "STUCK_RECOVERY"
    max_budget = 3

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_stuck

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "stuck"},
            feedback_data={"recovered": True},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class TargetLostRecovery(RecoveryRecipe):
    """Recover when combat target is lost."""
    recipe_id = "TARGET_LOST_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_target_lost

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "target_lost"},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class LoadingTimeoutRecovery(RecoveryRecipe):
    """Recover when loading screen doesn't end."""
    recipe_id = "LOADING_TIMEOUT_RECOVERY"
    max_budget = 1

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_loading

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "loading_timeout"},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "ask_user"


class CombatDefeatRecovery(RecoveryRecipe):
    """Recover after combat defeat."""
    recipe_id = "COMBAT_DEFEAT_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return not snapshot.is_healthy()

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "combat_defeat"},
            feedback_data={"revived": True},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class LowHealthRecovery(RecoveryRecipe):
    """Recover when team health is critically low."""
    recipe_id = "LOW_HEALTH_RECOVERY"
    max_budget = 3

    def check_precondition(self, snapshot: SomaticState) -> bool:
        if not snapshot.team_state.hp_ratios:
            return False
        active_hp = snapshot.team_state.hp_ratios[0] if snapshot.team_state.hp_ratios else 1.0
        return active_hp < 0.2

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "low_health"},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class DriftRecovery(RecoveryRecipe):
    """Recover when agent has drifted from expected state."""
    recipe_id = "DRIFT_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_drifting

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "drift"},
        )

    def verify_restabilized(self, perception: Any = None, claim_runtime: Any = None) -> bool:
        return True

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "replan"


class ModelProviderFailureRecovery(RecoveryRecipe):
    """Recover when the LLM/model provider fails."""
    recipe_id = "MODEL_PROVIDER_FAILURE_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.model_provider_failed

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=1,
            new_screen_state="",
            claim_data={"recovery_type": "model_provider_failure"},
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
