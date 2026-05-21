from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class SpeechStyle:
    first_person: str
    catchphrase: str
    tone: str
    vocabulary_level: str
    sentence_patterns: tuple[str, ...]
    exclamation_frequency: str
    uses_emoji_in_text: bool
    sentence_starters: tuple[str, ...] = ()
    filler_words: tuple[str, ...] = ()
    topic_transition: str = ""


@dataclass(frozen=True, slots=True)
class PersonalityProfile:
    traits: tuple[str, ...]
    mbti_hint: str
    likes: tuple[str, ...]
    dislikes: tuple[str, ...]
    fears: tuple[str, ...]
    humor_style: str
    emotional_range: str


@dataclass(frozen=True, slots=True)
class WorldviewProfile:
    location_knowledge: tuple[str, ...]
    knows_elements: bool
    knows_reactions: bool
    lore_depth: str
    special_knowledge: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VoiceHint:
    pitch: str
    speed: str
    energy: str


@dataclass(frozen=True, slots=True)
class ExtendedBehavior:
    daily_life: str = ""
    stress_response: str = ""
    humor_expression: str = ""
    comfort_signals: str = ""
    when_bored: str = ""
    when_excited: str = ""


@dataclass(frozen=True, slots=True)
class InteractionStyles:
    greeting_style: str = ""
    teaching_style: str = ""
    consoling_style: str = ""
    celebrating_style: str = ""
    disagreement_style: str = ""


@dataclass(frozen=True, slots=True)
class CharacterPersona:
    character_id: str
    game: str
    name: str
    name_en: str
    role: str
    title: str
    speech: SpeechStyle
    personality: PersonalityProfile
    worldview: WorldviewProfile
    emotional_triggers: tuple[tuple[str, str], ...]
    combat_voices: dict[str, str]
    guide_topics: tuple[str, ...]
    voice_hint: VoiceHint
    extended: ExtendedBehavior = field(default_factory=ExtendedBehavior)
    interactions: InteractionStyles = field(default_factory=InteractionStyles)


class CharacterPersonaRegistry:
    """Load and query rich character personas from YAML."""

    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self._dir = knowledge_dir or Path(__file__).resolve().parent.parent / "knowledge"
        self._personas: dict[str, CharacterPersona] | None = None

    @property
    def personas(self) -> dict[str, CharacterPersona]:
        if self._personas is None:
            self._personas = self._load()
        return self._personas

    def get(self, character_id: str) -> CharacterPersona | None:
        return self.personas.get(character_id)

    def list_by_game(self, game: str) -> list[CharacterPersona]:
        return [p for p in self.personas.values() if p.game == game]

    def list_all(self) -> list[CharacterPersona]:
        return list(self.personas.values())

    def build_system_prompt(
        self,
        character_id: str,
        scenario: str = "",
        context_budget: int = 2000,
    ) -> str:
        """Build an LLM system prompt from a character persona."""
        persona = self.get(character_id)
        if persona is None:
            return ""

        sections = [
            self._identity_section(persona),
            self._speech_section(persona),
            self._personality_section(persona),
        ]

        remaining = context_budget - sum(len(s) for s in sections)

        # Extended behavior — how the character acts beyond the game
        if remaining > 300 and persona.extended.daily_life:
            sections.append(self._extended_section(persona))
            remaining = context_budget - sum(len(s) for s in sections)

        if remaining > 200:
            sections.append(self._combat_section(persona))

        remaining = context_budget - sum(len(s) for s in sections)
        if remaining > 300 and scenario:
            sections.append(self._scenario_section(persona, scenario))

        remaining = context_budget - sum(len(s) for s in sections)
        if remaining > 400:
            sections.append(self._worldview_section(persona))

        remaining = context_budget - sum(len(s) for s in sections)
        if remaining > 300 and persona.interactions.teaching_style:
            sections.append(self._interaction_section(persona))

        return "\n\n".join(sections)

    def _identity_section(self, p: CharacterPersona) -> str:
        game_map = {
            "genshin": "原神",
            "hsr": "崩坏：星穹铁道",
            "honkai3rd": "崩坏3",
            "crossover": "跨作品联动",
        }
        return (
            f"你现在扮演「{p.name}」（{p.name_en}），"
            f"来自{game_map.get(p.game, p.game)}。"
            f"你的身份是：{p.title}。"
            f"你以「{p.speech.first_person}」自称。"
        )

    def _speech_section(self, p: CharacterPersona) -> str:
        patterns = "、".join(f"「{s}」" for s in p.speech.sentence_patterns[:5])
        emoji_note = "可以使用 emoji。" if p.speech.uses_emoji_in_text else "不使用 emoji。"
        parts = [
            f"语气：{p.speech.tone}。{emoji_note}",
            f"常用句式：{patterns}",
            f"标志性台词：「{p.speech.catchphrase}」",
            f"感叹频率：{p.speech.exclamation_frequency}。",
        ]
        if p.speech.sentence_starters:
            starters = "、".join(f"「{s}」" for s in p.speech.sentence_starters[:4])
            parts.append(f"开头习惯：{starters}")
        if p.speech.topic_transition:
            parts.append(f"话题切换方式：{p.speech.topic_transition}")
        return "\n".join(parts)

    def _personality_section(self, p: CharacterPersona) -> str:
        traits = "、".join(p.personality.traits[:6])
        likes = "、".join(p.personality.likes[:4])
        return (
            f"性格特质：{traits}。\n"
            f"喜欢的事物：{likes}。\n"
            f"幽默风格：{p.personality.humor_style}。"
        )

    def _extended_section(self, p: CharacterPersona) -> str:
        lines = ["[性格的自然延伸——你不仅在游戏里，在任何场景下都保持这个人格]"]
        if p.extended.daily_life:
            lines.append(f"日常生活：{p.extended.daily_life}")
        if p.extended.stress_response:
            lines.append(f"压力下的反应：{p.extended.stress_response}")
        if p.extended.humor_expression:
            lines.append(f"幽默表达：{p.extended.humor_expression}")
        if p.extended.comfort_signals:
            lines.append(f"放松的信号：{p.extended.comfort_signals}")
        if p.extended.when_excited:
            lines.append(f"兴奋时：{p.extended.when_excited}")
        return "\n".join(lines)

    def _combat_section(self, p: CharacterPersona) -> str:
        lines = []
        for key in ("encouragement", "danger_warning", "victory", "defeat"):
            if key in p.combat_voices:
                label = {"encouragement": "鼓励队友", "danger_warning": "危险警告",
                         "victory": "战斗胜利", "defeat": "战斗失败"}.get(key, key)
                lines.append(f"  {label}：「{p.combat_voices[key]}」")
        if not lines:
            return ""
        return "战斗中的台词风格：\n" + "\n".join(lines)

    def _worldview_section(self, p: CharacterPersona) -> str:
        knowledge = "、".join(p.worldview.special_knowledge[:5])
        return (
            f"知识背景（深度：{p.worldview.lore_depth}）：{knowledge}\n"
            f"了解的地区：{'、'.join(p.worldview.location_knowledge[:6])}。"
        )

    def _scenario_section(self, p: CharacterPersona, scenario: str) -> str:
        lines = [f"当前场景：{scenario}。"]
        for trigger, response in p.emotional_triggers:
            if scenario in trigger or trigger in scenario:
                lines.append(f"场景触发的情绪：{response}。")
        combat_key = {"combat": "encouragement", "danger": "danger_warning",
                      "victory": "victory", "defeat": "defeat"}.get(scenario)
        if combat_key and combat_key in p.combat_voices:
            lines.append(f"此时你可能会说：「{p.combat_voices[combat_key]}」")
        return "\n".join(lines)

    def _interaction_section(self, p: CharacterPersona) -> str:
        lines = ["[与人互动的风格]"]
        if p.interactions.greeting_style:
            lines.append(f"打招呼：{p.interactions.greeting_style}")
        if p.interactions.teaching_style:
            lines.append(f"教你东西时：{p.interactions.teaching_style}")
        if p.interactions.consoling_style:
            lines.append(f"安慰你时：{p.interactions.consoling_style}")
        if p.interactions.celebrating_style:
            lines.append(f"为你庆祝时：{p.interactions.celebrating_style}")
        if p.interactions.disagreement_style:
            lines.append(f"意见不同时：{p.interactions.disagreement_style}")
        return "\n".join(lines)

    def _load(self) -> dict[str, CharacterPersona]:
        path = self._dir / "persona_characters.yaml"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        personas: dict[str, CharacterPersona] = {}
        for entry in data.get("characters", []):
            speech = entry.get("speech_style", {})
            pers = entry.get("personality", {})
            world = entry.get("worldview", {})
            voice = entry.get("voice_hint", {})
            triggers = entry.get("emotional_triggers", {})
            combat = entry.get("combat_style", {})
            topics = entry.get("guide_topics", [])
            ext = entry.get("extended_behavior", {})
            inter = entry.get("interaction_styles", {})

            persona = CharacterPersona(
                character_id=entry["character_id"],
                game=entry.get("game", "unknown"),
                name=entry.get("name", entry["character_id"]),
                name_en=entry.get("name_en", entry["character_id"]),
                role=entry.get("role", "companion"),
                title=entry.get("title", ""),
                speech=SpeechStyle(
                    first_person=speech.get("first_person", "我"),
                    catchphrase=speech.get("catchphrase", ""),
                    tone=speech.get("tone", "neutral"),
                    vocabulary_level=speech.get("vocabulary_level", "casual"),
                    sentence_patterns=tuple(speech.get("sentence_patterns", [])),
                    exclamation_frequency=speech.get("exclamation_frequency", "medium"),
                    uses_emoji_in_text=speech.get("uses_emoji_in_text", False),
                    sentence_starters=tuple(speech.get("sentence_starters", [])),
                    filler_words=tuple(speech.get("filler_words", [])),
                    topic_transition=speech.get("topic_transition", ""),
                ),
                personality=PersonalityProfile(
                    traits=tuple(pers.get("traits", [])),
                    mbti_hint=pers.get("mbti_hint", ""),
                    likes=tuple(pers.get("likes", [])),
                    dislikes=tuple(pers.get("dislikes", [])),
                    fears=tuple(pers.get("fears", [])),
                    humor_style=pers.get("humor_style", ""),
                    emotional_range=pers.get("emotional_range", ""),
                ),
                worldview=WorldviewProfile(
                    location_knowledge=tuple(world.get("location_knowledge", [])),
                    knows_elements=world.get("knows_elements", False),
                    knows_reactions=world.get("knows_reactions", False),
                    lore_depth=world.get("lore_depth", ""),
                    special_knowledge=tuple(world.get("special_knowledge", [])),
                ),
                emotional_triggers=tuple(
                    (k, v) for k, v in triggers.items()
                ),
                combat_voices=combat,
                guide_topics=tuple(topics),
                voice_hint=VoiceHint(
                    pitch=voice.get("pitch", "medium"),
                    speed=voice.get("speed", "medium"),
                    energy=voice.get("energy", "medium"),
                ),
                extended=ExtendedBehavior(
                    daily_life=ext.get("daily_life", ""),
                    stress_response=ext.get("stress_response", ""),
                    humor_expression=ext.get("humor_expression", ""),
                    comfort_signals=ext.get("comfort_signals", ""),
                    when_bored=ext.get("when_bored", ""),
                    when_excited=ext.get("when_excited", ""),
                ),
                interactions=InteractionStyles(
                    greeting_style=inter.get("greeting_style", ""),
                    teaching_style=inter.get("teaching_style", ""),
                    consoling_style=inter.get("consoling_style", ""),
                    celebrating_style=inter.get("celebrating_style", ""),
                    disagreement_style=inter.get("disagreement_style", ""),
                ),
            )
            personas[persona.character_id] = persona
        return personas
