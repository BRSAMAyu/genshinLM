"""R-43: AR stage progression planner — AR-dependent progression priorities.

Provides stage-aware guidance for autonomous character progression.
AR 1-20: Exploration + ascension + talent basics
AR 20-35: Talent upgrades + weapon enhance + 4-star artifacts
AR 35-45: 4-star artifact farming + boss materials
AR 45+: 5-star artifact farming + talent crown priorities
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProgressionPriority:
    priority_name: str
    ar_range: tuple[int, int]
    focus_areas: tuple[str, ...]
    daily_resin_budget: tuple[str, float]  # (domain_name, resin_fraction)
    avoid: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ARStagePlan:
    ar_stage: str
    ar_range: tuple[int, int]
    priorities: tuple[ProgressionPriority, ...]
    daily_tasks: tuple[str, ...]
    weekly_tasks: tuple[str, ...]


# AR stage definitions with progression priorities
AR_STAGES: tuple[ARStagePlan, ...] = (
    ARStagePlan(
        ar_stage="early",
        ar_range=(1, 20),
        priorities=(
            ProgressionPriority(
                priority_name="exploration",
                ar_range=(1, 20),
                focus_areas=("unlock_teleports", "open_chests", "collect_anemoculi"),
                daily_resin_budget=("boss", 0.5),
                notes="Focus on exploration to unlock map and earn primogems",
            ),
            ProgressionPriority(
                priority_name="character_ascension",
                ar_range=(1, 20),
                focus_areas=("ascend_characters", "level_up_main_dps", "equip_weapons"),
                daily_resin_budget=("boss", 0.3),
                notes="Ascend main DPS to max level for current AR cap",
            ),
            ProgressionPriority(
                priority_name="talent_basics",
                ar_range=(15, 20),
                focus_areas=("upgrade_burst_talent", "upgrade_skill_talent"),
                daily_resin_budget=("talent_domain", 0.2),
                notes="Talent domains unlock at AR15+",
            ),
        ),
        daily_tasks=("commissions", "spend_resin", "expedition"),
        weekly_tasks=("weekly_boss_discount",),
    ),
    ARStagePlan(
        ar_stage="mid_early",
        ar_range=(20, 35),
        priorities=(
            ProgressionPriority(
                priority_name="talent_upgrade",
                ar_range=(20, 35),
                focus_areas=("upgrade_all_talents", "talent_domain_farming"),
                daily_resin_budget=("talent_domain", 0.4),
                notes="Talent upgrade priority: burst > skill > normal_attack",
            ),
            ProgressionPriority(
                priority_name="weapon_enhance",
                ar_range=(20, 35),
                focus_areas=("enhance_weapons", "forge_f2p_weapons"),
                daily_resin_budget=("weapon_domain", 0.3),
                notes="Max enhance F2P weapons for main team",
            ),
            ProgressionPriority(
                priority_name="artifact_basics",
                ar_range=(25, 35),
                focus_areas=("equip_4star_artifacts", "set_bonus_priority"),
                daily_resin_budget=("artifact_domain", 0.3),
                notes="Use 4-star artifacts from bosses; don't farm domains yet",
                avoid=("5_star_artifact_farming",),
            ),
        ),
        daily_tasks=("commissions", "spend_resin", "expedition", "talent_domain"),
        weekly_tasks=("weekly_boss_discount", "bounty_request"),
    ),
    ARStagePlan(
        ar_stage="mid_late",
        ar_range=(35, 45),
        priorities=(
            ProgressionPriority(
                priority_name="boss_materials",
                ar_range=(35, 45),
                focus_areas=("farm_boss_materials", "ascend_all_characters"),
                daily_resin_budget=("boss", 0.4),
                notes="Stock up on boss materials for character ascension",
            ),
            ProgressionPriority(
                priority_name="artifact_prep",
                ar_range=(35, 45),
                focus_areas=("farm_4star_artifacts", "build_support_sets"),
                daily_resin_budget=("artifact_domain", 0.4),
                notes="Build functional 4pc sets for main team from domains",
            ),
            ProgressionPriority(
                priority_name="weapon_refinement",
                ar_range=(35, 45),
                focus_areas=("refine_f2p_weapons", "max_weapon_levels"),
                daily_resin_budget=("weapon_domain", 0.2),
                notes="R5 F2P weapons before AR45",
            ),
        ),
        daily_tasks=("commissions", "spend_resin", "expedition", "domain_farming"),
        weekly_tasks=("weekly_boss_discount", "bounty_request"),
    ),
    ARStagePlan(
        ar_stage="endgame_prep",
        ar_range=(45, 55),
        priorities=(
            ProgressionPriority(
                priority_name="artifact_farming",
                ar_range=(45, 55),
                focus_areas=("farm_5star_artifacts", "correct_main_stats", "set_bonuses"),
                daily_resin_budget=("artifact_domain", 0.7),
                notes="AR45 unlocks guaranteed 5-star artifacts from domains",
            ),
            ProgressionPriority(
                priority_name="talent_maxing",
                ar_range=(45, 55),
                focus_areas=("max_talents_8+", "crown_priority_talents"),
                daily_resin_budget=("talent_domain", 0.2),
                notes="Push talents to 8+ for main DPS",
            ),
            ProgressionPriority(
                priority_name="weekly_boss_materials",
                ar_range=(45, 55),
                focus_areas=("weekly_boss_farming", "talent_book_conversion"),
                daily_resin_budget=("weekly_boss", 0.1),
                notes="Weekly boss materials for talent levels 9-10",
            ),
        ),
        daily_tasks=("commissions", "spend_resin", "expedition", "artifact_domains"),
        weekly_tasks=("weekly_boss_discount", "bounty_request"),
    ),
    ARStagePlan(
        ar_stage="endgame",
        ar_range=(55, 60),
        priorities=(
            ProgressionPriority(
                priority_name="artifact_optimization",
                ar_range=(55, 60),
                focus_areas=("artifact_substats", "strongbox_fodder", "set_optimization"),
                daily_resin_budget=("artifact_domain", 0.6),
                notes="Farm for substats; use strongbox for missing pieces",
            ),
            ProgressionPriority(
                priority_name="team_building",
                ar_range=(55, 60),
                focus_areas=("build_second_team", "abyss_preparation", "support_investment"),
                daily_resin_budget=("talent_domain", 0.2),
                notes="Build a second team for Spiral Abyss",
            ),
            ProgressionPriority(
                priority_name="crown_talents",
                ar_range=(55, 60),
                focus_areas=("crown_core_talents", "weekly_boss_materials"),
                daily_resin_budget=("weekly_boss", 0.2),
                notes="Use crowns on highest-value talents only",
            ),
        ),
        daily_tasks=("commissions", "spend_resin", "expedition", "artifact_domains"),
        weekly_tasks=("weekly_boss_discount", "bounty_request", "teapot"),
    ),
)


class ARStagePlanner:
    """Plan progression priorities based on Adventure Rank."""

    def get_stage(self, ar: int) -> ARStagePlan:
        """Get the AR stage plan for a given Adventure Rank.

        Args:
            ar: Current Adventure Rank (1-60).

        Returns:
            ARStagePlan with priorities, daily/weekly tasks.
        """
        for stage in AR_STAGES:
            if stage.ar_range[0] <= ar <= stage.ar_range[1]:
                return stage
        # Default to endgame for AR > 60 or < 1
        return AR_STAGES[-1]

    def get_priority_names(self, ar: int) -> list[str]:
        """Get priority names for current AR."""
        stage = self.get_stage(ar)
        return [p.priority_name for p in stage.priorities]

    def get_resin_budget(self, ar: int) -> list[tuple[str, float]]:
        """Get recommended resin budget allocation for current AR."""
        stage = self.get_stage(ar)
        return [(p.daily_resin_budget[0], p.daily_resin_budget[1]) for p in stage.priorities]

    def get_avoid_list(self, ar: int) -> list[str]:
        """Get activities to avoid at current AR."""
        stage = self.get_stage(ar)
        avoid: list[str] = []
        for p in stage.priorities:
            avoid.extend(p.avoid)
        return avoid

    def get_daily_tasks(self, ar: int) -> list[str]:
        """Get recommended daily tasks for current AR."""
        stage = self.get_stage(ar)
        return list(stage.daily_tasks)

    def get_weekly_tasks(self, ar: int) -> list[str]:
        """Get recommended weekly tasks for current AR."""
        stage = self.get_stage(ar)
        return list(stage.weekly_tasks)

    def should_farm_artifacts(self, ar: int) -> bool:
        """Whether 5-star artifact farming is worthwhile at current AR."""
        return ar >= 45

    def should_farm_talents(self, ar: int) -> bool:
        """Whether talent farming is available at current AR."""
        return ar >= 15
