"""Quest and dialog enhancement: special quest mechanics, dialog management, quest log.

Extends existing QuestStateMachine and DialogDriver with advanced quest handling
for stealth missions, escort quests, timed challenges, and puzzle domains.
Covers Q-05 through Q-16, D-03 through D-09.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quest type classification
# ---------------------------------------------------------------------------

class QuestType(Enum):
    ARCHON = "archon"              # Main storyline
    STORY = "story"                # Character story quests
    WORLD = "world"                # World quests
    DAILY_COMMISSION = "daily"     # Daily commissions
    HANGOUT = "hangout"            # Character hangout events
    DOMAIN = "domain"              # Quest-specific domains
    EVENT = "event"                # Limited-time events


class QuestMechanic(Enum):
    """Special quest mechanics that require specific handling."""
    COMBAT = "combat"
    DIALOG = "dialog"
    STEALTH = "stealth"             # Avoid detection by enemies/NPCs
    ESCORT = "escort"               # Protect and follow an NPC
    TIMED = "timed"                 # Time-limited challenge
    INVESTIGATION = "investigation"  # Collect clues, interrogate
    DREAM_LOOP = "dream_loop"       # Sumeru dream sequence puzzle
    PUZZLE = "puzzle"               # Solve environmental puzzles
    COLLECTION = "collection"       # Gather items in area
    NAVIGATION = "navigation"       # Navigate to specific location
    ELEMENTAL = "elemental"         # Use specific element abilities
    BOSS_FIGHT = "boss_fight"       # Boss combat encounter
    AR_BREAKTHROUGH = "ar_breakthrough"  # AR ascension domain


class QuestMarkerColor(Enum):
    YELLOW = "yellow"    # Archon quest
    BLUE = "blue"        # Story/world quest
    GREEN = "green"      # Daily commission
    PURPLE = "purple"    # Event quest
    ORANGE = "orange"    # Special quest


# ---------------------------------------------------------------------------
# Quest data
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class QuestObjective:
    """A specific objective within a quest."""
    objective_id: str
    description: str
    mechanic: QuestMechanic
    marker_color: QuestMarkerColor = QuestMarkerColor.YELLOW
    element_required: str | None = None  # e.g., "Anemo" for wind puzzles
    time_limit_sec: float | None = None
    follow_up_objectives: tuple[str, ...] = ()
    fail_conditions: tuple[str, ...] = ()
    tips: str = ""


@dataclass(slots=True)
class QuestLog:
    """Manages the player's quest tracking and navigation."""
    active_quests: dict[str, QuestObjective] = field(default_factory=dict)
    tracked_quest_id: str | None = None
    completed_quests: set[str] = field(default_factory=set)
    failed_objectives: dict[str, int] = field(default_factory=dict)  # objective_id -> fail_count

    def track(self, quest_id: str) -> None:
        self.tracked_quest_id = quest_id

    def add_quest(self, quest: QuestObjective) -> None:
        self.active_quests[quest.objective_id] = quest

    def complete_quest(self, quest_id: str) -> None:
        self.active_quests.pop(quest_id, None)
        self.completed_quests.add(quest_id)
        if self.tracked_quest_id == quest_id:
            self.tracked_quest_id = None

    def fail_objective(self, objective_id: str) -> None:
        self.failed_objectives[objective_id] = self.failed_objectives.get(objective_id, 0) + 1

    def get_tracked(self) -> QuestObjective | None:
        if self.tracked_quest_id is None:
            return None
        return self.active_quests.get(self.tracked_quest_id)

    def get_by_mechanic(self, mechanic: QuestMechanic) -> list[QuestObjective]:
        return [q for q in self.active_quests.values() if q.mechanic == mechanic]

    def should_abandon(self, objective_id: str, max_fails: int = 3) -> bool:
        return self.failed_objectives.get(objective_id, 0) >= max_fails


# ---------------------------------------------------------------------------
# Special quest mechanism handlers
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class StealthConfig:
    """Configuration for stealth mission handling."""
    detection_radius_px: int = 150      # pixel radius to avoid enemies
    safe_distance_px: int = 250         # minimum safe distance
    patrol_watch_sec: float = 3.0       # seconds to observe patrol pattern
    crouch_speed: float = 0.3           # movement speed during stealth
    dash_cooldown_sec: float = 2.0      # wait between dashes


@dataclass(slots=True, frozen=True)
class EscortConfig:
    """Configuration for escort mission handling."""
    follow_distance_px: int = 100       # stay this close to NPC
    max_distance_px: int = 300          # NPC goes too far warning
    heal_npc_threshold: float = 0.5     # heal NPC if HP below this
    protect_radius_px: int = 200        # engage enemies within this range


@dataclass(slots=True, frozen=True)
class TimedChallengeConfig:
    """Configuration for timed challenge handling."""
    time_limit_sec: float
    items_to_collect: int = 0
    enemies_to_defeat: int = 0
    optimal_route: tuple[str, ...] = ()  # waypoint IDs in order
    speed_food_recommended: bool = True


@dataclass(slots=True, frozen=True)
class ARBreakthroughConfig:
    """Configuration for AR breakthrough domain."""
    ar_level: int
    domain_name: str
    recommended_team: tuple[str, ...]
    enemy_elements: tuple[str, ...]
    strategy: str


# AR breakthrough domains
AR_BREAKTHROUGH_CONFIGS: dict[int, ARBreakthroughConfig] = {
    25: ARBreakthroughConfig(
        25, "Ascend: Clear the Ruins",
        ("xiangling", "kaeya", "barbara", "amber"),
        ("Pyro", "Electro"),
        "Focus on elemental reactions, use Kaeya for superconduct",
    ),
    35: ARBreakthroughConfig(
        35, "Clear the Abyssal Moon",
        ("xiangling", "xingqiu", "bennett", "kaeya"),
        ("Pyro", "Hydro"),
        "National team core, save burst for waves",
    ),
    45: ARBreakthroughConfig(
        45, "Bloom and Grief",
        ("xiangling", "xingqiu", "bennett", "kaeya"),
        ("Physical", "Cryo"),
        "Full combat, bring food buffs",
    ),
    50: ARBreakthroughConfig(
        50, "Realm of Slumber",
        ("xiangling", "xingqiu", "bennett", "kaeya"),
        ("Electro", "Cryo"),
        "High damage requirement, optimize rotation",
    ),
}


# ---------------------------------------------------------------------------
# Dialog enhancement (D-03 through D-09)
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class DialogChoice:
    """A dialog choice with context for decision-making."""
    text: str
    index: int               # position in choice list
    is_progression: bool = False   # advances the main quest
    is_flavor: bool = False        # doesn't affect outcome
    is_branch_point: bool = False  # affects quest outcome


@dataclass(slots=True)
class DialogSession:
    """Tracks state within a multi-turn dialog."""
    npc_name: str = ""
    turns: int = 0
    choices_made: list[DialogChoice] = field(default_factory=list)
    key_choices: list[DialogChoice] = field(default_factory=list)
    auto_play_enabled: bool = False
    dialog_complete: bool = False

    def record_choice(self, choice: DialogChoice) -> None:
        self.turns += 1
        self.choices_made.append(choice)
        if choice.is_branch_point:
            self.key_choices.append(choice)

    def should_skip(self) -> bool:
        """Check if dialog can be skipped (all seen)."""
        return self.auto_play_enabled and self.turns > 5


# Dialog selection strategies
class DialogStrategy(Enum):
    FIRST_OPTION = "first"           # always pick first option
    PROGRESSION_FIRST = "progression"  # pick quest-advancing options
    SKIP_ALL = "skip"               # try to skip as fast as possible
    ANALYZE = "analyze"             # use VLM to understand and choose


def choose_dialog_option(
    choices: list[DialogChoice],
    strategy: DialogStrategy = DialogStrategy.PROGRESSION_FIRST,
) -> DialogChoice | None:
    """Select a dialog option based on strategy."""
    if not choices:
        return None

    if strategy == DialogStrategy.FIRST_OPTION:
        return choices[0]

    if strategy == DialogStrategy.PROGRESSION_FIRST:
        # Prefer progression options, then first
        for choice in choices:
            if choice.is_progression:
                return choice
        return choices[0]

    if strategy == DialogStrategy.SKIP_ALL:
        # Pick whatever closes the dialog fastest
        for choice in choices:
            if choice.is_flavor:
                return choice
        return choices[-1]  # often "skip" or "leave" is last

    # ANALYZE: return first for now (VLM integration later)
    return choices[0]


# ---------------------------------------------------------------------------
# NPC interaction patterns (D-07, Q-06)
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class NPCInteractionPattern:
    """Pattern for interacting with quest NPCs."""
    npc_name: str
    location: str
    interaction_type: str    # "talk", "trade", "quest_accept", "quest_turn_in"
    quest_prerequisite: str | None = None
    available_hours: tuple[int, int] | None = None  # (start_hour, end_hour) or None = always
    required_item: str | None = None


# Key NPC interaction patterns for Archon Quests
ARCHON_NPC_PATTERNS: dict[str, NPCInteractionPattern] = {
    "katheryne_mondstadt": NPCInteractionPattern(
        "Katheryne", "Mondstadt Adventurers' Guild", "quest_turn_in",
    ),
    "katheryne_liyue": NPCInteractionPattern(
        "Katheryne", "Liyue Adventurers' Guild", "quest_turn_in",
    ),
    "zhongli": NPCInteractionPattern(
        "Zhongli", "Liyue Harbor", "talk", quest_prerequisite="ch1_act1",
    ),
    "ayaka": NPCInteractionPattern(
        "Kamisato Ayaka", "Kamisato Estate", "talk", quest_prerequisite="ch2_prologue",
    ),
    "nahida": NPCInteractionPattern(
        "Nahida", "Sumeru City", "talk", quest_prerequisite="ch3_act1",
    ),
}


# ---------------------------------------------------------------------------
# Quest mechanism router
# ---------------------------------------------------------------------------

class QuestMechanismRouter:
    """Routes quest objectives to appropriate handling strategies.

    Determines how to handle each quest type and delegates to
    the appropriate system (combat, navigation, dialog, stealth, etc.).
    """

    def __init__(self) -> None:
        self._handlers: dict[QuestMechanic, str] = {
            QuestMechanic.COMBAT: "combat_playbook",
            QuestMechanic.DIALOG: "dialog_driver",
            QuestMechanic.STEALTH: "stealth_handler",
            QuestMechanic.ESCORT: "escort_handler",
            QuestMechanic.TIMED: "timed_handler",
            QuestMechanic.INVESTIGATION: "vlm_investigation",
            QuestMechanic.DREAM_LOOP: "dream_loop_solver",
            QuestMechanic.PUZZLE: "puzzle_solver",
            QuestMechanic.COLLECTION: "collection_handler",
            QuestMechanic.NAVIGATION: "quest_marker_follower",
            QuestMechanic.ELEMENTAL: "elemental_handler",
            QuestMechanic.BOSS_FIGHT: "boss_combat",
            QuestMechanic.AR_BREAKTHROUGH: "ar_breakthrough",
        }

    def get_handler(self, mechanic: QuestMechanic) -> str:
        return self._handlers.get(mechanic, "generic_handler")

    def get_config(self, objective: QuestObjective) -> dict[str, Any]:
        """Return mechanism-specific configuration for an objective."""
        config: dict[str, Any] = {"mechanic": objective.mechanic.value}

        if objective.mechanic == QuestMechanic.STEALTH:
            config["stealth_config"] = StealthConfig()
        elif objective.mechanic == QuestMechanic.ESCORT:
            config["escort_config"] = EscortConfig()
        elif objective.mechanic == QuestMechanic.TIMED:
            config["timed_config"] = TimedChallengeConfig(
                time_limit_sec=objective.time_limit_sec or 120.0,
            )
        elif objective.mechanic == QuestMechanic.AR_BREAKTHROUGH:
            # Determine AR level from description
            ar = 0
            for ar_lv, cfg in AR_BREAKTHROUGH_CONFIGS.items():
                if str(ar_lv) in objective.description:
                    ar = ar_lv
                    break
            if ar > 0:
                config["ar_config"] = AR_BREAKTHROUGH_CONFIGS[ar]

        if objective.element_required:
            config["element_required"] = objective.element_required

        return config

    def assess_difficulty(self, objective: QuestObjective) -> str:
        """Assess difficulty of a quest objective for planning."""
        hard_mechanics = {
            QuestMechanic.BOSS_FIGHT, QuestMechanic.STEALTH,
            QuestMechanic.TIMED, QuestMechanic.AR_BREAKTHROUGH,
        }
        if objective.mechanic in hard_mechanics:
            return "hard"
        if objective.mechanic in (QuestMechanic.COMBAT, QuestMechanic.ESCORT):
            return "moderate"
        return "easy"
