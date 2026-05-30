"""Quest timeout handler: decision tree for quest completion failures.

Covers S-20: Quest timeout handling with strategic fallback decisions.
When a quest or domain takes too long, this module determines the optimal
next action based on time budget, character state, and strategic priorities.

Integrates with:
- planning/quest_tracker.py for quest state
- planning/strategic_decision_engine.py for action priorities
- execution/daily_loop_executor.py for session management
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timeout reasons
# ---------------------------------------------------------------------------

class TimeoutReason(str, Enum):
    ENEMY_KILL_SLOW = "enemy_kill_slow"         # DPS too low
    EXCESSIVE_DEATHS = "excessive_deaths"        # Survival issues
    MECHANIC_FAILURE = "mechanic_failure"        # Failed puzzle/mechanic
    PATH_BLOCKED = "path_blocked"                # Navigation blocked
    UI_STUCK = "ui_stuck"                        # Menu/popup stuck
    RESOURCE_DEPLETED = "resource_depleted"     # Out of food/resin
    PLAYER_ABANDONED = "player_abandoned"        # User intervention
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Decision outcomes
# ---------------------------------------------------------------------------

class TimeoutDecision(str, Enum):
    RETRY_SAME = "retry_same"          # Retry immediately with same strategy
    RETRY_BUFFED = "retry_buffed"      # Retry with food buffs
    RETRY_TEAM = "retry_team_change"   # Retry with different team
    RETREAT_REST = "retreat_rest"       # Exit and recover (heal/resupply)
    SKIP_QUEST = "skip_quest"           # Skip this quest for now
    REDUCE_DIFFICULTY = "reduce_level" # Lower world level or difficulty
    GIVE_UP = "give_up"                # Abandon quest (very rare)
    SEEK_HELP = "seek_help"            # Search online for strategy


@dataclass(slots=True)
class TimeoutAnalysis:
    """Analysis of why a quest timed out."""
    reason: TimeoutReason
    elapsed_sec: float
    time_budget_sec: float
    exceeded_by_pct: float
    likely_cause: str
    suggested_fix: str
    estimated_difficulty_pct: float = 0.0  # How much harder is this vs. expected


@dataclass(slots=True)
class TimeoutDecisionTree:
    """Output from the timeout decision tree."""
    decision: TimeoutDecision
    reasoning: str
    next_action: str = ""
    retry_count: int = 0
    wait_before_retry_sec: float = 0.0
    use_food_buffs: bool = False
    team_change: tuple[str, ...] | None = None


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------

# Time thresholds by quest type (in seconds)
QUEST_TIME_THRESHOLDS: dict[str, float] = {
    "daily_commission": 120.0,      # 2 min
    "world_quest": 300.0,           # 5 min
    "archon_quest": 600.0,           # 10 min per act
    "domain": 180.0,                 # 3 min
    "ley_line": 60.0,                # 1 min (should be fast)
    "boss": 240.0,                   # 4 min
    "weekly_boss": 300.0,            # 5 min
    "spiral_abyss_chamber": 180.0,   # 3 min per chamber
    "exploration_chest": 45.0,       # 45 sec
}


# ---------------------------------------------------------------------------
# Decision tree engine
# ---------------------------------------------------------------------------

class QuestTimeoutDecisionTree:
    """Determines optimal action when a quest times out.

    Decision tree logic:
    1. If exceeded by < 20%: retry with minor adjustments
    2. If exceeded by 20-50%: retry with buffs or team changes
    3. If exceeded by > 50%: retreat and reassess strategy
    4. Special cases for specific timeout reasons
    """

    # Retry limits
    MAX_RETRIES_SAME = 1
    MAX_RETRIES_BUFFED = 2
    MAX_RETRIES_TEAM_CHANGE = 1
    TOTAL_MAX_RETRIES = 3

    def analyze_timeout(
        self,
        quest_type: str,
        elapsed_sec: float,
        time_budget: float | None = None,
        reason: TimeoutReason = TimeoutReason.UNKNOWN,
        character_levels: dict[str, int] | None = None,
        has_food_buff: bool = False,
    ) -> TimeoutAnalysis:
        """Analyze a timeout situation."""
        if time_budget is None:
            time_budget = QUEST_TIME_THRESHOLDS.get(quest_type, 300.0)

        exceeded = max(0.0, elapsed_sec - time_budget)
        exceeded_pct = (exceeded / time_budget * 100.0) if time_budget > 0 else 999.0

        # Determine likely cause
        likely_cause, suggested_fix = self._diagnose(
            reason, elapsed_sec, time_budget, character_levels
        )

        # Estimate difficulty gap
        difficulty_pct = (elapsed_sec / time_budget * 100.0) if time_budget > 0 else 100.0

        return TimeoutAnalysis(
            reason=reason,
            elapsed_sec=elapsed_sec,
            time_budget_sec=time_budget,
            exceeded_by_pct=exceeded_pct,
            likely_cause=likely_cause,
            suggested_fix=suggested_fix,
            estimated_difficulty_pct=min(difficulty_pct, 200.0),
        )

    def decide(
        self,
        analysis: TimeoutAnalysis,
        quest_type: str,
        retry_count: int = 0,
        current_team: tuple[str, ...] | None = None,
        has_food_buff: bool = False,
        mora_available: int = 0,
    ) -> TimeoutDecisionTree:
        """Execute decision tree based on timeout analysis.

        Args:
            analysis: The timeout analysis results
            quest_type: Type of quest that timed out
            retry_count: Number of previous retries for this quest
            current_team: Current team composition
            has_food_buff: Whether food buffs are currently active
            mora_available: Available mora for food/retry resources

        Returns:
            TimeoutDecisionTree with recommended action
        """
        exceeded = analysis.exceeded_by_pct

        # --- Node: Too many retries ---
        if retry_count >= self.TOTAL_MAX_RETRIES:
            return self._give_up_decision(analysis, quest_type)

        # --- Node: Specific timeout reasons ---
        if analysis.reason == TimeoutReason.RESOURCE_DEPLETED:
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETREAT_REST,
                reasoning="Out of food/resin - retreat to resupply",
                next_action="return_to_world",
                wait_before_retry_sec=30.0,
            )

        if analysis.reason == TimeoutReason.UI_STUCK:
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETRY_SAME,
                reasoning="UI stuck - likely transient, retry after Escape",
                next_action="retry_after_escape",
                wait_before_retry_sec=5.0,
            )

        if analysis.reason == TimeoutReason.PATH_BLOCKED:
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETREAT_REST,
                reasoning="Path blocked - need to find alternate route",
                next_action="retreat_and_reexplore",
                wait_before_retry_sec=15.0,
            )

        # --- Node: Mechanical failure ---
        if analysis.reason == TimeoutReason.MECHANIC_FAILURE:
            if exceeded > 50.0:
                return TimeoutDecisionTree(
                    decision=TimeoutDecision.SEEK_HELP,
                    reasoning="Mechanic failure + large timeout - search guide",
                    next_action="search_online_guide",
                    wait_before_retry_sec=0.0,
                )
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETRY_BUFFED,
                reasoning="Mechanic failure - retry with buffs",
                next_action="retry_with_food",
                use_food_buffs=True,
                wait_before_retry_sec=10.0,
            )

        # --- Node: Excessive deaths ---
        if analysis.reason == TimeoutReason.EXCESSIVE_DEATHS:
            if not has_food_buff and mora_available >= 5000:
                return TimeoutDecisionTree(
                    decision=TimeoutDecision.RETRY_BUFFED,
                    reasoning="Died multiple times - use healing food",
                    next_action="buy_and_use_healing_food",
                    use_food_buffs=True,
                    wait_before_retry_sec=20.0,
                )
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETREAT_REST,
                reasoning="Died multiple times - build character first",
                next_action="focus_on_character_build",
                wait_before_retry_sec=60.0,
            )

        # --- Node: Slow DPS (most common) ---
        if analysis.reason == TimeoutReason.ENEMY_KILL_SLOW:
            if exceeded < 20.0:
                # Minor overage: retry with same strategy
                return TimeoutDecisionTree(
                    decision=TimeoutDecision.RETRY_SAME,
                    reasoning=f"Slightly over time ({exceeded:.0f}%) - retry",
                    next_action="retry_same_strategy",
                    retry_count=retry_count + 1,
                    wait_before_retry_sec=5.0,
                )
            if exceeded < 50.0:
                # Medium overage: try with food buffs
                if not has_food_buff and mora_available >= 3000:
                    return TimeoutDecisionTree(
                        decision=TimeoutDecision.RETRY_BUFFED,
                        reasoning=f"Moderately over time ({exceeded:.0f}%) - use buffs",
                        next_action="use_atk_buff_food",
                        use_food_buffs=True,
                        retry_count=retry_count + 1,
                        wait_before_retry_sec=15.0,
                    )
                return TimeoutDecisionTree(
                    decision=TimeoutDecision.RETREAT_REST,
                    reasoning=f"Moderately over time ({exceeded:.0f}%) - too weak",
                    next_action="return_and_build_character",
                    wait_before_retry_sec=30.0,
                )
            # Large overage: retreat and build
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETREAT_REST,
                reasoning=f"Greatly over time ({exceeded:.0f}%) - need more power",
                next_action="focus_on_weapon_and_talent",
                wait_before_retry_sec=60.0,
            )

        # --- Node: Default handling ---
        if exceeded < 30.0:
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETRY_SAME,
                reasoning=f"Minor timeout ({exceeded:.0f}%) - retry",
                next_action="retry",
                retry_count=retry_count + 1,
                wait_before_retry_sec=5.0,
            )
        if exceeded < 60.0:
            return TimeoutDecisionTree(
                decision=TimeoutDecision.RETRY_BUFFED,
                reasoning=f"Moderate timeout ({exceeded:.0f}%) - try buffs",
                next_action="retry_with_food",
                use_food_buffs=True,
                retry_count=retry_count + 1,
                wait_before_retry_sec=10.0,
            )
        return TimeoutDecisionTree(
            decision=TimeoutDecision.RETREAT_REST,
            reasoning=f"Major timeout ({exceeded:.0f}%) - need more strength",
            next_action="build_character_before_retry",
            wait_before_retry_sec=60.0,
        )

    def _diagnose(
        self,
        reason: TimeoutReason,
        elapsed: float,
        budget: float,
        char_levels: dict[str, int] | None,
    ) -> tuple[str, str]:
        """Diagnose likely cause and suggested fix."""
        if reason == TimeoutReason.ENEMY_KILL_SLOW:
            if char_levels:
                avg_level = sum(char_levels.values()) / len(char_levels)
                # Threshold: characters should be at least level 40 for most content
                if avg_level < 40:
                    return (
                        "Characters under-levelled for this content",
                        "Level up characters and weapons before retrying",
                    )
            return (
                "Damage output too low for time constraint",
                "Upgrade weapons, talents, or bring stronger team",
            )

        if reason == TimeoutReason.EXCESSIVE_DEATHS:
            return (
                "Team lacks survivability for this content",
                "Use shield/healer characters or bring defensive food",
            )

        if reason == TimeoutReason.MECHANIC_FAILURE:
            return (
                "Failed to understand or execute quest mechanic",
                "Search guide or watch tutorial for this mechanic",
            )

        if reason == TimeoutReason.UI_STUCK:
            return (
                "Game UI was stuck or unresponsive",
                "Press Escape and retry - likely a UI bug",
            )

        if reason == TimeoutReason.PATH_BLOCKED:
            return (
                "Navigation blocked or failed to find path",
                "Find alternate route or use waypoint",
            )

        return (
            "Unknown cause - possibly network or game issue",
            "Try restarting the quest or checking game status",
        )

    def _give_up_decision(
        self,
        analysis: TimeoutAnalysis,
        quest_type: str,
    ) -> TimeoutDecisionTree:
        """Generate give-up decision with strategic fallback."""
        if quest_type in ("archon_quest",):
            # Archon quests are critical - seek help first
            return TimeoutDecisionTree(
                decision=TimeoutDecision.SEEK_HELP,
                reasoning=f"Too many retries for {quest_type} - search guide",
                next_action="search_online_for_strategy",
            )
        if quest_type in ("daily_commission", "world_quest"):
            # Non-critical quests: skip and move on
            return TimeoutDecisionTree(
                decision=TimeoutDecision.SKIP_QUEST,
                reasoning=f"Too many retries for {quest_type} - skip for now",
                next_action="move_to_next_quest",
            )
        # Domain/boss: reduce difficulty
        return TimeoutDecisionTree(
            decision=TimeoutDecision.REDUCE_DIFFICULTY,
            reasoning=f"Too many retries - reduce difficulty setting",
            next_action="lower_world_level_or_difficulty",
        )


# ---------------------------------------------------------------------------
# Session timeout manager
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SessionTimeout:
    """Tracks session-level timeout decisions."""
    quest_id: str
    retry_count: int = 0
    last_timeout_at: float = 0.0
    total_time_spent_sec: float = 0.0
    decision_history: list[str] = field(default_factory=list)


class QuestTimeoutManager:
    """Manages quest timeout tracking and decision-making across sessions.

    Maintains state about which quests have timed out previously and how
    they were resolved, to inform future timeout decisions.
    """

    def __init__(self) -> None:
        self._session_timeouts: dict[str, SessionTimeout] = {}
        self._decision_tree = QuestTimeoutDecisionTree()

    def record_timeout(
        self,
        quest_id: str,
        analysis: TimeoutAnalysis,
        decision: TimeoutDecisionTree,
    ) -> None:
        """Record a timeout event and its resolution."""
        session = self._session_timeouts.get(quest_id)
        if session is None:
            session = SessionTimeout(quest_id=quest_id)
            self._session_timeouts[quest_id] = session

        session.retry_count += 1
        session.last_timeout_at = analysis.elapsed_sec
        session.total_time_spent_sec += analysis.elapsed_sec
        session.decision_history.append(decision.decision.value)

        log.info("[TimeoutMgr] quest=%s retry=%d decision=%s elapsed=%.0fs",
                 quest_id, session.retry_count, decision.decision.value, analysis.elapsed_sec)

    def should_skip_quest(self, quest_id: str, max_retries: int = 3) -> bool:
        """Check if a quest should be skipped based on history."""
        session = self._session_timeouts.get(quest_id)
        if session is None:
            return False
        return session.retry_count >= max_retries

    def get_timeout_stats(self, quest_id: str) -> dict[str, float]:
        """Get timeout statistics for a quest."""
        session = self._session_timeouts.get(quest_id)
        if session is None:
            return {}
        return {
            "retry_count": float(session.retry_count),
            "total_time_spent": session.total_time_spent_sec,
            "avg_time_per_attempt": session.total_time_spent_sec / max(1, session.retry_count),
        }

    def clear_quest(self, quest_id: str) -> None:
        """Clear timeout tracking for a completed quest."""
        if quest_id in self._session_timeouts:
            del self._session_timeouts[quest_id]

    def decide_next_action(
        self,
        quest_id: str,
        quest_type: str,
        elapsed_sec: float,
        reason: TimeoutReason = TimeoutReason.UNKNOWN,
        current_team: tuple[str, ...] | None = None,
        has_food_buff: bool = False,
        mora_available: int = 0,
    ) -> TimeoutDecisionTree:
        """Main entry point for timeout decision-making.

        Analyzes the timeout and produces a decision tree recommendation.
        """
        # Get current retry count
        session = self._session_timeouts.get(quest_id)
        retry_count = session.retry_count if session else 0

        # Analyze
        analysis = self._decision_tree.analyze_timeout(
            quest_type=quest_type,
            elapsed_sec=elapsed_sec,
            reason=reason,
        )

        # Decide
        decision = self._decision_tree.decide(
            analysis=analysis,
            quest_type=quest_type,
            retry_count=retry_count,
            current_team=current_team,
            has_food_buff=has_food_buff,
            mora_available=mora_available,
        )

        # Record
        self.record_timeout(quest_id, analysis, decision)

        return decision