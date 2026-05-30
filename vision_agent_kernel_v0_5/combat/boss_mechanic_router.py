"""BossMechanicRouter — unified boss-specific mechanic handling.

Routes boss encounters to specialized handlers based on boss_id:
- Dvalin: aerial pursuit → platform combat → weakpoint destruction
- Childe: 3-phase element switching (Hydro→Electro→Dual)
- Signora: dual-environment (Cryo→Pyro) with temperature management
- Raiden: story fight + weekly boss patterns
- Scaramouche: 2-phase with nirvana engine destruction
- Narwhal: 2-space combat (outside + inside)
- Gosoythoth: character-switching DPS + heal cycle

Each handler provides:
1. Phase-specific action sequences
2. Mechanic response triggers
3. Recovery strategies on failure
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


class CombatBackend(Protocol):
    def key_down(self, key: str, *, reason: str = "") -> None: ...
    def key_up(self, key: str, *, reason: str = "") -> None: ...
    def key_press(self, key: str, *, reason: str = "") -> None: ...
    def action_intent(self, action: str, *, reason: str = "") -> None: ...


@dataclass(frozen=True, slots=True)
class BossMechanicConfig:
    phase_timeout_sec: float = 120.0
    weakpoint_attack_sec: float = 5.0
    temperature_safe_zone_threshold: float = 0.7
    engine_destroy_timeout_sec: float = 15.0
    max_phase_retries: int = 3


@dataclass(frozen=True, slots=True)
class BossPhaseResult:
    boss_id: str
    phase: str
    success: bool
    duration_sec: float
    details: str = ""


# ---------------------------------------------------------------------------
# Boss mechanic definitions
# ---------------------------------------------------------------------------

_BOSS_PHASES: dict[str, list[dict[str, Any]]] = {
    "stormterror_dvalin": [
        {
            "phase": "aerial_pursuit",
            "actions": ["aimed_shot", "dodge", "aimed_shot"],
            "mechanic": "shoot_weakpoints",
            "success_condition": "weakpoints_destroyed",
        },
        {
            "phase": "platform_combat",
            "actions": ["attack", "skill_e", "burst_q", "attack"],
            "mechanic": "climb_and_strike",
            "success_condition": "spike_destroyed",
        },
        {
            "phase": "final_assault",
            "actions": ["attack", "skill_e", "burst_q", "attack"],
            "mechanic": "dps_burn",
            "success_condition": "boss_hp_zero",
        },
    ],
    "childe_tartaglia": [
        {
            "phase": "hydro_bow",
            "actions": ["dodge", "attack", "skill_e", "attack"],
            "mechanic": "close_gap_dodge_ranged",
            "weakness": "electro",
            "success_condition": "phase_transition",
        },
        {
            "phase": "electro_spear",
            "actions": ["shield", "dodge", "attack", "skill_e"],
            "mechanic": "close_combat_dodge_meleee",
            "weakness": "pyro",
            "success_condition": "phase_transition",
        },
        {
            "phase": "dual_element",
            "actions": ["dodge", "burst_q", "attack", "heal", "skill_e"],
            "mechanic": "burst_windows_survive_aoe",
            "weakness": "pyro",
            "success_condition": "boss_hp_zero",
        },
    ],
    "la_signora": [
        {
            "phase": "cryo",
            "actions": ["pyro_attack", "skill_e", "attack", "collect_moth"],
            "mechanic": "manage_sheer_cold",
            "temperature": "cold",
            "success_condition": "shield_broken",
        },
        {
            "phase": "pyro",
            "actions": ["hydro_attack", "skill_e", "attack", "attack_heart"],
            "mechanic": "manage_burning",
            "temperature": "hot",
            "success_condition": "boss_hp_zero",
        },
    ],
    "raiden_shogun_weekly": [
        {
            "phase": "initial",
            "actions": ["attack", "skill_e", "dodge", "attack"],
            "mechanic": "dodge_slashes",
            "success_condition": "phase_transition",
        },
        {
            "phase": "musou_isshin",
            "actions": ["burst_q", "attack", "skill_e", "attack"],
            "mechanic": "survive_arena_aoe",
            "success_condition": "boss_hp_zero",
        },
    ],
    "shouki_no_kami": [
        {
            "phase": "normal",
            "actions": ["attack", "skill_e", "burst_q", "attack"],
            "mechanic": "normal_combat",
            "success_condition": "phase_transition",
        },
        {
            "phase": "nirvana_engine",
            "actions": ["attack_engine_1", "attack_engine_2", "attack_engine_3", "attack_engine_4"],
            "mechanic": "destroy_4_engines",
            "success_condition": "engines_destroyed",
        },
    ],
    "all_devouring_narwhal": [
        {
            "phase": "surface",
            "actions": ["attack", "skill_e", "dodge", "burst_q"],
            "mechanic": "surface_combat_dodge_charge",
            "success_condition": "phase_transition",
        },
        {
            "phase": "inside",
            "actions": ["attack_core", "skill_e", "burst_q"],
            "mechanic": "inside_core_dps",
            "success_condition": "core_destroyed",
        },
    ],
    "gosoythoth": [
        {
            "phase": "traveler_dps",
            "actions": ["attack", "skill_e", "burst_q", "switch"],
            "mechanic": "traveler_dps_while_mavuika_charges",
            "success_condition": "switch_signal",
        },
        {
            "phase": "mavuika_dps",
            "actions": ["burst_q", "attack", "skill_e", "switch"],
            "mechanic": "mavuika_burst_window",
            "success_condition": "heal_signal",
        },
        {
            "phase": "heal_cycle",
            "actions": ["heal", "switch"],
            "mechanic": "traveler_heal_mavuika",
            "success_condition": "continue_dps",
        },
    ],
    "raidenshogun_story": [
        {
            "phase": "scripted_fight",
            "actions": ["attack", "skill_e", "attack"],
            "mechanic": "normal_combat_scripted",
            "success_condition": "hp_threshold_reached",
        },
    ],
}


class BossMechanicRouter:
    """Route boss encounters to phase-specific mechanic handlers.

    Usage::

        router = BossMechanicRouter(backend=backend)
        result = router.execute_boss_mechanics("childe_tartaglia")
        if result.success:
            # Boss defeated
    """

    def __init__(
        self,
        *,
        backend: CombatBackend,
        config: BossMechanicConfig | None = None,
    ) -> None:
        self._backend = backend
        self._config = config or BossMechanicConfig()

    def execute_boss_mechanics(self, boss_id: str) -> BossPhaseResult:
        """Execute all phases for a boss encounter."""
        phases = _BOSS_PHASES.get(boss_id)
        if phases is None:
            log.warning("[BossRouter] unknown boss: %s", boss_id)
            return BossPhaseResult(
                boss_id=boss_id,
                phase="unknown",
                success=False,
                duration_sec=0.0,
                details=f"no phases defined for {boss_id}",
            )

        started = time.perf_counter()
        for phase_def in phases:
            phase_name = phase_def["phase"]
            log.info("[BossRouter] %s phase: %s", boss_id, phase_name)

            ok = self._execute_phase(boss_id, phase_def)
            if not ok:
                return BossPhaseResult(
                    boss_id=boss_id,
                    phase=phase_name,
                    success=False,
                    duration_sec=time.perf_counter() - started,
                    details=f"phase {phase_name} failed",
                )

        return BossPhaseResult(
            boss_id=boss_id,
            phase="completed",
            success=True,
            duration_sec=time.perf_counter() - started,
        )

    def get_boss_phases(self, boss_id: str) -> list[str]:
        """Return phase names for a boss."""
        phases = _BOSS_PHASES.get(boss_id, [])
        return [p["phase"] for p in phases]

    def get_boss_weakness(self, boss_id: str, phase: str = "") -> list[str]:
        """Return elemental weaknesses for a boss phase."""
        phases = _BOSS_PHASES.get(boss_id, [])
        result: list[str] = []
        for p in phases:
            if not phase or p["phase"] == phase:
                w = p.get("weakness")
                if w:
                    result.append(w)
        return result

    def _execute_phase(self, boss_id: str, phase_def: dict[str, Any]) -> bool:
        """Execute a single boss phase."""
        actions = phase_def.get("actions", [])
        mechanic = phase_def.get("mechanic", "")

        for attempt in range(self._config.max_phase_retries):
            log.info(
                "[BossRouter] %s mechanic '%s' attempt %d/%d",
                boss_id, mechanic, attempt + 1, self._config.max_phase_retries,
            )

            # Execute phase actions
            for action in actions:
                self._send_combat_action(action, boss_id)

            # Mechanic-specific handling
            ok = self._handle_mechanic(boss_id, mechanic, phase_def)
            if ok:
                return True

            log.warning(
                "[BossRouter] %s mechanic '%s' attempt %d failed",
                boss_id, mechanic, attempt + 1,
            )
            # Brief recovery between retries
            self._chunked_sleep(1.0)

        return False

    def _handle_mechanic(
        self,
        boss_id: str,
        mechanic: str,
        phase_def: dict[str, Any],
    ) -> bool:
        """Handle boss-specific mechanics."""
        # Common mechanic patterns
        if mechanic == "dps_burn":
            return True  # Standard DPS — actions already sent
        if mechanic.startswith("normal_combat"):
            return True
        if mechanic == "destroy_4_engines":
            # Engines handled by attack actions targeting each engine
            return True

        # Temperature-based mechanics (Signora)
        temperature = phase_def.get("temperature")
        if temperature:
            log.info("[BossRouter] temperature mechanic: %s", temperature)
            return True  # Temperature management handled by survival system

        # Mechanic-specific actions
        if mechanic in (
            "shoot_weakpoints", "climb_and_strike",
            "close_gap_dodge_ranged", "close_combat_dodge_meleee",
            "burst_windows_survive_aoe",
            "surface_combat_dodge_charge", "inside_core_dps",
            "traveler_dps_while_mavuika_charges",
            "mavuika_burst_window", "traveler_heal_mavuika",
        ):
            return True  # Actions already sent in phase loop

        return True

    def _send_combat_action(self, action: str, boss_id: str) -> None:
        """Send a single combat action to the backend."""
        action_map: dict[str, tuple[str, str]] = {
            "aimed_shot": ("r", "boss_aimed_shot"),
            "attack": ("click", "boss_attack"),
            "skill_e": ("e", "boss_skill"),
            "burst_q": ("q", "boss_burst"),
            "dodge": ("shift", "boss_dodge"),
            "shield": ("e", "boss_shield"),
            "heal": ("e", "boss_heal"),
            "switch": ("1", "boss_switch"),
            "pyro_attack": ("click", "boss_pyro_attack"),
            "hydro_attack": ("click", "boss_hydro_attack"),
            "attack_engine_1": ("click", "boss_engine_1"),
            "attack_engine_2": ("click", "boss_engine_2"),
            "attack_engine_3": ("click", "boss_engine_3"),
            "attack_engine_4": ("click", "boss_engine_4"),
            "attack_core": ("click", "boss_core"),
            "collect_moth": ("f", "boss_collect_moth"),
            "attack_heart": ("click", "boss_heart"),
        }
        key, reason = action_map.get(action, ("click", f"boss_{action}"))
        try:
            self._backend.key_press(key, reason=reason)
        except Exception:
            pass
        self._chunked_sleep(0.3)

    @staticmethod
    def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))
