"""Achievement tracker: tracking and prioritizing achievements for primogem rewards.

Covers S-37: Tracking achievement completion and optimal order for primogem farming.
Identifies easiest achievements, tracks progress, and recommends completion order.

Integrates with:
- knowledge/online_guide_system.py for achievement guides
- planning/quest_tracker.py for quest-based achievements
- planning/exploration_engine.py for exploration achievements
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Achievement categories
# ---------------------------------------------------------------------------

class AchievementCategory(str, Enum):
    ADVENTURE = "adventure"          # General exploration
    COMBAT = "combat"                # Battle achievements
    QUEST = "quest"                  # Quest completion
    EXPLORATION = "exploration"      # World exploration
    COLLECTION = "collection"        # Collection achievements
    DIFFICULT = "difficult"          # Hard achievements


# ---------------------------------------------------------------------------
# Achievement data
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Achievement:
    """A single achievement."""
    achievement_id: str
    name: str
    description: str
    category: AchievementCategory
    primogem_reward: int = 5        # Standard: 5, some: 10, rare: 20
    difficulty: float = 1.0         # 1.0 (easy) to 5.0 (hard)
    prerequisites: list[str] = field(default_factory=list)
    is_secret: bool = False
    is_time_limited: bool = False


@dataclass(slots=True)
class AchievementProgress:
    """Progress tracking for an achievement."""
    achievement_id: str
    is_completed: bool = False
    progress_pct: float = 0.0
    last_checked: float = 0.0
    completion_date: str = ""


@dataclass(slots=True)
class AchievementRecommendation:
    """Recommendation for next achievement to complete."""
    achievement: Achievement
    estimated_time_min: float
    priority_score: float  # primogem / time
    prerequisites_met: bool
    recommended_order: int = 0


# ---------------------------------------------------------------------------
# Achievement database (subset of actual achievements)
# ---------------------------------------------------------------------------

ACHIEVEMENTS_DB: dict[str, Achievement] = {
    # Easy achievements (< 5 min, high priority)
    "archon_1": Achievement(
        achievement_id="archon_1",
        name="Prologue: Of the Land Beneath",
        description="Complete the Mondstadt Archon Quest",
        category=AchievementCategory.QUEST,
        primogem_reward=20,
        difficulty=1.5,
    ),
    "exploration_mondstadt": Achievement(
        achievement_id="exploration_mondstadt",
        name="Mondstadt Adventurer",
        description="Explore Mondstadt region",
        category=AchievementCategory.EXPLORATION,
        primogem_reward=10,
        difficulty=2.0,
    ),
    "first_domain": Achievement(
        achievement_id="first_domain",
        name="Challenger: Exploring a Domain",
        description="Complete your first domain",
        category=AchievementCategory.COMBAT,
        primogem_reward=5,
        difficulty=1.0,
    ),
    "first_character": Achievement(
        achievement_id="first_character",
        name="New Beginnings",
        description="Level up a character",
        category=AchievementCategory.ADVENTURE,
        primogem_reward=5,
        difficulty=1.0,
    ),
    "first_weapon": Achievement(
        achievement_id="first_weapon",
        name="Armed and Ready",
        description="Enhance a weapon",
        category=AchievementCategory.ADVENTURE,
        primogem_reward=5,
        difficulty=1.0,
    ),
    # Medium difficulty achievements
    "defeat_500": Achievement(
        achievement_id="defeat_500",
        name="Slayer of Many",
        description="Defeat 500 enemies",
        category=AchievementCategory.COMBAT,
        primogem_reward=10,
        difficulty=2.5,
    ),
    "collect_100_chests": Achievement(
        achievement_id="collect_100_chests",
        name="Treasure Hunter",
        description="Open 100 chests",
        category=AchievementCategory.EXPLORATION,
        primogem_reward=10,
        difficulty=2.0,
    ),
    "all_commissions": Achievement(
        achievement_id="all_commissions",
        name="Daylight in the City of Freedom",
        description="Complete all 4 daily commissions",
        category=AchievementCategory.QUEST,
        primogem_reward=5,
        difficulty=1.5,
    ),
    # Harder achievements
    "defeat_10000": Achievement(
        achievement_id="defeat_10000",
        name="Archon of War",
        description="Defeat 10,000 enemies",
        category=AchievementCategory.COMBAT,
        primogem_reward=20,
        difficulty=4.5,
    ),
    "full_exploration": Achievement(
        achievement_id="full_exploration",
        name="World Explorer",
        description="Achieve 100% exploration in all regions",
        category=AchievementCategory.EXPLORATION,
        primogem_reward=20,
        difficulty=5.0,
    ),
    "spiral_abyss_9": Achievement(
        achievement_id="spiral_abyss_9",
        name="Spiral Abyss Challenger",
        description="Reach Spiral Abyss Floor 9",
        category=AchievementCategory.COMBAT,
        primogem_reward=30,
        difficulty=4.0,
    ),
}


# ---------------------------------------------------------------------------
# Achievement tracker
# ---------------------------------------------------------------------------

class AchievementTracker:
    """Tracks achievement progress and recommends completion order.

    Optimizes primogem farming by recommending achievable achievements
    based on current progress and play session.
    """

    def __init__(self) -> None:
        self._progress: dict[str, AchievementProgress] = {}
        self._completion_order: list[str] = []

    def update_progress(
        self,
        achievement_id: str,
        progress_pct: float,
    ) -> None:
        """Update progress for an achievement."""
        progress = self._progress.get(achievement_id, AchievementProgress(achievement_id))
        progress.progress_pct = min(100.0, progress_pct)
        progress.last_checked = 0.0  # Would use time.perf_counter()
        self._progress[achievement_id] = progress

        if progress_pct >= 100.0 and not progress.is_completed:
            progress.is_completed = True
            progress.completion_date = self._get_date_string()

    def mark_completed(self, achievement_id: str) -> None:
        """Mark an achievement as completed."""
        progress = self._progress.get(achievement_id)
        if progress is None:
            progress = AchievementProgress(achievement_id=achievement_id)
            self._progress[achievement_id] = progress
        progress.is_completed = True
        progress.progress_pct = 100.0
        progress.completion_date = self._get_date_string()

        if achievement_id not in self._completion_order:
            self._completion_order.append(achievement_id)

    def get_recommendations(
        self,
        max_time_min: float = 30.0,
        include_completed: bool = False,
    ) -> list[AchievementRecommendation]:
        """Get recommended achievements to complete next.

        Args:
            max_time_min: Maximum time available
            include_completed: Include already completed achievements

        Returns:
            Sorted list of AchievementRecommendation
        """
        recommendations: list[AchievementRecommendation] = []
        remaining_time = max_time_min * 60  # Convert to seconds

        for achievement_id, achievement in ACHIEVEMENTS_DB.items():
            progress = self._progress.get(achievement_id)

            # Skip completed unless requested
            if progress and progress.is_completed:
                if not include_completed:
                    continue

            # Check prerequisites
            prereqs_met = self._check_prerequisites(achievement.prerequisites)

            # Estimate time based on difficulty
            est_time_sec = achievement.difficulty * 60  # difficulty 1 = 1 min
            if remaining_time < est_time_sec:
                continue

            # Calculate priority score (primogem per minute)
            est_time_min = est_time_sec / 60.0
            priority_score = achievement.primogem_reward / max(est_time_min, 1.0)

            # Boost priority for incomplete achievements
            if progress and progress.progress_pct > 0:
                priority_score *= 1.5  # Already started, easy to finish

            recommendations.append(AchievementRecommendation(
                achievement=achievement,
                estimated_time_min=est_time_min,
                priority_score=priority_score,
                prerequisites_met=prereqs_met,
                recommended_order=len(recommendations),
            ))

            remaining_time -= est_time_sec

        # Sort by priority score
        recommendations.sort(key=lambda r: r.priority_score, reverse=True)
        return recommendations[:10]  # Return top 10

    def get_category_progress(self, category: AchievementCategory) -> dict[str, float]:
        """Get progress stats for an achievement category."""
        category_achievements = [
            a for a in ACHIEVEMENTS_DB.values() if a.category == category
        ]
        total = len(category_achievements)
        completed = sum(
            1 for a in category_achievements
            if self._progress.get(a.achievement_id, AchievementProgress(a.achievement_id)).is_completed
        )
        return {
            "total": total,
            "completed": completed,
            "progress_pct": (completed / max(total, 1)) * 100.0,
        }

    def get_total_primogem(self) -> dict[str, int]:
        """Calculate total primogems from achievements."""
        total = 0
        earned = 0

        for achievement_id, achievement in ACHIEVEMENTS_DB.items():
            total += achievement.primogem_reward
            progress = self._progress.get(achievement_id)
            if progress and progress.is_completed:
                earned += achievement.primogem_reward

        return {
            "total_available": total,
            "earned": earned,
            "remaining": total - earned,
        }

    def _check_prerequisites(self, prereqs: list[str]) -> bool:
        """Check if all prerequisites are met."""
        for prereq_id in prereqs:
            progress = self._progress.get(prereq_id)
            if progress is None or not progress.is_completed:
                return False
        return True

    def _get_date_string(self) -> str:
        """Get current date string."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")

    def get_easy_achievements(self, max_difficulty: float = 2.0) -> list[Achievement]:
        """Get achievements below a difficulty threshold."""
        easy = []
        for achievement in ACHIEVEMENTS_DB.values():
            if achievement.difficulty <= max_difficulty:
                progress = self._progress.get(achievement.achievement_id)
                if progress is None or not progress.is_completed:
                    easy.append(achievement)
        return easy


# ---------------------------------------------------------------------------
# Achievement flow integration
# ---------------------------------------------------------------------------

class AchievementFlowBuilder:
    """Builds UI flows for achievement completion."""

    @staticmethod
    def build_achievement_check_flow(achievement_id: str) -> list[str]:
        """Build a flow to check an achievement's completion.

        Returns list of UI actions.
        """
        flow = [
            "press_f1",  # Open adventure handbook
            "wait_state:adventure_handbook",
            "click:0.80,0.10",  # Click Achievements tab
            f"search:{achievement_id}",
        ]
        return flow