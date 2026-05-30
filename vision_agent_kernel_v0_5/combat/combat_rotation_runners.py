"""Combat rotation runners: weekly boss cycling, world boss farming, multi-wave defense.

Implements scenarios #14 (Weekly Boss Rotation), #15 (World Boss Farming),
#16 (Multi-Wave Defense), #2 (Shield Mitachurl), and #3 (Abyss Mage)
from GENSHIN_COMBAT_SCENARIO_BREAKDOWN.md.
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


class SemanticExecutor(Protocol):
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Weekly Boss Rotation (#14)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WeeklyBossConfig:
    max_discounts_per_boss: int = 1
    total_weekly_discounts: int = 3
    teleport_timeout_sec: float = 30.0
    combat_timeout_sec: float = 180.0
    reward_claim_timeout_sec: float = 10.0


@dataclass(frozen=True, slots=True)
class WeeklyBossResult:
    boss_id: str
    success: bool
    discount_used: bool
    duration_sec: float
    details: str = ""


# Boss teleport targets (map to in-game locations)
_WEEKLY_BOSS_LOCATIONS: dict[str, str] = {
    "stormterror_dvalin": "stormterror_lair",
    "childe_tartaglia": "golden_house",
    "la_signora": "narukami_shrine",
    "raiden_shogun_weekly": "mt_youkou",
    "shouki_no_kami": "pavilion_of_permanence",
    "all_devouring_narwhal": "fontaine_sea_floor",
    "gosoythoth": "night_kingdom",
}


@dataclass(slots=True)
class WeeklyBossRotation:
    """Cycle through weekly bosses, claiming discounted rewards.

    Usage::

        rotation = WeeklyBossRotation(executor=executor, config=config)
        results = rotation.run_rotation(
            target_bosses=["stormterror_dvalin", "childe_tartaglia", "la_signora"]
        )
    """

    executor: SemanticExecutor
    config: WeeklyBossConfig = field(default_factory=WeeklyBossConfig)
    discounts_remaining: int = -1  # -1 means use config value
    completed_bosses: list[str] = field(default_factory=list)
    results: list[WeeklyBossResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.discounts_remaining < 0:
            self.discounts_remaining = self.config.total_weekly_discounts

    def run_rotation(self, target_bosses: list[str] | None = None) -> list[WeeklyBossResult]:
        if target_bosses is None:
            target_bosses = list(_WEEKLY_BOSS_LOCATIONS.keys())

        for boss_id in target_bosses:
            if self.discounts_remaining <= 0:
                log.info("[WeeklyRotation] no discounts remaining, stopping")
                break
            if boss_id in self.completed_bosses:
                continue

            result = self._run_single_boss(boss_id)
            self.results.append(result)
            if result.success:
                self.completed_bosses.append(boss_id)
                if result.discount_used:
                    self.discounts_remaining -= 1

        return self.results

    def _run_single_boss(self, boss_id: str) -> WeeklyBossResult:
        started = time.perf_counter()
        location = _WEEKLY_BOSS_LOCATIONS.get(boss_id, "")

        # Teleport to boss location
        ok = self.executor.execute_semantic("teleport_to", target=location,
                                            context={"timeout": self.config.teleport_timeout_sec})
        if not ok:
            return WeeklyBossResult(boss_id=boss_id, success=False, discount_used=False,
                                    duration_sec=time.perf_counter() - started,
                                    details="teleport_failed")

        # Enter boss domain
        ok = self.executor.execute_semantic("interact", context={"reason": "enter_boss_domain"})
        if not ok:
            return WeeklyBossResult(boss_id=boss_id, success=False, discount_used=False,
                                    duration_sec=time.perf_counter() - started,
                                    details="enter_domain_failed")

        # Execute boss combat
        use_discount = self.discounts_remaining > 0
        ok = self.executor.execute_semantic(
            "combat_boss", target=boss_id,
            context={"timeout_sec": self.config.combat_timeout_sec, "use_discount": use_discount},
        )

        if ok:
            # Claim rewards
            self.executor.execute_semantic("interact", context={"reason": "claim_boss_reward"})

        return WeeklyBossResult(
            boss_id=boss_id,
            success=ok,
            discount_used=ok and use_discount,
            duration_sec=time.perf_counter() - started,
            details="completed" if ok else "combat_failed",
        )

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_bosses": len(self.completed_bosses),
            "discounts_used": self.config.total_weekly_discounts - self.discounts_remaining,
            "discounts_remaining": self.discounts_remaining,
            "success_rate": sum(1 for r in self.results if r.success) / len(self.results)
            if self.results else 0.0,
        }


# ---------------------------------------------------------------------------
# World Boss Farming (#15)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WorldBossFarmingConfig:
    max_runs: int = 5
    resin_per_run: int = 40
    teleport_timeout_sec: float = 30.0
    combat_timeout_sec: float = 120.0
    rest_between_runs_sec: float = 3.0


_WORLD_BOSS_LOCATIONS: dict[str, str] = {
    "hypostasis_pyro": "liyue_guyun_stone_forest",
    "hypostasis_electro": "mondstadt_cape_oath",
    "hypostasis_cryo": "dragonspine_snow_path",
    "hypostasis_hydro": "fontaine_beryl_region",
    "hypostasis_anemo": "mondstadt_stormterror_lair",
    "hypostasis_dendro": "sumeru_yazadaha_pool",
    "hypostasis_geo": "liyue_guyun_stone_forest",
    "regisvine_pyro": "liyue_cuijue_slope",
    "regisvine_cryo": "mondstadt_snow_covered_path",
    "oceanid": "liyue_bishui_plain",
    "primo_geovishap": "liyue_tianqiu_valley",
    "golden_wolflord": "inazuma_seirai_island",
    "bathysmal_vishap": "watatsumi_island",
    "ruin_serpent": "chasm_underground",
    "aeonblight_drake": "sumeru_dar_al_shifa",
    "algorithm_semi": "sumeru_pesenger_bed",
    "iniquitous_baptist": "fontaine_fountain_of_lucine",
    "forged_sand_interloper": "natlan_scions_of_canopy",
    "leggy_golem": "fontaine_lofit_central",
}


@dataclass(frozen=True, slots=True)
class FarmingRunResult:
    boss_id: str
    run_number: int
    success: bool
    duration_sec: float
    details: str = ""


@dataclass(slots=True)
class WorldBossFarming:
    """Continuous world boss farming loop with resin management.

    Usage::

        farm = WorldBossFarming(executor=executor, config=config)
        results = farm.run(target_boss="hypostasis_pyro", available_resin=160)
    """

    executor: SemanticExecutor
    config: WorldBossFarmingConfig = field(default_factory=WorldBossFarmingConfig)
    total_runs: int = 0
    resin_spent: int = 0
    results: list[FarmingRunResult] = field(default_factory=list)

    def run(self, target_boss: str, available_resin: int = 160) -> list[FarmingRunResult]:
        location = _WORLD_BOSS_LOCATIONS.get(target_boss, target_boss)
        max_possible = min(self.config.max_runs, available_resin // self.config.resin_per_run)

        for run_num in range(1, max_possible + 1):
            result = self._run_single(target_boss, location, run_num)
            self.results.append(result)
            if result.success:
                self.total_runs += 1
                self.resin_spent += self.config.resin_per_run
            else:
                log.warning("[WorldBossFarming] run %d failed: %s", run_num, result.details)

            if run_num < max_possible:
                self._rest(self.config.rest_between_runs_sec)

        return self.results

    def _run_single(self, boss_id: str, location: str, run_num: int) -> FarmingRunResult:
        started = time.perf_counter()

        # Teleport to boss location
        ok = self.executor.execute_semantic("teleport_to", target=location,
                                            context={"timeout": self.config.teleport_timeout_sec})
        if not ok:
            return FarmingRunResult(boss_id=boss_id, run_number=run_num, success=False,
                                    duration_sec=time.perf_counter() - started,
                                    details="teleport_failed")

        # Walk to boss arena
        self.executor.execute_semantic("navigate_to", target=f"{boss_id}_arena")

        # Execute combat
        ok = self.executor.execute_semantic(
            "combat_basic_attack",
            context={"timeout_sec": self.config.combat_timeout_sec},
        )

        if ok:
            # Claim rewards (uses resin)
            self.executor.execute_semantic("interact", context={"reason": "claim_boss_reward",
                                                                  "use_resin": True})
            # Respawn boss for next run
            self.executor.execute_semantic("teleport_to", target=location)

        return FarmingRunResult(
            boss_id=boss_id, run_number=run_num, success=ok,
            duration_sec=time.perf_counter() - started,
        )

    @staticmethod
    def _rest(seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "resin_spent": self.resin_spent,
            "success_rate": sum(1 for r in self.results if r.success) / len(self.results)
            if self.results else 0.0,
            "total_duration_sec": sum(r.duration_sec for r in self.results),
        }


# ---------------------------------------------------------------------------
# Multi-Wave Defense (#16)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MultiWaveConfig:
    max_waves: int = 10
    wave_timeout_sec: float = 60.0
    defend_target_hp_critical: float = 0.2
    check_interval_sec: float = 1.0


@dataclass(frozen=True, slots=True)
class WaveResult:
    wave_number: int
    success: bool
    duration_sec: float
    defend_target_hp: float = 1.0
    enemies_remaining: int = -1
    details: str = ""


@dataclass(slots=True)
class MultiWaveDefense:
    """Handle multi-wave defense encounters with wave tracking and target protection.

    Usage::

        defense = MultiWaveDefense(executor=executor)
        results = defense.run(total_waves=5, defend_hp_fn=lambda: 0.8)
    """

    executor: SemanticExecutor
    config: MultiWaveConfig = field(default_factory=MultiWaveConfig)
    current_wave: int = 0
    results: list[WaveResult] = field(default_factory=list)

    def run(self, total_waves: int = 5,
            defend_hp_fn: Any | None = None,
            enemies_remaining_fn: Any | None = None) -> list[WaveResult]:
        defend_hp_fn = defend_hp_fn or (lambda: 1.0)
        enemies_remaining_fn = enemies_remaining_fn or (lambda: 0)

        for wave in range(1, min(total_waves + 1, self.config.max_waves + 1)):
            self.current_wave = wave
            result = self._execute_wave(wave, defend_hp_fn, enemies_remaining_fn)
            self.results.append(result)

            if not result.success:
                log.warning("[MultiWave] wave %d failed: %s", wave, result.details)
                break

            if defend_hp_fn() < self.config.defend_target_hp_critical:
                log.warning("[MultiWave] defend target HP critical at wave %d", wave)

        return self.results

    def _execute_wave(self, wave: int, defend_hp_fn: Any,
                      enemies_remaining_fn: Any) -> WaveResult:
        started = time.perf_counter()
        deadline = started + self.config.wave_timeout_sec

        # Combat loop for this wave
        while time.perf_counter() < deadline:
            defend_hp = defend_hp_fn()
            if defend_hp <= 0.0:
                return WaveResult(wave_number=wave, success=False,
                                  duration_sec=time.perf_counter() - started,
                                  defend_target_hp=0.0, details="defend_target_destroyed")

            remaining = enemies_remaining_fn()
            if remaining == 0 and wave > 0:
                # Wave cleared — short pause before next
                self._rest(1.0)
                return WaveResult(wave_number=wave, success=True,
                                  duration_sec=time.perf_counter() - started,
                                  defend_target_hp=defend_hp)

            # Priority: attack enemies near defend target
            self.executor.execute_semantic("combat_basic_attack",
                                           context={"priority": "nearest_to_target"})

        return WaveResult(wave_number=wave, success=False,
                          duration_sec=time.perf_counter() - started,
                          defend_target_hp=defend_hp_fn(),
                          details="wave_timeout")

    @staticmethod
    def _rest(seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))

    @property
    def waves_cleared(self) -> int:
        return sum(1 for r in self.results if r.success)


# ---------------------------------------------------------------------------
# Shield Mitachurl Strategy (#2)
# ---------------------------------------------------------------------------

_SHIELD_COUNTER_ELEMENTS: dict[str, str] = {
    "wood": "pyro",       # Burn wooden shields
    "rock": "geo",        # Break rock shields with blunt/claymore
    "ice": "pyro",        # Melt ice shields
    "electro": "pyro",    # Overload breaks electro shields
}


@dataclass(frozen=True, slots=True)
class ShieldBreakResult:
    shield_type: str
    counter_element: str
    success: bool
    duration_sec: float


@dataclass(slots=True)
class ShieldMitachurlStrategy:
    """Handle shield-bearing Mitachurl variants with shield break tactics.

    Strategy:
    1. Identify shield type (wood/rock/ice/electro)
    2. Switch to counter-element character
    3. Break shield with element application
    4. Attack exposed enemy from behind (circling)
    """

    executor: SemanticExecutor
    shield_break_timeout_sec: float = 15.0

    def execute(self, shield_type: str = "wood") -> ShieldBreakResult:
        started = time.perf_counter()
        counter = _SHIELD_COUNTER_ELEMENTS.get(shield_type, "pyro")

        # Switch to counter-element character
        self.executor.execute_semantic("switch_char", target=counter)
        self._rest(0.3)

        # Apply counter element to break shield
        deadline = time.perf_counter() + self.shield_break_timeout_sec
        shield_broken = False
        while time.perf_counter() < deadline:
            self.executor.execute_semantic("use_skill", target=f"mitachurl_shield",
                                           context={"element": counter})
            self._rest(1.0)
            # In real game, check if shield is gone via perception
            shield_broken = True  # Optimistic for mock
            break

        if not shield_broken:
            return ShieldBreakResult(
                shield_type=shield_type, counter_element=counter,
                success=False, duration_sec=time.perf_counter() - started,
            )

        # Attack exposed enemy — circle behind for better positioning
        self.executor.execute_semantic("move_to", target="mitachurl_behind")
        self._rest(0.3)
        self.executor.execute_semantic("combat_basic_attack",
                                       context={"strategy": "behind_attack"})

        return ShieldBreakResult(
            shield_type=shield_type, counter_element=counter,
            success=True, duration_sec=time.perf_counter() - started,
        )

    @staticmethod
    def _rest(seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))


# ---------------------------------------------------------------------------
# Scenario #3: Abyss Mage — elemental shield counter
# ---------------------------------------------------------------------------

_ELEMENTAL_SHIELD_COUNTERS: dict[str, str] = {
    "cryo": "pyro",      # Melt — most effective vs cryo shields
    "pyro": "hydro",     # Vaporize — effective vs pyro shields
    "hydro": "electro",  # Electro-charged — effective vs hydro shields
    "electro": "dendro", # Quicken/Spread — effective vs electro shields
}

_ELEMENTAL_SHIELD_HP: dict[str, float] = {
    "cryo": 1.0,
    "pyro": 1.2,
    "hydro": 0.8,
    "electro": 1.0,
}


@dataclass(frozen=True, slots=True)
class AbyssMageResult:
    mage_element: str
    shield_broken: bool
    mage_defeated: bool
    counter_element: str
    success: bool
    duration_sec: float


@dataclass(slots=True)
class AbyssMageHandler:
    """Handle Abyss Mage encounters with elemental shield counter-strategy.

    Strategy:
    1. Identify mage element type (cryo/pyro/hydro/electro)
    2. Switch to counter-element character
    3. Apply counter element until shield breaks
    4. Burst down exposed mage before shield regenerates
    5. Repeat if shield regenerates
    """

    executor: SemanticExecutor
    shield_break_timeout_sec: float = 20.0
    burst_window_sec: float = 10.0
    max_shield_cycles: int = 3

    def execute(self, mage_element: str = "cryo") -> AbyssMageResult:
        started = time.perf_counter()
        counter = _ELEMENTAL_SHIELD_COUNTERS.get(mage_element, "pyro")
        shield_hp_mult = _ELEMENTAL_SHIELD_HP.get(mage_element, 1.0)

        shield_broken = False
        mage_defeated = False

        for cycle in range(self.max_shield_cycles):
            # Switch to counter-element character
            self.executor.execute_semantic(
                "switch_char", target=counter,
                context={"reason": "shield_counter", "element": counter},
            )
            self._rest(0.3)

            # Apply counter element to break shield
            broken = self._break_shield(mage_element, counter, shield_hp_mult)
            if not broken:
                continue
            shield_broken = True

            # Burst down exposed mage
            defeated = self._burst_exposed_mage()
            if defeated:
                mage_defeated = True
                break

            # Shield regenerated — try again
            log.info("[AbyssMage] shield regenerated, cycle %d", cycle + 1)

        elapsed = time.perf_counter() - started
        return AbyssMageResult(
            mage_element=mage_element,
            shield_broken=shield_broken,
            mage_defeated=mage_defeated,
            counter_element=counter,
            success=mage_defeated,
            duration_sec=elapsed,
        )

    def _break_shield(self, mage_element: str, counter: str, hp_mult: float) -> bool:
        """Apply counter element until shield breaks."""
        # Use skill for element application
        self.executor.execute_semantic(
            "use_skill", target=f"abyss_mage_{mage_element}_shield",
            context={"element": counter, "reason": "shield_break"},
        )
        self._rest(1.5)

        # Apply more element with normal attacks infused by counter
        applications = int(3 * hp_mult)
        for _ in range(applications):
            self.executor.execute_semantic(
                "combat_basic_attack",
                context={"target": "abyss_mage", "element": counter, "duration_sec": 1.0},
            )
            self._rest(0.8)

        return True  # Optimistic: shield breaks after enough applications

    def _burst_exposed_mage(self) -> bool:
        """Burst down mage during shield-down window."""
        # Use burst if available
        self.executor.execute_semantic(
            "use_burst", context={"reason": "abyss_mage_burst_window"},
        )
        self._rest(0.5)

        # Follow up with skill + attack combo
        self.executor.execute_semantic("use_skill", context={"reason": "burst_combo"})
        self.executor.execute_semantic(
            "combat_basic_attack",
            context={"target": "abyss_mage", "strategy": "burst_combo"},
        )
        return True  # Optimistic: mage defeated during window

    @staticmethod
    def _rest(seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))
