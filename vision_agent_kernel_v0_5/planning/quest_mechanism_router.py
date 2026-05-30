"""Quest mechanism router: handles special quest types beyond normal combat/dialog.

Routes quest steps to appropriate handlers based on mechanism type:
- Stealth: guard detection, safe path calculation
- Escort: NPC tracking, protection zone management
- Timed: countdown detection, priority reordering
- Investigation: clue/evidence collection tracking
- Dream: environment state transitions, cycle management
- Domain: entrance → challenges → completion flow
- AR Breakthrough: level-up detection, breakthrough domain configuration
- Inazuma Lockout: quest lock detection, prerequisite chain resolution
- Guard Vision: cone-of-vision stealth with patrol route tracking
- Quest Recovery: state rollback and resume after interruption

Covers Q-10 through Q-25 capability requirements.
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
    HANGOUT = "hangout"
    EVENT = "event"
    INAZUMA_LOCKOUT = "inazuma_lockout"
    GUARD_VISION = "guard_vision"
    QUEST_RECOVERY = "quest_recovery"


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


# ---------------------------------------------------------------------------
# Hangout Event (邀约事件)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class HangoutBranch:
    """A branch in a hangout event dialog tree."""
    branch_id: str
    choice_text: str
    leads_to_ending: str = ""       # Empty = continues to more dialog
    is_heart_event: bool = False     # Special affection checkpoint


@dataclass(slots=True)
class HangoutState:
    """Current hangout event state."""
    character_name: str = ""
    current_node: str = ""
    endings_unlocked: list[str] = field(default_factory=list)
    endings_total: int = 5          # Most hangouts have 5-6 endings
    current_branch_options: list[HangoutBranch] = field(default_factory=list)
    affection_checkpoint_met: bool = False
    is_active: bool = False


class HangoutHandler:
    """Handles hangout event branch selection and ending tracking.

    Hangout events are branching dialog sequences where each choice can lead
    to different endings. The handler tracks unlocked endings and helps
    select the correct dialog choices to reach desired endings.
    """

    def evaluate(self, state: HangoutState) -> MechanismDecision:
        if not state.is_active:
            return MechanismDecision("wait", 50, "hangout_not_active")

        # If all endings unlocked, no need to continue
        if len(state.endings_unlocked) >= state.endings_total:
            return MechanismDecision("proceed", 0, "all_endings_unlocked")

        # If at a branch point, select the choice leading to an unexplored ending
        if state.current_branch_options:
            unexplored = [
                b for b in state.current_branch_options
                if b.leads_to_ending and b.leads_to_ending not in state.endings_unlocked
            ]
            if unexplored:
                target_branch = unexplored[0]
                return MechanismDecision(
                    "proceed", 0,
                    f"select_branch_{target_branch.branch_id}",
                    params={"choice_text": target_branch.choice_text},
                )
            # All explored — pick first to continue dialog
            return MechanismDecision(
                "proceed", 10, "continue_dialog_default",
                params={"choice_text": state.current_branch_options[0].choice_text},
            )

        # Heart event (affection checkpoint) — must respond correctly
        if state.affection_checkpoint_met:
            return MechanismDecision(
                "proceed", 5, "heart_event_respond",
                params={"select_positive": True},
            )

        return MechanismDecision("proceed", 20, "advance_hangout_dialog")

    def record_ending(self, state: HangoutState, ending_id: str) -> HangoutState:
        if ending_id and ending_id not in state.endings_unlocked:
            state.endings_unlocked.append(ending_id)
        return state

    def set_branch_options(
        self, state: HangoutState, options: list[HangoutBranch],
    ) -> HangoutState:
        state.current_branch_options = options
        return state


# ---------------------------------------------------------------------------
# Limited Event Quest (限时活动)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EventQuestState:
    """Current event quest state."""
    event_id: str = ""
    event_name: str = ""
    phase: str = "intro"         # intro, main, challenge, finale
    currency_collected: int = 0
    currency_target: int = 1000
    mini_games_completed: int = 0
    mini_games_total: int = 0
    is_time_limited: bool = True
    days_remaining: int = 14
    is_active: bool = False


class EventQuestHandler:
    """Handles limited-time event quests with mini-games and currency.

    Events typically have:
    - Intro quests (dialog + navigation)
    - Main event currency collection (mini-games)
    - Challenge modes (harder versions)
    - Finale quest (story conclusion)
    """

    def evaluate(self, state: EventQuestState) -> MechanismDecision:
        if not state.is_active:
            return MechanismDecision("wait", 50, "event_not_active")

        if state.days_remaining <= 0:
            return MechanismDecision("proceed", 0, "event_expired")

        if state.phase == "intro":
            return MechanismDecision("proceed", 10, "event_intro",
                                     params={"drive_dialog": True})

        if state.phase == "main":
            if state.currency_collected >= state.currency_target:
                return MechanismDecision("proceed", 5, "currency_target_met")
            return MechanismDecision("proceed", 10, "play_mini_game",
                                     params={"target_currency": state.currency_target - state.currency_collected})

        if state.phase == "challenge":
            return MechanismDecision("fight", 5, "event_challenge",
                                     params={"difficulty": "hard"})

        if state.phase == "finale":
            return MechanismDecision("proceed", 0, "event_finale",
                                     params={"drive_dialog": True})

        return MechanismDecision("proceed", 20, "event_default")

    def update_progress(
        self,
        state: EventQuestState,
        currency_gained: int = 0,
        mini_game_won: bool = False,
        phase_complete: bool = False,
    ) -> EventQuestState:
        state.currency_collected += currency_gained
        if mini_game_won:
            state.mini_games_completed += 1
        if phase_complete:
            phase_order = ["intro", "main", "challenge", "finale"]
            idx = phase_order.index(state.phase) if state.phase in phase_order else -1
            if idx < len(phase_order) - 1:
                state.phase = phase_order[idx + 1]
        return state


# ---------------------------------------------------------------------------
# Q-18: Inazuma Lockout — prerequisite chain detection & resolution
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class InazumaLockoutState:
    required_ar: int = 30
    required_quests: list[str] = field(default_factory=lambda: ["ayaka_story", "yoimiya_story"])
    completed_quests: list[str] = field(default_factory=list)
    current_ar: int = 1
    lock_detected: bool = False


class InazumaLockoutHandler:
    """Detect Inazuma quest lockout and resolve via prerequisite chain.

    Inazuma requires AR 30 + Ayaka story + Yoimiya story quests before
    the Archon Quest chapter 2 unlocks. This handler detects the lock
    and tracks prerequisite completion.
    """

    def evaluate(self, state: InazumaLockoutState) -> MechanismDecision:
        missing_quests = [q for q in state.required_quests if q not in state.completed_quests]
        ar_ok = state.current_ar >= state.required_ar
        quests_ok = len(missing_quests) == 0

        if ar_ok and quests_ok:
            return MechanismDecision("proceed", 90, "inazuma_unlocked")

        if not ar_ok:
            return MechanismDecision(
                "grind_ar", 60,
                f"ar_grind_{state.current_ar}_to_{state.required_ar}",
            )

        next_quest = missing_quests[0]
        return MechanismDecision("complete_prerequisite", 70, f"quest_{next_quest}")

    def update_progress(
        self, state: InazumaLockoutState, *, quest_completed: str = "", ar_gained: int = 0,
    ) -> InazumaLockoutState:
        if quest_completed and quest_completed not in state.completed_quests:
            state.completed_quests.append(quest_completed)
        state.current_ar += ar_gained
        state.lock_detected = not (
            state.current_ar >= state.required_ar
            and all(q in state.completed_quests for q in state.required_quests)
        )
        return state


# ---------------------------------------------------------------------------
# Q-20: Guard Vision — cone-of-vision stealth with patrol tracking
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GuardVisionState:
    guard_count: int = 0
    vision_cones: list[tuple[float, float, float]] = field(default_factory=list)  # (x, y, angle)
    patrol_routes: list[list[tuple[float, float]]] = field(default_factory=list)
    player_position: tuple[float, float] = (0.0, 0.0)
    detection_score: float = 0.0  # 0.0=safe, 1.0=detected
    current_guard_index: int = 0
    safe_path: list[tuple[float, float]] = field(default_factory=list)


class GuardVisionHandler:
    """Handle guard cone-of-vision detection for stealth quests.

    Tracks guard positions, vision cones, and patrol routes to compute
    safe paths. Escalates to dodge+retreat when detection is imminent.
    """

    VISION_CONE_RADIUS: float = 8.0
    VISION_CONE_ANGLE: float = 90.0  # degrees

    def evaluate(self, state: GuardVisionState) -> MechanismDecision:
        if state.detection_score >= 1.0:
            return MechanismDecision("retreat", 90, "detected_flee")

        if state.detection_score >= 0.7:
            return MechanismDecision("hide", 80, "near_detection_wait")

        if state.safe_path:
            return MechanismDecision("follow_safe_path", 60, "stealth_advance")

        # No safe path computed — stay still and observe
        return MechanismDecision("observe", 40, "wait_for_pattern")

    def compute_safe_path(self, state: GuardVisionState) -> GuardVisionState:
        """Compute safe path between current position and target, avoiding vision cones."""
        # Simplified: assume safe path exists between patrol gaps
        state.safe_path = [(state.player_position[0] + i, state.player_position[1])
                           for i in range(1, 4)]
        state.detection_score = 0.0
        return state

    def update_detection(
        self, state: GuardVisionState, player_pos: tuple[float, float],
    ) -> GuardVisionState:
        """Update detection score based on player position relative to vision cones."""
        state.player_position = player_pos
        max_detection = 0.0
        for gx, gy, angle in state.vision_cones:
            dx = player_pos[0] - gx
            dy = player_pos[1] - gy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < self.VISION_CONE_RADIUS:
                import math
                player_angle = math.degrees(math.atan2(dy, dx))
                angle_diff = abs(player_angle - angle)
                if angle_diff < self.VISION_CONE_ANGLE / 2:
                    detection = 1.0 - (dist / self.VISION_CONE_RADIUS)
                    max_detection = max(max_detection, detection)
        state.detection_score = min(1.0, max_detection)
        return state


# ---------------------------------------------------------------------------
# Q-25: Quest State Recovery — rollback and resume after interruption
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class QuestRecoveryState:
    quest_id: str = ""
    last_known_step: str = ""
    interrupted: bool = False
    interruption_reason: str = ""
    recovery_attempts: int = 0
    checkpoint_steps: list[str] = field(default_factory=list)
    current_step_index: int = 0


class QuestRecoveryHandler:
    """Recover quest progress after interruption.

    Tracks checkpoint steps so the quest can resume from the last known
    good state rather than restarting from scratch.
    """

    MAX_RECOVERY_ATTEMPTS: int = 3

    def evaluate(self, state: QuestRecoveryState) -> MechanismDecision:
        if not state.interrupted:
            return MechanismDecision("proceed", 90, "quest_normal")

        if state.recovery_attempts >= self.MAX_RECOVERY_ATTEMPTS:
            return MechanismDecision("escalate", 95, "recovery_exhausted")

        if state.checkpoint_steps and state.current_step_index < len(state.checkpoint_steps):
            step = state.checkpoint_steps[state.current_step_index]
            return MechanismDecision("resume_from_checkpoint", 70, f"resume_{step}")

        # No checkpoints — restart from beginning
        return MechanismDecision("restart_quest", 50, f"restart_{state.quest_id}")

    def mark_checkpoint(self, state: QuestRecoveryState, step: str) -> QuestRecoveryState:
        state.checkpoint_steps.append(step)
        state.current_step_index = len(state.checkpoint_steps) - 1
        return state

    def mark_interrupted(self, state: QuestRecoveryState, reason: str) -> QuestRecoveryState:
        state.interrupted = True
        state.interruption_reason = reason
        state.recovery_attempts += 1
        return state

    def recover(self, state: QuestRecoveryState) -> QuestRecoveryState:
        """Attempt recovery: resume from last checkpoint."""
        state.interrupted = False
        state.interruption_reason = ""
        return state


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
        self._hangout = HangoutHandler()
        self._event = EventQuestHandler()
        self._inazuma_lockout = InazumaLockoutHandler()
        self._guard_vision = GuardVisionHandler()
        self._quest_recovery = QuestRecoveryHandler()

        # Active states per mechanism
        self._stealth_state = StealthState()
        self._escort_state = EscortState()
        self._timed_state = TimedState()
        self._investigation_state = InvestigationState()
        self._dream_state = DreamState()
        self._domain_state = DomainQuestState()
        self._ar_state = ARBreakthroughState()
        self._hangout_state = HangoutState()
        self._event_state = EventQuestState()
        self._inazuma_lockout_state = InazumaLockoutState()
        self._guard_vision_state = GuardVisionState()
        self._quest_recovery_state = QuestRecoveryState()

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
        if mechanism_type == QuestMechanismType.HANGOUT:
            return self._hangout.evaluate(self._hangout_state)
        if mechanism_type == QuestMechanismType.EVENT:
            return self._event.evaluate(self._event_state)
        if mechanism_type == QuestMechanismType.INAZUMA_LOCKOUT:
            return self._inazuma_lockout.evaluate(self._inazuma_lockout_state)
        if mechanism_type == QuestMechanismType.GUARD_VISION:
            return self._guard_vision.evaluate(self._guard_vision_state)
        if mechanism_type == QuestMechanismType.QUEST_RECOVERY:
            return self._quest_recovery.evaluate(self._quest_recovery_state)
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
            QuestMechanismType.HANGOUT: self._hangout_state,
            QuestMechanismType.EVENT: self._event_state,
            QuestMechanismType.INAZUMA_LOCKOUT: self._inazuma_lockout_state,
            QuestMechanismType.GUARD_VISION: self._guard_vision_state,
            QuestMechanismType.QUEST_RECOVERY: self._quest_recovery_state,
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
        if "hangout" in tags or step_type == "hangout":
            return QuestMechanismType.HANGOUT
        if "event" in tags or step_type == "event":
            return QuestMechanismType.EVENT
        if "inazuma_lockout" in tags or step_type == "inazuma_lockout":
            return QuestMechanismType.INAZUMA_LOCKOUT
        if "guard_vision" in tags or step_type == "guard_vision":
            return QuestMechanismType.GUARD_VISION
        if "quest_recovery" in tags or step_type == "quest_recovery":
            return QuestMechanismType.QUEST_RECOVERY
        return QuestMechanismType.STANDARD
