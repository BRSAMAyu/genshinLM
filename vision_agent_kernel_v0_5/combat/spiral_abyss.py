"""Combat aiming system and Spiral Abyss automation.

Covers:
- C-06: Bow aiming mode (R key hold, weak point targeting)
- C-25: Spiral Abyss team configuration (2 teams of 4)
- C-26: Abyss room enemy identification (element shields, weaknesses)
- C-27: Abyss blessing selection (optimal buff for team)
- C-28: Spiral Abyss auto-challenge (3 chambers per floor)

Integrates with:
- combat/genshin_combat_planner.py for playbook generation
- combat/team_capability.py for team analysis
- combat/combat_survival.py for survival decisions
- combat/genshin_element_reactions.py for elemental counters
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Aiming system (C-06)
# ---------------------------------------------------------------------------

class WeakPointType(str, Enum):
    """Types of weak points on enemies."""
    HEAD = "head"              # Most humanoid enemies
    CORE = "core"              # Slimes, specters
    WEAK_SPOT = "weak_spot"   # Ruin guards, specific bosses
    EYE = "eye"                # Eye of the storm type enemies
    NONE = "none"


@dataclass(slots=True)
class AimTarget:
    """Detected aim target with weak point info."""
    position: tuple[int, int]   # Pixel coordinates
    weak_point: WeakPointType
    confidence: float = 0.0
    element_shield: str = ""     # Element if target has shield


@dataclass(slots=True)
class AimState:
    """Current aiming state."""
    is_aiming: bool = False
    charge_level: float = 0.0      # 0.0-1.0, charged shot
    target: AimTarget | None = None
    should_release: bool = False


@dataclass(slots=True)
class AimDecision:
    """Output from aim controller."""
    action: str   # "aim", "charge", "release", "move_to_target", "cancel"
    target_pos: tuple[int, int] = (0, 0)
    charge_ms: int = 0
    reason: str = ""


class BowAimController:
    """Controls bow aiming mode for charged shots and weak point hits (C-06).

    Manages R-key hold for aiming, target selection, and shot release timing.
    Charged shots apply elemental damage — critical for shield breaking.
    """

    def __init__(self, charge_time_ms: int = 1500) -> None:
        self._state = AimState()
        self._charge_time_ms = charge_time_ms

    @property
    def state(self) -> AimState:
        return self._state

    def start_aiming(self) -> AimDecision:
        """Enter aiming mode (hold R)."""
        self._state.is_aiming = True
        self._state.charge_level = 0.0
        return AimDecision(action="aim", reason="enter_aiming_mode")

    def update(self, target: AimTarget | None, charge_ms: int,
               target_moving: bool = False) -> AimDecision:
        """Evaluate aiming state and return action decision."""
        self._state.target = target

        if not self._state.is_aiming:
            return AimDecision(action="aim", reason="not_aiming")

        if target is None:
            return AimDecision(action="cancel", reason="no_target")

        self._state.charge_level = min(charge_ms / self._charge_time_ms, 1.0)

        # Wait for full charge for elemental shot
        if self._state.charge_level < 1.0:
            return AimDecision(
                action="charge",
                target_pos=target.position,
                charge_ms=self._charge_time_ms - charge_ms,
                reason=f"charging_{self._state.charge_level:.0%}",
            )

        # Fully charged — release if target is in crosshair
        if target_moving and target.confidence < 0.7:
            return AimDecision(
                action="charge",
                target_pos=target.position,
                reason="waiting_for_target_to_stabilize",
            )

        self._state.should_release = True
        return AimDecision(
            action="release",
            target_pos=target.position,
            reason=f"release_charged_shot_{target.weak_point.value}",
        )

    def cancel_aim(self) -> AimDecision:
        """Cancel aiming mode."""
        self._state.is_aiming = False
        self._state.charge_level = 0.0
        self._state.target = None
        return AimDecision(action="cancel", reason="exit_aiming")


# ---------------------------------------------------------------------------
# Spiral Abyss (C-25~C-28)
# ---------------------------------------------------------------------------

class AbyssTeamRole(str, Enum):
    """Roles in an Abyss team."""
    MAIN_DPS = "main_dps"
    SUB_DPS = "sub_dps"
    SUPPORT = "support"
    HEALER = "healer"
    SHIELD = "shield"


class ChamberStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class AbyssCharacter:
    """A character in an Abyss team."""
    name: str
    element: str
    role: AbyssTeamRole
    level: int = 80
    is_built: bool = True


@dataclass(slots=True)
class AbyssTeam:
    """One half of a Spiral Abyss party (4 characters)."""
    team_id: int                # 1 or 2
    characters: list[AbyssCharacter] = field(default_factory=list)
    recommended_elements: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.characters) == 4

    @property
    def elements(self) -> list[str]:
        return [c.element for c in self.characters]

    @property
    def has_healer(self) -> bool:
        return any(c.role == AbyssTeamRole.HEALER for c in self.characters)

    @property
    def has_shield(self) -> bool:
        return any(c.role == AbyssTeamRole.SHIELD for c in self.characters)

    @property
    def dps_element(self) -> str:
        for c in self.characters:
            if c.role == AbyssTeamRole.MAIN_DPS:
                return c.element
        return "anemo"


@dataclass(slots=True)
class AbyssRoom:
    """Enemy composition in an Abyss chamber."""
    room_id: int
    enemies: list[str] = field(default_factory=list)
    element_shields: list[str] = field(default_factory=list)
    recommended_elements: list[str] = field(default_factory=list)
    enemy_count: int = 0


@dataclass(slots=True)
class AbyssChamber:
    """A single chamber in Spiral Abyss (3 per floor)."""
    chamber_id: int              # 1, 2, or 3
    first_half: AbyssRoom = field(default_factory=lambda: AbyssRoom(room_id=1))
    second_half: AbyssRoom = field(default_factory=lambda: AbyssRoom(room_id=2))
    status: ChamberStatus = ChamberStatus.PENDING
    stars_earned: int = 0        # 0-3

    @property
    def is_complete(self) -> bool:
        return self.status == ChamberStatus.COMPLETED


@dataclass(slots=True)
class AbyssBlessing:
    """A selectable Abyss blessing/card."""
    blessing_id: str
    name: str
    description: str = ""
    buff_type: str = ""          # "atk", "crit", "elemental", "defense", "heal"
    element_affinity: str = ""   # Element this blessing favors

    def synergy_score(self, team_elements: list[str]) -> float:
        """Calculate how well this blessing synergizes with the team."""
        base = 1.0
        if self.element_affinity and self.element_affinity in team_elements:
            base += 2.0
        if self.buff_type == "atk":
            base += 0.5
        if self.buff_type == "crit":
            base += 0.8
        return base


class SpiralAbyssTeamBuilder:
    """Builds optimal Abyss teams from available characters (C-25).

    Ensures both teams have DPS, support, and healing coverage.
    Matches elements to chamber requirements.
    """

    def build_teams(self, available: list[AbyssCharacter],
                    chambers: list[AbyssChamber] | None = None,
                    ) -> tuple[AbyssTeam, AbyssTeam] | None:
        """Build two teams from available characters.

        Returns None if insufficient characters (need at least 8).
        """
        built = [c for c in available if c.is_built]
        if len(built) < 8:
            log.warning("Need 8 built characters, have %d", len(built))
            return None

        # Separate by role
        dps_chars = [c for c in built if c.role == AbyssTeamRole.MAIN_DPS]
        support_chars = [c for c in built if c.role in (
            AbyssTeamRole.SUPPORT, AbyssTeamRole.SUB_DPS,
        )]
        sustain_chars = [c for c in built if c.role in (
            AbyssTeamRole.HEALER, AbyssTeamRole.SHIELD,
        )]

        if len(dps_chars) < 2:
            log.warning("Need 2 DPS characters, have %d", len(dps_chars))
            return None

        # Assign 1 DPS to each team
        team1_chars: list[AbyssCharacter] = [dps_chars[0]]
        team2_chars: list[AbyssCharacter] = [dps_chars[1]]

        # Distribute sustain (1 per team minimum)
        for team_chars in [team1_chars, team2_chars]:
            if sustain_chars:
                team_chars.append(sustain_chars.pop(0))

        # Fill remaining slots with supports
        all_remaining = support_chars + sustain_chars
        for i, char in enumerate(all_remaining):
            if len(team1_chars) < 4:
                team1_chars.append(char)
            elif len(team2_chars) < 4:
                team2_chars.append(char)

        # Pad if needed
        while len(team1_chars) < 4:
            team1_chars.append(built[len(team1_chars) % len(built)])
        while len(team2_chars) < 4:
            team2_chars.append(built[(len(team1_chars) + len(team2_chars)) % len(built)])

        team1 = AbyssTeam(
            team_id=1,
            characters=team1_chars[:4],
            recommended_elements=self._get_recommended_elements(chambers, 1),
        )
        team2 = AbyssTeam(
            team_id=2,
            characters=team2_chars[:4],
            recommended_elements=self._get_recommended_elements(chambers, 2),
        )

        return team1, team2

    def _get_recommended_elements(self, chambers: list[AbyssChamber] | None,
                                  half: int) -> list[str]:
        """Get recommended elements for a team based on chamber data."""
        if not chambers:
            return []
        elements: set[str] = set()
        for chamber in chambers:
            room = chamber.first_half if half == 1 else chamber.second_half
            elements.update(room.recommended_elements)
        return list(elements)


class SpiralAbyssRoomAnalyzer:
    """Analyzes Abyss chamber enemies and identifies weaknesses (C-26)."""

    def __init__(self) -> None:
        self._reaction_table: GenshinReactionTable | None = None

    def _get_table(self) -> GenshinReactionTable:
        if self._reaction_table is None:
            from combat.genshin_element_reactions import GenshinReactionTable
            self._reaction_table = GenshinReactionTable()
        return self._reaction_table

    def analyze_room(self, room: AbyssRoom) -> dict[str, str]:
        """Analyze a room's enemy composition and return strategy recommendations."""
        recommendations: dict[str, str] = {}

        if room.element_shields:
            counter_elements = self._get_counter_elements(room.element_shields)
            recommendations["shield_counters"] = ", ".join(counter_elements)

        if room.enemy_count > 5:
            recommendations["tactics"] = "aoe_focus"
        elif room.enemy_count <= 2:
            recommendations["tactics"] = "single_target_burst"
        else:
            recommendations["tactics"] = "balanced"

        return recommendations

    def _get_counter_elements(self, shields: list[str]) -> list[str]:
        """Get counter elements for shield types."""
        counters: list[str] = []
        table = self._get_table()
        for shield in shields:
            try:
                counter = table.get_shield_counter(shield)
                if counter and counter not in counters:
                    counters.append(counter)
            except (KeyError, ValueError):
                counters.append("pyro")  # Default most versatile
        return counters if counters else ["pyro"]


class SpiralAbyssBlessingSelector:
    """Selects optimal Abyss blessings for the team (C-27)."""

    def select_blessing(self, blessings: list[AbyssBlessing],
                        team1: AbyssTeam, team2: AbyssTeam) -> AbyssBlessing | None:
        """Select the blessing with highest synergy across both teams."""
        if not blessings:
            return None

        all_elements = team1.elements + team2.elements
        scored = [(b, b.synergy_score(all_elements)) for b in blessings]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]


@dataclass(slots=True)
class AbyssFloorState:
    """Tracks progress through a single Abyss floor (3 chambers)."""
    floor_number: int
    chambers: list[AbyssChamber] = field(default_factory=list)
    team1: AbyssTeam | None = None
    team2: AbyssTeam | None = None
    selected_blessing: AbyssBlessing | None = None
    total_stars: int = 0

    @property
    def current_chamber(self) -> AbyssChamber | None:
        for c in self.chambers:
            if c.status in (ChamberStatus.PENDING, ChamberStatus.IN_PROGRESS):
                return c
        return None

    @property
    def is_complete(self) -> bool:
        return all(c.is_complete for c in self.chambers)

    @property
    def max_possible_stars(self) -> int:
        return len(self.chambers) * 3


class SpiralAbyssRunner:
    """Orchestrates a full Spiral Abyss floor run (C-28).

    Coordinates team building, room analysis, blessing selection,
    and chamber-by-chamber execution.
    """

    def __init__(self) -> None:
        self._team_builder = SpiralAbyssTeamBuilder()
        self._room_analyzer = SpiralAbyssRoomAnalyzer()
        self._blessing_selector = SpiralAbyssBlessingSelector()

    def prepare_floor(self, floor_number: int,
                      available_chars: list[AbyssCharacter],
                      chambers: list[AbyssChamber],
                      blessings: list[AbyssBlessing] | None = None,
                      ) -> AbyssFloorState:
        """Prepare a floor run: build teams, analyze rooms, select blessing."""
        teams = self._team_builder.build_teams(available_chars, chambers)
        if teams is None:
            return AbyssFloorState(floor_number=floor_number, chambers=chambers)

        team1, team2 = teams

        # Analyze all rooms and store recommendations
        for chamber in chambers:
            rec1 = self._room_analyzer.analyze_room(chamber.first_half)
            rec2 = self._room_analyzer.analyze_room(chamber.second_half)
            if rec1.get("shield_counters"):
                team1.recommended_elements.extend(
                    e.strip() for e in rec1["shield_counters"].split(",")
                )
            if rec2.get("shield_counters"):
                team2.recommended_elements.extend(
                    e.strip() for e in rec2["shield_counters"].split(",")
                )

        # Select blessing
        blessing = None
        if blessings:
            blessing = self._blessing_selector.select_blessing(blessings, team1, team2)

        return AbyssFloorState(
            floor_number=floor_number,
            chambers=chambers,
            team1=team1,
            team2=team2,
            selected_blessing=blessing,
        )

    def advance_chamber(self, state: AbyssFloorState,
                        stars: int = 3) -> ChamberStatus:
        """Advance to next chamber after completing current one."""
        current = state.current_chamber
        if current is None:
            return ChamberStatus.COMPLETED

        if current.status == ChamberStatus.FAILED:
            return ChamberStatus.FAILED

        current.status = ChamberStatus.COMPLETED
        current.stars_earned = min(stars, 3)
        state.total_stars += current.stars_earned

        return state.current_chamber.status if state.current_chamber else ChamberStatus.COMPLETED

    def fail_chamber(self, state: AbyssFloorState) -> ChamberStatus:
        """Mark current chamber as failed."""
        current = state.current_chamber
        if current is None:
            return ChamberStatus.COMPLETED

        current.status = ChamberStatus.FAILED
        return ChamberStatus.FAILED


# ---------------------------------------------------------------------------
# S-30: Spiral Abyss time pressure management
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AbyssTimePressure:
    """Time pressure analysis for Abyss chambers."""
    chamber_id: int
    time_limit_sec: float = 180.0      # 3 min per chamber
    time_remaining_sec: float = 180.0
    is_under_pressure: bool = False
    pressure_level: str = "none"       # "none", "low", "medium", "high", "critical"

    @property
    def elapsed_pct(self) -> float:
        return ((self.time_limit_sec - self.time_remaining_sec) / self.time_limit_sec) * 100.0

    @property
    def should_rush(self) -> bool:
        return self.pressure_level in ("high", "critical")


@dataclass(slots=True)
class AbyssTimeStrategy:
    """Strategy recommendation based on time pressure."""
    recommended_dps_burst: bool
    recommended_rotation: str
    recommended_ult_timing: str
    emergency_actions: list[str] = field(default_factory=list)
    reasoning: str = ""


class AbyssTimePressureManager:
    """Manages time pressure in Spiral Abyss chambers (S-30).

    Provides real-time time pressure analysis and strategic recommendations
    to optimize DPS during time-critical chambers.
    """

    # Time thresholds (seconds)
    FULL_TIME = 180.0      # Full time
    LOW_PRESSURE = 120.0   # > 120 sec remaining = low pressure
    MEDIUM_PRESSURE = 90.0  # 90-120 sec = medium pressure
    HIGH_PRESSURE = 60.0    # 60-90 sec = high pressure
    CRITICAL_PRESSURE = 30.0  # < 30 sec = critical pressure

    def analyze_time_pressure(
        self,
        chamber_id: int,
        elapsed_sec: float,
        enemy_health_pct: float,
    ) -> AbyssTimePressure:
        """Analyze time pressure for a chamber.

        Args:
            chamber_id: Chamber number (1-3)
            elapsed_sec: Time elapsed in chamber
            enemy_health_pct: Remaining enemy health percentage

        Returns:
            AbyssTimePressure with pressure analysis
        """
        time_remaining = max(0.0, self.FULL_TIME - elapsed_sec)
        elapsed_pct = (elapsed_sec / self.FULL_TIME) * 100.0

        # Determine pressure level
        pressure_level = "none"
        is_under_pressure = False

        if time_remaining < self.CRITICAL_PRESSURE:
            pressure_level = "critical"
            is_under_pressure = True
        elif time_remaining < self.HIGH_PRESSURE:
            pressure_level = "high"
            is_under_pressure = True
        elif time_remaining < self.MEDIUM_PRESSURE:
            pressure_level = "medium"
            is_under_pressure = True
        elif time_remaining < self.LOW_PRESSURE:
            pressure_level = "low"

        return AbyssTimePressure(
            chamber_id=chamber_id,
            time_limit_sec=self.FULL_TIME,
            time_remaining_sec=time_remaining,
            is_under_pressure=is_under_pressure,
            pressure_level=pressure_level,
        )

    def get_strategy(
        self,
        pressure: AbyssTimePressure,
        team_elements: list[str],
    ) -> AbyssTimeStrategy:
        """Get strategic recommendations based on time pressure.

        Args:
            pressure: Current time pressure analysis
            team_elements: Team element composition

        Returns:
            AbyssTimeStrategy with recommendations
        """
        if pressure.pressure_level == "critical":
            return AbyssTimeStrategy(
                recommended_dps_burst=True,
                recommended_rotation="burst_all",
                recommended_ult_timing="use_all_ults_immediately",
                emergency_actions=[
                    "Switch to main DPS",
                    "Use all burst abilities",
                    "Focus fire on lowest health enemy",
                    "Use food if available",
                ],
                reasoning="Critical time pressure - all resources now",
            )

        if pressure.pressure_level == "high":
            return AbyssTimeStrategy(
                recommended_dps_burst=True,
                recommended_rotation="fast_rotation",
                recommended_ult_timing="save_ults_for_burst_window",
                emergency_actions=[
                    "Optimize rotation speed",
                    "Switch characters quickly",
                    "Use reactions for quick damage",
                ],
                reasoning="High pressure - maintain DPS burst",
            )

        if pressure.pressure_level == "medium":
            return AbyssTimeStrategy(
                recommended_dps_burst=False,
                recommended_rotation="standard_rotation",
                recommended_ult_timing="normal_ult_timing",
                emergency_actions=[
                    "Monitor time closely",
                    "Prepare for burst if needed",
                ],
                reasoning="Medium pressure - stay on standard rotation",
            )

        return AbyssTimeStrategy(
            recommended_dps_burst=False,
            recommended_rotation="normal",
            recommended_ult_timing="normal",
            emergency_actions=[],
            reasoning="No time pressure - continue normally",
        )

    def should_use_food(
        self,
        pressure: AbyssTimePressure,
        team_health_pct: float,
        mora_available: int,
    ) -> tuple[bool, str]:
        """Decide if food should be used during time pressure.

        Returns (should_use, reason).
        """
        if not pressure.is_under_pressure:
            return False, "No time pressure"

        if pressure.pressure_level == "critical" and team_health_pct < 50:
            if mora_available >= 5000:
                return True, "Critical pressure + low health - use emergency heal"
            return True, "Critical pressure + low health - use any available heal"

        if pressure.pressure_level == "high" and team_health_pct < 30:
            return True, "High pressure + critical health - heal before burst"

        return False, "Health sufficient for current pressure"

    def estimate_clear_probability(
        self,
        current_time_sec: float,
        enemy_health_pct: float,
        team_dps: float,
    ) -> float:
        """Estimate probability of clearing chamber.

        Uses simple model: can we deal remaining damage in remaining time?
        """
        time_remaining = max(0.0, self.FULL_TIME - current_time_sec)
        if time_remaining <= 0:
            return 0.0

        # Rough estimate
        damage_needed = enemy_health_pct * 10000  # Assume 10k total enemy HP
        possible_damage = team_dps * time_remaining

        probability = min(1.0, possible_damage / damage_needed)
        return probability
