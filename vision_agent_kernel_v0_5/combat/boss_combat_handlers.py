"""Boss combat handlers for 6 major weekly bosses.

Implements boss scenarios #4-9 from GENSHIN_COMBAT_SCENARIO_BREAKDOWN.md:
- DvalinHandler (#4): 风魔龙·特瓦林 — multi-phase aerial + platform fight
- ChildeHandler (#5): 公子·达达利亚 — 3-phase elemental switching
- SignoraHandler (#6): 女士·罗莎琳 — dual-environment temperature management
- RaidenShogunHandler (#7): 雷电将军 — high-frequency dodge + burst windows
- ShoukiNoKamiHandler (#8): 正机之神·散兵 — energy ball + construct mechanics
- NarwhalHandler (#9): 吞噬一切的巨鲸 — outside/inside dual-space combat

Each handler is a state machine that tracks boss phases and delegates to
the SemanticExecutor for combat, dodge, and mechanic-specific actions.
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
# Shared result type
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BossCombatResult:
    success: bool
    boss_name: str
    phases_completed: int = 0
    total_phases: int = 1
    deaths: int = 0
    duration_sec: float = 0.0
    details: str = ""


# ---------------------------------------------------------------------------
# #4: Dvalin (Stormterror) — 3-phase aerial + platform
# ---------------------------------------------------------------------------

class DvalinPhase(Enum):
    AERIAL_SHOOTING = "aerial"      # Wind currents, shoot spines
    PLATFORM_MELEE = "platform"     # Attack claws, then head
    FINAL_PHASE = "final"           # Ground cracks + head attack


@dataclass(slots=True)
class DvalinState:
    phase: DvalinPhase = DvalinPhase.AERIAL_SHOOTING
    spines_remaining: int = 2
    claw_hp: float = 1.0
    head_exposed: bool = False
    down_count: int = 0


class DvalinHandler:
    """风魔龙·特瓦林: 3-phase aerial shooting → platform melee → final burst.

    Phase transitions:
    - P1→P2: Both spines destroyed
    - P2→P3: After 2-3 knockdown cycles
    """

    MAX_DOWN_CYCLES: int = 3
    PHASE_TIMEOUT_SEC: float = 300.0

    def __init__(self, executor: SemanticExecutor) -> None:
        self._executor = executor

    def execute(self) -> BossCombatResult:
        started = time.perf_counter()
        state = DvalinState()
        deaths = 0

        # P1: Aerial — shoot spines from wind currents
        while state.spines_remaining > 0:
            elapsed = time.perf_counter() - started
            if elapsed > self.PHASE_TIMEOUT_SEC:
                return BossCombatResult(False, "dvalin", 0, 3, deaths, elapsed, "p1_timeout")

            # Enter wind current and glide
            self._executor.execute_semantic("glide", context={"reason": "dvalin_wind_current"})
            # Aim and shoot at spine
            ok = self._executor.execute_semantic(
                "aimed_shot", target="dvalin_spine",
                context={"reason": "destroy_spine"},
            )
            if ok:
                state.spines_remaining -= 1
                log.info("[Dvalin] spine destroyed (%d remaining)", state.spines_remaining)
            else:
                # Missed — reposition and retry
                self._executor.execute_semantic("dodge", context={"reason": "dvalin_breath"})

        # P2: Platform — attack claws until boss downs
        state.phase = DvalinPhase.PLATFORM_MELEE
        while state.down_count < self.MAX_DOWN_CYCLES:
            elapsed = time.perf_counter() - started
            if elapsed > self.PHASE_TIMEOUT_SEC * 2:
                return BossCombatResult(False, "dvalin", 1, 3, deaths, elapsed, "p2_timeout")

            # Attack claws
            ok = self._executor.execute_semantic(
                "combat_basic_attack",
                context={"duration_sec": 15.0, "target": "dvalin_claw"},
            )
            if ok:
                state.down_count += 1
                state.head_exposed = True
                # Burst window on exposed head
                self._executor.execute_semantic(
                    "combat_boss", target="dvalin",
                    context={"phase": "head_exposed", "timeout_sec": 20.0},
                )
                state.head_exposed = False
                log.info("[Dvalin] knockdown %d/%d", state.down_count, self.MAX_DOWN_CYCLES)
            else:
                # Dodge platform swipe
                self._executor.execute_semantic("dodge", context={"reason": "claw_sweep"})

        # P3: Final — ground cracks + head
        state.phase = DvalinPhase.FINAL_PHASE
        ok = self._executor.execute_semantic(
            "combat_boss", target="dvalin",
            context={"phase": "final", "timeout_sec": 60.0, "dodge_cracks": True},
        )

        elapsed = time.perf_counter() - started
        phases = 3 if ok else 2
        return BossCombatResult(ok, "dvalin", phases, 3, deaths, elapsed)


# ---------------------------------------------------------------------------
# #5: Childe (Tartaglia) — 3-phase elemental
# ---------------------------------------------------------------------------

class ChildePhase(Enum):
    HYDRO = "hydro"          # Water dual blades
    ELECTRO = "electro"      # Lightning spear
    DUAL_ELEMENT = "dual"    # Hydro + Electro combined


@dataclass(slots=True)
class ChildeState:
    phase: ChildePhase = ChildePhase.HYDRO
    is_marked: bool = False  # Water mark = extra damage taken


class ChildeHandler:
    """公子·达达利亚: 3-phase elemental switching fight.

    Phase transitions at ~60% HP (P1→P2) and ~30% HP (P2→P3).
    Each phase change has invulnerability animation.
    """

    PHASE_TIMEOUT_SEC: float = 600.0

    def __init__(self, executor: SemanticExecutor) -> None:
        self._executor = executor

    def execute(self) -> BossCombatResult:
        started = time.perf_counter()
        state = ChildeState()
        deaths = 0

        # P1: Hydro — dodge combos, watch for mark
        state.phase = ChildePhase.HYDRO
        ok = self._executor.execute_semantic(
            "combat_boss", target="childe",
            context={"phase": "hydro", "element": "pyro", "timeout_sec": 120.0},
        )
        if not ok:
            elapsed = time.perf_counter() - started
            return BossCombatResult(False, "childe", 0, 3, deaths, elapsed, "p1_failed")

        # Phase transition (invulnerable — save skills)
        self._executor.execute_semantic("wait", context={"reason": "childe_phase_transition"})

        # P2: Electro — ranged AOE, teleport strikes
        state.phase = ChildePhase.ELECTRO
        ok = self._executor.execute_semantic(
            "combat_boss", target="childe",
            context={"phase": "electro", "element": "cryo", "timeout_sec": 120.0},
        )
        if not ok:
            elapsed = time.perf_counter() - started
            return BossCombatResult(False, "childe", 1, 3, deaths, elapsed, "p2_failed")

        # Phase transition
        self._executor.execute_semantic("wait", context={"reason": "childe_phase_transition"})

        # P3: Dual element — break shield then burst
        state.phase = ChildePhase.DUAL_ELEMENT
        # Break elemental shield first
        self._executor.execute_semantic(
            "use_skill", target="childe_shield",
            context={"reason": "break_dual_shield", "element": "cryo"},
        )
        ok = self._executor.execute_semantic(
            "combat_boss", target="childe",
            context={"phase": "dual", "timeout_sec": 180.0, "dodge_whale": True},
        )

        elapsed = time.perf_counter() - started
        phases = 3 if ok else 2
        return BossCombatResult(ok, "childe", phases, 3, deaths, elapsed)


# ---------------------------------------------------------------------------
# #6: Signora (La Signora) — dual-environment temperature
# ---------------------------------------------------------------------------

class SignoraPhase(Enum):
    CRYO = "cryo"     # Freezing environment
    PYRO = "pyro"     # Scorching environment


class TemperatureGauge(Enum):
    SAFE = "safe"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(slots=True)
class SignoraState:
    phase: SignoraPhase = SignoraPhase.CRYO
    temperature_gauge: float = 0.0  # 0.0-1.0
    devices_remaining: int = 4       # Temperature devices on field


class SignoraHandler:
    """女士·罗莎琳: Dual-environment temperature management fight.

    Unique mechanic: temperature gauge must be managed alongside combat.
    P1: Collect flame hearts to reduce cold; P2: Collect frost seeds to reduce heat.
    Signora destroys devices over time — must use remaining ones wisely.
    """

    TEMP_WARNING: float = 0.60
    TEMP_CRITICAL: float = 0.80
    TEMP_REDUCTION_DEVICE: float = 0.35
    TEMP_REDUCTION_ITEM: float = 0.20
    PHASE_TIMEOUT_SEC: float = 720.0

    def __init__(self, executor: SemanticExecutor) -> None:
        self._executor = executor

    def execute(self) -> BossCombatResult:
        started = time.perf_counter()
        state = SignoraState()
        deaths = 0

        # P1: Cryo environment — collect flame hearts
        state.phase = SignoraPhase.CRYO
        p1_ok = self._fight_cryo_phase(state)
        if not p1_ok:
            elapsed = time.perf_counter() - started
            return BossCombatResult(False, "signora", 0, 2, deaths, elapsed, "p1_failed")

        # Phase transition
        state.phase = SignoraPhase.PYRO
        state.temperature_gauge = 0.0
        state.devices_remaining = max(1, state.devices_remaining - 1)

        # P2: Pyro environment — collect frost seeds
        p2_ok = self._fight_pyro_phase(state)
        elapsed = time.perf_counter() - started
        phases = 2 if p2_ok else 1
        return BossCombatResult(p2_ok, "signora", phases, 2, deaths, elapsed)

    def _fight_cryo_phase(self, state: SignoraState) -> bool:
        """P1: Fight in cold environment, collect flame hearts."""
        for cycle in range(6):
            # Check temperature
            if state.temperature_gauge >= self.TEMP_CRITICAL:
                self._use_device(state, "flame_heart")

            # Attack Signora with pyro
            ok = self._executor.execute_semantic(
                "combat_boss", target="signora",
                context={"phase": "cryo", "element": "pyro", "timeout_sec": 30.0},
            )
            if ok:
                return True  # Boss HP threshold reached

            # Temperature accumulates during combat
            state.temperature_gauge = min(1.0, state.temperature_gauge + 0.15)
            if state.temperature_gauge >= self.TEMP_WARNING:
                self._collect_item(state, "flame_heart")

        return False

    def _fight_pyro_phase(self, state: SignoraState) -> bool:
        """P2: Fight in hot environment, collect frost seeds."""
        for cycle in range(6):
            if state.temperature_gauge >= self.TEMP_CRITICAL:
                self._use_device(state, "frost_seed")

            ok = self._executor.execute_semantic(
                "combat_boss", target="signora",
                context={"phase": "pyro", "element": "hydro", "timeout_sec": 30.0},
            )
            if ok:
                return True

            state.temperature_gauge = min(1.0, state.temperature_gauge + 0.15)
            if state.temperature_gauge >= self.TEMP_WARNING:
                self._collect_item(state, "frost_seed")

        return False

    def _use_device(self, state: SignoraState, item_type: str) -> None:
        if state.devices_remaining > 0:
            self._executor.execute_semantic(
                "interact", target="temperature_device",
                context={"reason": f"collect_{item_type}"},
            )
            state.devices_remaining -= 1
            state.temperature_gauge = max(0.0, state.temperature_gauge - self.TEMP_REDUCTION_DEVICE)

    def _collect_item(self, state: SignoraState, item_type: str) -> None:
        self._executor.execute_semantic(
            "navigate_to", target=item_type,
            context={"reason": "temperature_management"},
        )
        state.temperature_gauge = max(0.0, state.temperature_gauge - self.TEMP_REDUCTION_ITEM)


# ---------------------------------------------------------------------------
# #7: Raiden Shogun — high-frequency dodge + burst windows
# ---------------------------------------------------------------------------

class RaidenPhase(Enum):
    NORMAL = "normal"          # Standard sword combos
    ENHANCED = "enhanced"      # Faster + Musou no Hitokiri
    MUSOU = "musou"            # Final burst with clones


@dataclass(slots=True)
class RaidenState:
    phase: RaidenPhase = RaidenPhase.NORMAL
    burst_saved: bool = True   # Keep burst for iframe


class RaidenShogunHandler:
    """雷电将军: High-frequency attack dodge + burst iframe windows.

    Key mechanic: Save elemental bursts for Musou no Hitokiri iframe dodge.
    P1: Standard combos, dodge after each pattern. P2: Faster attacks + full AOE.
    P3: Clones + mega attack requiring burst iframe.
    """

    MAX_DODGE_FAILS: int = 5
    PHASE_TIMEOUT_SEC: float = 720.0

    def __init__(self, executor: SemanticExecutor) -> None:
        self._executor = executor

    def execute(self) -> BossCombatResult:
        started = time.perf_counter()
        state = RaidenState()
        deaths = 0
        dodge_fails = 0

        # P1: Normal — dodge combos, counter in gaps
        state.phase = RaidenPhase.NORMAL
        for attempt in range(8):
            # Dodge the combo
            dodge_ok = self._executor.execute_semantic(
                "dodge", context={"reason": "raiden_combo", "timing": "post_swing"},
            )
            if not dodge_ok:
                dodge_fails += 1
                if dodge_fails >= self.MAX_DODGE_FAILS:
                    deaths += 1

            # Counter-attack in the gap
            ok = self._executor.execute_semantic(
                "combat_basic_attack",
                context={"duration_sec": 3.0, "target": "raiden_shogun"},
            )
            if ok:
                break  # HP threshold reached, phase transition

        # P2: Enhanced — faster attacks + AOE
        state.phase = RaidenPhase.ENHANCED
        for attempt in range(8):
            # Dodge enhanced AOE
            self._executor.execute_semantic(
                "dodge", context={"reason": "raiden_lightning_storm"},
            )
            ok = self._executor.execute_semantic(
                "combat_boss", target="raiden_shogun",
                context={"phase": "enhanced", "timeout_sec": 30.0},
            )
            if ok:
                break

        # P3: Musou — burst iframe required
        state.phase = RaidenPhase.MUSOU
        # Save burst for Musou no Hitokiri
        state.burst_saved = True
        # Detect Musou wind-up (screen darkens)
        self._executor.execute_semantic(
            "dodge", context={"reason": "musou_wind_up"},
        )
        # Use burst as iframe during Musou
        if state.burst_saved:
            self._executor.execute_semantic(
                "use_burst", context={"reason": "musou_iframe"},
            )
            state.burst_saved = False

        # Final damage phase
        ok = self._executor.execute_semantic(
            "combat_boss", target="raiden_shogun",
            context={"phase": "musou_final", "timeout_sec": 60.0},
        )

        elapsed = time.perf_counter() - started
        phases = 3 if ok else 2
        return BossCombatResult(ok, "raiden_shogun", phases, 3, deaths, elapsed)


# ---------------------------------------------------------------------------
# #8: Shouki no Kami (Scaramouche) — energy ball + construct mechanics
# ---------------------------------------------------------------------------

class ShoukiPhase(Enum):
    ARMOR = "armor"        # Destroy constructs, gather energy
    CORE_EXPOSED = "core"  # Attack core with energy
    FINAL = "final"        # Mega attack + energy blocks


@dataclass(slots=True)
class ShoukiState:
    phase: ShoukiPhase = ShoukiPhase.ARMOR
    energy_collected: int = 0
    towers_destroyed: int = 0
    armor_hp: float = 1.0


class ShoukiNoKamiHandler:
    """正机之神·散兵: Energy ball collection + construct destruction.

    Mechanic loop:
    1. Kill constructs → they drop energy balls
    2. Collect energy balls → gain special attack
    3. Use special attack on boss armor
    4. Repeat until armor breaks
    5. Destroy defense towers when they appear (10s window)
    """

    ENERGY_PER_CONSTRUCT: int = 1
    ENERGY_NEEDED_SPECIAL: int = 3
    TOWER_DESTROY_WINDOW_SEC: float = 10.0
    PHASE_TIMEOUT_SEC: float = 900.0

    def __init__(self, executor: SemanticExecutor) -> None:
        self._executor = executor

    def execute(self) -> BossCombatResult:
        started = time.perf_counter()
        state = ShoukiState()
        deaths = 0

        # P1: Armor — collect energy, break armor
        state.phase = ShoukiPhase.ARMOR
        while state.armor_hp > 0:
            elapsed = time.perf_counter() - started
            if elapsed > self.PHASE_TIMEOUT_SEC:
                return BossCombatResult(
                    False, "shouki_no_kami", 0, 3, deaths, elapsed, "p1_timeout",
                )

            # Kill construct
            ok = self._executor.execute_semantic(
                "combat_basic_attack",
                context={"duration_sec": 5.0, "target": "construct"},
            )
            if ok:
                state.energy_collected += self.ENERGY_PER_CONSTRUCT

            # Check for defense towers
            self._handle_towers(state)

            # Use special attack when enough energy
            if state.energy_collected >= self.ENERGY_NEEDED_SPECIAL:
                special_ok = self._executor.execute_semantic(
                    "use_skill", target="shouki_armor",
                    context={"reason": "energy_attack", "energy": state.energy_collected},
                )
                if special_ok:
                    state.armor_hp -= 0.25
                    state.energy_collected = 0
                    log.info("[Shouki] armor HP: %.0f%%", state.armor_hp * 100)

        # P2: Core exposed — attack with energy
        state.phase = ShoukiPhase.CORE_EXPOSED
        for cycle in range(8):
            # Collect energy
            self._executor.execute_semantic(
                "combat_basic_attack",
                context={"duration_sec": 5.0, "target": "construct"},
            )
            state.energy_collected += self.ENERGY_PER_CONSTRUCT

            # Attack core
            ok = self._executor.execute_semantic(
                "combat_boss", target="shouki_core",
                context={
                    "phase": "core_exposed",
                    "timeout_sec": 30.0,
                    "energy": state.energy_collected,
                },
            )
            if ok:
                break

            # Dodge lasers and missiles
            self._executor.execute_semantic("dodge", context={"reason": "laser_sweep"})
            self._executor.execute_semantic("dodge", context={"reason": "missile_rain"})

        # P3: Final — mega attack + finish
        state.phase = ShoukiPhase.FINAL
        self._executor.execute_semantic(
            "dodge", context={"reason": "mega_attack_windup"},
        )
        ok = self._executor.execute_semantic(
            "combat_boss", target="shouki_core",
            context={"phase": "final", "timeout_sec": 60.0},
        )

        elapsed = time.perf_counter() - started
        phases = 3 if ok else 2
        return BossCombatResult(ok, "shouki_no_kami", phases, 3, deaths, elapsed)

    def _handle_towers(self, state: ShoukiState) -> None:
        """Destroy defense towers before they shield the boss."""
        self._executor.execute_semantic(
            "combat_basic_attack",
            context={"duration_sec": 3.0, "target": "defense_tower", "priority": "high"},
        )
        state.towers_destroyed += 1


# ---------------------------------------------------------------------------
# #9: Narwhal (All-Devouring) — outside/inside dual-space
# ---------------------------------------------------------------------------

class NarwhalPhase(Enum):
    OUTSIDE = "outside"       # Fighting on the ship deck
    INGESTED = "ingested"     # Inside the narwhal
    BERSERK = "berserk"       # Final enraged phase


@dataclass(slots=True)
class NarwhalState:
    phase: NarwhalPhase = NarwhalPhase.OUTSIDE
    cycle_count: int = 0       # Number of outside→inside cycles
    parasite_defeated: int = 0
    core_damage_dealt: int = 0


class NarwhalHandler:
    """吞噬一切的巨鲸: Dual-space outside/inside combat.

    Mechanic loop:
    1. Outside: Attack whale when it surfaces, dodge charges/tail slaps
    2. Whale swallows player → Inside: defeat parasites + attack core
    3. Expelled back outside → whale takes more damage
    4. Repeat 2-3 times until whale HP depleted
    """

    MAX_CYCLES: int = 3
    PHASE_TIMEOUT_SEC: float = 600.0

    def __init__(self, executor: SemanticExecutor) -> None:
        self._executor = executor

    def execute(self) -> BossCombatResult:
        started = time.perf_counter()
        state = NarwhalState()
        deaths = 0

        while state.cycle_count < self.MAX_CYCLES:
            elapsed = time.perf_counter() - started
            if elapsed > self.PHASE_TIMEOUT_SEC:
                return BossCombatResult(
                    False, "narwhal", state.cycle_count * 2, 6,
                    deaths, elapsed, "timeout",
                )

            # Outside phase: attack whale during surface windows
            state.phase = NarwhalPhase.OUTSIDE
            outside_ok = self._executor.execute_semantic(
                "combat_boss", target="narwhal",
                context={"phase": "outside", "timeout_sec": 60.0},
            )

            # Whale swallows player — enter inside phase
            state.phase = NarwhalPhase.INGESTED
            self._executor.execute_semantic(
                "navigate_to", target="parasite_cluster",
                context={"reason": "inside_narwhal"},
            )
            # Defeat parasites
            parasite_ok = self._executor.execute_semantic(
                "combat_basic_attack",
                context={"duration_sec": 10.0, "target": "parasite"},
            )
            if parasite_ok:
                state.parasite_defeated += 1

            # Attack core
            core_ok = self._executor.execute_semantic(
                "combat_boss", target="narwhal_core",
                context={"phase": "inside_core", "timeout_sec": 30.0},
            )
            if core_ok:
                state.core_damage_dealt += 1

            state.cycle_count += 1
            log.info(
                "[Narwhal] cycle %d/%d complete", state.cycle_count, self.MAX_CYCLES,
            )

            # Check if whale is defeated (outside combat succeeded = whale surfacing less)
            if outside_ok and state.cycle_count >= 2:
                # Final phase
                state.phase = NarwhalPhase.BERSERK
                break

        # Final outside burst
        ok = self._executor.execute_semantic(
            "combat_boss", target="narwhal",
            context={"phase": "final_berserk", "timeout_sec": 60.0},
        )

        elapsed = time.perf_counter() - started
        phases = 6 if ok else state.cycle_count * 2
        return BossCombatResult(ok, "narwhal", phases, 6, deaths, elapsed)
