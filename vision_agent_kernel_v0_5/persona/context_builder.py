from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge.guides.guide_loader import GuideKnowledgeBase
from persona.character_persona import CharacterPersonaRegistry


@dataclass(frozen=True, slots=True)
class ContextConfig:
    character_id: str
    game: str
    scenario: str = ""
    tags: tuple[str, ...] = ()
    max_chars: int = 4000
    include_guides: bool = True
    include_lore: bool = True


class PersonaContextBuilder:
    """Assemble LLM system prompts from character persona + game knowledge + guide tips."""

    def __init__(
        self,
        persona_registry: CharacterPersonaRegistry | None = None,
        guide_db: GuideKnowledgeBase | None = None,
    ) -> None:
        self._personas = persona_registry or CharacterPersonaRegistry()
        self._guides = guide_db or GuideKnowledgeBase()

    def build_system_prompt(self, config: ContextConfig) -> str:
        """Build a complete system prompt within character budget."""
        sections: list[tuple[int, str]] = []

        # 1. Character identity and speech (always included, highest priority)
        char_prompt = self._personas.build_system_prompt(
            config.character_id,
            scenario=config.scenario,
            context_budget=min(config.max_chars // 2, 2000),
        )
        if char_prompt:
            sections.append((100, char_prompt))

        remaining = config.max_chars - sum(len(s[1]) for s in sections)

        # 2. Guide tips relevant to current scenario
        if config.include_guides and remaining > 500:
            tags = list(config.tags) if config.tags else self._scenario_to_tags(config.scenario)
            guide_ctx = self._guides.get_relevant_context(
                tags=tags,
                game=config.game,
                max_tips=3,
                max_chars=min(remaining - 200, 1500),
            )
            if guide_ctx:
                sections.append((80, f"[攻略参考]\n{guide_ctx}"))
                remaining -= len(guide_ctx) + 10

        # 3. Lore and worldview (if budget allows)
        if config.include_lore and remaining > 300:
            lore = self._build_lore_hint(config.character_id, config.game)
            if lore:
                sections.append((60, lore))

        # 4. Interaction rules (always appended)
        rules = self._interaction_rules(config.character_id)
        sections.append((90, rules))

        sections.sort(key=lambda x: -x[0])
        return "\n\n".join(s[1] for s in sections)

    def build_quick_response_prompt(
        self,
        character_id: str,
        event: str,
        game: str = "",
    ) -> str:
        """Build a short prompt for real-time event responses."""
        persona = self._personas.get(character_id)
        if persona is None:
            return ""

        lines = [
            f"你是「{persona.name}」。",
            f"说话方式：{persona.speech.tone}，自称「{persona.speech.first_person}」。",
            f"口头禅：「{persona.speech.catchphrase}」",
        ]

        combat_key = {
            "COMBAT_START": "encouragement",
            "COMBAT_VICTORY": "victory",
            "COMBAT_DIFFICULT": "danger_warning",
            "LOW_HP": "danger_warning",
            "DANGER_HIT": "danger_warning",
            "TARGET_DEFEATED": "victory",
        }.get(event)

        if combat_key and combat_key in persona.combat_voices:
            lines.append(f"这种情况下你会说类似：「{persona.combat_voices[combat_key]}」")

        lines.append("请用角色语气简短回应当前事件，不超过两句话。")
        return "\n".join(lines)

    def build_guide_query_prompt(
        self,
        character_id: str,
        query: str,
        game: str = "",
    ) -> str:
        """Build a prompt for answering player game questions in character."""
        config = ContextConfig(
            character_id=character_id,
            game=game,
            scenario="guide_query",
            tags=("guide", "strategy"),
            max_chars=5000,
        )
        base = self.build_system_prompt(config)

        tips = self._guides.get_relevant_context(
            tags=["combat", "team", "boss", "elements", "strategy", "beginner"],
            game=game,
            max_tips=3,
            max_chars=2000,
        )

        guide_section = f"\n\n[相关攻略参考]\n{tips}" if tips else ""
        return f"{base}{guide_section}\n\n玩家提问：{query}\n\n请用角色语气回答，给出实用建议。"

    def _scenario_to_tags(self, scenario: str) -> list[str]:
        mapping = {
            "combat": ["combat", "elements", "reactions"],
            "boss": ["boss", "mechanics", "advanced"],
            "exploration": ["exploration", "resources"],
            "team_building": ["team", "building", "strategy"],
            "daily": ["daily", "efficiency", "resources"],
            "guide_query": ["guide", "strategy"],
        }
        return mapping.get(scenario, [scenario])

    def _build_lore_hint(self, character_id: str, game: str) -> str:
        persona = self._personas.get(character_id)
        if persona is None:
            return ""
        locations = "、".join(persona.worldview.location_knowledge[:4])
        if not locations:
            return ""
        game_name = {"genshin": "提瓦特", "hsr": "星穹列车的旅程", "honkai3rd": "圣芙蕾雅学园"}.get(
            game, game
        )
        return f"[世界观背景] 你对{game_name}的了解涵盖：{locations}。知识深度：{persona.worldview.lore_depth}。"

    def _interaction_rules(self, character_id: str) -> str:
        persona = self._personas.get(character_id)
        emoji_rule = "可以适当使用 emoji 表达情绪。" if persona and persona.speech.uses_emoji_in_text else "不要使用 emoji。"
        return (
            "[互动规则]\n"
            "1. 始终保持角色语气和性格，不要跳出角色。\n"
            "2. 给出实用的游戏建议，但要融入角色风格。\n"
            f"3. {emoji_rule}\n"
            "4. 如果不确定某个游戏数据，坦诚说明而非编造。\n"
            "5. 优先考虑玩家体验，用鼓励性语言。"
        )
