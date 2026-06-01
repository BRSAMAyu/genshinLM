"""Dialog text capture — captures and persists Genshin dialog text.

Captures dialog text from the screen bottom region using PaddleOCR,
extracts speaker name and content, saves to chapter-specific files.

Output format: [timestamp] Speaker: Dialog text
Output dir: data/genshin_story/{chapter_slug}/captured.txt
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from perception.ocr_engine import OcrResult

log = logging.getLogger(__name__)

# Normalized dialog ROI for Genshin (resolution-independent)
_DIALOG_ROI_NORMALIZED = (0.15, 0.60, 0.70, 0.25)  # (x_norm, y_norm, w_norm, h_norm)

# Speaker extraction: top 15% of ROI height
_SPEAKER_ZONE_HEIGHT_RATIO = 0.15

# Flush buffer size
_BUFFER_FLUSH_THRESHOLD = 10


def _normalize_text_for_dedup(text: str) -> str:
    """Normalize text for deduplication comparison.

    Strip whitespace, remove common punctuation, and lowercase for comparison.
    """
    # Remove common punctuation and normalize whitespace
    normalized = re.sub(r"[\s　  -​]+", " ", text.strip())
    normalized = re.sub(r"[，。！？：；、·''""【】（）『』「」〈〉《》]", "", normalized)
    return normalized.strip().lower()


def _looks_like_speaker_name(text: str) -> bool:
    """Check if text looks like a Genshin character name.

    Character names are typically:
    - Chinese: 1-4 characters
    - English: 2-10 characters (flexible for names like "Paimon", "Traveler")
    """
    if not text:
        return False

    # Strip common decorative brackets and prefixes
    cleaned = text.strip()
    cleaned = re.sub(r"^[\[\(【「『〈《]\s*", "", cleaned)
    cleaned = re.sub(r"\s*[\]\)】」』〉》]\s*$", "", cleaned).strip()

    # Check if it looks like a name
    has_chinese = bool(re.search(r"[一-鿿]", cleaned))
    has_latin = bool(re.search(r"[a-zA-Z]", cleaned))

    if has_latin:
        # English names: 2-10 characters, mostly letters
        if 2 <= len(cleaned) <= 10:
            # Reject if it has many digits or special chars
            special_ratio = sum(1 for c in cleaned if not c.isalnum()) / len(cleaned)
            if special_ratio <= 0.3:
                return True

    if has_chinese:
        # Chinese names: typically 1-4 characters
        # Count Chinese characters
        chinese_chars = re.findall(r"[一-鿿]", cleaned)
        if 1 <= len(chinese_chars) <= 4:
            # Check if it's mostly Chinese
            if len(chinese_chars) / len(cleaned) >= 0.6:
                return True

    return False


def _extract_speaker_from_ocr_results(
    results: list[OcrResult], roi_height: int
) -> tuple[str, list[OcrResult]]:
    """Extract speaker name from top portion of OCR results.

    Args:
        results: OCR results sorted by vertical position (top to bottom)
        roi_height: Height of the ROI in pixels

    Returns:
        Tuple of (speaker_name, remaining_ocr_results)
        If no speaker found, returns ("旁白", results)
    """
    if not results:
        return ("旁白", [])

    # Calculate the speaker zone boundary (top 15% of ROI)
    speaker_zone_bottom = int(roi_height * _SPEAKER_ZONE_HEIGHT_RATIO)

    # Find all OCR results in the speaker zone
    speaker_results: list[OcrResult] = []
    dialog_results: list[OcrResult] = []

    for r in results:
        # Get the vertical center of the bbox
        y_center = (r.bbox[1] + r.bbox[3]) / 2
        if y_center <= speaker_zone_bottom:
            speaker_results.append(r)
        else:
            dialog_results.append(r)

    # Check if speaker zone has a single line of text that looks like a name
    if speaker_results:
        # Combine text from speaker zone
        combined_text = " ".join(r.text.strip() for r in speaker_results if r.text.strip())

        if combined_text and _looks_like_speaker_name(combined_text):
            # Clean up the speaker name
            speaker = combined_text.strip()
            # Remove decorative brackets if present
            speaker = re.sub(r"^[\[\(【「『〈《]\s*", "", speaker)
            speaker = re.sub(r"\s*[\]\)】」』〉》]\s*$", "", speaker)
            return (speaker, dialog_results)

    return ("旁白", results)


def _combine_dialog_text(results: list[OcrResult]) -> str:
    """Combine OCR results into a single dialog text string.

    Results are sorted by vertical position, then by horizontal position.
    """
    if not results:
        return ""

    # Sort by vertical position (top to bottom), then horizontal (left to right)
    sorted_results = sorted(results, key=lambda r: (r.bbox[1], r.bbox[0]))

    # Join with spaces, preserving line breaks for multi-line dialog
    lines: list[str] = []
    current_y = None
    current_line: list[str] = []

    for r in sorted_results:
        y_center = (r.bbox[1] + r.bbox[3]) / 2
        if current_y is not None and abs(y_center - current_y) > 20:
            # New line detected
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [r.text.strip()]
            current_y = y_center
        else:
            current_line.append(r.text.strip())
            if current_y is None:
                current_y = y_center

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)


@dataclass(slots=True)
class DialogCaptureResult:
    """Result of a single dialog capture."""

    speaker: str
    text: str
    confidence: float
    timestamp: str  # HH:MM:SS format

    def normalized_key(self) -> str:
        """Return normalized text key for deduplication."""
        return _normalize_text_for_dedup(self.text)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DialogCaptureResult):
            return NotImplemented
        return self.normalized_key() == other.normalized_key()

    def __hash__(self) -> int:
        return hash(self.normalized_key())


class ChapterRegistry:
    """Maps quest IDs to chapter slugs and titles for output paths."""

    def __init__(self) -> None:
        self._quest_map: dict[str, tuple[str, str]] = {}
        self._load_from_archon_quests()

    def _load_from_archon_quests(self) -> None:
        """Load quest mappings from genshin_archon_quests module."""
        try:
            from knowledge.genshin_archon_quests import ARCHON_QUESTS

            for quest in ARCHON_QUESTS:
                slug = self._make_slug(quest.chapter)
                self._quest_map[quest.quest_id] = (slug, quest.title)
        except ImportError:
            log.warning("Could not import genshin_archon_quests, using empty registry")

    @staticmethod
    def _make_slug(chapter: str) -> str:
        """Convert chapter name to filesystem-safe slug.

        Examples:
            "序章·第一幕" -> "xu_zhang_di_yi_mu"
            "第一章·第一幕" -> "di_yi_zhang_di_yi_mu"
        """
        # Remove special characters and normalize
        slug = chapter.replace("·", "_").replace("·", "_")
        # Replace Chinese number prefixes
        chinese_numbers = {
            "序章": "xu_zhang",
            "第一章": "di_yi_zhang",
            "第二章": "di_er_zhang",
            "第三章": "di_san_zhang",
            "第四章": "di_si_zhang",
            "第五章": "di_wu_zhang",
        }
        for cn, latin in chinese_numbers.items():
            if slug.startswith(cn):
                slug = latin + slug[len(cn) :]
                break

        # Convert to pinyin-ish slug (simple approach: keep Chinese chars)
        # For now, just clean up special chars
        slug = re.sub(r"[^a-zA-Z0-9_一-鿿]", "_", slug)
        slug = re.sub(r"_+", "_", slug)
        slug = slug.strip("_")
        return slug.lower()

    def get_output_path(self, quest_id: str) -> Path:
        """Get output file path for a quest ID.

        Returns:
            Path to captured.txt in the chapter's story directory
        """
        slug, _ = self.get_chapter_info(quest_id)
        base_dir = Path("data") / "genshin_story" / slug
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / "captured.txt"

    def get_chapter_info(self, quest_id: str) -> tuple[str, str]:
        """Get chapter slug and title for a quest ID.

        Returns:
            Tuple of (slug, title)
            Defaults to ("general", "通用对话") if quest_id not found
        """
        if quest_id in self._quest_map:
            return self._quest_map[quest_id]
        return ("general", "通用对话")

    def register_quest(self, quest_id: str, chapter: str, title: str) -> None:
        """Register a custom quest mapping.

        Useful for sub-quests or world quests not in the archon quest list.
        """
        slug = self._make_slug(chapter)
        self._quest_map[quest_id] = (slug, title)


class DialogCaptureSession:
    """Captures dialog text from Genshin dialog regions.

    Uses PaddleOCR to read dialog text from the bottom of the screen,
    extracts speaker names and content, and persists to chapter files.
    """

    def __init__(
        self,
        ocr_provider: object,
        chapter_id: str,
        chapter_title: str,
        output_dir: Path | None = None,
    ) -> None:
        """Initialize dialog capture session.

        Args:
            ocr_provider: OCR provider with detect_text(image, roi) method
            chapter_id: Quest ID or chapter identifier
            chapter_title: Display title for the chapter
            output_dir: Optional custom output directory (defaults to data/genshin_story/{slug})
        """
        self._ocr = ocr_provider
        self._chapter_id = chapter_id
        self._chapter_title = chapter_title

        # Determine output path
        if output_dir:
            self._output_path = output_dir / "captured.txt"
            self._output_dir = output_dir
        else:
            registry = ChapterRegistry()
            self._output_path = registry.get_output_path(chapter_id)
            self._output_dir = self._output_path.parent

        # Ensure output directory exists
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Buffer for captures
        self._buffer: list[DialogCaptureResult] = []
        self._last_normalized: str = ""

        # Statistics
        self._capture_count = 0
        self._skip_count = 0

    @property
    def output_path(self) -> Path:
        """Get the output file path."""
        return self._output_path

    @property
    def capture_count(self) -> int:
        """Get total number of captures (excluding skipped duplicates)."""
        return self._capture_count

    @property
    def skip_count(self) -> int:
        """Get number of skipped duplicate captures."""
        return self._skip_count

    def _get_current_timestamp(self) -> str:
        """Get current time in HH:MM:SS format."""
        t = time.localtime()
        return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

    def _compute_roi_pixels(
        self, frame: np.ndarray
    ) -> tuple[int, int, int, int]:
        """Compute pixel ROI from normalized coordinates.

        Args:
            frame: Input frame (H x W x C)

        Returns:
            Pixel ROI as (x1, y1, x2, y2)
        """
        h, w = frame.shape[:2]
        x_norm, y_norm, w_norm, h_norm = _DIALOG_ROI_NORMALIZED

        x1 = int(x_norm * w)
        y1 = int(y_norm * h)
        x2 = int((x_norm + w_norm) * w)
        y2 = int((y_norm + h_norm) * h)

        # Clamp to frame bounds
        x1 = max(0, min(x1, w))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h))
        y2 = max(0, min(y2, h))

        return (x1, y1, x2, y2)

    def capture(self, frame: np.ndarray) -> DialogCaptureResult | None:
        """Capture dialog text from the current frame.

        Args:
            frame: BGR frame from screen capture

        Returns:
            DialogCaptureResult if text was found and not a duplicate,
            None if no text or duplicate
        """
        # Compute pixel ROI
        roi_pixels = self._compute_roi_pixels(frame)
        x1, y1, x2, y2 = roi_pixels
        roi_height = y2 - y1

        # Run OCR on dialog region
        ocr_results = self._ocr.detect_text(frame, roi=roi_pixels)

        if not ocr_results:
            return None

        # Extract speaker from top of ROI
        speaker, dialog_results = _extract_speaker_from_ocr_results(
            ocr_results, roi_height
        )

        if not dialog_results:
            # No dialog content found
            return None

        # Combine dialog text
        dialog_text = _combine_dialog_text(dialog_results)

        if not dialog_text:
            return None

        # Calculate average confidence
        avg_confidence = sum(r.confidence for r in dialog_results) / len(dialog_results)

        # Create result
        result = DialogCaptureResult(
            speaker=speaker,
            text=dialog_text,
            confidence=avg_confidence,
            timestamp=self._get_current_timestamp(),
        )

        # Check for duplicate
        normalized = result.normalized_key()
        if normalized == self._last_normalized:
            self._skip_count += 1
            return None

        self._last_normalized = normalized

        # Add to buffer
        self._buffer.append(result)
        self._capture_count += 1

        # Auto-flush if buffer is full
        if len(self._buffer) >= _BUFFER_FLUSH_THRESHOLD:
            self.flush()

        return result

    def flush(self) -> int:
        """Write buffered captures to file.

        Returns:
            Number of entries written
        """
        if not self._buffer:
            return 0

        # Write to file
        lines: list[str] = []
        for result in self._buffer:
            lines.append(f"[{result.timestamp}] {result.speaker}: {result.text}")

        try:
            with open(self._output_path, "a", encoding="utf-8") as f:
                for line in lines:
                    f.write(line + "\n")
        except IOError as e:
            log.error("Failed to write dialog captures: %s", e)
            return 0

        count = len(self._buffer)
        self._buffer.clear()
        log.info(
            "Flushed %d dialog captures to %s", count, self._output_path
        )
        return count

    def __enter__(self) -> "DialogCaptureSession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.flush()