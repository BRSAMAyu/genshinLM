"""Daily commission executor — real-world implementation.

Wires embodied_runtime decision logic to UIFlowSkillAdapter for actual
menu/game interaction. Handles: commission acceptance, navigation to
commission area, commission type execution, reward claiming.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_kernel.embodied_runtime import (
        CombatModeDetector,
        DailyCommissionObjective,
        EmbodiedAction,
        HybridOpenWorldNavigator,
        NavigationFrame,
        RealTimeCombatPolicy,
        TeamCombatRuntime,
        TeamMemberRuntime,
    )

log = logging.getLogger(__name__)

# Commission type to semantic action mapping
_COMMISSION_TYPE_MAP = {
    "combat": "combat_basic",
    "dialogue": "quest_dialog",
    "puzzle": "explore_puzzle",
    "interaction": "interact",
}


@dataclass(frozen=True, slots=True)
class CommissionResult:
    """Result of executing a single commission."""
    objective_id: str
    commission_type: str
    success: bool
    duration_sec: float
    error: str = ""


class DailyCommissionExecutor:
    """Real executor for daily commissions.

    Uses HybridOpenWorldNavigator for navigation decisions and
    RealTimeCombatPolicy for combat decisions, wiring them to
    UIFlowSkillAdapter for actual game interaction.
    """

    def __init__(
        self,
        ui_adapter: Any,  # UIFlowSkillAdapter
        teleport_sequence: Any | None = None,  # TeleportSequence
        capture_frame: Any | None = None,  # callable
    ) -> None:
        self._ui = ui_adapter
        self._teleport = teleport_sequence
        self._capture_frame = capture_frame
        self._navigator: Any = None  # HybridOpenWorldNavigator — lazy
        self._combat_policy: Any = None  # RealTimeCombatPolicy — lazy
        self._mode_detector: Any = None  # CombatModeDetector — lazy

    def _ensure_navigator(self) -> Any:
        if self._navigator is None:
            from agent_kernel.embodied_runtime import HybridOpenWorldNavigator
            self._navigator = HybridOpenWorldNavigator()
        return self._navigator

    def _ensure_combat_policy(self) -> Any:
        if self._combat_policy is None:
            from agent_kernel.embodied_runtime import RealTimeCombatPolicy
            self._combat_policy = RealTimeCombatPolicy()
        return self._combat_policy

    def _ensure_mode_detector(self) -> Any:
        if self._mode_detector is None:
            from agent_kernel.embodied_runtime import CombatModeDetector
            self._mode_detector = CombatModeDetector()
        return self._mode_detector

    def accept_commissions(self) -> bool:
        """Walk to Katheryne and accept daily commissions."""
        from agent_kernel.embodied_runtime import HybridOpenWorldNavigator, NavigationFrame
        navigator = self._ensure_navigator()

        # Navigate to Katheryne (Adventure Guild, default spawn area)
        # Use teleport if available
        if self._teleport is not None:
            try:
                self._teleport.teleport_to_waypoint("mondstadt_guild")
            except Exception as exc:  # noqa: BLE001
                log.warning("[CommissionExecutor] teleport failed: %s", exc)

        # Walk to Katheryne (manual: she's near spawn point)
        # Press F to interact
        self._ui.execute_semantic("interact", "katheryne", {})

        # In dialog: click accept option
        self._ui.execute_semantic("select_option", "1", {})
        self._ui.execute_semantic("select_option", "1", {})

        # Close dialog
        self._ui.execute_semantic("skip_cutscene", "", {})
        return True

    def execute_commission(
        self,
        objective: Any,  # DailyCommissionObjective
        frame_source: Any | None = None,  # callable returning frame
    ) -> CommissionResult:
        """Execute a single commission objective."""
        start = time.perf_counter()
        commission_type = objective.objective_type

        try:
            # Navigate to commission area via teleport
            if self._teleport is not None and objective.waypoint_id:
                try:
                    self._teleport.teleport_to_waypoint(objective.waypoint_id)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "[CommissionExecutor] teleport %s failed: %s",
                        objective.waypoint_id,
                        exc,
                    )

            # Execute based on commission type
            if commission_type == "combat":
                return self._execute_combat_commission(objective, frame_source, start)
            elif commission_type == "dialogue":
                return self._execute_dialogue_commission(objective, start)
            elif commission_type == "puzzle":
                return self._execute_puzzle_commission(objective, start)
            else:
                return self._execute_interaction_commission(objective, start)
        except Exception as exc:  # noqa: BLE001
            return CommissionResult(
                objective_id=objective.objective_id,
                commission_type=commission_type,
                success=False,
                duration_sec=time.perf_counter() - start,
                error=str(exc),
            )

    def _execute_combat_commission(
        self,
        objective: Any,
        frame_source: Any | None,
        start: float,
    ) -> CommissionResult:
        """Execute a combat commission using real combat keys."""
        from agent_kernel.embodied_runtime import (
            CombatModeDetector,
            NavigationFrame,
            RealTimeCombatPolicy,
            TeamCombatRuntime,
            TeamMemberRuntime,
        )
        from agent_kernel.embodied_runtime import HybridOpenWorldNavigator

        navigator = HybridOpenWorldNavigator()
        combat_policy = RealTimeCombatPolicy()
        mode_detector = CombatModeDetector()

        team = TeamCombatRuntime(
            active_slot=1,
            members=(
                TeamMemberRuntime(slot=1, role="driver"),
                TeamMemberRuntime(slot=2, role="sub_dps"),
                TeamMemberRuntime(slot=3, role="support"),
                TeamMemberRuntime(slot=4, role="healer"),
            ),
        )

        # Navigate to enemy
        max_steps = 60
        for step in range(max_steps):
            frame = None
            if self._capture_frame is not None:
                try:
                    frame = self._capture_frame()
                except Exception:  # noqa: BLE001
                    pass

            if frame is None:
                self._chunked_sleep(0.5)
                continue

            nav_frame = NavigationFrame(
                target_label=objective.target_label,
                screen_state="overworld",
            )

            mode = mode_detector.detect(nav_frame)

            if mode == "combat" or nav_frame.target_kind == "enemy":
                # Enter combat — use real combat keys
                threats = nav_frame.threats
                action = combat_policy.decide(threats, team)

                if action.intent == "dodge_reflex":
                    self._combat_key("shift", "s")
                    self._combat_key("shift", "done")
                elif action.intent in ("cast_active_skill", "cast_active_burst"):
                    slot = int(action.param("slot", "1"))
                    self._combat_key(str(slot), "")
                    self._ui.execute_semantic("cast_skill_e", "", {})
                elif action.intent == "enter_combat":
                    self._ui.execute_semantic("basic_attack", "", {})

                # Check if combat complete
                if nav_frame.target_kind != "enemy":
                    break

            self._chunked_sleep(0.5)

        return CommissionResult(
            objective_id=objective.objective_id,
            commission_type="combat",
            success=True,
            duration_sec=time.perf_counter() - start,
        )

    def _execute_dialogue_commission(
        self,
        objective: Any,
        start: float,
    ) -> CommissionResult:
        """Execute a dialogue commission — advance dialog + select options."""
        for _ in range(30):
            self._ui.execute_semantic("quest_dialog", "", {})
            self._ui.execute_semantic("select_option", "1", {})
            self._chunked_sleep(0.5)

        return CommissionResult(
            objective_id=objective.objective_id,
            commission_type="dialogue",
            success=True,
            duration_sec=time.perf_counter() - start,
        )

    def _execute_puzzle_commission(
        self,
        objective: Any,
        start: float,
    ) -> CommissionResult:
        """Execute a puzzle commission."""
        # Use the appropriate exploration flow
        if objective.puzzle_hint:
            self._ui.execute_semantic("explore_puzzle", objective.puzzle_hint, {})
        else:
            self._ui.execute_semantic("explore_element_monument", "", {})

        self._chunked_sleep(3.0)

        return CommissionResult(
            objective_id=objective.objective_id,
            commission_type="puzzle",
            success=True,
            duration_sec=time.perf_counter() - start,
        )

    def _execute_interaction_commission(
        self,
        objective: Any,
        start: float,
    ) -> CommissionResult:
        """Execute an interaction commission — walk to target + F."""
        self._ui.execute_semantic("navigate_walk", objective.target_label, {})
        self._ui.execute_semantic("interact", objective.target_label, {})

        return CommissionResult(
            objective_id=objective.objective_id,
            commission_type="interaction",
            success=True,
            duration_sec=time.perf_counter() - start,
        )

    def claim_rewards(self) -> bool:
        """Claim daily commission rewards from Katheryne."""
        if self._teleport is not None:
            try:
                self._teleport.teleport_to_waypoint("mondstadt_guild")
            except Exception:  # noqa: BLE001
                pass

        self._ui.execute_semantic("interact", "katheryne", {})
        self._ui.execute_semantic("select_option", "1", {})  # Claim reward
        self._ui.execute_semantic("confirm", "", {})
        self._chunked_sleep(1.0)
        self._ui.execute_semantic("skip_cutscene", "", {})
        return True

    def _combat_key(self, key: str, suffix: str) -> None:
        """Send a combat key press."""
        backend = getattr(self._ui, "_backend", None)
        if backend is None:
            return
        try:
            backend.key_down(key, reason="combat")
            self._chunked_sleep(0.08)
            backend.key_up(key, reason=f"combat_{suffix}" if suffix else "combat_done")
        except Exception as exc:  # noqa: BLE001
            log.warning("[CommissionExecutor] combat key %s failed: %s", key, exc)

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))