"""UniversalEntryAgent: user intent → game execution pipeline.

Translates natural language goals into executable mission graphs.
Bridges the gap between user-facing text ("do daily commissions")
and the internal MissionGraphV4 execution system.

Phase 4 roadmap: single entry point for all user goals.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParsedIntent:
    goal_type: str  # daily, quest, combat, explore, upgrade, custom
    game_id: str
    raw_text: str
    parameters: tuple[tuple[str, str], ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    plan_id: str
    goal_type: str
    steps: tuple[dict[str, Any], ...]
    estimated_duration_sec: float
    requires_combat: bool
    requires_navigation: bool
    requires_dialog: bool


class GoalParser(Protocol):
    def parse(self, text: str, game_id: str) -> ParsedIntent: ...


class MissionBuilder(Protocol):
    def build(self, intent: ParsedIntent) -> ExecutionPlan: ...


# Keyword → goal type mapping
_GOAL_KEYWORDS: dict[str, list[str]] = {
    "daily": ["每日", "委托", "daily", "commission", "日常"],
    "quest": ["主线", "任务", "quest", "mission", "主线任务"],
    "combat": ["战斗", "打boss", "combat", "fight", "boss", "战斗"],
    "explore": ["探索", "explore", "探索", "开图", "宝箱", "chest"],
    "upgrade": ["升级", "强化", "upgrade", "level up", "培养"],
    "dialog": ["对话", "对话", "talk", "npc"],
    "navigation": ["传送", "导航", "teleport", "navigate", "去"],
}


@dataclass(slots=True)
class EntryConfig:
    default_game: str = "genshin"
    max_plan_steps: int = 20
    default_duration_sec: float = 300.0


class UniversalEntryAgent:
    """Single entry point for user goals → executable plans."""

    def __init__(
        self,
        goal_parser: GoalParser | None = None,
        config: EntryConfig | None = None,
    ) -> None:
        self._goal_parser = goal_parser
        self._config = config or EntryConfig()

    def process(self, text: str, game_id: str = "") -> ExecutionPlan:
        """Process a natural language goal into an execution plan."""
        gid = game_id or self._config.default_game

        if self._goal_parser is not None:
            intent = self._goal_parser.parse(text, gid)
        else:
            intent = self._parse_intent(text, gid)

        return self._build_plan(intent)

    def _parse_intent(self, text: str, game_id: str) -> ParsedIntent:
        """Parse natural language text into a structured intent."""
        text_lower = text.lower()
        goal_type = "custom"
        best_score = 0

        for gtype, keywords in _GOAL_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                goal_type = gtype

        confidence = min(0.5 + best_score * 0.2, 1.0) if best_score > 0 else 0.3

        return ParsedIntent(
            goal_type=goal_type,
            game_id=game_id,
            raw_text=text,
            parameters=(),
            confidence=confidence,
        )

    def _build_plan(self, intent: ParsedIntent) -> ExecutionPlan:
        """Build an execution plan from a parsed intent."""
        import hashlib
        plan_id = hashlib.md5(f"{intent.goal_type}:{intent.raw_text}".encode()).hexdigest()[:12]

        # Template-based plan generation
        templates: dict[str, list[dict[str, Any]]] = {
            "daily": [
                {"action": "open_menu", "type": "ui"},
                {"action": "navigate_to_commissions", "type": "navigation"},
                {"action": "accept_commissions", "type": "ui"},
                {"action": "execute_commissions", "type": "combat"},
                {"action": "claim_rewards", "type": "ui"},
            ],
            "quest": [
                {"action": "open_quest_log", "type": "ui"},
                {"action": "select_quest", "type": "ui"},
                {"action": "navigate_to_objective", "type": "navigation"},
                {"action": "complete_objective", "type": "combat"},
            ],
            "combat": [
                {"action": "navigate_to_boss", "type": "navigation"},
                {"action": "engage_combat", "type": "combat"},
                {"action": "claim_drops", "type": "ui"},
            ],
            "explore": [
                {"action": "open_map", "type": "ui"},
                {"action": "navigate_to_area", "type": "navigation"},
                {"action": "discover_landmarks", "type": "navigation"},
            ],
            "upgrade": [
                {"action": "open_character_screen", "type": "ui"},
                {"action": "select_character", "type": "ui"},
                {"action": "upgrade_materials", "type": "ui"},
            ],
            "dialog": [
                {"action": "navigate_to_npc", "type": "navigation"},
                {"action": "initiate_dialog", "type": "ui"},
                {"action": "advance_dialog", "type": "ui"},
            ],
            "navigation": [
                {"action": "open_map", "type": "ui"},
                {"action": "teleport_to_destination", "type": "navigation"},
            ],
        }

        steps = templates.get(intent.goal_type, [
            {"action": "analyze_goal", "type": "system"},
            {"action": "plan_execution", "type": "system"},
        ])

        requires_combat = any(s["type"] == "combat" for s in steps)
        requires_navigation = any(s["type"] == "navigation" for s in steps)
        requires_dialog = any(s["type"] == "ui" and "dialog" in s["action"] for s in steps)

        return ExecutionPlan(
            plan_id=plan_id,
            goal_type=intent.goal_type,
            steps=tuple(steps),
            estimated_duration_sec=self._config.default_duration_sec,
            requires_combat=requires_combat,
            requires_navigation=requires_navigation,
            requires_dialog=requires_dialog,
        )
