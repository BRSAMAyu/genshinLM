"""Map screen detector for Genshin Impact.

P-47: Detects map interface elements:
- Map base layer (地图底图)
- Teleport waypoints (传送锚点/神瞳)
- Player position marker (蓝点/玩家位置)
- Domain markers
- Quest markers on map

Uses color segmentation and shape detection for robust map UI identification.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class MapMarkerType(str, Enum):
    TELEPORT_WAYPOINT = "teleport_waypoint"    #传送锚点 - blue diamond
    ECHO_WAYPOINT = "echo_waypoint"            #七天神像 - geo shrine
    DOMAIN = "domain"                         #秘境 - domains
    QUEST = "quest"                           #任务标记 - quest markers
    PLAYER = "player"                         #玩家位置 - player marker
    CHEST = "chest"                           #宝箱 - treasure chests


@dataclass(frozen=True, slots=True)
class MapMarker:
    """A detected marker on the map."""
    marker_type: MapMarkerType
    x: float              # Normalized 0-1
    y: float              # Normalized 0-1
    radius_px: float
    confidence: float


@dataclass(frozen=True, slots=True)
class MapDetection:
    """P-47: Map screen detection result."""
    is_map_open: bool = False
    map_base_detected: bool = False
    player_position: tuple[float, float] | None = None  # (x_norm, y_norm)
    markers: list[MapMarker] | None = None
    waypoints_count: int = 0
    domains_count: int = 0
    quests_count: int = 0
    confidence: float = 0.0
    frame_id: int = 0


class MapScreenDetector:
    """P-47: Detect map screen and extract markers.

    Identifies:
    - Map base layer (semi-transparent overlay)
    - Player blue dot (constant position indicator)
    - Teleport waypoints (blue diamonds)
    - Domain markers (purple circles)
    - Quest markers (yellow/orange dots)

    Works on both full-screen and mini-map modes.
    """

    _REF_W = 1280
    _REF_H = 720

    # Map UI region indicators
    _MAP_OVERLAY_ROI = (0.0, 0.0, 1.0, 1.0)
    _PLAYER_DOT_ROI = (0.0, 0.0, 1.0, 1.0)

    # Player marker: distinctive blue with white border
    _PLAYER_BLUE_LOW = np.array([100, 100, 180])
    _PLAYER_BLUE_HIGH = np.array([130, 200, 255])

    # Waypoint markers: cyan/teal diamonds
    _WAYPOINT_CYAN_LOW = np.array([80, 100, 150])
    _WAYPOINT_CYAN_HIGH = np.array([100, 255, 255])

    # Domain markers: purple/violet
    _DOMAIN_PURPLE_LOW = np.array([130, 60, 100])
    _DOMAIN_PURPLE_HIGH = np.array([170, 150, 200])

    # Quest markers: golden/orange
    _QUEST_GOLD_LOW = np.array([15, 100, 150])
    _QUEST_GOLD_HIGH = np.array([35, 255, 255])

    # Chest markers: gold/yellow
    _CHEST_GOLD_LOW = np.array([20, 80, 150])
    _CHEST_GOLD_HIGH = np.array([35, 200, 255])

    # Map UI dark borders
    _MAP_DARK_THRESHOLD = 40

    # Marker size constraints
    _MIN_MARKER_AREA = 50
    _MAX_MARKER_AREA = 5000

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> MapDetection:
        """Detect map screen and extract markers.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            MapDetection with all detected elements
        """
        if frame is None or frame.size == 0:
            return MapDetection(frame_id=frame_id)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Check if map is open
        is_map = self._is_map_open(frame, sx, sy)
        if not is_map:
            return MapDetection(is_map_open=False, confidence=0.0, frame_id=frame_id)

        # Detect player position
        player_pos = self._detect_player_position(frame, sx, sy)

        # Detect all markers
        markers = self._detect_all_markers(frame, sx, sy)

        # Count by type
        waypoints = [m for m in markers if m.marker_type == MapMarkerType.TELEPORT_WAYPOINT]
        domains = [m for m in markers if m.marker_type == MapMarkerType.DOMAIN]
        quests = [m for m in markers if m.marker_type == MapMarkerType.QUEST]

        return MapDetection(
            is_map_open=True,
            map_base_detected=True,
            player_position=player_pos,
            markers=markers,
            waypoints_count=len(waypoints),
            domains_count=len(domains),
            quests_count=len(quests),
            confidence=0.85,
            frame_id=frame_id,
        )

    def _is_map_open(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Check if map UI is visible."""
        if cv2 is None:
            return False

        # Map overlay has distinctive dark edges
        # Check top/bottom borders
        top_strip = frame[0:int(h * 0.05), :] if (h := frame.shape[0]) else frame
        bottom_strip = frame[int(h * 0.95):h, :] if h else frame

        gray_top = cv2.cvtColor(top_strip, cv2.COLOR_BGR2GRAY) if top_strip.size else top_strip
        gray_bottom = cv2.cvtColor(bottom_strip, cv2.COLOR_BGR2GRAY) if bottom_strip.size else bottom_strip

        # Map mode has many UI elements
        top_dark = float(np.mean(gray_top < self._MAP_DARK_THRESHOLD)) if gray_top.size else 0
        bottom_dark = float(np.mean(gray_bottom < self._MAP_DARK_THRESHOLD)) if gray_bottom.size else 0

        # Map UI typically has structured dark borders
        if top_dark > 0.3 or bottom_dark > 0.3:
            return True

        # Fallback: check for map-like elements
        return self._has_map_elements(frame)

    def _has_map_elements(self, frame: np.ndarray) -> bool:
        """Fallback check for map elements."""
        if cv2 is None:
            return False

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Check for waypoint cyan
        waypoint_mask = cv2.inRange(hsv, self._WAYPOINT_CYAN_LOW, self._WAYPOINT_CYAN_HIGH)
        waypoint_ratio = float(cv2.countNonZero(waypoint_mask)) / max(waypoint_mask.size, 1)

        return waypoint_ratio > 0.005

    def _detect_player_position(self, frame: np.ndarray, sx: float, sy: float) -> tuple[float, float] | None:
        """Detect player position marker (blue dot)."""
        if cv2 is None:
            return None

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Player marker is distinctive blue
        player_mask = cv2.inRange(hsv, self._PLAYER_BLUE_LOW, self._PLAYER_BLUE_HIGH)

        # Find contours
        contours, _ = cv2.findContours(player_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Look for small circular marker
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self._MIN_MARKER_AREA < area < self._MAX_MARKER_AREA * 2:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = M["m10"] / M["m00"]
                    cy = M["m01"] / M["m00"]
                    return (cx / w, cy / h)

        return None

    def _detect_all_markers(self, frame: np.ndarray, sx: float, sy: float) -> list[MapMarker]:
        """Detect all map markers."""
        if cv2 is None:
            return []

        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        markers: list[MapMarker] = []

        # Detect waypoints (cyan diamonds)
        waypoint_markers = self._detect_markers_by_color(
            hsv, w, h,
            self._WAYPOINT_CYAN_LOW, self._WAYPOINT_CYAN_HIGH,
            MapMarkerType.TELEPORT_WAYPOINT
        )
        markers.extend(waypoint_markers)

        # Detect domains (purple)
        domain_markers = self._detect_markers_by_color(
            hsv, w, h,
            self._DOMAIN_PURPLE_LOW, self._DOMAIN_PURPLE_HIGH,
            MapMarkerType.DOMAIN
        )
        markers.extend(domain_markers)

        # Detect quest markers (gold)
        quest_markers = self._detect_markers_by_color(
            hsv, w, h,
            self._QUEST_GOLD_LOW, self._QUEST_GOLD_HIGH,
            MapMarkerType.QUEST
        )
        markers.extend(quest_markers)

        # Detect chests (brighter gold)
        chest_markers = self._detect_markers_by_color(
            hsv, w, h,
            self._CHEST_GOLD_LOW, self._CHEST_GOLD_HIGH,
            MapMarkerType.CHEST
        )
        markers.extend(chest_markers)

        return markers

    def _detect_markers_by_color(
        self,
        hsv: np.ndarray,
        w: int,
        h: int,
        lower: np.ndarray,
        upper: np.ndarray,
        marker_type: MapMarkerType,
    ) -> list[MapMarker]:
        """Detect markers of a specific color."""
        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        markers = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self._MIN_MARKER_AREA < area < self._MAX_MARKER_AREA:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = M["m10"] / M["m00"]
                    cy = M["m01"] / M["m00"]
                    radius = np.sqrt(area / np.pi)
                    confidence = min(area / 200, 1.0)
                    markers.append(MapMarker(
                        marker_type=marker_type,
                        x=cx / w,
                        y=cy / h,
                        radius_px=float(radius),
                        confidence=confidence,
                    ))

        return markers