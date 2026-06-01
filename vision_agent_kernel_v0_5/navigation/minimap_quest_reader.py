from __future__ import annotations

import math

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class MinimapQuestReader:
    """Read quest marker direction from minimap ROI."""

    _REF_W = 1920
    _REF_H = 1080

    def __init__(self, viewport: tuple[int, int] = (1920, 1080)) -> None:
        self._viewport = viewport
        self._minimap_roi = (20, 20, 200, 200)  # left-top circular minimap
        self._quest_color_ranges = [
            ((0, 180, 180), (10, 255, 255)),    # red quest marker (low hue)
            ((170, 180, 180), (179, 255, 255)),  # red quest marker (wraparound)
            ((20, 180, 180), (35, 255, 255)),    # yellow quest marker
        ]

    def read_quest_direction(self, frame: np.ndarray) -> float | None:
        """Return angle in radians from minimap center to quest marker.

        0 = up/north, pi/2 = right/east.  None if no marker.
        """
        if cv2 is None:
            return None
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H
        x1, y1, x2, y2 = self._scale_roi(self._minimap_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        avg_v = float(np.mean(hsv[:, :, 2]))

        mask = np.zeros(roi.shape[:2], dtype=np.uint8)
        for lower, upper in self._quest_color_ranges:
            lower_h, lower_s, lower_v = lower
            upper_h, upper_s, upper_v = upper
            if avg_v < 100:  # Dark environments (night, caves, underwater)
                lower_s = max(80, lower_s - 50)
                lower_v = max(60, lower_v - 60)
            elif avg_v > 220:  # High glare (daytime glare, snowfields)
                lower_s = min(220, lower_s + 20)
                lower_v = min(220, lower_v + 20)
            mask |= cv2.inRange(hsv, np.array((lower_h, lower_s, lower_v)), np.array((upper_h, upper_s, upper_v)))

        if np.count_nonzero(mask) < 5:
            return None

        # Find centroid of quest marker pixels
        ys, xs = np.where(mask > 0)
        cx = float(xs.mean())
        cy = float(ys.mean())

        # Angle from minimap center to marker
        center_x = (x2 - x1) / 2.0
        center_y = (y2 - y1) / 2.0
        dx = cx - center_x
        dy = cy - center_y

        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 5:  # marker at center = arrived
            return 0.0

        return math.atan2(dx, -dy)  # 0=up, positive=clockwise

    def has_quest_marker(self, frame: np.ndarray) -> bool:
        """Check if a quest marker is visible on minimap."""
        return self.read_quest_direction(frame) is not None

    def is_at_destination(self, frame: np.ndarray) -> bool:
        """Check if quest marker is at minimap center (arrived)."""
        if cv2 is None:
            return False
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H
        x1, y1, x2, y2 = self._scale_roi(self._minimap_roi, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        avg_v = float(np.mean(hsv[:, :, 2]))

        mask = np.zeros(roi.shape[:2], dtype=np.uint8)
        for lower, upper in self._quest_color_ranges:
            lower_h, lower_s, lower_v = lower
            upper_h, upper_s, upper_v = upper
            if avg_v < 100:  # Dark environments
                lower_s = max(80, lower_s - 50)
                lower_v = max(60, lower_v - 60)
            elif avg_v > 220:  # Glare
                lower_s = min(220, lower_s + 20)
                lower_v = min(220, lower_v + 20)
            mask |= cv2.inRange(hsv, np.array((lower_h, lower_s, lower_v)), np.array((upper_h, upper_s, upper_v)))
        if np.count_nonzero(mask) < 3:
            return True  # no marker = arrived or no quest
        ys, xs = np.where(mask > 0)
        cx = float(xs.mean())
        cy = float(ys.mean())
        center_x = (x2 - x1) / 2.0
        center_y = (y2 - y1) / 2.0
        dist = math.sqrt((cx - center_x) ** 2 + (cy - center_y) ** 2)
        return dist < 10

    @staticmethod
    def _scale_roi(
        roi: tuple[int, int, int, int], sx: float, sy: float,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
