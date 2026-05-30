"""E-39: Quicksand edge detector for Sumeru desert areas.

Detects the edge of quicksand areas to avoid getting stuck.
Quicksand appears as darker sand that shifts when stepped on.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class QuicksandEdgeDetection:
    """Detected quicksand edge."""
    edge_detected: bool
    edge_distance_px: int | None  # Distance to edge from character
    is_too_close: bool
    direction: str | None  # "left" | "right" | "ahead" | "behind"
    confidence: float


class QuicksandDetector:
    """Detect quicksand edges to avoid getting stuck."""

    _REF_W = 1920
    _REF_H = 1080

    # Quicksand color (darker brown than normal sand)
    _QUICKSAND_DARK_LOW = np.array([10, 20, 30], dtype=np.uint8)
    _QUICKSAND_DARK_HIGH = np.array([25, 80, 120], dtype=np.uint8)

    # Normal sand color
    _NORMAL_SAND_LOW = np.array([10, 40, 80], dtype=np.uint8)
    _NORMAL_SAND_HIGH = np.array([25, 100, 180], dtype=np.uint8)

    # Safe distance threshold
    _SAFE_DISTANCE_PX = 150

    def __init__(self) -> None:
        self._last_safe_position: tuple[int, int] | None = None

    def detect_edge(self, frame: np.ndarray, character_pos: tuple[int, int], frame_id: int = 0) -> QuicksandEdgeDetection:
        """Detect proximity to quicksand edge.

        Args:
            frame: BGR image from screen capture
            character_pos: Character screen position (x, y)
            frame_id: Current frame ID

        Returns:
            QuicksandEdgeDetection with edge proximity info
        """
        if cv2 is None:
            return QuicksandEdgeDetection(
                edge_detected=False,
                edge_distance_px=None,
                is_too_close=False,
                direction=None,
                confidence=0.0,
            )

        h, w = frame.shape[:2]

        # Focus on area around character
        cx, cy = character_pos
        roi_size = 400
        x1 = max(0, cx - roi_size // 2)
        y1 = max(0, cy - roi_size // 2)
        x2 = min(w, cx + roi_size // 2)
        y2 = min(h, cy + roi_size // 2)

        scan_region = frame[y1:y2, x1:x2]

        if scan_region.size == 0:
            return QuicksandEdgeDetection(
                edge_detected=False,
                edge_distance_px=None,
                is_too_close=False,
                direction=None,
                confidence=0.0,
            )

        hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)

        # Detect quicksand (dark areas)
        quicksand_mask = cv2.inRange(hsv, self._QUICKSAND_DARK_LOW, self._QUICKSAND_DARK_HIGH)

        # Look for edge contours
        contours, _ = cv2.findContours(quicksand_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return QuicksandEdgeDetection(
                edge_detected=False,
                edge_distance_px=None,
                is_too_close=False,
                direction=None,
                confidence=0.0,
            )

        # Find closest quicksand edge to character
        char_local_x = cx - x1
        char_local_y = cy - y1
        min_distance = float('inf')
        closest_edge_point = None

        for contour in contours:
            for point in contour:
                px, py = point[0]
                dist = np.sqrt((px - char_local_x) ** 2 + (py - char_local_y) ** 2)
                if dist < min_distance:
                    min_distance = dist
                    closest_edge_point = (px + x1, py + y1)

        if closest_edge_point is None:
            return QuicksandEdgeDetection(
                edge_detected=False,
                edge_distance_px=None,
                is_too_close=False,
                direction=None,
                confidence=0.0,
            )

        # Determine direction
        dx = closest_edge_point[0] - cx
        dy = closest_edge_point[1] - cy

        if abs(dx) > abs(dy):
            direction = "right" if dx > 0 else "left"
        else:
            direction = "ahead" if dy < 0 else "behind"

        is_too_close = min_distance < self._SAFE_DISTANCE_PX
        confidence = min(0.9, 0.5 + (1.0 - min_distance / 300))

        return QuicksandEdgeDetection(
            edge_detected=True,
            edge_distance_px=int(min_distance),
            is_too_close=is_too_close,
            direction=direction,
            confidence=confidence,
        )

    def record_safe_position(self, pos: tuple[int, int]) -> None:
        """Record a safe position to return to if stuck."""
        self._last_safe_position = pos

    def get_safe_return_position(self) -> tuple[int, int] | None:
        """Get position to return to if stuck in quicksand."""
        return self._last_safe_position