"""Tests for OCR Router, GLM-OCR provider, and OCR PostProcessor."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from perception.glm_ocr_provider import GlmOcrConfig, GlmOcrProvider
from perception.ocr_base import OcrConfig, OcrResult, ProviderStatus
from perception.ocr_engine import OcrEngine, PaddleOcrProvider
from perception.ocr_post_processor import OcrPostProcessor, OcrPostProcessorConfig, OcrScanRegion
from perception.ocr_router import OcrRouter, OcrRouterConfig


# ---------------------------------------------------------------------------
# GlmOcrProvider tests
# ---------------------------------------------------------------------------


class TestGlmOcrProvider:
    def test_status_without_api_key(self):
        provider = GlmOcrProvider(config=GlmOcrConfig(api_key=""))
        status = provider.status()
        assert not status.ok
        assert "ZHIPU_API_KEY" in status.message

    def test_status_with_api_key(self):
        provider = GlmOcrProvider(config=GlmOcrConfig(api_key="test_key"))
        status = provider.status()
        assert status.ok

    def test_detect_text_parses_layout_details(self):
        fake_response = {
            "layout_details": [[
                {"index": 1, "label": "text", "bbox_2d": [10, 20, 200, 50], "content": "Hello World"},
                {"index": 2, "label": "title", "bbox_2d": [10, 60, 300, 90], "content": "Title"},
                {"index": 3, "label": "figure", "bbox_2d": [0, 0, 100, 100], "content": "skip this"},
            ]],
        }
        provider = GlmOcrProvider(config=GlmOcrConfig(api_key="test_key"))
        with patch.object(provider, "_request", return_value=fake_response):
            image = np.zeros((100, 200, 3), dtype=np.uint8)
            results = provider.detect_text(image)
            assert len(results) == 2
            assert results[0].text == "Hello World"
            assert results[0].source == "glm_ocr"
            assert results[1].text == "Title"

    def test_detect_text_with_roi_offsets_bbox(self):
        fake_response = {
            "layout_details": [[
                {"index": 1, "label": "text", "bbox_2d": [5, 10, 100, 30], "content": "cropped text"},
            ]],
        }
        provider = GlmOcrProvider(config=GlmOcrConfig(api_key="test_key"))
        with patch.object(provider, "_request", return_value=fake_response):
            image = np.zeros((600, 800, 3), dtype=np.uint8)
            roi = (100, 200, 400, 400)
            results = provider.detect_text(image, roi=roi)
            assert len(results) == 1
            assert results[0].text == "cropped text"
            assert results[0].bbox == (105, 210, 200, 230)

    def test_detect_text_handles_api_error(self):
        from llm.provider_base import ProviderRequestError
        provider = GlmOcrProvider(config=GlmOcrConfig(api_key="test_key"))
        with patch.object(provider, "_request", side_effect=ProviderRequestError("timeout")):
            image = np.zeros((100, 200, 3), dtype=np.uint8)
            with pytest.raises(ProviderRequestError):
                provider.detect_text(image)

    def test_detect_text_falls_back_to_md_results(self):
        fake_response = {
            "layout_details": [],
            "md_results": "Line one\nLine two\n",
        }
        provider = GlmOcrProvider(config=GlmOcrConfig(api_key="test_key"))
        with patch.object(provider, "_request", return_value=fake_response):
            image = np.zeros((100, 200, 3), dtype=np.uint8)
            results = provider.detect_text(image)
            assert len(results) == 2
            assert results[0].source == "glm_ocr_md"
            assert results[0].confidence == 0.7


# ---------------------------------------------------------------------------
# OcrRouter tests
# ---------------------------------------------------------------------------


def _make_provider(name: str, results: list[OcrResult], available: bool = True) -> MagicMock:
    provider = MagicMock()
    provider.name = name
    provider.detect_text.return_value = results
    provider.status.return_value = ProviderStatus(name, available)
    return provider


class TestOcrRouter:
    def test_returns_primary_results_synchronously(self):
        primary_results = [OcrResult("hello", 0.95, (0, 0, 100, 30))]
        primary = _make_provider("fast", primary_results)
        router = OcrRouter(primary=primary, fallback=None)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        results = router.detect_text(image)
        assert results == primary_results

    def test_escalates_on_low_confidence_high_value(self):
        low_conf = [OcrResult("unclear", 0.4, (0, 0, 100, 30))]
        high_conf = [OcrResult("clear text", 0.9, (0, 0, 100, 30), "glm_ocr")]
        primary = _make_provider("fast", low_conf)
        fallback = _make_provider("cloud", high_conf)
        config = OcrRouterConfig(confidence_threshold=0.7)
        router = OcrRouter(primary=primary, fallback=fallback, config=config)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        results = router.detect_text(image, roi_id="dialog_text")
        assert results == low_conf
        import time as _t
        _t.sleep(0.1)
        fallback.detect_text.assert_called_once()

    def test_does_not_escalate_on_low_confidence_low_value(self):
        low_conf = [OcrResult("unclear", 0.4, (0, 0, 100, 30))]
        primary = _make_provider("fast", low_conf)
        fallback = _make_provider("cloud", [])
        config = OcrRouterConfig(confidence_threshold=0.7)
        router = OcrRouter(primary=primary, fallback=fallback, config=config)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        results = router.detect_text(image, roi_id="random_area")
        assert results == low_conf
        fallback.detect_text.assert_not_called()

    def test_does_not_escalate_when_disabled(self):
        low_conf = [OcrResult("unclear", 0.4, (0, 0, 100, 30))]
        primary = _make_provider("fast", low_conf)
        fallback = _make_provider("cloud", [])
        config = OcrRouterConfig(escalation_enabled=False)
        router = OcrRouter(primary=primary, fallback=fallback, config=config)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        results = router.detect_text(image, roi_id="dialog_text")
        assert results == low_conf
        fallback.detect_text.assert_not_called()

    def test_escalates_on_empty_results(self):
        primary = _make_provider("fast", [])
        fallback_results = [OcrResult("found", 0.9, (0, 0, 50, 20), "glm_ocr")]
        fallback = _make_provider("cloud", fallback_results)
        router = OcrRouter(primary=primary, fallback=fallback)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        results = router.detect_text(image, roi_id="dialog_text")
        assert results == []
        import time as _t
        _t.sleep(0.1)
        fallback.detect_text.assert_called_once()

    def test_merge_prefers_fallback_on_overlap(self):
        primary = [OcrResult("unclear", 0.4, (10, 10, 100, 40), "paddle")]
        fallback = [OcrResult("clear text", 0.9, (10, 10, 100, 40), "glm_ocr")]
        merged = OcrRouter._merge(primary, fallback)
        texts = [r.text for r in merged]
        assert "clear text" in texts
        assert merged[0].text == "clear text"

    def test_merge_keeps_non_overlapping(self):
        primary = [OcrResult("left text", 0.95, (0, 0, 50, 20), "paddle")]
        fallback = [OcrResult("right text", 0.9, (200, 0, 300, 20), "glm_ocr")]
        merged = OcrRouter._merge(primary, fallback)
        assert len(merged) == 2
        texts = {r.text for r in merged}
        assert texts == {"left text", "right text"}

    def test_force_fallback_bypasses_check(self):
        high_conf = [OcrResult("good", 0.95, (0, 0, 100, 30))]
        primary = _make_provider("fast", high_conf)
        fallback = _make_provider("cloud", [])
        config = OcrRouterConfig(escalation_enabled=False)
        router = OcrRouter(primary=primary, fallback=fallback, config=config)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        router.detect_text(image, force_fallback=True)
        import time as _t
        _t.sleep(0.1)
        fallback.detect_text.assert_called_once()

    def test_status_combines_both_providers(self):
        primary = _make_provider("fast", [], available=True)
        fallback = _make_provider("cloud", [], available=True)
        router = OcrRouter(primary=primary, fallback=fallback)
        status = router.status()
        assert status.ok
        assert "primary=True" in status.message
        assert "fallback=True" in status.message


# ---------------------------------------------------------------------------
# OcrPostProcessor tests
# ---------------------------------------------------------------------------


class TestOcrPostProcessor:
    def _make_observation(self, frame_id: int = 1) -> MagicMock:
        obs = MagicMock()
        obs.frame_id = frame_id
        obs.viewport_size = (1920, 1080)
        obs.extensions = {}
        return obs

    def test_publishes_cached_results_every_frame(self):
        provider = _make_provider("ocr", [OcrResult("cached", 0.9, (10, 20, 100, 40))])
        config = OcrPostProcessorConfig(
            interval_sec=9999.0,
            scan_regions=(OcrScanRegion("test_roi", (0, 0, 200, 50)),),
        )
        pp = OcrPostProcessor(provider, config)
        pp._cached_blocks = [{"id": "ocr:test_roi:0:0", "text": "cached", "confidence": 0.9}]

        obs = self._make_observation()
        state_bus = MagicMock()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        pp.process(frame, obs, state_bus)
        assert len(obs.extensions["ocr_blocks"]) == 1
        assert obs.extensions["ocr_blocks"][0]["text"] == "cached"

    def test_triggers_async_scan_on_interval(self):
        provider = _make_provider("ocr", [OcrResult("new text", 0.95, (100, 200, 300, 220))])
        config = OcrPostProcessorConfig(
            interval_sec=0.0,
            scan_regions=(OcrScanRegion("dialog", (0, 700, 1920, 1080)),),
        )
        pp = OcrPostProcessor(provider, config)
        pp._last_call_time = 0.0

        obs = self._make_observation()
        state_bus = MagicMock()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        pp.process(frame, obs, state_bus)
        import time as _t
        _t.sleep(0.2)

        obs2 = self._make_observation(frame_id=2)
        pp.process(frame, obs2, state_bus)
        blocks = obs2.extensions["ocr_blocks"]
        assert len(blocks) >= 1
        assert blocks[0]["text"] == "new text"
        assert blocks[0]["roi_id"] == "dialog"

    def test_scan_output_matches_ocr_block_schema(self):
        provider = _make_provider("ocr", [OcrResult("hello", 0.88, (100, 200, 300, 230), "paddle_ocr")])
        config = OcrPostProcessorConfig(
            interval_sec=0.0,
            scan_regions=(OcrScanRegion("test_area", (50, 50, 400, 300)),),
        )
        pp = OcrPostProcessor(provider, config)
        pp._last_call_time = 0.0

        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        pp._async_scan(frame, 42, (1920, 1080))

        blocks = pp._cached_blocks
        assert len(blocks) == 1
        b = blocks[0]
        assert "id" in b
        assert b["roi_id"] == "test_area"
        assert b["text"] == "hello"
        assert b["confidence"] == 0.88
        assert "bbox_norm" in b
        assert len(b["bbox_norm"]) == 4
        assert b["source"] == "paddle_ocr"
        assert b["frame_id"] == 42

    def test_handles_ocr_failure_gracefully(self):
        provider = MagicMock()
        provider.name = "fail_ocr"
        provider.detect_text.side_effect = RuntimeError("boom")
        config = OcrPostProcessorConfig(
            interval_sec=0.0,
            scan_regions=(OcrScanRegion("bad_roi", (0, 0, 100, 100)),),
        )
        pp = OcrPostProcessor(provider, config)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        pp._async_scan(frame, 1, (100, 100))
        assert pp._cached_blocks == []


# ---------------------------------------------------------------------------
# PaddleOcrProvider backward compat tests
# ---------------------------------------------------------------------------


class TestPaddleOcrProviderCompat:
    def test_ocr_engine_inherits_paddle_provider(self):
        engine = OcrEngine()
        assert isinstance(engine, PaddleOcrProvider)
        assert engine.name == "paddle_ocr"

    def test_detect_text_roi_delegates(self):
        engine = OcrEngine()
        results = [OcrResult("test", 0.9, (10, 20, 100, 40))]
        with patch.object(PaddleOcrProvider, "detect_text", return_value=results):
            image = np.zeros((600, 800, 3), dtype=np.uint8)
            out = engine.detect_text_roi(image, (0, 0, 400, 300))
            assert out == results

    def test_read_number_extracts_digits(self):
        engine = OcrEngine()
        results = [OcrResult("CD: 5s", 0.9, (0, 0, 50, 20))]
        with patch.object(PaddleOcrProvider, "detect_text", return_value=results):
            assert engine.read_number(np.zeros((100, 100, 3), dtype=np.uint8)) == 5

    def test_contains_text_finds_keyword(self):
        engine = OcrEngine()
        results = [OcrResult("奖励已领取", 0.9, (0, 0, 200, 40))]
        with patch.object(PaddleOcrProvider, "detect_text", return_value=results):
            found, kw = engine.contains_text(np.zeros((100, 200, 3), dtype=np.uint8), ["奖励", "完成"])
            assert found
            assert kw == "奖励"
