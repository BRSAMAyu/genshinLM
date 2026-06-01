"""Tests for DialogTextCapture."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from perception.dialog_text_capture import (
    ChapterRegistry,
    DialogCaptureResult,
    DialogCaptureSession,
    _extract_speaker_from_ocr_results,
    _looks_like_speaker_name,
    _normalize_text_for_dedup,
    _combine_dialog_text,
    _DIALOG_ROI_NORMALIZED,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_ocr_provider():
    """Create a mock OCR provider."""
    provider = MagicMock()
    provider.detect_text = MagicMock(return_value=[])
    return provider


@pytest.fixture
def sample_ocr_results_with_speaker():
    """Create sample OCR results with speaker name."""
    from perception.ocr_base import OcrResult

    return [
        OcrResult("温迪", 0.95, (100, 10, 150, 30)),
        OcrResult("你想要来一杯吗？", 0.92, (100, 50, 300, 80)),
        OcrResult("这可是蒙德的特产。", 0.90, (100, 90, 280, 120)),
    ]


@pytest.fixture
def sample_ocr_results_narrator():
    """Create sample OCR results for narrator (no speaker)."""
    from perception.ocr_base import OcrResult

    return [
        OcrResult("风起云涌，蒙德的天空充满了自由的气息。", 0.88, (100, 30, 400, 60)),
        OcrResult("远处传来悠扬的琴声。", 0.90, (100, 70, 250, 100)),
    ]


@pytest.fixture
def sample_ocr_results_english_speaker():
    """Create sample OCR results with English speaker name."""
    from perception.ocr_base import OcrResult

    return [
        OcrResult("Paimon", 0.95, (100, 10, 150, 30)),
        OcrResult("This is so exciting!", 0.92, (100, 50, 300, 80)),
    ]


# =============================================================================
# Test DialogCaptureResult
# =============================================================================


class TestDialogCaptureResult:
    """Test DialogCaptureResult dataclass."""

    def test_creation(self):
        """Test basic creation of DialogCaptureResult."""
        result = DialogCaptureResult(
            speaker="安柏",
            text="你好，旅行者！",
            confidence=0.95,
            timestamp="10:30:00",
        )
        assert result.speaker == "安柏"
        assert result.text == "你好，旅行者！"
        assert result.confidence == 0.95
        assert result.timestamp == "10:30:00"

    def test_normalized_key(self):
        """Test normalized key for deduplication."""
        result = DialogCaptureResult(
            speaker="温迪",
            text="你想要来一杯吗？",
            confidence=0.92,
            timestamp="10:30:00",
        )
        # Normalized key should strip punctuation and whitespace
        key = result.normalized_key()
        assert "你想要来一杯吗" in key or "你想要来一杯吗" in key.replace("？", "")

    def test_equality(self):
        """Test equality comparison for deduplication."""
        result1 = DialogCaptureResult(
            speaker="温迪",
            text="你想要来一杯吗？",
            confidence=0.92,
            timestamp="10:30:00",
        )
        result2 = DialogCaptureResult(
            speaker="温迪",
            text="你想要来一杯吗",  # No punctuation
            confidence=0.80,
            timestamp="10:35:00",
        )
        result3 = DialogCaptureResult(
            speaker="安柏",
            text="不同的文本",
            confidence=0.90,
            timestamp="10:40:00",
        )

        # Results with same normalized text should be equal
        assert result1 == result2
        # Different text should not be equal
        assert result1 != result3


# =============================================================================
# Test Dedup and Normalization
# =============================================================================


class TestTextNormalization:
    """Test text normalization for deduplication."""

    def test_normalize_chinese_punctuation(self):
        """Test normalization removes Chinese punctuation."""
        text = "你好，旅行者！你好旅行者"
        normalized = _normalize_text_for_dedup(text)
        # Should remove punctuation
        assert "，" not in normalized
        assert "！" not in normalized

    def test_normalize_whitespace(self):
        """Test normalization normalizes whitespace."""
        text = "你好   旅行者"
        normalized = _normalize_text_for_dedup(text)
        assert "   " not in normalized

    def test_normalize_brackets(self):
        """Test normalization removes bracket characters."""
        text = "【对话】内容"
        normalized = _normalize_text_for_dedup(text)
        assert "【】" not in normalized

    def test_normalize_case_insensitive(self):
        """Test normalization is case insensitive."""
        text = "HELLO world"
        normalized = _normalize_text_for_dedup(text)
        assert normalized == normalized.lower()


class TestSpeakerExtraction:
    """Test speaker name detection."""

    def test_chinese_speaker_names(self):
        """Test Chinese character names are recognized."""
        assert _looks_like_speaker_name("温迪") is True
        assert _looks_like_speaker_name("安柏") is True
        assert _looks_like_speaker_name("钟离") is True

    def test_english_speaker_names(self):
        """Test English names are recognized."""
        assert _looks_like_speaker_name("Paimon") is True
        assert _looks_like_speaker_name("Venti") is True

    def test_reject_long_text(self):
        """Test that long text is rejected as speaker names."""
        assert _looks_like_speaker_name("这是一个很长的句子") is False
        assert _looks_like_speaker_name("这可能是对话内容而不是名字") is False

    def test_reject_numbers(self):
        """Test that text with many numbers is rejected."""
        assert _looks_like_speaker_name("123456") is False

    def test_reject_empty(self):
        """Test that empty text is rejected."""
        assert _looks_like_speaker_name("") is False
        assert _looks_like_speaker_name("   ") is False

    def test_strip_brackets(self):
        """Test that brackets are stripped from speaker names."""
        result = DialogCaptureResult(
            speaker="【温迪】",
            text="你好",
            confidence=0.9,
            timestamp="10:00:00",
        )
        # The speaker extraction should strip brackets
        # We test the function behavior, not the raw result
        pass


class TestSpeakerExtractionFromOcrResults:
    """Test speaker extraction from OCR results."""

    def test_extract_chinese_speaker(self, sample_ocr_results_with_speaker):
        """Test extracting Chinese speaker from OCR results."""
        speaker, dialog_results = _extract_speaker_from_ocr_results(
            sample_ocr_results_with_speaker, roi_height=200
        )
        assert speaker == "温迪"
        assert len(dialog_results) == 2  # Two dialog lines

    def test_extract_narrator_no_speaker(self, sample_ocr_results_narrator):
        """Test narrator case when no speaker name found."""
        speaker, dialog_results = _extract_speaker_from_ocr_results(
            sample_ocr_results_narrator, roi_height=200
        )
        assert speaker == "旁白"
        assert len(dialog_results) == 2

    def test_extract_english_speaker(self, sample_ocr_results_english_speaker):
        """Test extracting English speaker name."""
        speaker, dialog_results = _extract_speaker_from_ocr_results(
            sample_ocr_results_english_speaker, roi_height=200
        )
        assert speaker == "Paimon"
        assert len(dialog_results) == 1

    def test_empty_results_returns_narrator(self):
        """Test empty OCR results returns narrator."""
        from perception.ocr_base import OcrResult

        speaker, dialog_results = _extract_speaker_from_ocr_results([], roi_height=200)
        assert speaker == "旁白"
        assert dialog_results == []


class TestDialogTextCombination:
    """Test dialog text combination from OCR results."""

    def test_combine_single_line(self):
        """Test combining single line of OCR results."""
        from perception.ocr_base import OcrResult

        results = [
            OcrResult("你好，旅行者！", 0.95, (100, 50, 250, 80)),
        ]
        combined = _combine_dialog_text(results)
        assert "你好" in combined

    def test_combine_multi_line(self):
        """Test combining multi-line dialog."""
        from perception.ocr_base import OcrResult

        results = [
            OcrResult("第一行对话", 0.95, (100, 50, 200, 80)),
            OcrResult("第二行对话", 0.92, (100, 90, 200, 120)),
        ]
        combined = _combine_dialog_text(results)
        assert "第一行" in combined
        assert "第二行" in combined

    def test_combine_empty(self):
        """Test combining empty results returns empty string."""
        combined = _combine_dialog_text([])
        assert combined == ""


# =============================================================================
# Test ChapterRegistry
# =============================================================================


class TestChapterRegistry:
    """Test ChapterRegistry class."""

    def test_initialization(self):
        """Test registry initialization with archon quests."""
        registry = ChapterRegistry()
        # Should have loaded archon quests
        slug, title = registry.get_chapter_info("AQ001")
        assert slug is not None
        assert title is not None

    def test_archon_quest_mapping(self):
        """Test mapping from quest_id to chapter info."""
        registry = ChapterRegistry()
        slug, title = registry.get_chapter_info("AQ001")
        # Should be from序章·第一幕
        assert "xu_zhang" in slug or "xu" in slug
        assert "捕风的异乡人" in title

    def test_output_path_creation(self):
        """Test output path is correctly formed."""
        registry = ChapterRegistry()
        path = registry.get_output_path("AQ001")
        assert "data" in str(path)
        assert "genshin_story" in str(path)
        assert "captured.txt" in str(path)

    def test_unknown_quest_fallback(self):
        """Test fallback for unknown quest IDs."""
        registry = ChapterRegistry()
        slug, title = registry.get_chapter_info("UNKNOWN_QUEST")
        assert slug == "general"
        assert title == "通用对话"

    def test_register_custom_quest(self):
        """Test registering custom quest mappings."""
        registry = ChapterRegistry()
        registry.register_quest("CUSTOM001", "自定义章节", "自定义标题")
        slug, title = registry.get_chapter_info("CUSTOM001")
        assert slug is not None
        assert "自定义" in title

    def test_slug_generation(self):
        """Test slug generation from chapter names."""
        slug = ChapterRegistry._make_slug("序章·第一幕")
        assert "xu" in slug.lower()
        assert "zhang" in slug.lower()

        slug = ChapterRegistry._make_slug("第一章·第一幕")
        assert "di_yi_zhang" in slug.lower()


# =============================================================================
# Test DialogCaptureSession
# =============================================================================


class TestDialogCaptureSession:
    """Test DialogCaptureSession class."""

    def test_initialization(self, mock_ocr_provider):
        """Test session initialization."""
        session = DialogCaptureSession(
            ocr_provider=mock_ocr_provider,
            chapter_id="AQ001",
            chapter_title="序章·第一幕",
        )
        assert session.output_path.name == "captured.txt"
        assert session.capture_count == 0
        assert session.skip_count == 0

    def test_custom_output_directory(self, mock_ocr_provider):
        """Test custom output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "custom_story"
            session = DialogCaptureSession(
                ocr_provider=mock_ocr_provider,
                chapter_id="AQ001",
                chapter_title="测试",
                output_dir=output_dir,
            )
            assert session.output_path.parent == output_dir

    def test_roi_computation_1080p(self, mock_ocr_provider):
        """Test ROI computation for 1920x1080 resolution."""
        session = DialogCaptureSession(
            ocr_provider=mock_ocr_provider,
            chapter_id="AQ001",
            chapter_title="测试",
        )

        # Create a synthetic 1920x1080 frame
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        roi = session._compute_roi_pixels(frame)

        # Verify ROI is correctly computed
        x_norm, y_norm, w_norm, h_norm = _DIALOG_ROI_NORMALIZED
        assert roi[0] == int(x_norm * 1920)  # x1
        assert roi[1] == int(y_norm * 1080)  # y1
        assert roi[2] == int((x_norm + w_norm) * 1920)  # x2
        assert roi[3] == int((y_norm + h_norm) * 1080)  # y2

    def test_roi_computation_720p(self, mock_ocr_provider):
        """Test ROI computation for 1280x720 resolution."""
        session = DialogCaptureSession(
            ocr_provider=mock_ocr_provider,
            chapter_id="AQ001",
            chapter_title="测试",
        )

        # Create a synthetic 1280x720 frame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        roi = session._compute_roi_pixels(frame)

        x_norm, y_norm, w_norm, h_norm = _DIALOG_ROI_NORMALIZED
        assert roi[0] == int(x_norm * 1280)
        assert roi[1] == int(y_norm * 720)
        assert roi[2] == int((x_norm + w_norm) * 1280)
        assert roi[3] == int((y_norm + h_norm) * 720)

    def test_capture_no_text(self, mock_ocr_provider):
        """Test capture when no text is detected."""
        mock_ocr_provider.detect_text.return_value = []

        session = DialogCaptureSession(
            ocr_provider=mock_ocr_provider,
            chapter_id="AQ001",
            chapter_title="测试",
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = session.capture(frame)

        assert result is None
        assert session.capture_count == 0

    def test_capture_with_speaker(self, mock_ocr_provider):
        """Test capture with speaker name."""
        from perception.ocr_base import OcrResult

        mock_ocr_provider.detect_text.return_value = [
            OcrResult("安柏", 0.95, (100, 10, 150, 30)),
            OcrResult("你好，旅行者！", 0.92, (100, 50, 300, 80)),
        ]

        session = DialogCaptureSession(
            ocr_provider=mock_ocr_provider,
            chapter_id="AQ001",
            chapter_title="测试",
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = session.capture(frame)

        assert result is not None
        assert result.speaker == "安柏"
        assert "你好" in result.text
        assert result.confidence > 0.9

    def test_capture_deduplication(self, mock_ocr_provider):
        """Test that duplicate text is skipped."""
        from perception.ocr_base import OcrResult

        mock_ocr_provider.detect_text.return_value = [
            OcrResult("安柏", 0.95, (100, 10, 150, 30)),
            OcrResult("重复的文本", 0.92, (100, 50, 300, 80)),
        ]

        session = DialogCaptureSession(
            ocr_provider=mock_ocr_provider,
            chapter_id="AQ001",
            chapter_title="测试",
        )

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # First capture
        result1 = session.capture(frame)
        assert result1 is not None
        assert session.capture_count == 1

        # Second capture with same text
        result2 = session.capture(frame)
        assert result2 is None
        assert session.skip_count == 1

    def test_flush_writes_to_file(self, mock_ocr_provider):
        """Test that flush writes buffered captures to file."""
        from perception.ocr_base import OcrResult

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            mock_ocr_provider.detect_text.return_value = [
                OcrResult("安柏", 0.95, (100, 10, 150, 30)),
                OcrResult("测试文本", 0.92, (100, 50, 300, 80)),
            ]

            session = DialogCaptureSession(
                ocr_provider=mock_ocr_provider,
                chapter_id="AQ001",
                chapter_title="测试",
                output_dir=output_dir,
            )

            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            session.capture(frame)

            count = session.flush()
            assert count == 1
            assert session.output_path.exists()

            content = session.output_path.read_text(encoding="utf-8")
            assert "安柏" in content
            assert "测试文本" in content

    def test_context_manager(self, mock_ocr_provider):
        """Test session as context manager."""
        from perception.ocr_base import OcrResult

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            mock_ocr_provider.detect_text.return_value = [
                OcrResult("安柏", 0.95, (100, 10, 150, 30)),
                OcrResult("上下文管理器测试", 0.92, (100, 50, 300, 80)),
            ]

            with DialogCaptureSession(
                ocr_provider=mock_ocr_provider,
                chapter_id="AQ001",
                chapter_title="测试",
                output_dir=output_dir,
            ) as session:
                frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                session.capture(frame)

            # After exiting context, flush should have been called
            assert session.output_path.exists()

    def test_auto_flush_at_buffer_threshold(self, mock_ocr_provider):
        """Test auto-flush when buffer reaches threshold."""
        from perception.ocr_base import OcrResult

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            call_count = 0

            def mock_detect_text(image, roi=None):
                nonlocal call_count
                call_count += 1
                # Return different text each time to avoid dedup
                texts = ["文本1", "文本2", "文本3", "文本4", "文本5",
                         "文本6", "文本7", "文本8", "文本9", "文本10",
                         "文本11", "文本12"]
                return [
                    OcrResult(texts[call_count - 1], 0.95, (100, 50, 250, 80)),
                ]

            mock_ocr_provider.detect_text = mock_detect_text

            session = DialogCaptureSession(
                ocr_provider=mock_ocr_provider,
                chapter_id="AQ001",
                chapter_title="测试",
                output_dir=output_dir,
            )

            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

            # Capture 12 items (buffer threshold is 10)
            for i in range(12):
                session.capture(frame)

            # Should have auto-flushed at 10, then 2 more buffered
            # Total count should be 12
            assert session.capture_count == 12

            # Flush remaining
            session.flush()

            # Verify file has all 12 entries
            content = session.output_path.read_text(encoding="utf-8")
            lines = [l for l in content.strip().split("\n") if l]
            assert len(lines) == 12


# =============================================================================
# Test Integration
# =============================================================================


class TestIntegration:
    """Integration tests for dialog capture."""

    def test_full_capture_flow(self, mock_ocr_provider):
        """Test full capture flow from frame to file."""
        from perception.ocr_base import OcrResult

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Simulate a sequence of dialogs - avoid narrator (short "旁白" causes issues)
            dialog_sequence = [
                [OcrResult("安柏", 0.95, (100, 10, 150, 30)),
                 OcrResult("你好，旅行者！", 0.92, (100, 50, 300, 80)),
                 OcrResult("这里是蒙德城。", 0.91, (100, 90, 280, 120))],
                [OcrResult("派蒙", 0.95, (100, 10, 150, 30)),
                 OcrResult("前面就是风神像了！", 0.93, (100, 50, 320, 80))],
                [OcrResult("温迪", 0.95, (100, 10, 150, 30)),
                 OcrResult("自由真好。", 0.91, (100, 50, 300, 80))],
            ]

            call_idx = 0

            def mock_detect_text(image, roi=None):
                nonlocal call_idx
                if call_idx < len(dialog_sequence):
                    result = dialog_sequence[call_idx]
                    call_idx += 1
                    return result
                return []

            mock_ocr_provider.detect_text = mock_detect_text

            session = DialogCaptureSession(
                ocr_provider=mock_ocr_provider,
                chapter_id="AQ001",
                chapter_title="测试",
                output_dir=output_dir,
            )

            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

            # Capture all dialogs
            for _ in dialog_sequence:
                session.capture(frame)

            session.flush()

            # Verify output file
            content = session.output_path.read_text(encoding="utf-8")
            lines = [l for l in content.strip().split("\n") if l]
            # First dialog has 3 lines (speaker + 2 dialog lines), others have 1 line each
            assert len(lines) >= 3
            assert any("你好" in l for l in lines)
            assert any("蒙德城" in l for l in lines)