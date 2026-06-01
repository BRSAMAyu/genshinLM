"""Genshin Capsule — OperatorAgent keyword registry.

Provides game-specific task keyword mappings injected into the Kernel's
OperatorAgent at construction time. This is the Capsule side of the
Kernel/Capsule boundary: Kernel has no game-specific keywords, Capsule
provides them.
"""
from __future__ import annotations

GENSHIN_TASK_KEYWORDS: dict[str, str] = {
    # Chinese
    "升级": "character_level_up",
    "突破": "character_ascend",
    "强化": "enhance",
    "精炼": "refine",
    "祈愿": "wish_pull",
    "天赋": "talent_upgrade",
    "圣遗物": "artifact_manage",
    "武器": "weapon_manage",
    "打怪": "combat",
    "战斗": "combat",
    "探索": "explore",
    "宝箱": "explore_chest",
    "传送": "teleport",
    "任务": "quest",
    "日常": "daily",
    "主线": "mainline",
    # English
    "level up": "character_level_up",
    "ascend": "character_ascend",
    "enhance": "enhance",
    "refine": "refine",
    "wish": "wish_pull",
    "talent": "talent_upgrade",
    "artifact": "artifact_manage",
    "weapon": "weapon_manage",
    "combat": "combat",
    "fight": "combat",
    "explore": "explore",
    "chest": "explore_chest",
    "teleport": "teleport",
    "quest": "quest",
    "daily": "daily",
    "mainline": "mainline",
}
"""Keyword → capability mapping for Genshin Impact.

Usage:
    from agent_kernel.operator_agent import SimpleOperatorAgent
    from data.genshin_operator_keywords import GENSHIN_TASK_KEYWORDS

    agent = SimpleOperatorAgent(task_keywords=GENSHIN_TASK_KEYWORDS)
"""
