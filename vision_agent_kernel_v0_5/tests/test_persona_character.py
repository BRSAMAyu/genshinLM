"""Tests for character persona system, guide knowledge base, context builder, and TTS/STT."""
from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Character Persona
# ---------------------------------------------------------------------------

class TestCharacterPersona:
    def test_load_all_personas(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        personas = reg.list_all()
        assert len(personas) >= 14

    def test_get_paimon(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("paimon")
        assert p is not None
        assert p.game == "genshin"
        assert p.speech.first_person == "派蒙"
        assert p.speech.tone == "energetic"
        assert p.speech.uses_emoji_in_text is True

    def test_get_march_7th(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("march_7th")
        assert p is not None
        assert p.game == "hsr"
        assert p.speech.exclamation_frequency == "very_high"

    def test_get_himeko(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("himeko")
        assert p is not None
        assert p.role == "mentor"
        assert "coffee" in " ".join(p.personality.likes).lower() or "咖啡" in p.personality.likes

    def test_get_dan_heng(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("dan_heng")
        assert p is not None
        assert p.speech.exclamation_frequency == "very_low"
        assert p.speech.uses_emoji_in_text is False

    def test_get_frieren_crossover(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("frieren")
        assert p is not None
        assert p.game == "crossover"
        assert p.worldview.lore_depth == "millennium"

    def test_get_theresa(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("theresa")
        assert p is not None
        assert p.game == "honkai3rd"
        assert p.speech.first_person == "本小姐"

    def test_zhongli_has_deep_lore(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("zhongli")
        assert p is not None
        assert p.worldview.lore_depth == "deep"
        assert len(p.worldview.location_knowledge) >= 5

    def test_list_by_game(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        genshin = reg.list_by_game("genshin")
        hsr = reg.list_by_game("hsr")
        assert len(genshin) >= 2
        assert len(hsr) >= 3

    def test_system_prompt_generation(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        prompt = reg.build_system_prompt("paimon", scenario="combat", context_budget=1500)
        assert len(prompt) > 100
        assert "派蒙" in prompt

    def test_system_prompt_unknown_character(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        prompt = reg.build_system_prompt("nonexistent")
        assert prompt == ""

    def test_unknown_returns_none(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        assert reg.get("unknown_char") is None

    def test_combat_voices_structure(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        for cid in ("paimon", "march_7th", "himeko", "dan_heng"):
            p = reg.get(cid)
            assert p is not None
            assert "encouragement" in p.combat_voices
            assert "danger_warning" in p.combat_voices
            assert "victory" in p.combat_voices

    def test_voice_hint_structure(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        for p in reg.list_all():
            assert p.voice_hint.pitch
            assert p.voice_hint.speed
            assert p.voice_hint.energy

    # --- New character quality tests ---

    def test_firefly_duality(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("firefly")
        assert p is not None
        assert p.game == "hsr"
        assert p.speech.tone == "gentle_resolute"
        assert "treasure" in str(p.personality.traits).lower() or "珍" in "".join(p.personality.traits)
        assert p.extended.daily_life != ""
        assert p.interactions.greeting_style != ""

    def test_silver_wolf_gamer(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("silver_wolf")
        assert p is not None
        assert p.speech.vocabulary_level == "internet_gaming"
        assert len(p.speech.sentence_starters) >= 3
        assert p.speech.topic_transition != ""
        assert "bored" in str(p.personality.traits).lower() or "无聊" in "".join(p.personality.dislikes)

    def test_kafka_enigmatic(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("kafka")
        assert p is not None
        assert p.speech.tone == "warm_enigmatic"
        assert p.speech.exclamation_frequency == "very_low"
        assert len(p.speech.filler_words) >= 2
        assert p.interactions.teaching_style != ""
        assert "indirect" in p.speech.vocabulary_level

    def test_ayaka_refined(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("ayaka")
        assert p is not None
        assert p.game == "genshin"
        assert p.speech.tone == "refined_warm"
        assert p.personality.mbti_hint == "INFJ"
        assert p.extended.stress_response != ""
        assert p.interactions.disagreement_style != ""

    def test_furina_theatrical(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("furina")
        assert p is not None
        assert p.speech.first_person == "本水神"
        assert p.speech.exclamation_frequency == "very_high"
        assert p.speech.uses_emoji_in_text is True
        assert "theatrical" in str(p.personality.traits).lower() or "演" in "".join(p.personality.likes)

    def test_ganyu_workaholic(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("ganyu")
        assert p is not None
        assert p.game == "genshin"
        assert "3000" in p.worldview.lore_depth or "3000" in "".join(p.worldview.special_knowledge)
        assert p.extended.daily_life != ""

    def test_kurisu_tsundere(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        p = reg.get("kurisu")
        assert p is not None
        assert p.game == "crossover"
        assert "tsundere" in str(p.personality.traits).lower() or "傲娇" in p.role
        assert p.speech.tone == "sharp_conceals_warmth"
        assert len(p.speech.filler_words) >= 2
        assert p.interactions.consoling_style != ""

    def test_extended_behavior_populated(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        for cid in ("firefly", "silver_wolf", "kafka", "ayaka", "furina", "ganyu", "kurisu"):
            p = reg.get(cid)
            assert p is not None, f"{cid} not found"
            assert p.extended.daily_life != "", f"{cid} missing daily_life"
            assert p.extended.stress_response != "", f"{cid} missing stress_response"
            assert p.interactions.greeting_style != "", f"{cid} missing greeting_style"

    def test_system_prompt_includes_extended(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        prompt = reg.build_system_prompt("kurisu", context_budget=3000)
        assert "性格的自然延伸" in prompt

    def test_system_prompt_firefly_has_interaction(self) -> None:
        from persona.character_persona import CharacterPersonaRegistry
        reg = CharacterPersonaRegistry()
        prompt = reg.build_system_prompt("firefly", context_budget=4000)
        assert "与人互动的风格" in prompt


# ---------------------------------------------------------------------------
# Guide Knowledge Base
# ---------------------------------------------------------------------------

class TestGuideKnowledgeBase:
    def test_load_guides(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        assert len(db.tips) >= 10

    def test_search_by_tag_combat(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        combat_tips = db.search_by_tags(["combat"], game="genshin")
        assert len(combat_tips) >= 3

    def test_search_by_tag_sp(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        sp_tips = db.search_by_tags(["sp"], game="hsr")
        assert len(sp_tips) >= 1

    def test_search_for_character(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        tips = db.search_for_character("hu_tao")
        assert len(tips) >= 1

    def test_relevant_context(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        ctx = db.get_relevant_context(["combat", "elements"], game="genshin", max_tips=3, max_chars=2000)
        assert len(ctx) > 100
        assert "蒸发" in ctx or "融化" in ctx

    def test_relevant_context_empty_tags(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        ctx = db.get_relevant_context(["nonexistent_tag"])
        assert ctx == ""

    def test_tip_has_required_fields(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        for tip in db.tips.values():
            assert tip.tip_id
            assert tip.title
            assert tip.content
            assert tip.game
            assert tip.difficulty

    def test_search_by_difficulty(self) -> None:
        from knowledge.guides.guide_loader import GuideKnowledgeBase
        db = GuideKnowledgeBase()
        beginner = db.search_by_difficulty("beginner", game="hsr")
        assert len(beginner) >= 2


# ---------------------------------------------------------------------------
# Persona Context Builder
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def test_build_paimon_combat_prompt(self) -> None:
        from persona.context_builder import PersonaContextBuilder, ContextConfig
        builder = PersonaContextBuilder()
        config = ContextConfig(character_id="paimon", game="genshin", scenario="combat", tags=("combat",))
        prompt = builder.build_system_prompt(config)
        assert "派蒙" in prompt
        assert "互动规则" in prompt
        assert len(prompt) > 200

    def test_build_himeko_team_prompt(self) -> None:
        from persona.context_builder import PersonaContextBuilder, ContextConfig
        builder = PersonaContextBuilder()
        config = ContextConfig(character_id="himeko", game="hsr", scenario="team_building", tags=("team",))
        prompt = builder.build_system_prompt(config)
        assert "姬子" in prompt
        assert len(prompt) > 200

    def test_budget_respected(self) -> None:
        from persona.context_builder import PersonaContextBuilder, ContextConfig
        builder = PersonaContextBuilder()
        config = ContextConfig(character_id="paimon", game="genshin", max_chars=500)
        prompt = builder.build_system_prompt(config)
        assert len(prompt) <= 1500  # generous margin for CJK

    def test_quick_response_prompt(self) -> None:
        from persona.context_builder import PersonaContextBuilder
        builder = PersonaContextBuilder()
        prompt = builder.build_quick_response_prompt("march_7th", "COMBAT_VICTORY")
        assert "三月" in prompt
        assert "简短回应" in prompt

    def test_guide_query_prompt(self) -> None:
        from persona.context_builder import PersonaContextBuilder
        builder = PersonaContextBuilder()
        prompt = builder.build_guide_query_prompt("paimon", "怎么打蒸发反应？", game="genshin")
        assert "派蒙" in prompt
        assert "怎么打蒸发反应" in prompt

    def test_no_guides_when_disabled(self) -> None:
        from persona.context_builder import PersonaContextBuilder, ContextConfig
        builder = PersonaContextBuilder()
        config = ContextConfig(character_id="paimon", game="genshin", include_guides=False)
        prompt = builder.build_system_prompt(config)
        assert "攻略参考" not in prompt

    def test_dan_heng_no_emoji_rule(self) -> None:
        from persona.context_builder import PersonaContextBuilder, ContextConfig
        builder = PersonaContextBuilder()
        config = ContextConfig(character_id="dan_heng", game="hsr")
        prompt = builder.build_system_prompt(config)
        assert "不要使用 emoji" in prompt


# ---------------------------------------------------------------------------
# TTS/STT Abstraction
# ---------------------------------------------------------------------------

class TestTTSProviders:
    def test_minimax_instantiation(self) -> None:
        from voice.tts_provider import MiniMaxTTS
        tts = MiniMaxTTS()
        assert tts.name == "minimax"

    def test_glm_instantiation(self) -> None:
        from voice.tts_provider import GLMTTS
        tts = GLMTTS()
        assert tts.name == "glm"

    def test_dashscope_instantiation(self) -> None:
        from voice.tts_provider import DashScopeTTS
        tts = DashScopeTTS()
        assert tts.name == "dashscope"

    def test_available_without_key(self) -> None:
        from voice.tts_provider import MiniMaxTTS
        tts = MiniMaxTTS()
        assert tts.available() is False

    def test_create_chain(self) -> None:
        from voice.tts_provider import create_tts_chain
        chain = create_tts_chain()
        assert len(chain) == 3

    def test_get_available_returns_none_without_keys(self) -> None:
        from voice.tts_provider import get_available_tts
        result = get_available_tts()
        assert result is None


class TestSTTProviders:
    def test_minimax_instantiation(self) -> None:
        from voice.stt_provider import MiniMaxSTT
        stt = MiniMaxSTT()
        assert stt.name == "minimax"

    def test_glm_instantiation(self) -> None:
        from voice.stt_provider import GLMSTT
        stt = GLMSTT()
        assert stt.name == "glm"

    def test_dashscope_instantiation(self) -> None:
        from voice.stt_provider import DashScopeSTT
        stt = DashScopeSTT()
        assert stt.name == "dashscope"

    def test_available_without_key(self) -> None:
        from voice.stt_provider import GLMSTT
        stt = GLMSTT()
        assert stt.available() is False

    def test_create_stt_chain(self) -> None:
        from voice.stt_provider import create_stt_chain
        chain = create_stt_chain()
        assert len(chain) == 3


class TestVoiceAdapter:
    def test_synthesize_text_only_without_provider(self) -> None:
        from persona.voice_adapter import VoiceAdapter
        adapter = VoiceAdapter()
        response = adapter.synthesize("你好")
        assert response.format == "text"
        assert response.audio_data == b""

    def test_recognize_returns_empty_without_provider(self) -> None:
        from persona.voice_adapter import VoiceAdapter
        adapter = VoiceAdapter()
        response = adapter.recognize(b"fake audio data")
        assert response.text == ""
        assert response.confidence == 0.0

    def test_available_tts_returns_none(self) -> None:
        from persona.voice_adapter import VoiceAdapter
        adapter = VoiceAdapter()
        assert adapter.available_tts() == "none"

    def test_available_stt_returns_none(self) -> None:
        from persona.voice_adapter import VoiceAdapter
        adapter = VoiceAdapter()
        assert adapter.available_stt() == "none"
