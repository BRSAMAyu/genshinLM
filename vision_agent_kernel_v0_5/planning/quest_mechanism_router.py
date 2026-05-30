"""Quest mechanism router: handles special quest types beyond normal combat/dialog.

Routes quest steps to appropriate handlers based on mechanism type:
- Stealth: guard detection, safe path calculation
- Escort: NPC tracking, protection zone management
- Timed: countdown detection, priority reordering
- Investigation: clue/evidence collection tracking
- Dream: environment state transitions, cycle management
- Domain: entrance → challenges → completion flow
- AR Breakthrough: level-up detection, breakthrough domain configuration

Covers Q-10 through Q-16 capability requirements.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class QuestMechanismType(str, Enum):
    STANDARD = "standard"
    STEALTH = "stealth"
    ESCORT = "escort"
    TIMED = "timed"
    INVESTIGATION = "investigation"
    DREAM = "dream"
    DOMAIN = "domain"
    AR_BREAKTHROUGH = "ar_breakthrough"


@dataclass(slots=True)
class StealthState:
    """Current stealth encounter state."""
    guard_positions: list[tuple[float, float]] = field(default_factory=list)
    detection_level: float = 0.0          # 0.0=safe, 1.0=detected
    safe_zones: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y, radius)
    target_position: tuple[float, float] | None = None
    is_detected: bool = False


@dataclass(slots=True)
class EscortState:
    """Current escort mission state."""
    npc_position: tuple[float, float] | None = None
    npc_health_ratio: float = 1.0
    npc_is_moving: bool = False
    protection_radius: float = 5.0        # meters
    destination: tuple[float, float] | None = None
    threats_nearby: int = 0


@dataclass(slots=True)
class TimedState:
    """Current timed challenge state."""
    time_remaining_sec: float = 0.0
    objectives_completed: int = 0
    objectives_total: int = 1
    is_active: bool = False


@dataclass(slots=True)
class InvestigationState:
    """Current investigation/clue collection state."""
    clues_found: list[str] = field(default_factory=list)
    clues_total: int = 1
    current_area: str = ""
    evidence_collected: list[str] = field(default_factory=list)
    suspects_questioned: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DreamState:
    """Current dream sequence state."""
    cycle_number: int = 1
    is_dream: bool = False
    environment_changed: bool = False
    exit_found: bool = False


@dataclass(slots=True)
class DomainQuestState:
    """Current domain quest state."""
    phase: str = "entrance"       # entrance, combat, puzzle, boss, completion
    enemies_remaining: int = 0
    puzzles_solved: int = 0
    puzzles_total: int = 0
    resin_to_claim: int = 0


@dataclass(slots=True)
class ARBreakthroughState:
    """AR breakthrough quest state."""
    target_ar: int = 25
    domain_name: str = ""
    recommended_team: tuple[str, ...] = ()
    is_active: bool = False


@dataclass(slots=True)
class MechanismDecision:
    """Decision output from a quest mechanism handler."""
    action: str                  # "proceed", "wait", "hide", "protect", "search", "exit", "fight"
    priority: int                # Lower = more urgent
    reason: str = ""
    target: tuple[float, float] | None = None
    params: dict[str, Any] = field(default_factory=dict)


class StealthHandler:
    """Handles stealth quest segments (Q-10).

    Mondstadt/Liyue guard patrols, Inazuma escape sequences, etc.
    Detection is based on visual guard position tracking from screen analysis.
    """

    def evaluate(self, state: StealthState) -> MechanismDecision:
        if state.is_detected or state.detection_level > 0.8:
            return MechanismDecision("hide", 0, "detected_or_near_detected",
                                     params={"wait_for": "detection_level_below_0.3"})

        if state.detection_level > 0.5:
            return MechanismDecision("wait", 5, "guards_suspicious")

        if state.target_position is not None:
            return MechanismDecision("proceed", 10, "path_clear",
                                     target=state.target_position)

        return MechanismDecision("wait", 20, "no_target_set")

    def update_from_screen(self, stealth: StealthState,
                           guard_detections: list[tuple[float, float]],
                           detection_alert: float) -> StealthState:
        stealth.guard_positions = guard_detections
        stealth.detection_level = detection_alert
        stealth.is_detected = detection_alert >= 1.0
        return stealth


class EscortHandler:
    """Handles escort missions (Q-11).

    Protect NPC while they move to destination. Priority is keeping NPC alive.
    """

    def evaluate(self, state: EscortState) -> MechanismDecision:
        if state.npc_health_ratio < 0.3:
            return MechanismDecision("protect", 0, "npc_critical",
                                     target=state.npc_position,
                                     params={"use_defensive_skills": True})

        if state.threats_nearby > 0:
            return MechanismDecision("fight", 5,
                                     f"eliminate_{state.threats_nearby}_threats",
                                     params={"priority": "nearest_to_npc"})

        if state.npc_is_moving and state.destination is not None:
            return MechanismDecision("proceed", 10, "follow_npc",
                                     target=state.destination)

        return MechanismDecision("wait", 20, "escort_idle")

    def update_from_screen(self, escort: EscortState,
                           npc_pos: tuple[float, float] | None,
                           npc_hp: float,
                           npc_moving: bool,
                           threats: int) -> EscortState:
        escort.npc_position = npc_pos
        escort.npc_health_ratio = npc_hp
        escort.npc_is_moving = npc_moving
        escort.threats_nearby = threats
        return escort


class TimedHandler:
    """Handles timed challenges (Q-12).

    Countdown timer detection and priority reordering under time pressure.
    """

    def evaluate(self, state: TimedState) -> MechanismDecision:
        if not state.is_active:
            return MechanismDecision("wait", 50, "timer_not_active")

        progress = state.objectives_completed / max(state.objectives_total, 1)
        time_pressure = 1.0 - (state.time_remaining_sec / 300.0)

        if state.time_remaining_sec < 30 and progress < 0.5:
            return MechanismDecision("proceed", 0, "critical_time",
                                     params={"speed_mode": True, "skip_optionals": True})

        if state.time_remaining_sec < 60:
            return MechanismDecision("proceed", 5, "urgent_time",
                                     params={"speed_mode": True})

        if progress >= 1.0:
            return MechanismDecision("wait", 0, "all_objectives_done")

        return MechanismDecision("proceed", 10, "normal_pace")

    def update_from_screen(self, timed: TimedState,
                           time_remaining: float | None,
                           objectives_done: int | None,
                           objectives_total: int | None) -> TimedState:
        if time_remaining is not None:
            timed.time_remaining_sec = time_remaining
            timed.is_active = time_remaining > 0
        if objectives_done is not None:
            timed.objectives_completed = objectives_done
        if objectives_total is not None:
            timed.objectives_total = objectives_total
        return timed


class InvestigationHandler:
    """Handles investigation quests (Q-13).

    Fontaine Meropide investigations, clue collection, evidence gathering.
    """

    def evaluate(self, state: InvestigationState) -> MechanismDecision:
        if len(state.clues_found) >= state.clues_total:
            return MechanismDecision("proceed", 0, "all_clues_found")

        if state.current_area:
            return MechanismDecision("search", 10,
                                     f"search_{state.current_area}",
                                     params={"look_for_interactables": True})

        return MechanismDecision("search", 20, "explore_for_clues")

    def update_from_screen(self, inv: InvestigationState,
                           new_clue: str | None = None,
                           area_name: str | None = None,
                           new_evidence: str | None = None) -> InvestigationState:
        if new_clue and new_clue not in inv.clues_found:
            inv.clues_found.append(new_clue)
        if area_name:
            inv.current_area = area_name
        if new_evidence and new_evidence not in inv.evidence_collected:
            inv.evidence_collected.append(new_evidence)
        return inv


class DreamHandler:
    """Handles dream sequence quests (Q-14).

    Sumeru dream loop puzzles. Detect dream state transitions, track cycles.
    """

    def evaluate(self, state: DreamState) -> MechanismDecision:
        if state.exit_found:
            return MechanismDecision("exit", 0, "dream_exit_found")

        if state.environment_changed:
            return MechanismDecision("search", 5, f"dream_cycle_{state.cycle_number}",
                                     params={"look_for_anomalies": True})

        if state.is_dream:
            return MechanismDecision("search", 10, "explore_dream")

        return MechanismDecision("proceed", 20, "not_in_dream")

    def update_from_screen(self, dream: DreamState,
                           is_dream_env: bool,
                           env_changed: bool,
                           exit_visible: bool) -> DreamState:
        was_dream = dream.is_dream
        dream.is_dream = is_dream_env
        dream.environment_changed = env_changed
        dream.exit_found = exit_visible
        if is_dream_env and not was_dream:
            dream.cycle_number += 1
        return dream


class DomainQuestHandler:
    """Handles domain quest execution (Q-15).

    Quest-specific domains with combat + puzzle phases.
    """

    def evaluate(self, state: DomainQuestState) -> MechanismDecision:
        if state.phase == "entrance":
            return MechanismDecision("proceed", 10, "enter_domain",
                                     params={"trigger_interaction": True})

        if state.phase == "combat":
            if state.enemies_remaining > 0:
                return MechanismDecision("fight", 5,
                                         f"defeat_{state.enemies_remaining}_enemies")
            return MechanismDecision("proceed", 10, "combat_done_advance")

        if state.phase == "puzzle":
            if state.puzzles_solved < state.puzzles_total:
                return MechanismDecision("search", 10, "solve_puzzle")
            return MechanismDecision("proceed", 10, "puzzle_done_advance")

        if state.phase == "boss":
            return MechanismDecision("fight", 0, "boss_phase",
                                     params={"use_survival_engine": True})

        if state.phase == "completion":
            if state.resin_to_claim > 0:
                return MechanismDecision("proceed", 0, "claim_reward",
                                         params={"use_resin": state.resin_to_claim})
            return MechanismDecision("proceed", 5, "exit_domain")

        return MechanismDecision("wait", 50, "unknown_domain_phase")

    def update_from_screen(self, domain: DomainQuestState,
                           phase: str | None = None,
                           enemies: int | None = None,
                           puzzles_solved: int | None = None,
                           puzzles_total: int | None = None,
                           resin: int | None = None) -> DomainQuestState:
        if phase:
            domain.phase = phase
        if enemies is not None:
            domain.enemies_remaining = enemies
        if puzzles_solved is not None:
            domain.puzzles_solved = puzzles_solved
        if puzzles_total is not None:
            domain.puzzles_total = puzzles_total
        if resin is not None:
            domain.resin_to_claim = resin
        return domain


# AR breakthrough configurations (approximate — verify against current game version)
AR_BREAKTHROUGH_DOMAINS: dict[int, dict[str, Any]] = {
    25: {
        "domain": "Ascend: Clear the Ruins",
        "recommended_team_size": 2,
        "enemy_levels": (35, 40),
        "elements_needed": (),
    },
    35: {
        "domain": "Adventure Rank Ascension 1",
        "recommended_team_size": 4,
        "enemy_levels": (50, 55),
        "elements_needed": (),
    },
    45: {
        "domain": "Adventure Rank Ascension 2",
        "recommended_team_size": 4,
        "enemy_levels": (65, 70),
        "elements_needed": (),
    },
    50: {
        "domain": "Adventure Rank Ascension 3",
        "recommended_team_size": 4,
        "enemy_levels": (75, 80),
        "elements_needed": (),
    },
}


class ARBreakthroughHandler:
    """Handles AR breakthrough quests (Q-16).

    Detects when AR requires breakthrough, configures team for domain.
    """

    def evaluate(self, state: ARBreakthroughState) -> MechanismDecision:
        if not state.is_active:
            return MechanismDecision("wait", 50, "no_breakthrough_needed")

        config = AR_BREAKTHROUGH_DOMAINS.get(state.target_ar)
        if config is None:
            return MechanismDecision("proceed", 0, "auto_complete_no_domain")

        return MechanismDecision("fight", 0,
                                 f"ar_{state.target_ar}_breakthrough",
                                 params={
                                     "domain": config["domain"],
                                     "team_size": config["recommended_team_size"],
                                     "enemy_levels": config["enemy_levels"],
                                     "elements": config["elements_needed"],
                                 })

    def check_ar_breakthrough_needed(self, current_ar: int,
                                     ar_cap: int) -> ARBreakthroughState:
        if current_ar >= ar_cap and ar_cap in AR_BREAKTHROUGH_DOMAINS:
            config = AR_BREAKTHROUGH_DOMAINS[ar_cap]
            return ARBreakthroughState(
                target_ar=ar_cap,
                domain_name=config["domain"],
                recommended_team=tuple(
                    f"slot_{i}" for i in range(config["recommended_team_size"])
                ),
                is_active=True,
            )
        return ARBreakthroughState(is_active=False)


class QuestMechanismRouter:
    """Routes quest steps to the appropriate mechanism handler.

    Central dispatcher that identifies the quest mechanism type from
    step metadata and delegates to the correct handler.
    """

    def __init__(self) -> None:
        self._stealth = StealthHandler()
        self._escort = EscortHandler()
        self._timed = TimedHandler()
        self._investigation = InvestigationHandler()
        self._dream = DreamHandler()
        self._domain = DomainQuestHandler()
        self._ar_breakthrough = ARBreakthroughHandler()

        # Active states per mechanism
        self._stealth_state = StealthState()
        self._escort_state = EscortState()
        self._timed_state = TimedState()
        self._investigation_state = InvestigationState()
        self._dream_state = DreamState()
        self._domain_state = DomainQuestState()
        self._ar_state = ARBreakthroughState()

    def route(self, mechanism_type: QuestMechanismType) -> MechanismDecision:
        """Evaluate current state for given mechanism and return decision."""
        if mechanism_type == QuestMechanismType.STEALTH:
            return self._stealth.evaluate(self._stealth_state)
        if mechanism_type == QuestMechanismType.ESCORT:
            return self._escort.evaluate(self._escort_state)
        if mechanism_type == QuestMechanismType.TIMED:
            return self._timed.evaluate(self._timed_state)
        if mechanism_type == QuestMechanismType.INVESTIGATION:
            return self._investigation.evaluate(self._investigation_state)
        if mechanism_type == QuestMechanismType.DREAM:
            return self._dream.evaluate(self._dream_state)
        if mechanism_type == QuestMechanismType.DOMAIN:
            return self._domain.evaluate(self._domain_state)
        if mechanism_type == QuestMechanismType.AR_BREAKTHROUGH:
            return self._ar_breakthrough.evaluate(self._ar_state)
        return MechanismDecision("proceed", 50, "standard_quest")

    def get_state(self, mechanism_type: QuestMechanismType) -> Any:
        """Get the current state object for a mechanism type."""
        states = {
            QuestMechanismType.STEALTH: self._stealth_state,
            QuestMechanismType.ESCORT: self._escort_state,
            QuestMechanismType.TIMED: self._timed_state,
            QuestMechanismType.INVESTIGATION: self._investigation_state,
            QuestMechanismType.DREAM: self._dream_state,
            QuestMechanismType.DOMAIN: self._domain_state,
            QuestMechanismType.AR_BREAKTHROUGH: self._ar_state,
        }
        return states.get(mechanism_type)

    def identify_mechanism(self, step_metadata: dict[str, Any]) -> QuestMechanismType:
        """Identify the mechanism type from quest step metadata."""
        tags = step_metadata.get("tags", [])
        step_type = step_metadata.get("type", "")

        if "stealth" in tags or step_type == "stealth":
            return QuestMechanismType.STEALTH
        if "escort" in tags or step_type == "escort":
            return QuestMechanismType.ESCORT
        if "timed" in tags or step_type == "timed":
            return QuestMechanismType.TIMED
        if "investigation" in tags or step_type == "investigation":
            return QuestMechanismType.INVESTIGATION
        if "dream" in tags or step_type == "dream":
            return QuestMechanismType.DREAM
        if "domain" in tags or step_type == "domain":
            return QuestMechanismType.DOMAIN
        if "ar_breakthrough" in tags or step_type == "ar_breakthrough":
            return QuestMechanismType.AR_BREAKTHROUGH
        return QuestMechanismType.STANDARD
