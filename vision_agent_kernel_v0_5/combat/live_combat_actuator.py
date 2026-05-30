from __future__ import annotations

import logging
import time
from typing import Any, Callable

log = logging.getLogger(__name__)


def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))


class LiveCombatActuator:
    """Read real-time character states and execute elemental-reaction playbooks seamlessly

    without timing corruption, incorporating poise-broken/stiffness shift escapes.
    """

    def __init__(self, backend: Any) -> None:
        self._backend = backend
        # Maps character index (1-based) to the monotonic timestamp when they can be switched in again
        self._switch_cooldowns: dict[int, float] = {}
        # Maps character index (1-based) to a dict of skill name -> ready timestamp
        self._skill_cooldowns: dict[int, dict[str, float]] = {
            1: {},
            2: {},
            3: {},
            4: {},
        }
        self._active_character: int = 1

    def execute_combat_loop(
        self,
        playbook_steps: list[dict[str, Any]],
        obs_stream: Callable[[], dict[str, Any] | None],
        duration_limit_sec: float = 10.0,
    ) -> bool:
        """Executes a sequence of elemental reactions and playbook steps.

        Monitors health, poise, and control effects, escaping stiffness where necessary.
        """
        start_time = time.perf_counter()

        for step in playbook_steps:
            if time.perf_counter() - start_time > duration_limit_sec:
                log.warning("[LiveCombat] combat loop exceeded duration limit")
                return False

            # 1. Active sentinel check before step execution
            obs = obs_stream()
            if obs:
                # Read HP ratio and check for emergency healing
                hp_ratio = obs.get("hp_ratio", 1.0)
                if hp_ratio < 0.2:
                    log.warning("[LiveCombat] Critical HP detected! Pressing esc/food")
                    # Emergency escape/healing
                    try:
                        self._backend.key_down("esc", reason="emergency_heal")
                        _chunked_sleep(0.05)
                        self._backend.key_up("esc")
                    except Exception:
                        pass
                    return False

                # Resolve Gap 22 (Target Kite Deadlock): Center camera onto target if off-screen/off-center
                target_offset_x = obs.get("target_offset_x", 0.0)
                if abs(target_offset_x) > 0.15:
                    log.info("[LiveCombat] Aligning combat camera to target: offset=%.2f", target_offset_x)
                    try:
                        self._backend.mouse_move(target_offset_x * 40.0, 0.0, reason="combat_camera_align")
                        _chunked_sleep(0.08)
                    except Exception as e:
                        log.debug("[LiveCombat] combat camera align error: %s", e)

                # Read signals for interruption/poise/stiffness
                signals = obs.get("signals", {})
                
                # Resolve Gap 17 (Dodge Timing Latency): Fast-path incoming attack dodge reflex
                if signals.get("attack_incoming", 0.0) > 0.5:
                    log.info("[LiveCombat] Attack threat incoming! Sending rapid dodge iframe sprint")
                    self._escape_stiffness()
                    continue

                if (
                    signals.get("hitstun", 0.0) > 0.5
                    or signals.get("knocked_back", 0.0) > 0.5
                    or signals.get("frozen", 0.0) > 0.5
                    or signals.get("poise_broken", 0.0) > 0.5
                ):
                    log.info("[LiveCombat] stiffness detected, executing escape sprint")
                    self._escape_stiffness()

            # 2. Execute step
            step_type = step.get("type")
            if step_type == "switch":
                target_char = step.get("character", 1)
                self._switch_character(target_char)
            elif step_type == "skill_e":
                self._cast_skill_e()
            elif step_type == "burst_q":
                self._cast_burst_q()
            elif step_type == "attack":
                duration = step.get("duration", 0.5)
                self._perform_attack(duration)
            else:
                # Default: small pause or walk
                _chunked_sleep(0.1)

        return True

    def _escape_stiffness(self) -> None:
        """Execute a rapid Double-Shift (sprint) input sequence to break out

        of hitstun, freeze, or poise-broken states.
        """
        log.info("[LiveCombat] Stiffness escape triggered: Double-Shift")
        for i in range(2):
            try:
                self._backend.key_down("shift", reason=f"escape_shift_{i}")
                _chunked_sleep(0.05)
                self._backend.key_up("shift", reason=f"escape_shift_{i}_done")
                if i == 0:
                    _chunked_sleep(0.08)  # brief human-like delay between double clicks/presses
            except Exception as e:
                log.error("[LiveCombat] failed to send escape shift input: %s", e)

    def _switch_character(self, target_char: int) -> None:
        if target_char == self._active_character:
            return

        now = time.perf_counter()
        ready_time = self._switch_cooldowns.get(target_char, 0.0)
        if now < ready_time:
            wait_time = ready_time - now
            log.info("[LiveCombat] Waiting %.2fs for character %d switch CD", wait_time, target_char)
            _chunked_sleep(wait_time)

        log.info("[LiveCombat] Switching from character %d to %d", self._active_character, target_char)
        try:
            self._backend.key_down(str(target_char), reason="character_switch")
            _chunked_sleep(0.05)
            self._backend.key_up(str(target_char), reason="character_switch_done")
        except Exception:
            pass

        self._active_character = target_char
        # Enforce 1.0s switch cooldown on all other characters in the team
        now = time.perf_counter()
        for i in range(1, 5):
            self._switch_cooldowns[i] = now + 1.0

        # Wait a small transition delay for switch animation to complete
        _chunked_sleep(0.15)

    def _cast_skill_e(self) -> None:
        log.info("[LiveCombat] Casting Elemental Skill (E)")
        try:
            self._backend.key_down("e", reason="cast_skill_e")
            _chunked_sleep(0.08)
            self._backend.key_up("e", reason="cast_skill_e_done")
        except Exception:
            pass
        # Track 6s default skill cooldown for demo
        self._skill_cooldowns[self._active_character]["e"] = time.perf_counter() + 6.0
        _chunked_sleep(0.2)  # animation cast time lock

    def _cast_burst_q(self) -> None:
        log.info("[LiveCombat] Casting Elemental Burst (Q)")
        try:
            self._backend.key_down("q", reason="cast_burst_q")
            _chunked_sleep(0.08)
            self._backend.key_up("q", reason="cast_burst_q_done")
        except Exception:
            pass
        # Track 15s default burst cooldown
        self._skill_cooldowns[self._active_character]["q"] = time.perf_counter() + 15.0
        _chunked_sleep(1.2)  # burst iframe animation lock

    def _perform_attack(self, duration: float) -> None:
        log.info("[LiveCombat] Performing attack sequence for %.2fs", duration)
        end = time.perf_counter() + duration
        while time.perf_counter() < end:
            try:
                self._backend.left_click(reason="combat_attack")
            except Exception:
                pass
            _chunked_sleep(0.12)
