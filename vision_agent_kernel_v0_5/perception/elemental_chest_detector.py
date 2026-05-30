"""E-30: Elemental chest detection with element symbol recognition.

Some chests in Genshin require specific elemental activation to open.
This module detects elemental symbols around chests and determines
which element is needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class ElementType(str, Enum):
    PYRO = "pyro"      # Red/orange, flame symbol
    HYDRO = "hydro"    # Blue, water drop symbol
    ELECTRO = "electro"  # Purple, lightning symbol
    CRYO = "cryo"      # Cyan, snowflake symbol
    ANEMO = "anemo"    # Green, swirl symbol
    GEO = "geo"        # Orange/brown, diamond symbol
    DENDRO = "dendro"  # Yellow/green, leaf symbol


@dataclass(frozen=True, slots=True)
class ElementalSymbolDetection:
    """Detected elemental symbol near a chest."""
    element: ElementType
    position: tuple[int, int]  # center pixel
    radius: int
    confidence: float


@dataclass(frozen=True, slots=True)
class ElementalChestDetection:
    """Result of elemental chest detection."""
    chest_found: bool
    elemental_barrier: bool
    required_elements: list[ElementType]
    symbols: list[ElementalSymbolDetection]
    confidence: float
    bounding_box: tuple[int, int, int, int] | None = None


class ElementalChestDetector:
    """Detect elemental activation chests and their required elements."""

    _REF_W = 1920
    _REF_H = 1080

    # Element-specific HSV ranges
    _ELEMENT_RANGES: dict[ElementType, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
        ElementType.PYRO: ((0, 100, 100), (20, 255, 255)),       # Orange-red
        ElementType.HYDRO: ((90, 80, 80), (130, 255, 255)),      # Blue
        ElementType.ELECTRO: ((130, 80, 80), (170, 255, 255)),  # Purple
        ElementType.CRYO: ((85, 50, 100), (110, 255, 255)),      # Cyan
        ElementType.ANEMO: ((35, 60, 60), (85, 255, 255)),      # Green
        ElementType.GEO: ((10, 60, 60), (30, 255, 255)),        # Brown
        ElementType.DENDRO: ((25, 80, 80), (85, 255, 255)),     # Yellow-green
    }

    def __init__(self, scan_radius_px: int = 80) -> None:
        self._scan_radius = scan_radius_px
        self._chest_color_lower = np.array([15, 100, 100], dtype=np.uint8)
        self._chest_color_upper = np.array([40, 255, 255], dtype=np.uint8)  # Golden

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> ElementalChestDetection:
        """Detect elemental chest and required elements.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            ElementalChestDetection with element requirements
        """
        if cv2 is None:
            return ElementalChestDetection(
                chest_found=False,
                elemental_barrier=False,
                required_elements=[],
                symbols=[],
                confidence=0.0,
            )

        # Find potential chest regions
        chest_regions = self._find_chest_regions(frame)

        if not chest_regions:
            return ElementalChestDetection(
                chest_found=False,
                elemental_barrier=False,
                required_elements=[],
                symbols=[],
                confidence=0.0,
            )

        # For each chest region, check surrounding area for elemental symbols
        all_symbols: list[ElementalSymbolDetection] = []
        all_required: list[ElementType] = []
        chest_box = None

        for (cx, cy), (x1, y1, x2, y2) in chest_regions:
            chest_box = (x1, y1, x2, y2)
            region_symbols = self._scan_for_elemental_symbols(
                frame, (x1, y1, x2, y2)
            )
            all_symbols.extend(region_symbols)
            for sym in region_symbols:
                if sym.element not in all_required:
                    all_required.append(sym.element)

        # Determine if elemental barrier present
        has_barrier = len(all_required) > 0

        confidence = 0.9 if chest_box else 0.5

        return ElementalChestDetection(
            chest_found=chest_box is not None,
            elemental_barrier=has_barrier,
            required_elements=all_required,
            symbols=all_symbols,
            confidence=confidence,
            bounding_box=chest_box,
        )

    def _find_chest_regions(self, frame: np.ndarray) -> list[tuple[tuple[int, int], tuple[int, int, int, int]]]:
        """Find golden chest regions in frame."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._chest_color_lower, self._chest_color_upper)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if 500 < area < 50000:  # Reasonable chest size
                x, y, w, h = cv2.boundingRect(contour)
                aspect = w / max(h, 1)
                if 0.3 < aspect < 3.0:  # Chest-like aspect ratio
                    cx, cy = x + w // 2, y + h // 2
                    regions.append(((cx, cy), (x, y, x + w, y + h)))

        return regions

    def _scan_for_elemental_symbols(
        self, frame: np.ndarray, chest_box: tuple[int, int, int, int]
    ) -> list[ElementalSymbolDetection]:
        """Scan area around chest for elemental symbols."""
        x1, y1, x2, y2 = chest_box
        h, w = frame.shape[:2]

        # Expand search area
        expand = self._scan_radius
        sx1 = max(0, x1 - expand)
        sy1 = max(0, y1 - expand)
        sx2 = min(w, x2 + expand)
        sy2 = min(h, y2 + expand)

        search_region = frame[sy1:sy2, sx1:sx2]
        hsv = cv2.cvtColor(search_region, cv2.COLOR_BGR2HSV)

        symbols: list[ElementalSymbolDetection] = []

        for element, (lower_hsv, upper_hsv) in self._ELEMENT_RANGES.items():
            lower = np.array(lower_hsv, dtype=np.uint8)
            upper = np.array(upper_hsv, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)

            # Find distinct regions
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                if 100 < area < 5000:  # Element symbol size
                    M = cv2.moments(contour)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"]) + sx1
                        cy = int(M["m01"] / M["m00"]) + sy1
                        radius = int(np.sqrt(area / np.pi))

                        symbols.append(ElementalSymbolDetection(
                            element=element,
                            position=(cx, cy),
                            radius=radius,
                            confidence=0.75,
                        ))

        return symbols

    def get_activation_guidance(self, detection: ElementalChestDetection) -> str | None:
        """Get text guidance for elemental activation."""
        if not detection.elemental_barrier:
            return None
        elements_str = ", ".join(e.value for e in detection.required_elements)
        return f"Use {elements_str} to activate the chest"