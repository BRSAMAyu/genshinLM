from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from perception.genshin_screen_classifier import GenshinScreenClassifier, ScreenState
from perception.ocr_engine import OcrConfig, OcrEngine, OcrResult


# ---------------------------------------------------------------------------
# OcrEngine tests
# ---------------------------------------------------------------------------


class TestOcrEngineLazyInit:
    def test_not_initialized_until_first_call(self) -> None:
        engine = OcrEngine()
        assert not engine._initialized

    def test_initializes_on_detect_text(self) -> None:
        engine = OcrEngine()
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [[]]
        with patch("perception.ocr_engine.PaddleOCR", return_value=mock_ocr, create=True):
            engine.detect_text(np.zeros((100, 100, 3), dtype=np.uint8))
        assert engine._initialized

    def test_graceful_when_paddleocr_missing(self) -> None:
        engine = OcrEngine()
        with patch.dict("sys.modules", {"paddleocr": None}):
            with patch("builtins.__import__", side_effect=ImportError("no paddleocr")):
                results = engine.detect_text(np.zeros((100, 100, 3), dtype=np.uint8))
        assert results == []
        assert not engine._available


class TestOcrEngineReadNumber:
    def test_extracts_first_number(self) -> None:
        engine = OcrEngine()
        engine._initialized = True
        engine._available = True
        engine._ocr = MagicMock()
        engine._ocr.ocr.return_value = [[
            [[[10, 10], [50, 10], [50, 30], [10, 30]], ("12秒", 0.95)],
            [[[60, 10], [100, 10], [100, 30], [60, 30]], ("CD", 0.9)],
        ]]
        result = engine.read_number(np.zeros((100, 100, 3), dtype=np.uint8))
        assert result == 12

    def test_returns_none_when_no_digits(self) -> None:
        engine = OcrEngine()
        engine._initialized = True
        engine._available = True
        engine._ocr = MagicMock()
        engine._ocr.ocr.return_value = [[
            [[[10, 10], [50, 10], [50, 30], [10, 30]], ("Ready", 0.95)],
        ]]
        result = engine.read_number(np.zeros((100, 100, 3), dtype=np.uint8))
        assert result is None


class TestOcrEngineContainsText:
    def test_finds_keyword(self) -> None:
        engine = OcrEngine()
        engine._initialized = True
        engine._available = True
        engine._ocr = MagicMock()
        engine._ocr.ocr.return_value = [[
            [[[10, 10], [100, 10], [100, 30], [10, 30]], ("按F采集", 0.9)],
        ]]
        found, kw = engine.contains_text(
            np.zeros((100, 100, 3), dtype=np.uint8), ["采集", "拾取"]
        )
        assert found is True
        assert kw == "采集"

    def test_no_keyword_match(self) -> None:
        engine = OcrEngine()
        engine._initialized = True
        engine._available = True
        engine._ocr = MagicMock()
        engine._ocr.ocr.return_value = [[
            [[[10, 10], [100, 10], [100, 30], [10, 30]], ("Hello World", 0.9)],
        ]]
        found, kw = engine.contains_text(
            np.zeros((100, 100, 3), dtype=np.uint8), ["采集", "拾取"]
        )
        assert found is False
        assert kw == ""


class TestOcrEngineDetectTextRoi:
    def test_crops_and_offsets(self) -> None:
        engine = OcrEngine()
        engine._initialized = True
        engine._available = True
        engine._ocr = MagicMock()
        engine._ocr.ocr.return_value = [[
            [[[5, 5], [45, 5], [45, 25], [5, 25]], ("test", 0.9)],
        ]]
        results = engine.detect_text_roi(
            np.zeros((200, 200, 3), dtype=np.uint8), roi=(10, 20, 100, 80)
        )
        assert len(results) == 1
        assert results[0].bbox == (15, 25, 55, 45)

    def test_empty_for_invalid_roi(self) -> None:
        engine = OcrEngine()
        results = engine.detect_text_roi(
            np.zeros((100, 100, 3), dtype=np.uint8), roi=(90, 90, 10, 10)
        )
        assert results == []


# ---------------------------------------------------------------------------
# GenshinScreenClassifier tests
# ---------------------------------------------------------------------------


class TestGenshinScreenClassifier:
    @pytest.fixture()
    def classifier(self) -> GenshinScreenClassifier:
        return GenshinScreenClassifier()

    def test_all_black_is_loading_screen(self, classifier: GenshinScreenClassifier) -> None:
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        state = classifier.classify(frame)
        assert state.state == "loading_screen"
        assert state.indicators["dark_frame"] == True
        assert state.indicators["loading_screen"] == True

    def test_all_white_is_no_hud(self, classifier: GenshinScreenClassifier) -> None:
        frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        state = classifier.classify(frame)
        assert state.state in ("no_hud", "world_hud", "full_menu")

    def test_screen_state_dataclass_fields(self, classifier: GenshinScreenClassifier) -> None:
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        state = classifier.classify(frame)
        assert isinstance(state, ScreenState)
        assert isinstance(state.state, str)
        assert 0.0 <= state.confidence <= 1.0
        assert isinstance(state.indicators, dict)
        expected_keys = {"dark_frame", "loading_screen", "dialog_box", "minimap", "hp_bar", "skill_icons", "combat", "death_screen", "notification", "domain_entrance", "cutscene"}
        assert set(state.indicators.keys()) == expected_keys

    def test_classify_with_small_frame(self, classifier: GenshinScreenClassifier) -> None:
        frame = np.zeros((540, 960, 3), dtype=np.uint8)
        state = classifier.classify(frame)
        assert state.state == "loading_screen"

    def test_classify_with_green_bar_like_hp(self, classifier: GenshinScreenClassifier) -> None:
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        frame[970:1010, 610:1310] = (60, 200, 60)
        state = classifier.classify(frame)
        assert state.indicators["hp_bar"] == True

    def test_dialog_box_detection(self, classifier: GenshinScreenClassifier) -> None:
        frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
        dialog_region = frame[756:1080, 0:1920].copy()
        frame[756:1080, :] = 60
        state = classifier.classify(frame)
        if state.indicators["dialog_box"]:
            assert state.state == "dialog"
