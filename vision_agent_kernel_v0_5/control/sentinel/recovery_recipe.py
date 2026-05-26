"""RecoveryRecipe — base protocol and result for recovery actions.

Each recipe must:
- check_precondition: verify it's applicable to the current anomaly
- execute_recovery: perform bounded recovery actions
- verify_restabilized: confirm recovery succeeded
- failure_policy: declare what happens if recovery fails
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from control.sentinel.somatic_state import SomaticState


RecoveryPolicy = Literal["abort", "replan", "ask_user", "escalate"]
RecoveryStatus = Literal["success", "failed", "partial", "budget_exhausted", "skipped"]


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Outcome of a recovery recipe execution."""
    recipe_id: str
    status: RecoveryStatus
    actions_taken: int = 0
    new_screen_state: str = ""
    claim_data: dict[str, Any] = field(default_factory=dict)
    feedback_data: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class RecoveryRecipe:
    """Base class for recovery recipes.

    Subclasses override check_precondition, execute_recovery, and
    verify_restabilized. The sentinel runtime calls these in order.
    """

    recipe_id: str = "base"
    max_budget: int = 3

    def check_precondition(self, snapshot: SomaticState) -> bool:
        """Return True if this recipe is applicable."""
        return False

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        """Execute recovery actions. Must be bounded by max_budget."""
        return RecoveryResult(self.recipe_id, "skipped")

    def verify_restabilized(
        self,
        perception: Any = None,
        claim_runtime: Any = None,
    ) -> bool:
        """Verify the system has restabilized after recovery."""
        return False

    @property
    def failure_policy(self) -> RecoveryPolicy:
        return "escalate"
