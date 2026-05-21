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
        """Build an LLM system prompt from a character persona.

        Respects context_budget (approximate character count) by selecting
        the most relevant sections.
        """
        persona = self.get(character_id)
        if persona is None:
            return ""

        sections = [
            self._identity_section(persona),
            self._speech_section(persona),
            self._personality_section(persona),
        ]

        remaining = context_budget - sum(len(s) for s in sections)
        if remaining > 200:
            sections.append(self._combat_section(persona))

        remaining = context_budget - sum(len(s) for s in sections)
        if remaining > 300 and scenario:
            sections.append(self._scenario_section(persona, scenario))

        remaining = context_budget - sum(len(s) for s in sections)
        if remaining > 400:
            sections.append(self._worldview_section(persona))

        return "\n\n".join(sections)

    def _identity_section(self, p: CharacterPersona) -> str:
        return (
            f"你现在扮演「{p.name}」（{p.name_en}），"
            f"来自{'原神' if p.game == 'genshin' else '崩坏：星穹铁道' if p.game == 'hsr' else '崩坏3' if p.game == 'honkai3rd' else p.game}。"
            f"你的身份是：{p.title}。"
            f"你以「{p.speech.first_person}」自称。"
        )

    def _speech_section(self, p: CharacterPersona) -> str:
        patterns = "、".join(f"「{s}」" for s in p.speech.sentence_patterns[:5])
        emoji_note = "可以使用 emoji。" if p.speech.uses_emoji_in_text else "不使用 emoji。"
        return (
            f"语气：{p.speech.tone}。{emoji_note}\n"
            f"常用口头禅和句式：{patterns}\n"
            f"标志性的话：「{p.speech.catchphrase}」\n"
            f"感叹频率：{p.speech.exclamation_frequency}。"
        )

    def _personality_section(self, p: CharacterPersona) -> str:
        traits = "、".join(p.personality.traits[:6])
        likes = "、".join(p.personality.likes[:4])
        return (
            f"性格特质：{traits}。\n"
            f"喜欢的事物：{likes}。\n"
            f"幽默风格：{p.personality.humor_style}。"
        )

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
            )
            personas[persona.character_id] = persona
        return personas
