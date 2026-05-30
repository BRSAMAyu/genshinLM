"""Tests for Zhipu VLM provider and zero-shot agent components."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.zero_shot_agent import (
    AgentAction,
    GAME_KEYMAPS,
    LLMPlan,
    VLMAnalysis,
    ZeroShotAgent,
    _extract_json,
    _frame_to_image_input,
)
from llm.vision_provider import ImageInput
from llm.zhipu_vlm_provider import ZhipuVLMProvider


class TestZhipuVLMProvider:
    def test_status_without_api_key(self):
        provider = ZhipuVLMProvider(api_key="")
        status = provider.status()
        assert not status.ok
        assert "ZHIPU_API_KEY" in status.message

    def test_status_with_api_key(self):
        provider = ZhipuVLMProvider(api_key="test_key_123")
        status = provider.status()
        assert status.ok
        assert status.model == "glm-4v-flash"

    def test_describe_image_parses_response(self):
        fake_response = {
            "choices": [{"message": {"content": "A game screenshot showing a character in an open world."}}],
            "usage": {"total_tokens": 100},
        }
        provider = ZhipuVLMProvider(api_key="test_key")
        with patch.object(provider, "_chat", return_value=fake_response):
            image = ImageInput(data=b"fake_png", mime_type="image/png")
            result = provider.describe_image(image, "Describe this image")
            assert result.text == "A game screenshot showing a character in an open world."
            assert result.provider == "zhipu_vlm"

    def test_classify_screen_parses_json(self):
        fake_response = {
            "choices": [{"message": {"content": '{"screen_state": "combat", "confidence": 0.9}'}}],
            "usage": {},
        }
        provider = ZhipuVLMProvider(api_key="test_key")
        with patch.object(provider, "_chat", return_value=fake_response):
            image = ImageInput(data=b"fake_png")
            result = provider.classify_screen(image, ["overworld", "combat", "menu"])
            assert result.screen_state == "combat"
            assert result.confidence == 0.9

    def test_ground_ui_extracts_candidates(self):
        fake_response = {
            "choices": [{"message": {"content": json.dumps({
                "candidates": [{"label": "Attack Button", "bbox_norm": [0.1, 0.2, 0.3, 0.4], "confidence": 0.8, "reason": "sword icon"}]
            })}}],
            "usage": {},
        }
        provider = ZhipuVLMProvider(api_key="test_key")
        with patch.object(provider, "_chat", return_value=fake_response):
            image = ImageInput(data=b"fake_png")
            result = provider.ground_ui(image, "attack button")
            assert len(result.candidates) == 1
            assert result.candidates[0]["label"] == "Attack Button"


class TestExtractJson:
    def test_plain_json(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_markdown(self):
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_json_embedded_in_text(self):
        text = 'Here is the result: {"screen_state": "combat", "confidence": 0.9} done.'
        result = _extract_json(text)
        assert result["screen_state"] == "combat"

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            _extract_json("no json here")


class TestFrameEncoding:
    def test_encode_frame_with_numpy(self):
        import numpy as np
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[100:200, 100:200] = [255, 0, 0]
        image_input = _frame_to_image_input(frame, frame_id=42)
        assert image_input.frame_id == 42
        assert image_input.mime_type in {"image/png", "image/jpeg"}
        assert len(image_input.data) > 0
        assert image_input.data[:4] == b"\x89PNG" or image_input.data[:2] == b"\xff\xd8"


class TestGameKeymaps:
    def test_genshin_has_essential_keys(self):
        keys = GAME_KEYMAPS["genshin"]
        assert "move_forward" in keys
        assert "interact" in keys
        assert "elemental_skill" in keys

    def test_hsr_has_essential_keys(self):
        keys = GAME_KEYMAPS["hsr"]
        assert "move_forward" in keys
        assert "interact" in keys
        assert "skill" in keys


class TestZeroShotAgentInit:
    def test_agent_initializes_with_game(self):
        agent = ZeroShotAgent(
            game="genshin",
            goal="walk forward",
            api_key="test_key",
        )
        assert agent.game == "genshin"
        assert agent.goal == "walk forward"

    def test_agent_resolves_window_title(self):
        agent = ZeroShotAgent(
            game="genshin",
            goal="test",
            api_key="test_key",
        )
        assert agent._input.target_window_title == "Aurora Genshin-like Testbed"

    def test_agent_custom_window(self):
        agent = ZeroShotAgent(
            game="genshin",
            goal="test",
            api_key="test_key",
            window_title="Aurora QA Safe Window",
        )
        assert agent._input.target_window_title == "Aurora QA Safe Window"

    def test_agent_rejects_non_authorized_nondry_window(self):
        import pytest

        with pytest.raises(ValueError):
            ZeroShotAgent(
                game="genshin",
                goal="test",
                api_key="test_key",
                window_title="Untrusted Window",
                dry_run=False,
            )


class TestVLMAnalysis:
    def test_analysis_creation(self):
        analysis = VLMAnalysis(
            screen_state="overworld",
            player_status={"health": "full"},
            visible_objects=[{"type": "npc", "position": "center"}],
            ui_elements={"interaction_prompt": "F - Talk"},
            scene_description="A character standing in a field",
            suggested_action="interact",
            latency_ms=1200.0,
            raw_text="...",
        )
        assert analysis.screen_state == "overworld"
        assert len(analysis.visible_objects) == 1


class TestLLMPlan:
    def test_plan_creation(self):
        plan = LLMPlan(
            reasoning="NPC ahead, should interact",
            actions=[AgentAction(key="w", duration_ms=500, reason="approach NPC")],
            expected_result="closer to NPC",
            confidence=0.85,
            goal_progress="almost there",
            should_stop=False,
            latency_ms=800.0,
            raw_text="...",
        )
        assert len(plan.actions) == 1
        assert plan.actions[0].key == "w"

    def test_action_dict(self):
        action = AgentAction(key="space", duration_ms=200, reason="jump")
        d = action.as_dict()
        assert d == {"key": "space", "duration_ms": 200, "reason": "jump"}
