"""Wish result detector: identifying star rarity and wish outcomes.

Covers U-61: Detecting item rarity by star count from wish results.
Uses screen analysis and OCR to identify 3-star, 4-star, and 5-star items.

Integrates with:
- perception/ocr_router.py for text recognition
- perception/genshin_screen_classifier.py for screen state
- planning/wish_shop_system.py for pity tracking
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Star rarity levels
# ---------------------------------------------------------------------------

class StarRarity(str, Enum):
    THREE_STAR = "3_star"
    FOUR_STAR = "4_star"
    FIVE_STAR = "5_star"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WishResult:
    """A single wish result with rarity."""
    item_name: str
    item_type: str  # "weapon", "character"
    rarity: StarRarity
    is_featured: bool = False
    is_new: bool = True  # New to inventory


@dataclass(frozen=True, slots=True)
class RarityDetection:
    """Detection result for star rarity."""
    detected: bool
    star_count: int
    rarity: StarRarity
    confidence: float = 0.0
    method: str = ""  # "ocr", "color", "animation"


# ---------------------------------------------------------------------------
# Star detection regions
# ---------------------------------------------------------------------------

# Screen regions for star detection (normalized coordinates)
STAR_REGIONS: dict[StarRarity, tuple[tuple[float, float], tuple[float, float]]] = {
    StarRarity.THREE_STAR: ((0.45, 0.40), (0.55, 0.50)),
    StarRarity.FOUR_STAR: ((0.45, 0.35), (0.55, 0.45)),
    StarRarity.FIVE_STAR: ((0.45, 0.30), (0.55, 0.40)),
}

# Color thresholds for star detection (RGB)
STAR_COLORS: dict[StarRarity, tuple[int, int, int]] = {
    StarRarity.THREE_STAR: (150, 150, 150),  # Gray
    StarRarity.FOUR_STAR: (136, 88, 200),   # Purple
    StarRarity.FIVE_STAR: (200, 160, 80),    # Gold
}


# ---------------------------------------------------------------------------
# Wish result analyzer
# ---------------------------------------------------------------------------

class WishResultDetector:
    """Detects wish results and star rarity from screen (U-61).

    Analyzes wish animation, results screen, and item cards to identify
    the rarity of pulled items.
    """

    # Detection thresholds
    GOLD_COLOR_THRESHOLD = 50   # Color distance threshold for gold
    PURPLE_COLOR_THRESHOLD = 40  # Color distance for purple
    GRAY_COLOR_THRESHOLD = 30   # Color distance for gray

    # Animation timing
    WISH_ANIMATION_DURATION_MS = 3000
    RESULT_REVEAL_DELAY_MS = 500

    def __init__(self) -> None:
        self._results_history: list[WishResult] = []
        self._current_rarity: StarRarity = StarRarity.UNKNOWN

    @property
    def last_result(self) -> WishResult | None:
        """Get the last detected wish result."""
        return self._results_history[-1] if self._results_history else None

    def detect_rarity_from_color(
        self,
        frame_pixels: list[list[tuple[int, int, int]]],
        region: tuple[tuple[float, float], tuple[float, float]],
    ) -> StarRarity:
        """Detect star rarity from color analysis.

        Args:
            frame_pixels: RGB pixel data from frame
            region: Detection region ((x1,y1), (x2,y2))

        Returns:
            Detected StarRarity
        """
        # Extract region pixels
        height = len(frame_pixels)
        width = len(frame_pixels[0]) if height > 0 else 0

        (x1, y1), (x2, y2) = region
        x1_pix = int(x1 * width)
        x2_pix = int(x2 * width)
        y1_pix = int(y1 * height)
        y2_pix = int(y2 * height)

        # Sample colors in region
        sample_colors: list[tuple[int, int, int]] = []
        step = max(1, (y2_pix - y1_pix) // 5)
        for y in range(y1_pix, y2_pix, step):
            for x in range(x1_pix, x2_pix, step):
                if y < height and x < width:
                    sample_colors.append(frame_pixels[y][x])

        if not sample_colors:
            return StarRarity.UNKNOWN

        # Count gold/purple/gray pixels
        gold_count = 0
        purple_count = 0
        gray_count = 0

        for r, g, b in sample_colors:
            # Check for gold (five star)
            if self._color_distance(r, g, b, STAR_COLORS[StarRarity.FIVE_STAR]) < self.GOLD_COLOR_THRESHOLD:
                gold_count += 1
            # Check for purple (four star)
            elif self._color_distance(r, g, b, STAR_COLORS[StarRarity.FOUR_STAR]) < self.PURPLE_COLOR_THRESHOLD:
                purple_count += 1
            # Check for gray (three star)
            elif r == g == b and r < 200:  # Neutral color
                gray_count += 1

        total = len(sample_colors)
        gold_pct = gold_count / max(total, 1)
        purple_pct = purple_count / max(total, 1)
        gray_pct = gray_count / max(total, 1)

        # Determine rarity
        if gold_pct > 0.3:
            return StarRarity.FIVE_STAR
        if purple_pct > 0.3:
            return StarRarity.FOUR_STAR
        if gray_pct > 0.5:
            return StarRarity.THREE_STAR

        return StarRarity.UNKNOWN

    def detect_from_animation(
        self,
        animation_phase: str,
    ) -> StarRarity:
        """Detect rarity from animation phase.

        Args:
            animation_phase: Current animation phase

        Returns:
            Detected StarRarity based on animation
        """
        if "gold" in animation_phase.lower() or "five" in animation_phase.lower():
            return StarRarity.FIVE_STAR
        if "purple" in animation_phase.lower() or "four" in animation_phase.lower():
            return StarRarity.FOUR_STAR
        if "silver" in animation_phase.lower() or "three" in animation_phase.lower():
            return StarRarity.THREE_STAR
        return StarRarity.UNKNOWN

    def analyze_result_screen(
        self,
        screen_state: str,
        ocr_text: str | None = None,
        frame_pixels: list[list[tuple[int, int, int]]] | None = None,
    ) -> RarityDetection:
        """Analyze wish result screen for rarity.

        Args:
            screen_state: Current screen state
            ocr_text: Optional OCR text from screen
            frame_pixels: Optional pixel data for color analysis

        Returns:
            RarityDetection with detected rarity and confidence
        """
        detection = RarityDetection(detected=False, star_count=0, rarity=StarRarity.UNKNOWN)

        # Method 1: OCR text analysis
        if ocr_text:
            if "★" in ocr_text or "star" in ocr_text.lower():
                star_count = ocr_text.count("★") + (1 if "5" in ocr_text else 0) + (1 if "4" in ocr_text else 0)
                if "5" in ocr_text or star_count >= 5:
                    detection = RarityDetection(
                        detected=True,
                        star_count=5,
                        rarity=StarRarity.FIVE_STAR,
                        confidence=0.9,
                        method="ocr",
                    )
                elif "4" in ocr_text or star_count == 4:
                    detection = RarityDetection(
                        detected=True,
                        star_count=4,
                        rarity=StarRarity.FOUR_STAR,
                        confidence=0.9,
                        method="ocr",
                    )

        # Method 2: Color analysis
        if frame_pixels and not detection.detected:
            for rarity in (StarRarity.FIVE_STAR, StarRarity.FOUR_STAR, StarRarity.THREE_STAR):
                region = STAR_REGIONS.get(rarity)
                if region:
                    detected_rarity = self.detect_rarity_from_color(frame_pixels, region)
                    if detected_rarity != StarRarity.UNKNOWN:
                        detection = RarityDetection(
                            detected=True,
                            star_count=5 if rarity == StarRarity.FIVE_STAR else 4 if rarity == StarRarity.FOUR_STAR else 3,
                            rarity=detected_rarity,
                            confidence=0.75,
                            method="color",
                        )
                        break

        return detection

    def record_result(
        self,
        result: WishResult,
    ) -> None:
        """Record a wish result for history tracking."""
        self._results_history.append(result)
        if len(self._results_history) > 100:
            self._results_history = self._results_history[-100:]
        log.info("[WishResult] recorded %s %s (rarity: %s)",
                 result.item_type, result.item_name, result.rarity.value)

    def _color_distance(
        self,
        r1: int, g1: int, b1: int,
        rgb2: tuple[int, int, int],
    ) -> float:
        """Calculate color distance between two RGB colors."""
        r2, g2, b2 = rgb2
        return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5


# ---------------------------------------------------------------------------
# Rarity confirmation utility
# ---------------------------------------------------------------------------

class RarityConfirmation:
    """Confirms rarity detection through multiple methods."""

    def __init__(self) -> None:
        self._detector = WishResultDetector()

    def confirm_rarity(
        self,
        primary_detection: RarityDetection,
        secondary_data: dict[str, Any] | None = None,
    ) -> RarityDetection:
        """Confirm rarity with secondary validation.

        Args:
            primary_detection: Primary rarity detection
            secondary_data: Optional secondary validation data

        Returns:
            Confirmed RarityDetection with higher confidence
        """
        if not primary_detection.detected:
            return primary_detection

        confidence = primary_detection.confidence

        # Increase confidence if secondary data matches
        if secondary_data:
            if "ocr_name" in secondary_data:
                # Check if name matches expected rarity patterns
                name = secondary_data["ocr_name"].lower()
                if primary_detection.rarity == StarRarity.FIVE_STAR:
                    # 5-star characters have specific naming patterns
                    if any(c in name for c in ["旅行者", "温迪", "迪卢克", "刻晴", "琴"]):
                        confidence = min(1.0, confidence + 0.1)
                elif primary_detection.rarity == StarRarity.FOUR_STAR:
                    # 4-star names often include "四星" or specific patterns
                    confidence = min(1.0, confidence + 0.05)

        return RarityDetection(
            detected=primary_detection.detected,
            star_count=primary_detection.star_count,
            rarity=primary_detection.rarity,
            confidence=confidence,
            method=f"{primary_detection.method}_confirmed",
        )