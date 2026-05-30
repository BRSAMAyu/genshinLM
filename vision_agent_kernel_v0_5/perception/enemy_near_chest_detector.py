"""E-46: Enemy near chest detector.

Detects if enemies are guarding chests before attempting to open them.
Helps prioritize clearing enemies first.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class EnemyChestDetection:
    """Detection result for enemies near chest."""
    chest_position: tuple[int, int] | None
    enemies_nearby: bool
    enemy_count: int
    enemy_positions: list[tuple[int, int]]
    distance_to_nearest: float | None  # pixels
    should_clear_first: bool
    confidence: float


class EnemyNearChestDetector:
    """Detect enemies guarding treasure chests."""

    _REF_W = 1920
    _REF_H = 1080

    # Chest colors (golden)
    _CHEST_GOLD_LOW = np.array([15, 100, 100], dtype=np.uint8)
    _CHEST_GOLD_HIGH = np.array([40, 255, 255], dtype=np.uint8)

    # Enemy HP bar colors (red)
    _HP_RED_LOW = np.array([0, 100, 100], dtype=np.uint8)
    _HP_RED_HIGH = np.array([10, 255, 255], dtype=np.uint8)

    # Safe distance from chest (pixels)
    _SAFE_DISTANCE_PX = 200

    def __init__(self) -> None:
        self._last_chest_pos: tuple[int, int] | None = None

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> EnemyChestDetection:
        """Detect enemies near treasure chest.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID

        Returns:
            EnemyChestDetection with enemy count and positions
        """
        if cv2 is None:
            return EnemyChestDetection(
                chest_position=None,
                enemies_nearby=False,
                enemy_count=0,
                enemy_positions=[],
                distance_to_nearest=None,
                should_clear_first=False,
                confidence=0.0,
            )

        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        # Find chests
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        chest_mask = cv2.inRange(hsv, self._CHEST_GOLD_LOW, self._CHEST_GOLD_HIGH)

        chest_contours, _ = cv2.findContours(chest_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        chest_pos = None
        if chest_contours:
            # Find largest chest contour
            largest = max(chest_contours, key=cv2.contourArea)
            M = cv2.moments(largest)
            if M["m00"] > 0:
                chest_pos = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                self._last_chest_pos = chest_pos

        if chest_pos is None:
            return EnemyChestDetection(
                chest_position=self._last_chest_pos,
                enemies_nearby=False,
                enemy_count=0,
                enemy_positions=[],
                distance_to_nearest=None,
                should_clear_first=False,
                confidence=0.3,
            )

        # Scan area around chest for enemies
        roi_size = 400
        cx, cy = chest_pos
        x1 = max(0, cx - roi_size)
        y1 = max(0, cy - roi_size)
        x2 = min(w, cx + roi_size)
        y2 = min(h, cy + roi_size)

        scan_region = frame[y1:y2, x1:x2]
        scan_hsv = cv2.cvtColor(scan_region, cv2.COLOR_BGR2HSV)

        # Detect enemy HP bars (red indicators)
        hp_mask = cv2.inRange(scan_hsv, self._HP_RED_LOW, self._HP_RED_HIGH)

        # Clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        hp_mask = cv2.morphologyEx(hp_mask, cv2.MORPH_OPEN, kernel)

        # Find enemy HP bar contours
        hp_contours, _ = cv2.findContours(hp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        enemy_positions: list[tuple[int, int]] = []
        for contour in hp_contours:
            area = cv2.contourArea(contour)
            if 50 < area < 2000:  # HP bar size
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    px = int(M["m10"] / M["m00"]) + x1
                    py = int(M["m01"] / M["m00"]) + y1
                    enemy_positions.append((px, py))

        # Calculate distances
        min_distance = None
        if enemy_positions:
            distances = [
                np.sqrt((px - chest_pos[0]) ** 2 + (py - chest_pos[1]) ** 2)
                for px, py in enemy_positions
            ]
            min_distance = min(distances)

        enemies_nearby = len(enemy_positions) > 0
        should_clear = enemies_nearby and (min_distance or 999) < self._SAFE_DISTANCE_PX

        return EnemyChestDetection(
            chest_position=chest_pos,
            enemies_nearby=enemies_nearby,
            enemy_count=len(enemy_positions),
            enemy_positions=enemy_positions,
            distance_to_nearest=int(min_distance) if min_distance else None,
            should_clear_first=should_clear,
            confidence=0.7 if chest_pos else 0.5,
        )

    def get_combat_priority(self, detection: EnemyChestDetection) -> str:
        """Get guidance on combat priority."""
        if detection.should_clear_first:
            return f"Clear {detection.enemy_count} enemies before opening chest"
        elif detection.enemies_nearby:
            return f"Approach with caution - {detection.enemy_count} enemies nearby"
        return "Chest appears safe to open"

    def get_nearest_enemy(self, detection: EnemyChestDetection) -> tuple[int, int] | None:
        """Get position of nearest enemy to focus on."""
        if not detection.enemy_positions or detection.chest_position is None:
            return None

        distances = [
            (np.sqrt((px - detection.chest_position[0]) ** 2 + (py - detection.chest_position[1]) ** 2), px, py)
            for px, py in detection.enemy_positions
        ]
        distances.sort(key=lambda d: d[0])
        return (distances[0][1], distances[0][2]) if distances else None