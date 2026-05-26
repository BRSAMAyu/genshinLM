"""GenesisAgent Reflex Combat Director: Executes frame-exact micro-combos and visual cancels."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.state_bus import StateBus
from core.types import Observation
from execution.input_lease import InputLease  # Mock or actual background InputWorker leasing

log = logging.getLogger("CombatDirector")

@dataclass
class CombatComboStep:
    action_type: str  # "key_press", "mouse_click", "delay", "wait_visual"
    value: str        # "e", "q", "1", "2", "3", "4", "left_click"
    duration: float = 0.05
    post_delay: float = 0.1
    cancel_trigger: Optional[str] = None  # e.g., "visual_impact_flash" -> cancel delay
    allow_interrupt: bool = True

@dataclass
class ComboSequence:
    name: str
    steps: List[CombatComboStep] = field(default_factory=list)
    risk_level: str = "medium"
    cooldown: float = 8.0
    last_executed: float = 0.0

class CombatDirector:
    """Fast-Path Reflex Combat Controller operating at high frequencies.
    
    Tuned for 30+ FPS environments, bypassing slow textual reasoning to execute
    tactical movement, character swapping, key combos, and animation cancels.
    """

    def __init__(
        self,
        state_bus: StateBus,
        input_lease_provider: Any,  # InputLease / Executor backend
        combat_playbook: Optional[Dict[str, Any]] = None
    ) -> None:
        self._state_bus = state_bus
        self._input_lease = input_lease_provider
        self._combos: Dict[str, ComboSequence] = {}
        self._active_combo: Optional[ComboSequence] = None
        self._active_step_idx: int = 0
        self._next_step_ready_at: float = 0.0
        self._cooldowns: Dict[str, float] = {}  # Action/Character swap cooldown track
        self._running: bool = False
        
        # Load playbook if provided
        if combat_playbook:
            self.load_playbook(combat_playbook)

    def load_playbook(self, playbook: Dict[str, Any]) -> None:
        """Parse raw JSON playbook into ComboSequence definitions."""
        self._combos.clear()
        for name, data in playbook.get("combos", {}).items():
            steps = []
            for s in data.get("steps", []):
                steps.append(CombatComboStep(
                    action_type=s.get("action_type", "key_press"),
                    value=s.get("value", ""),
                    duration=s.get("duration", 0.05),
                    post_delay=s.get("post_delay", 0.1),
                    cancel_trigger=s.get("cancel_trigger"),
                    allow_interrupt=s.get("allow_interrupt", True)
                ))
            self._combos[name] = ComboSequence(
                name=name,
                steps=steps,
                cooldown=data.get("cooldown", 5.0)
            )
        log.info("CombatDirector loaded %d combos from playbook", len(self._combos))

    def trigger_combo(self, name: str) -> bool:
        """Attempt to activate a micro-combo sequence by name."""
        combo = self._combos.get(name)
        if not combo:
            log.warning("Combo '%s' not registered in playbook", name)
            return False

        now = time.perf_counter()
        if now - combo.last_executed < combo.cooldown:
            log.debug("Combo '%s' is on cooldown (elapsed=%.2fs)", name, now - combo.last_executed)
            return False

        self._active_combo = combo
        self._active_step_idx = 0
        self._next_step_ready_at = time.perf_counter()
        log.info("Combo '%s' activated successfully", name)
        return True

    def update(self, observation: Observation) -> None:
        """Core high-frequency tick. Read frame state and step through combo logic."""
        if not self._active_combo:
            return

        # Check visual interrupts / emergency dodge tokens first
        active_token = self._state_bus.get_slot("reflex.active_preemption_token")
        if active_token and active_token.get() is not None:
            log.info("Dodge preemption active, pausing combo execution")
            self._input_lease.release_all()
            return

        now = time.perf_counter()
        if now < self._next_step_ready_at:
            return
        step = self._active_combo.steps[self._active_step_idx]

        # Execute current step action
        success = self._execute_step_action(step, observation)
        
        if success:
            self._next_step_ready_at = max(
                self._next_step_ready_at,
                time.perf_counter() + max(0.0, step.post_delay),
            )
            # Advance step index
            self._active_step_idx += 1
            if self._active_step_idx >= len(self._active_combo.steps):
                log.info("Combo '%s' completed successfully", self._active_combo.name)
                self._active_combo.last_executed = now
                self._active_combo = None
                self._active_step_idx = 0
                self._next_step_ready_at = 0.0
        else:
            # Step block or visual trigger wait, retry next frame
            pass

    def clear_active_combos(self) -> None:
        """Instantly clear running combo and release all inputs."""
        self._active_combo = None
        self._active_step_idx = 0
        self._next_step_ready_at = 0.0
        self._input_lease.release_all()
        log.info("CombatDirector: Active combat sequences cleared")

    # -- Internal execution details -------------------------------------------

    def _execute_step_action(self, step: CombatComboStep, observation: Observation) -> bool:
        """Simulate specific mouse/keyboard action or wait for visual triggers."""
        # 1. Check visual preconditions if trigger is set
        if step.cancel_trigger:
            trigger_found = observation.extensions.get(step.cancel_trigger, False)
            if trigger_found:
                log.debug("Animation cancel trigger '%s' detected! Skipping delay", step.cancel_trigger)
                return True

        if step.action_type == "key_press":
            # Direct lease press
            log.debug("Reflex key_press: '%s'", step.value)
            self._input_lease.press(step.value, duration=step.duration)
            return True

        elif step.action_type == "mouse_click":
            log.debug("Reflex mouse_click: '%s'", step.value)
            self._input_lease.click(step.value, duration=step.duration)
            return True

        elif step.action_type == "wait_visual":
            # Wait until observation flag becomes true
            is_valid = observation.extensions.get(step.value, False)
            if is_valid:
                log.debug("Visual state '%s' verified! Advancing sequence", step.value)
                return True
            return False

        elif step.action_type == "delay":
            self._next_step_ready_at = time.perf_counter() + max(0.0, step.duration)
            return True

        return False
