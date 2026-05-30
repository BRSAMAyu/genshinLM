"""Quest UI management: quest log, world quest discovery, commissions, completion.

Handles Q-05 through Q-09 capability requirements:
- Quest log browsing and tracking
- World quest discovery and acceptance
- Commission identification and routing
- Quest completion confirmation
- NPC occupation handling
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


class QuestCategory(str, Enum):
    ARCHON = "archon"
    STORY = "story"
    WORLD = "world"
    COMMISSION = "commission"
    EVENT = "event"


class QuestStatus(str, Enum):
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    TRACKED = "tracked"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class QuestEntry:
    """A single quest entry from the quest log."""
    quest_id: str
    title: str
    category: QuestCategory
    status: QuestStatus = QuestStatus.NOT_STARTED
    chapter: str = ""
    description: str = ""
    region: str = ""
    recommended_ar: int = 0
    is_tracked: bool = False


@dataclass(slots=True)
class CommissionInfo:
    """Daily commission quest information."""
    commission_id: str
    name: str
    region: str = ""
    commission_type: str = ""     # "combat", "delivery", "timed", "photography", "investigation"
    location: tuple[float, float] | None = None
    is_complete: bool = False


@dataclass(slots=True)
class QuestCompletionEvent:
    """Quest completion notification data."""
    quest_id: str
    rewards_claimed: bool = False
    exp_gained: int = 0
    primogems_gained: int = 0
    mora_gained: int = 0
    items_gained: list[str] = field(default_factory=list)


class QuestLogManager:
    """Manages quest log state from UI interactions (Q-05).

    Tracks which quests are visible, active, tracked, and completed.
    Works with ui_flow_engine to browse the quest menu.
    """

    def __init__(self) -> None:
        self._quests: dict[str, QuestEntry] = {}
        self._tracked_quest_id: str | None = None
        self._active_category: QuestCategory = QuestCategory.ARCHON

    @property
    def tracked_quest(self) -> QuestEntry | None:
        if self._tracked_quest_id:
            return self._quests.get(self._tracked_quest_id)
        return None

    @property
    def active_quests(self) -> list[QuestEntry]:
        return [q for q in self._quests.values() if q.status == QuestStatus.ACTIVE]

    def update_quest(self, entry: QuestEntry) -> None:
        self._quests[entry.quest_id] = entry
        if entry.is_tracked:
            self._tracked_quest_id = entry.quest_id

    def set_tracked(self, quest_id: str) -> bool:
        if quest_id in self._quests:
            for q in self._quests.values():
                q.is_tracked = False
            self._quests[quest_id].is_tracked = True
            self._tracked_quest_id = quest_id
            return True
        return False

    def mark_completed(self, quest_id: str, event: QuestCompletionEvent | None = None) -> None:
        if quest_id in self._quests:
            self._quests[quest_id].status = QuestStatus.COMPLETED
            if self._tracked_quest_id == quest_id:
                self._tracked_quest_id = None
            if event:
                log.info("[QuestLog] completed %s: +%d EXP, +%d primos",
                         quest_id, event.exp_gained, event.primogems_gained)

    def get_quests_by_category(self, category: QuestCategory) -> list[QuestEntry]:
        return [q for q in self._quests.values() if q.category == category]

    def browse_category(self, category: QuestCategory) -> list[QuestEntry]:
        """Switch to a category tab and return quests (simulates UI browsing)."""
        self._active_category = category
        return self.get_quests_by_category(category)

    def save_state(self) -> dict[str, Any]:
        return {
            "quests": {qid: {
                "title": q.title, "category": q.category.value,
                "status": q.status.value, "tracked": q.is_tracked,
            } for qid, q in self._quests.items()},
            "tracked": self._tracked_quest_id,
        }


class WorldQuestDiscovery:
    """Discovers and accepts world quests (Q-06).

    World quests appear as yellow exclamation marks above NPC heads
    or as markers on the map. This module tracks discovered quests
    and manages the acceptance flow.
    """

    def __init__(self) -> None:
        self._discovered: dict[str, QuestEntry] = {}
        self._pending_accept: list[str] = []
        self._declined: set[str] = set()

    def discover_quest(self, npc_name: str, location: tuple[float, float],
                       quest_title: str = "") -> QuestEntry:
        """Register a newly discovered world quest from NPC interaction."""
        qid = f"wq_{npc_name}_{hashlib.md5(quest_title.encode()).hexdigest()[:8]}"
        entry = QuestEntry(
            quest_id=qid,
            title=quest_title or f"World Quest from {npc_name}",
            category=QuestCategory.WORLD,
            status=QuestStatus.NOT_STARTED,
            region="",
        )
        self._discovered[qid] = entry
        self._pending_accept.append(qid)
        log.info("[WorldQuest] discovered: %s from %s", quest_title, npc_name)
        return entry

    def accept_quest(self, quest_id: str) -> bool:
        if quest_id in self._discovered and quest_id in self._pending_accept:
            self._discovered[quest_id].status = QuestStatus.ACTIVE
            self._pending_accept.remove(quest_id)
            log.info("[WorldQuest] accepted: %s", quest_id)
            return True
        return False

    def decline_quest(self, quest_id: str) -> None:
        self._declined.add(quest_id)
        if quest_id in self._pending_accept:
            self._pending_accept.remove(quest_id)

    @property
    def pending_quests(self) -> list[QuestEntry]:
        return [self._discovered[qid] for qid in self._pending_accept
                if qid in self._discovered]


class CommissionManager:
    """Manages daily commissions (Q-07).

    Identifies commission type, location, and completion status.
    4 commissions per day + Katheryne reward.
    """

    def __init__(self) -> None:
        self._commissions: dict[str, CommissionInfo] = {}
        self._katheryne_reward_claimed: bool = False
        self._day: str = ""

    def add_commission(self, info: CommissionInfo) -> None:
        self._commissions[info.commission_id] = info

    def complete_commission(self, commission_id: str) -> None:
        if commission_id in self._commissions:
            self._commissions[commission_id].is_complete = True
            log.info("[Commission] completed: %s", commission_id)

    @property
    def all_complete(self) -> bool:
        return (len(self._commissions) >= 4
                and all(c.is_complete for c in self._commissions.values()))

    @property
    def incomplete_commissions(self) -> list[CommissionInfo]:
        return [c for c in self._commissions.values() if not c.is_complete]

    def should_claim_katheryne(self) -> bool:
        return self.all_complete and not self._katheryne_reward_claimed

    def claim_katheryne_reward(self) -> int:
        """Claim Katheryne reward. Returns primogems gained (typically 20)."""
        if self.should_claim_katheryne():
            self._katheryne_reward_claimed = True
            log.info("[Commission] claimed Katheryne reward")
            return 20
        return 0

    def reset_daily(self, day: str = "") -> None:
        """Reset for new daily reset."""
        self._commissions.clear()
        self._katheryne_reward_claimed = False
        self._day = day


class QuestCompletionDetector:
    """Detects quest completion from screen state (Q-08).

    Monitors screen for quest completion popups, reward screens,
    and objective fulfillment indicators.
    """

    # Screen states that indicate quest progression
    COMPLETION_INDICATORS = {
        "quest_complete_popup",
        "reward_screen",
        "achievement_popup",
        "level_up_notification",
    }

    OBJECTIVE_KEYWORDS = {
        "defeated": "combat",
        "collected": "collection",
        "reached": "navigation",
        "spoken": "dialog",
        "investigated": "investigation",
        "completed": "generic",
    }

    def check_completion(self, screen_state: str,
                         screen_text: str = "",
                         notifications: list[str] | None = None) -> QuestCompletionEvent | None:
        """Check if a quest has been completed based on screen state."""
        if screen_state in ("quest_complete", "reward_screen"):
            return QuestCompletionEvent(
                quest_id=self._extract_quest_id(screen_text),
                rewards_claimed=screen_state == "reward_screen",
            )

        if notifications:
            for notif in notifications:
                lower = notif.lower()
                if "quest complete" in lower or "任务完成" in lower:
                    return QuestCompletionEvent(
                        quest_id=self._extract_quest_id(notif),
                        rewards_claimed=False,
                    )

        return None

    def _extract_quest_id(self, text: str) -> str:
        """Extract quest ID from notification text (best effort)."""
        if not text:
            return "unknown"
        return text[:50].strip()


class NPCOccupationHandler:
    """Handles NPC occupation conflicts (Q-09).

    When an NPC is occupied by another quest, tracks the conflict
    and recommends resolution (complete blocking quest first, or wait).
    """

    def __init__(self) -> None:
        self._occupied_npcs: dict[str, str] = {}   # npc_name -> blocking_quest_id

    def mark_occupied(self, npc_name: str, blocking_quest: str = "") -> None:
        self._occupied_npcs[npc_name] = blocking_quest
        log.info("[NPC] %s is occupied by quest: %s", npc_name, blocking_quest)

    def mark_available(self, npc_name: str) -> None:
        self._occupied_npcs.pop(npc_name, None)

    def is_available(self, npc_name: str) -> bool:
        return npc_name not in self._occupied_npcs

    def get_blocking_quest(self, npc_name: str) -> str | None:
        return self._occupied_npcs.get(npc_name)

    def resolve_conflict(self, npc_name: str,
                         active_quests: list[QuestEntry]) -> dict[str, Any]:
        """Recommend how to resolve NPC occupation."""
        blocking = self._occupied_npcs.get(npc_name)
        if not blocking:
            return {"action": "proceed", "reason": "npc_available"}

        for quest in active_quests:
            if quest.quest_id == blocking:
                return {
                    "action": "complete_blocking_quest",
                    "blocking_quest": blocking,
                    "reason": f"Complete '{quest.title}' first to free NPC",
                }

        return {
            "action": "wait",
            "reason": f"NPC occupied by unknown quest {blocking}",
            "blocking_quest": blocking,
        }


class QuestUIManager:
    """Unified quest UI management facade.

    Combines quest log, world quest discovery, commissions,
    completion detection, and NPC occupation into a single interface.
    """

    def __init__(self) -> None:
        self.log_manager = QuestLogManager()
        self.world_quest_discovery = WorldQuestDiscovery()
        self.commission_manager = CommissionManager()
        self.completion_detector = QuestCompletionDetector()
        self.npc_occupation = NPCOccupationHandler()

    def get_next_action(self, current_ar: int) -> dict[str, Any]:
        """Determine the next quest-related action to take."""
        # Priority 0: AR breakthrough check (only if explicitly needed)
        # This is checked externally; the router doesn't auto-detect AR caps from screen.

        # Priority 1: Complete remaining commissions
        if not self.commission_manager.all_complete:
            incomplete = self.commission_manager.incomplete_commissions
            if incomplete:
                return {
                    "action": "complete_commission",
                    "target": incomplete[0].commission_id,
                    "type": incomplete[0].commission_type,
                }

        # Priority 2: Claim Katheryne reward
        if self.commission_manager.should_claim_katheryne():
            return {"action": "claim_katheryne_reward"}

        # Priority 3: Continue tracked quest
        tracked = self.log_manager.tracked_quest
        if tracked:
            return {
                "action": "continue_quest",
                "quest_id": tracked.quest_id,
                "category": tracked.category.value,
            }

        # Priority 4: Accept pending world quests
        pending = self.world_quest_discovery.pending_quests
        if pending:
            return {
                "action": "accept_world_quest",
                "quest_id": pending[0].quest_id,
            }

        # Priority 5: Browse quest log for next quest
        archon_quests = self.log_manager.get_quests_by_category(QuestCategory.ARCHON)
        active_archon = [q for q in archon_quests if q.status == QuestStatus.ACTIVE]
        if active_archon:
            return {
                "action": "track_quest",
                "quest_id": active_archon[0].quest_id,
            }

        return {"action": "explore", "reason": "no_active_quests"}
