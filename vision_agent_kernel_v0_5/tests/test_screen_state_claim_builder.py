"""Tests for planning/screen_state_claim_builder.py."""
from __future__ import annotations

import pytest
import numpy as np

from planning.screen_state_claim_builder import (
    ScreenStateClaimBuilder,
    VLMOutput,
    ClassifierOutput,
    OcrOutput,
)
from planning.screen_state_claim import (
    ScreenStateClaim,
    ScreenStateKind,
    PlayerStatusClaim,
    UIElementClaim,
    ClaimSource,
)


class DummyVLM:
    def __init__(self, state="overworld", health="full"):
        self.screen_state = state
        self.player_status = {"health": health, "position_in_frame": "center"}
        self.visible_objects = [{"type": "npc", "name": "test_npc"}]
        self.ui_elements = {"button_1": "Claim", "interaction_prompt": "Talk"}
        self.scene_description = "overworld scene"
        self.suggested_action = "interact"
        self.raw_text = "raw vlm output"

    def as_output(self) -> VLMOutput:
        return VLMOutput(
            screen_state=self.screen_state,
            player_status=self.player_status,
            visible_objects=self.visible_objects,
            ui_elements=self.ui_elements,
            scene_description=self.scene_description,
            suggested_action=self.suggested_action,
            raw_text=self.raw_text,
        )


def dummy_classifier(state="overworld", conf=0.9):
    return ClassifierOutput(screen_state=state, confidence=conf, source="hsr_classifier")


def dummy_ocr(text="F - Talk", conf=0.9):
    return OcrOutput(text=text, confidence=conf, bbox_norm=(0.3, 0.5, 0.4, 0.1), source="ocr_engine")


class TestScreenStateClaimBuilder:
    def test_instantiation(self) -> None:
        b = ScreenStateClaimBuilder()
        assert b is not None

    def test_build_empty(self) -> None:
        b = ScreenStateClaimBuilder()
        result = b.build("test_game", 0)
        assert isinstance(result, ScreenStateClaim)
        assert result.game_id == "test_game"
        assert result.frame_id == 0
        assert result.confidence > 0

    def test_build_with_vlm(self) -> None:
        b = ScreenStateClaimBuilder()
        vlm = DummyVLM().as_output()
        result = b.build("test_game", 1, vlm=vlm)
        assert result.screen_state == "overworld"
        assert result.source == "vlm"
        assert len(result.ui_elements) > 0

    def test_build_with_classifier(self) -> None:
        b = ScreenStateClaimBuilder()
        classifier = dummy_classifier(state="combat", conf=0.85)
        result = b.build("test_game", 2, classifier=classifier)
        assert result.screen_state == "combat"
        assert result.confidence == 0.85
        assert result.source == "classifier"

    def test_build_with_ocr(self) -> None:
        b = ScreenStateClaimBuilder()
        ocr_results = [dummy_ocr(text="  "), dummy_ocr(text="按 F 交互", conf=0.8)]
        result = b.build("test_game", 3, ocr_results=ocr_results)
        assert len(result.ui_elements) >= 1
        assert any(e.role == "interaction_prompt" for e in result.ui_elements)

    def test_build_hybrid_source(self) -> None:
        b = ScreenStateClaimBuilder()
        vlm = DummyVLM().as_output()
        classifier = dummy_classifier()
        result = b.build("test_game", 4, vlm=vlm, classifier=classifier)
        assert result.source == "hybrid"

    def test_ocr_low_confidence_filtered(self) -> None:
        b = ScreenStateClaimBuilder()
        ocr_results = [
            dummy_ocr(text="hello", conf=0.3),
            dummy_ocr(text="world", conf=0.95),
        ]
        result = b.build("test_game", 5, ocr_results=ocr_results)
        texts = [e.text for e in result.ui_elements]
        assert "hello" not in texts
        assert "world" in texts

    def test_short_ocr_filtered(self) -> None:
        b = ScreenStateClaimBuilder()
        ocr_results = [dummy_ocr(text="X", conf=0.8)]
        result = b.build("test_game", 6, ocr_results=ocr_results)
        assert len(result.ui_elements) == 0

    def test_build_with_frame_raw(self) -> None:
        b = ScreenStateClaimBuilder()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = b.build("test_game", 7, frame_raw=frame)
        assert isinstance(result, ScreenStateClaim)

    def test_ui_claim_button_role(self) -> None:
        vlm = DummyVLM()
        vlm.ui_elements = {"confirm_btn": "OK", "null_val": ""}
        b = ScreenStateClaimBuilder()
        result = b.build("test_game", 8, vlm=vlm.as_output())
        buttons = [e for e in result.ui_elements if e.role == "button"]
        assert len(buttons) >= 1

    def test_interaction_prompt_detection(self) -> None:
        b = ScreenStateClaimBuilder()
        ocr_results = [
            dummy_ocr(text="按 F 交互", conf=0.75),
            dummy_ocr(text="ordinary text", conf=0.8),
        ]
        result = b.build("test_game", 9, ocr_results=ocr_results)
        assert "按 F 交互" in result.interaction_prompt

    def test_interaction_prompt_from_vlm(self) -> None:
        vlm = DummyVLM()
        vlm.ui_elements = {"interaction_prompt": "Press F to Open"}
        b = ScreenStateClaimBuilder()
        result = b.build("test_game", 10, vlm=vlm.as_output())
        assert "Press F to Open" in result.interaction_prompt

    def test_screen_state_aliases(self) -> None:
        b = ScreenStateClaimBuilder()
        assert b._resolve_screen_state(None, dummy_classifier("loading_screen")) == "loading"
        assert b._resolve_screen_state(None, dummy_classifier("world_hud")) == "overworld"
        assert b._resolve_screen_state(None, dummy_classifier("full_menu")) == "menu"
        assert b._resolve_screen_state(None, dummy_classifier("paimon_menu")) == "menu"

    def test_unknown_screen_state_fallback(self) -> None:
        b = ScreenStateClaimBuilder()
        state = b._resolve_screen_state(
            VLMOutput("unknown", {}, [], {}, "", "", ""),
            dummy_classifier("gameplay"),
        )
        assert state == "overworld"

    def test_build_with_null_ui_element(self) -> None:
        vlm = DummyVLM()
        vlm.ui_elements = {"button_1": "", "prompt": None}
        vlm_raw = vlm.as_output()
        b = ScreenStateClaimBuilder()
        result = b.build("test_game", 11, vlm=vlm_raw)
        assert isinstance(result, ScreenStateClaim)

    @pytest.mark.parametrize("keyword,role", [
        ("confirm", "button"),
        ("accept", "button"),
        ("F - Interact", "interaction_prompt"),
        ("reward collected", "notification"),
        ("daily quest", "quest_text"),
    ])
    def test_infer_role_from_text(self, keyword, role) -> None:
        from planning.screen_state_claim_builder import _infer_role_from_text
        assert _infer_role_from_text(keyword) == role

    @pytest.mark.parametrize("key,role", [
        ("button_1", "button"),
        ("interaction_prompt", "interaction_prompt"),
        ("quest_text_display", "quest_text"),
        ("notification_area", "notification"),
        ("dialog_option_1", "dialog_option"),
        ("unknown_field", "text"),
    ])
    def test_infer_role(self, key, role) -> None:
        from planning.screen_state_claim_builder import _infer_role
        assert _infer_role(key) == role
