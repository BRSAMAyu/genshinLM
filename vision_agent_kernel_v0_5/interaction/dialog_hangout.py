"""Hangout event branch detection and multi-turn dialog management.

Covers:
- D-06: Hangout event branch detection (identify critical branching points,
        track ending progress, recommend optimal choices per target ending)
- D-09: Multi-turn dialog management (session tracking across NPC interactions,
        conversation context accumulation, quest-chain dialog coordination)

Integrates with:
- interaction/dialog_driver.py for dialog progression
- interaction/dialog_branch_analyzer.py for choice selection
- planning/quest_state_machine.py for quest chain tracking
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D-06: Hangout Event Branch Detection
# ---------------------------------------------------------------------------

class HangoutEnding(str, Enum):
    """Hangout event ending types."""
    GOOD = "good"           # Best/positive ending
    NORMAL = "normal"       # Standard ending
    BAD = "bad"             # Negative ending
    HIDDEN = "hidden"       # Secret/hidden ending
    UNLOCKED = "unlocked"   # Ending already achieved


@dataclass(slots=True)
class HangoutBranch:
    """A branching point in a hangout event."""
    branch_id: str
    description: str
    options: list[str] = field(default_factory=list)
    target_endings: dict[int, str] = field(default_factory=dict)
    is_critical: bool = False  # True if this branch determines ending


@dataclass(slots=True)
class HangoutEndingState:
    """Tracking state for a character's hangout endings."""
    character: str
    total_endings: int = 6
    unlocked_endings: set[str] = field(default_factory=set)
    current_branch_path: list[str] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        if self.total_endings == 0:
            return 0.0
        return len(self.unlocked_endings) / self.total_endings

    @property
    def all_endings_unlocked(self) -> bool:
        return len(self.unlocked_endings) >= self.total_endings


class HangoutBranchDetector:
    """Detects and manages hangout event branches (D-06).

    Hangout events have multiple endings determined by dialog choices at
    specific branch points. This detector:
    1. Identifies critical branch points from dialog text
    2. Tracks which endings have been unlocked
    3. Recommends choices to reach target endings
    """

    # Keywords that signal a hangout branch point
    _BRANCH_SIGNALS = {
        "你怎么看": "opinion",
        "你觉得呢": "opinion",
        "你想": "choice",
        "要不要": "offer",
        "还是": "alternative",
        "或者": "alternative",
        "一起去": "invitation",
        "一个人": "alone",
    }

    # Hangout ending data per character (simplified representative set)
    _ENDING_MAP: dict[str, dict[str, list[str]]] = {
        "default": {
            "ending_1": ["opinion_positive", "agree", "together"],
            "ending_2": ["opinion_positive", "disagree", "alone"],
            "ending_3": ["opinion_neutral", "agree", "together"],
            "ending_4": ["opinion_neutral", "disagree", "alone"],
            "ending_5": ["opinion_negative", "refuse"],
            "ending_6": ["opinion_positive", "secret"],
        },
    }

    def __init__(self) -> None:
        self._states: dict[str, HangoutEndingState] = {}

    def get_or_create_state(self, character: str,
                            total_endings: int = 6) -> HangoutEndingState:
        """Get or create tracking state for a character's hangout."""
        if character not in self._states:
            self._states[character] = HangoutEndingState(
                character=character,
                total_endings=total_endings,
            )
        return self._states[character]

    def detect_branch(self, dialog_text: str,
                      option_texts: list[str]) -> HangoutBranch | None:
        """Detect if the current dialog is a hangout branch point.

        Returns None if this doesn't appear to be a branch point.
        """
        if not option_texts or len(option_texts) < 2:
            return None

        # Check for branch signal keywords in dialog text
        detected_signals: dict[str, str] = {}
        for keyword, signal_type in self._BRANCH_SIGNALS.items():
            if keyword in dialog_text:
                detected_signals[keyword] = signal_type

        if not detected_signals:
            return None

        branch = HangoutBranch(
            branch_id=f"hangout_{hash(dialog_text) % 10000:04d}",
            description=dialog_text[:80],
            options=option_texts,
            is_critical=len(option_texts) >= 2,
        )

        # Map options to likely endings based on signal analysis
        for i, option in enumerate(option_texts):
            if "一起" in option or "好" in option:
                branch.target_endings[i] = "good"
            elif "不了" in option or "算了" in option:
                branch.target_endings[i] = "bad"
            elif "秘密" in option or "秘密" in option:
                branch.target_endings[i] = "hidden"
            else:
                branch.target_endings[i] = "normal"

        log.info("[HangoutBranch] detected branch: %s (%d options, critical=%s)",
                 branch.branch_id, len(option_texts), branch.is_critical)
        return branch

    def recommend_choice(self, branch: HangoutBranch,
                         target_ending: str = "good") -> int:
        """Recommend which option to choose for a target ending.

        Returns the option index (0-based) most likely to lead to target_ending.
        """
        # Direct match from branch analysis
        for idx, ending_type in branch.target_endings.items():
            if target_ending in ending_type:
                return idx

        # Heuristic: prefer positive-sounding options for good endings
        _POSITIVE = {"一起", "好的", "当然", "没问题", "愿意"}
        if target_ending == "good":
            for i, opt in enumerate(branch.options):
                if any(kw in opt for kw in _POSITIVE):
                    return i

        # Default: first option
        return 0

    def record_ending(self, character: str, ending_id: str) -> None:
        """Record that an ending has been unlocked."""
        state = self.get_or_create_state(character)
        state.unlocked_endings.add(ending_id)
        log.info("[HangoutBranch] %s unlocked ending '%s' (%d/%d)",
                 character, ending_id, len(state.unlocked_endings), state.total_endings)

    def get_next_target_ending(self, character: str) -> str | None:
        """Get the next unachieved ending to target."""
        state = self.get_or_create_state(character)
        ending_map = self._ENDING_MAP.get(character, self._ENDING_MAP["default"])
        for ending_id in ending_map:
            if ending_id not in state.unlocked_endings:
                return ending_id
        return None


# ---------------------------------------------------------------------------
# D-09: Multi-turn Dialog Management
# ---------------------------------------------------------------------------

class DialogPhase(str, Enum):
    """Phases of a multi-turn dialog interaction."""
    INIT = "init"
    GREETING = "greeting"
    QUEST_OFFER = "quest_offer"
    INFORMATION = "information"
    COMMERCE = "commerce"
    FAREWELL = "farewell"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class DialogTurn:
    """A single turn in a dialog exchange."""
    turn_number: int
    npc_text: str = ""
    player_choices: list[str] = field(default_factory=list)
    selected_choice: int = -1
    phase: DialogPhase = DialogPhase.UNKNOWN
    timestamp: float = 0.0


@dataclass(slots=True)
class DialogSession:
    """Tracks a complete multi-turn dialog session with an NPC."""
    npc_name: str
    quest_context: str = ""
    turns: list[DialogTurn] = field(default_factory=list)
    phase: DialogPhase = DialogPhase.INIT
    started: bool = False
    completed: bool = False
    quest_accepted: bool = False
    key_info_extracted: list[str] = field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def current_turn(self) -> DialogTurn | None:
        return self.turns[-1] if self.turns else None


class MultiTurnDialogManager:
    """Manages multi-turn dialog sessions with NPCs (D-09).

    Handles:
    1. Session lifecycle (start, progress, end)
    2. Phase detection based on dialog content
    3. Context accumulation across turns
    4. Quest-chain dialog coordination
    """

    # Phase detection keywords
    _PHASE_KEYWORDS: dict[DialogPhase, set[str]] = {
        DialogPhase.GREETING: {"你好", "嗨", "旅行者", "最近怎么样", "好久不见"},
        DialogPhase.QUEST_OFFER: {"委托", "任务", "需要帮助", "能帮我", "请"},
        DialogPhase.INFORMATION: {"据说", "听说", "关于", "告诉我", "线索"},
        DialogPhase.COMMERCE: {"购买", "价格", "多少钱", "卖", "交易"},
        DialogPhase.FAREWELL: {"再见", "保重", "下次", "告辞", "一路平安"},
    }

    def __init__(self) -> None:
        self._active_sessions: dict[str, DialogSession] = {}
        self._completed_sessions: list[DialogSession] = []

    def start_session(self, npc_name: str,
                      quest_context: str = "") -> DialogSession:
        """Start a new dialog session with an NPC."""
        # End any existing session with same NPC
        if npc_name in self._active_sessions:
            self.end_session(npc_name)

        session = DialogSession(
            npc_name=npc_name,
            quest_context=quest_context,
            started=True,
            phase=DialogPhase.INIT,
        )
        self._active_sessions[npc_name] = session
        log.info("[DialogSession] started with '%s' (context: %s)",
                 npc_name, quest_context or "none")
        return session

    def get_session(self, npc_name: str) -> DialogSession | None:
        """Get the active session for an NPC, if any."""
        return self._active_sessions.get(npc_name)

    def add_turn(self, npc_name: str, npc_text: str,
                 choices: list[str] | None = None,
                 selected: int = -1) -> DialogTurn | None:
        """Add a turn to the active dialog session."""
        session = self._active_sessions.get(npc_name)
        if session is None:
            log.warning("[DialogSession] no active session for '%s'", npc_name)
            return None

        phase = self._detect_phase(npc_text)
        turn = DialogTurn(
            turn_number=session.turn_count + 1,
            npc_text=npc_text,
            player_choices=choices or [],
            selected_choice=selected,
            phase=phase,
        )

        session.turns.append(turn)
        session.phase = phase

        # Extract key info from NPC text
        info = self._extract_key_info(npc_text)
        if info:
            session.key_info_extracted.extend(info)

        # Detect quest acceptance
        if phase == DialogPhase.QUEST_OFFER and selected >= 0:
            _ACCEPT = {"接受", "好的", "没问题", "当然"}
            if choices and selected < len(choices):
                if any(kw in choices[selected] for kw in _ACCEPT):
                    session.quest_accepted = True

        log.debug("[DialogSession] '%s' turn %d: phase=%s, choices=%d",
                  npc_name, turn.turn_number, phase.value, len(choices or []))
        return turn

    def end_session(self, npc_name: str) -> DialogSession | None:
        """End the active dialog session with an NPC."""
        session = self._active_sessions.pop(npc_name, None)
        if session is None:
            return None

        session.completed = True
        session.phase = DialogPhase.FAREWELL
        self._completed_sessions.append(session)
        log.info("[DialogSession] ended with '%s' (%d turns, quest=%s)",
                 npc_name, session.turn_count, session.quest_accepted)
        return session

    def get_npc_history(self, npc_name: str) -> list[DialogSession]:
        """Get all completed sessions with a specific NPC."""
        return [s for s in self._completed_sessions if s.npc_name == npc_name]

    def detect_phase(self, text: str) -> DialogPhase:
        """Public wrapper for phase detection."""
        return self._detect_phase(text)

    def _detect_phase(self, text: str) -> DialogPhase:
        """Detect the current dialog phase from NPC text."""
        scores: dict[DialogPhase, int] = {}
        for phase, keywords in self._PHASE_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in text)
            if count > 0:
                scores[phase] = count

        if not scores:
            return DialogPhase.UNKNOWN

        return max(scores, key=lambda p: scores[p])

    def _extract_key_info(self, text: str) -> list[str]:
        """Extract key information fragments from NPC text."""
        info: list[str] = []
        _INFO_MARKERS = ["位于", "在", "需要", "收集", "找到", "击败", "前往"]
        for marker in _INFO_MARKERS:
            idx = text.find(marker)
            if idx >= 0:
                fragment = text[idx:idx + 30].strip()
                if fragment:
                    info.append(fragment)
        return info
