"""Environmental combat handlers: Dragonspine sheer cold & Inazuma thunderstorm.

Implements combat scenarios #12 and #13 from GENSHIN_COMBAT_SCENARIO_BREAKDOWN.md:
- DragonspineSheerColdHandler: C-50 ~ C-53 (严寒条监控, 热源导航, 战斗-取暖决策, 冰系集火)
- InazumaThunderstormHandler: C-54 ~ C-57 (落雷预警, 双重威胁闪避, 感电识别, 雷系集火)

Both handlers manage the interplay between environmental hazards and combat,
prioritizing survival (environment) over DPS when hazard gauges reach dangerous levels.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

log = logging.getLogger(__name__)


class SemanticExecutor(Protocol):
    def execute_semantic(
        self, action: str, target: str = "", context: dict[str, Any] | None = None,
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Dragonspine Sheer Cold (#12)
# ---------------------------------------------------------------------------

class SheerColdLevel(Enum):
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class WarmthSource:
    source_id: str
    source_type: str  # "bonfire", "statue", "scarlet_quartz", "warming_seelie"
    position_tag: str
    restoration_rate: float = 0.3  # gauge reduction per second near source


_WARMTH_SOURCES: tuple[WarmthSource, ...] = (
    WarmthSource("bonfire_camp_1", "bonfire", "dragonspine_camp_1", 0.4),
    WarmthSource("bonfire_camp_2", "bonfire", "dragonspine_camp_2", 0.4),
    WarmthSource("bonfire_cave_1", "bonfire", "dragonspine_cave_1", 0.35),
    WarmthSource("statue_of_seven_ds", "statue", "dragonspine_statue", 0.5),
    WarmthSource("scarlet_quartz", "scarlet_quartz", "nearby", 0.6),
    WarmthSource("warming_seelie", "warming_seelie", "following", 0.25),
)


@dataclass(frozen=True, slots=True)
class DragonspineCombatStep:
    step_id: str
    action: str
    reason: str
    cold_threshold: float  # gauge level that triggers this step


@dataclass(slots=True)
class DragonspineCombatResult:
    success: bool
    enemies_defeated: int = 0
    total_cold_events: int = 0
    warmth_used: int = 0
    duration_sec: float = 0.0
    details: str = ""


class DragonspineSheerColdHandler:
    """Handle combat in Dragonspine with sheer cold gauge management.

    Dual-priority system:
    - When cold gauge < WARNING (50%): prioritize combat
    - When cold gauge >= WARNING: prioritize finding warmth
    - When cold gauge >= CRITICAL (85%): emergency evacuation, ignore combat
    """

    GAUGE_SAFE: float = 0.30
    GAUGE_WARNING: float = 0.50
    GAUGE_DANGER: float = 0.70
    GAUGE_CRITICAL: float = 0.85
    COLD_ACCUMULATION_RATE: float = 0.05   # per second base
    BLIZZARD_MULTIPLIER: float = 2.0
    COMBAT_MULTIPLIER: float = 1.5         # ice enemy hits add cold

    def __init__(
        self,
        executor: SemanticExecutor,
        max_combat_duration_sec: float = 360.0,
    ) -> None:
        self._executor = executor
        self._max_duration = max_combat_duration_sec

    def execute(
        self,
        *,
        initial_gauge: float = 0.0,
        is_blizzard: bool = False,
        enemy_count: int = 3,
        has_fire_character: bool = True,
        has_warming_bottle: bool = False,
    ) -> DragonspineCombatResult:
        """Run the Dragonspine combat encounter with cold management."""
        started = time.perf_counter()
        gauge = initial_gauge
        enemies_left = enemy_count
        cold_events = 0
        warmth_used = 0
        rate = self.COLD_ACCUMULATION_RATE
        if is_blizzard:
            rate *= self.BLIZZARD_MULTIPLIER

        log.info(
            "[Dragonspine] starting combat: gauge=%.0f%% blizzard=%s enemies=%d fire=%s",
            gauge * 100, is_blizzard, enemy_count, has_fire_character,
        )

        while enemies_left > 0:
            elapsed = time.perf_counter() - started
            if elapsed > self._max_duration:
                return DragonspineCombatResult(
                    success=False, enemies_defeated=enemy_count - enemies_left,
                    total_cold_events=cold_events, warmth_used=warmth_used,
                    duration_sec=elapsed, details="timeout",
                )

            # 1. Check cold gauge level
            cold_level = self._classify_gauge(gauge)

            # 2. Critical: emergency warmth, no combat
            if cold_level == SheerColdLevel.CRITICAL:
                cold_events += 1
                warmth_used += 1
                ok = self._seek_warmth(gauge, has_fire_character, has_warming_bottle)
                gauge = max(0.0, gauge - 0.4) if ok else gauge
                log.warning("[Dragonspine] CRITICAL cold (%.0f%%), seeking warmth", gauge * 100)
                continue

            # 3. Danger: combat with warm-up pauses
            if cold_level in (SheerColdLevel.DANGER, SheerColdLevel.WARNING):
                cold_events += 1
                # Quick warmth top-up before resuming
                self._seek_warmth(gauge, has_fire_character, has_warming_bottle)
                warmth_used += 1
                gauge = max(0.0, gauge - 0.2)

            # 4. Prioritize ice-element ranged enemies (reduce cold accumulation)
            ok = self._executor.execute_semantic(
                "combat_basic_attack",
                context={
                    "duration_sec": 8.0,
                    "priority_target": "ice_ranged" if enemies_left > 1 else "any",
                },
            )
            if ok:
                enemies_left -= 1
                gauge += 5.0 * self.COLD_ACCUMULATION_RATE * self.COMBAT_MULTIPLIER
                log.info(
                    "[Dragonspine] enemy defeated (%d remaining), gauge=%.0f%%",
                    enemies_left, gauge * 100,
                )
            else:
                # Combat failed — likely taking too much damage, retreat
                gauge += 3.0 * rate * self.COMBAT_MULTIPLIER

            # 5. Passive cold accumulation
            gauge += rate * 2.0  # ~2 seconds per combat cycle
            gauge = min(1.0, gauge)

        elapsed = time.perf_counter() - started
        return DragonspineCombatResult(
            success=True, enemies_defeated=enemy_count,
            total_cold_events=cold_events, warmth_used=warmth_used,
            duration_sec=elapsed,
        )

    def _classify_gauge(self, gauge: float) -> SheerColdLevel:
        if gauge >= self.GAUGE_CRITICAL:
            return SheerColdLevel.CRITICAL
        if gauge >= self.GAUGE_DANGER:
            return SheerColdLevel.DANGER
        if gauge >= self.GAUGE_WARNING:
            return SheerColdLevel.WARNING
        return SheerColdLevel.SAFE

    def _seek_warmth(
        self,
        gauge: float,
        has_fire_character: bool,
        has_warming_bottle: bool,
    ) -> bool:
        """Navigate to warmth source or use fire skill."""
        # Priority 1: Use fire character's skill (self-warmth)
        if has_fire_character:
            ok = self._executor.execute_semantic(
                "use_skill", target="self",
                context={"reason": "sheer_cold_warmth"},
            )
            if ok:
                return True

        # Priority 2: Navigate to nearest bonfire/statue
        ok = self._executor.execute_semantic(
            "navigate_to", target="nearest_warmth_source",
            context={"reason": "sheer_cold_evacuate", "urgency": "high"},
        )
        if ok:
            return True

        # Priority 3: Use warming bottle
        if has_warming_bottle:
            return self._executor.execute_semantic(
                "use_item", target="warming_bottle",
                context={"reason": "sheer_cold_emergency"},
            )

        return False


# ---------------------------------------------------------------------------
# Inazuma Thunderstorm (#13)
# ---------------------------------------------------------------------------

class ThunderstormLevel(Enum):
    CLEAR = "clear"           # No lightning
    ACTIVE = "active"         # Periodic lightning
    INTENSE = "intense"       # Frequent lightning
    SUPERSTORM = "superstorm"  # Constant lightning + electro-charged ground


@dataclass(frozen=True, slots=True)
class LightningStrike:
    """Represents a predicted lightning strike."""
    strike_id: int
    predicted_position: str    # "near", "far", "on_player"
    warning_time_ms: int       # Time until impact
    aoe_radius_m: float = 3.0
    damage_type: str = "electro"


@dataclass(frozen=True, slots=True)
class InazumaCombatStep:
    step_id: str
    action: str
    reason: str
    requires_dodge: bool


@dataclass(slots=True)
class InazumaCombatResult:
    success: bool
    enemies_defeated: int = 0
    lightning_dodged: int = 0
    lightning_hits: int = 0
    electro_charged_events: int = 0
    duration_sec: float = 0.0
    details: str = ""


class InazumaThunderstormHandler:
    """Handle combat in Inazuma thunderstorm zones.

    Dual-threat management:
    - Monitor ground warning circles for incoming lightning
    - Fight electro-type enemies while dodging environmental lightning
    - Avoid electro-charged status (don't stay wet during storms)
    - Priority: dodge lightning > attack enemies > position optimally
    """

    LIGHTNING_INTERVAL_BASE_SEC: float = 7.0   # Average time between strikes
    LIGHTNING_WARNING_SEC: float = 1.0         # Warning circle visible time
    LIGHTNING_DAMAGE_RATIO: float = 0.35       # HP% lost per hit
    ELECTRO_CHARGED_DPS: float = 0.02          # HP% per second while wet+electro

    def __init__(
        self,
        executor: SemanticExecutor,
        max_combat_duration_sec: float = 360.0,
    ) -> None:
        self._executor = executor
        self._max_duration = max_combat_duration_sec
        self._strike_counter = 0

    def execute(
        self,
        *,
        storm_intensity: ThunderstormLevel = ThunderstormLevel.ACTIVE,
        enemy_count: int = 3,
        is_raining: bool = True,
        has_cryo_character: bool = True,
        has_pyro_character: bool = True,
    ) -> InazumaCombatResult:
        """Run the Inazuma thunderstorm combat encounter."""
        started = time.perf_counter()
        enemies_left = enemy_count
        dodged = 0
        hits = 0
        electro_events = 0
        is_wet = is_raining  # Raining = wet status

        log.info(
            "[InazumaStorm] starting: storm=%s enemies=%d rain=%s",
            storm_intensity.value, enemy_count, is_raining,
        )

        while enemies_left > 0:
            elapsed = time.perf_counter() - started
            if elapsed > self._max_duration:
                return InazumaCombatResult(
                    success=False, enemies_defeated=enemy_count - enemies_left,
                    lightning_dodged=dodged, lightning_hits=hits,
                    electro_charged_events=electro_events,
                    duration_sec=elapsed, details="timeout",
                )

            # 1. Check for incoming lightning
            lightning_due = self._check_lightning(storm_intensity, elapsed)
            if lightning_due:
                self._strike_counter += 1
                # Dodge lightning (priority over combat)
                dodge_ok = self._dodge_lightning()
                if dodge_ok:
                    dodged += 1
                else:
                    hits += 1
                    log.warning("[InazumaStorm] lightning hit! (%d hits total)", hits)
                    if hits >= 3:
                        # Too many hits, retreat
                        return InazumaCombatResult(
                            success=False, enemies_defeated=enemy_count - enemies_left,
                            lightning_dodged=dodged, lightning_hits=hits,
                            electro_charged_events=electro_events,
                            duration_sec=time.perf_counter() - started,
                            details="lightning_fatal",
                        )

            # 2. Manage electro-charged from rain
            if is_wet and storm_intensity.value in ("active", "intense", "superstorm"):
                # Wet + electro environment = periodic damage
                if self._strike_counter % 3 == 0:
                    electro_events += 1
                    # Use pyro to dry, or just accept damage
                    if has_pyro_character:
                        self._executor.execute_semantic(
                            "use_skill", target="self",
                            context={"reason": "remove_wet_status"},
                        )

            # 3. Attack enemies (with awareness of lightning timing)
            # Prioritize electro-ranged enemies to reduce pressure
            ok = self._executor.execute_semantic(
                "combat_basic_attack",
                context={
                    "duration_sec": 5.0,
                    "priority_target": "electro_ranged" if enemies_left > 1 else "any",
                    "dodge_ready": True,  # Signal to keep dodge ready
                },
            )
            if ok:
                enemies_left -= 1
                log.info(
                    "[InazumaStorm] enemy defeated (%d remaining)", enemies_left,
                )

        elapsed = time.perf_counter() - started
        return InazumaCombatResult(
            success=True, enemies_defeated=enemy_count,
            lightning_dodged=dodged, lightning_hits=hits,
            electro_charged_events=electro_events,
            duration_sec=elapsed,
        )

    def _check_lightning(self, intensity: ThunderstormLevel, elapsed: float) -> bool:
        """Determine if a lightning strike is due based on storm intensity."""
        intervals: dict[str, float] = {
            "clear": 999.0,
            "active": 7.0,
            "intense": 4.0,
            "superstorm": 2.0,
        }
        interval = intervals.get(intensity.value, 7.0)
        if interval >= 999.0:
            return False
        # Simplified: lightning strikes every interval seconds
        cycle = elapsed % interval
        return cycle < 0.5  # Within 0.5s of strike time

    def _dodge_lightning(self) -> bool:
        """Execute a dodge to avoid incoming lightning strike."""
        return self._executor.execute_semantic(
            "dodge",
            context={"reason": "lightning_dodge", "direction": "away_from_warning_circle"},
        )
