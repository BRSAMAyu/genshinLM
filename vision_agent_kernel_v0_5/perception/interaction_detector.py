from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


@dataclass(slots=True)
class InteractionPrompt:
    prompt_type: str     # "interact", "talk", "open", "collect"
    text: str
    position: tuple[int, int]


@dataclass(slots=True)
class NPCMarker:
    marker_type: str     # "quest_available", "quest_active", "daily"
    position: tuple[int, int]


class InteractionDetector:
    """Detect interaction prompts and NPC quest markers in Genshin Impact."""

    _REF_W = 1920
    _REF_H = 1080
    _INTERACT_ROI = (660, 900, 1260, 1000)   # bottom center for F-key prompt
    _NPC_SCAN_ROI = (0, 0, 1920, 540)         # upper half for NPC markers

    def detect_interact_prompt(self, frame: np.ndarray) -> InteractionPrompt | None:
        """Detect F-key interaction prompt in bottom center of screen."""
        if cv2 is None:
            return None
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._INTERACT_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        # Look for white "F" text via HSV thresholding
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # White text: high value, low saturation
        white_mask = cv2.inRange(hsv, (0, 0, 200), (180, 50, 255))
        if white_mask.size == 0:
            return None

        white_ratio = float(np.sum(white_mask > 0)) / white_mask.size
        if white_ratio < 0.005:
            return None

        # Find centroid of white pixels to get the prompt position
        ys, xs = np.where(white_mask > 0)
        if len(xs) == 0:
            return None

        cx = int(np.mean(xs)) + x1
        cy = int(np.mean(ys)) + y1

        # Classify prompt type by scanning for known patterns in surrounding area
        prompt_type = self._classify_prompt_type(roi, white_mask)

        return InteractionPrompt(
            prompt_type=prompt_type,
            text="",
            position=(cx, cy),
        )

    def detect_npc_quest_marker(self, frame: np.ndarray) -> list[NPCMarker]:
        """Detect blue/yellow exclamation marks above NPCs."""
        if cv2 is None:
            return []
        h, w = frame.shape[:2]
        sx = w / self._REF_W
        sy = h / self._REF_H

        x1, y1, x2, y2 = self._scale_roi(self._NPC_SCAN_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return []

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Blue quest marker: H in (100,130), S>150, V>150
        blue_mask = cv2.inRange(hsv, (100, 150, 150), (130, 255, 255))
        # Yellow quest marker: H in (20,35), S>150, V>150
        yellow_mask = cv2.inRange(hsv, (20, 150, 150), (35, 255, 255))

        markers: list[NPCMarker] = []
        markers.extend(self._cluster_marker_pixels(blue_mask, "quest_available", x1, y1))
        markers.extend(self._cluster_marker_pixels(yellow_mask, "quest_active", x1, y1))

        return markers

    def _classify_prompt_type(self, roi: np.ndarray, white_mask: np.ndarray) -> str:
        """Classify the interaction prompt type based on surrounding pixels."""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Check for greenish tones nearby (collect/gather)
        green_mask = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
        green_ratio = float(np.sum(green_mask > 0)) / max(green_mask.size, 1)
        if green_ratio > 0.1:
            return "collect"
        # Check for warm tones (talk/NPC)
        warm_mask = cv2.inRange(hsv, (10, 80, 80), (25, 255, 255))
        warm_ratio = float(np.sum(warm_mask > 0)) / max(warm_mask.size, 1)
        if warm_ratio > 0.05:
            return "talk"
        return "interact"

    @staticmethod
    def _cluster_marker_pixels(
        mask: np.ndarray,
        marker_type: str,
        offset_x: int,
        offset_y: int,
    ) -> list[NPCMarker]:
        """Cluster nearby bright pixels and return centroid positions."""
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return []

        markers: list[NPCMarker] = []
        visited: set[tuple[int, int]] = set()
        pixels = list(zip(xs.tolist(), ys.tolist()))

        # Simple grid-based clustering with step of 20px
        cluster_radius = 20
        for px, py in pixels:
            key = (px // cluster_radius, py // cluster_radius)
            if key in visited:
                continue
            visited.add(key)
            # Collect all nearby pixels
            nearby_x = [x for x, y in pixels if abs(x - px) < cluster_radius and abs(y - py) < cluster_radius]
            nearby_y = [y for x, y in pixels if abs(x - px) < cluster_radius and abs(y - py) < cluster_radius]
            if len(nearby_x) >= 5:  # minimum cluster size
                cx = int(np.mean(nearby_x)) + offset_x
                cy = int(np.mean(nearby_y)) + offset_y
                markers.append(NPCMarker(marker_type=marker_type, position=(cx, cy)))

        return markers

    @staticmethod
    def _scale_roi(
        roi: tuple[int, int, int, int], sx: float, sy: float,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
