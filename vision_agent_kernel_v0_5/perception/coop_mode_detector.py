"""Co-op mode detector for Genshin Impact multiplayer.

P-49: Detects co-op/ multiplayer mode:
- Co-op HP bar display (联机HP条)
- Connection line indicators (连线指示)
- Other player markers
- Co-op domain entrance indicators

Co-op mode has distinctive blue/green UI elements different from solo play.
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


class CoOpPlayerState(str, Enum):
    ONLINE = "online"                   # Player is present and active
    IDLE = "idle"                       # Player present but not moving
    OFFLINE = "offline"                 # Player disconnected


@dataclass(frozen=True, slots=True)
class CoOpPlayer:
    """A detected co-op player."""
    slot_index: int                     # 1-4 for team slots
    name: str = ""
    state: CoOpPlayerState = CoOpPlayerState.ONLINE
    health_ratio: float = 1.0           # 0.0-1.0
    x: float = 0.0                      # Screen position
    y: float = 0.0
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class CoOpDetection:
    """P-49: Co-op mode detection result."""
    is_coop_mode: bool = False
    player_count: int = 0               # Number of connected players
    players: list[CoOpPlayer] | None = None
    domain_ready: bool = False          # Can enter co-op domain
    connection_quality: Literal["good", "fair", "poor", "none"] = "none"
    is_leader: bool = False             # Current player is party leader
    confidence: float = 0.0
    frame_id: int = 0


class CoOpModeDetector:
    """P-49: Detect co-op/multiplayer mode state.

    Detects:
    - Co-op HP bars (multiplayer health display)
    - Connection line/ping indicators
    - Other player markers on screen
    - Co-op domain entrance UI

    Visual indicators:
    - Co-op HP bars have green outline different from solo blue
    - Player connection indicators (green dots = connected)
    - Party member icons in co-op mode
    - "Ready" button for co-op domain entry
    """

    _REF_W = 1280
    _REF_H = 720

    # Co-op specific regions
    _COOP_HP_BAR_ROI = (0.35, 0.92, 0.90, 0.98)
    _PLAYER_SLOT_ROI = (0.75, 0.88, 0.98, 0.98)
    _READY_BUTTON_ROI = (0.40, 0.70, 0.60, 0.78)
    _CONNECTION_INDICATOR_ROI = (0.90, 0.05, 1.0, 0.15)

    # Co-op HP bar colors (green border around HP)
    _COOP_GREEN_LOW = np.array([35, 80, 100])
    _COOP_GREEN_HIGH = np.array([85, 255, 255])

    # Player slot colors
    _PLAYER_ONLINE_LOW = np.array([30, 100, 150])
    _PLAYER_ONLINE_HIGH = np.array([45, 255, 255])
    _PLAYER_OFFLINE_LOW = np.array([0, 0, 50])
    _PLAYER_OFFLINE_HIGH = np.array([180, 30, 100])

    # Ready button detection
    _READY_GREEN_LOW = np.array([40, 80, 150])
    _READY_GREEN_HIGH = np.array([80, 255, 255])

    # Connection indicator colors
    _CONN_GOOD_LOW = np.array([35, 100, 150])
    _CONN_GOOD_HIGH = np.array([85, 255, 255])
    _CONN_POOR_LOW = np.array([0, 100, 150])
    _CONN_POOR_HIGH = np.array([15, 255, 255])

    _MIN_PLAYER_AREA = 100
    _MAX_PLAYER_AREA = 1000

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> CoOpDetection:
        """Detect co-op mode state.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            CoOpDetection with all detected co-op elements
        """
        if frame is None or frame.size == 0:
            return CoOpDetection(frame_id=frame_id)

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Check for co-op HP bar (primary indicator)
        is_coop = self._is_coop_mode(frame, sx, sy)
        if not is_coop:
            return CoOpDetection(is_coop_mode=False, confidence=0.0, frame_id=frame_id)

        # Detect players
        players = self._detect_players(frame, sx, sy)

        # Detect connection quality
        conn_quality = self._detect_connection_quality(frame, sx, sy)

        # Check for ready button (co-op domain)
        domain_ready = self._has_ready_button(frame, sx, sy)

        # Determine if current player is leader
        is_leader = self._check_leader_status(frame, sx, sy)

        return CoOpDetection(
            is_coop_mode=True,
            player_count=len([p for p in players if p.state != CoOpPlayerState.OFFLINE]),
            players=players,
            domain_ready=domain_ready,
            connection_quality=conn_quality,
            is_leader=is_leader,
            confidence=0.85,
            frame_id=frame_id,
        )

    def _is_coop_mode(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Check if in co-op mode."""
        if cv2 is None:
            return False

        x1, y1, x2, y2 = self._scale_roi(self._COOP_HP_BAR_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Co-op HP bar has green border
        green_mask = cv2.inRange(hsv, self._COOP_GREEN_LOW, self._COOP_GREEN_HIGH)
        green_ratio = float(cv2.countNonZero(green_mask)) / max(green_mask.size, 1)

        # Check for player slots (secondary indicator)
        x1, y1, x2, y2 = self._scale_roi(self._PLAYER_SLOT_ROI, sx, sy)
        slot_roi = frame[y1:y2, x1:x2]
        slot_has_content = False
        if slot_roi.size > 0:
            gray = cv2.cvtColor(slot_roi, cv2.COLOR_BGR2GRAY)
            variance = float(np.var(gray))
            slot_has_content = variance > 500

        return green_ratio > 0.02 or slot_has_content

    def _detect_players(self, frame: np.ndarray, sx: float, sy: float) -> list[CoOpPlayer]:
        """Detect other players in co-op session."""
        if cv2 is None:
            return []

        x1, y1, x2, y2 = self._scale_roi(self._PLAYER_SLOT_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return []

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        players: list[CoOpPlayer] = []

        # Detect online players (yellow/green icons)
        online_mask = cv2.inRange(hsv, self._PLAYER_ONLINE_LOW, self._PLAYER_ONLINE_HIGH)
        online_contours, _ = cv2.findContours(online_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for i, cnt in enumerate(sorted(online_contours, key=cv2.contourArea, reverse=True)[:4]):
            area = cv2.contourArea(cnt)
            if self._MIN_PLAYER_AREA < area < self._MAX_PLAYER_AREA:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = M["m10"] / M["m00"] + x1
                    cy = M["m01"] / M["m00"] + y1
                    players.append(CoOpPlayer(
                        slot_index=i + 1,
                        state=CoOpPlayerState.ONLINE,
                        x=cx / frame.shape[1],
                        y=cy / frame.shape[0],
                        confidence=min(area / 200, 1.0),
                    ))

        # Detect offline/disconnected players
        offline_mask = cv2.inRange(hsv, self._PLAYER_OFFLINE_LOW, self._PLAYER_OFFLINE_HIGH)
        offline_contours, _ = cv2.findContours(offline_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in offline_contours:
            area = cv2.contourArea(cnt)
            if self._MIN_PLAYER_AREA < area < self._MAX_PLAYER_AREA:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = M["m10"] / M["m00"] + x1
                    cy = M["m01"] / M["m00"] + y1
                    players.append(CoOpPlayer(
                        slot_index=len(players) + 1,
                        state=CoOpPlayerState.OFFLINE,
                        x=cx / frame.shape[1],
                        y=cy / frame.shape[0],
                        confidence=min(area / 200, 1.0),
                    ))

        return players

    def _detect_connection_quality(self, frame: np.ndarray, sx: float, sy: float) -> Literal["good", "fair", "poor", "none"]:
        """Detect connection quality from ping indicator."""
        if cv2 is None:
            return "none"

        x1, y1, x2, y2 = self._scale_roi(self._CONNECTION_INDICATOR_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return "none"

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Green = good connection
        good_mask = cv2.inRange(hsv, self._CONN_GOOD_LOW, self._CONN_GOOD_HIGH)
        good_ratio = float(cv2.countNonZero(good_mask)) / max(good_mask.size, 1)

        # Red/yellow = poor connection
        poor_mask = cv2.inRange(hsv, self._CONN_POOR_LOW, self._CONN_POOR_HIGH)
        poor_ratio = float(cv2.countNonZero(poor_mask)) / max(poor_mask.size, 1)

        if good_ratio > 0.01:
            return "good"
        elif poor_ratio > 0.01:
            return "poor"

        return "none"

    def _has_ready_button(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Check for ready button in co-op domain entrance."""
        if cv2 is None:
            return False

        x1, y1, x2, y2 = self._scale_roi(self._READY_BUTTON_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, self._READY_GREEN_LOW, self._READY_GREEN_HIGH)
        green_ratio = float(cv2.countNonZero(green_mask)) / max(green_mask.size, 1)

        return green_ratio > 0.05

    def _check_leader_status(self, frame: np.ndarray, sx: float, sy: float) -> bool:
        """Check if current player is party leader."""
        if cv2 is None:
            return False

        # Leader indicator is typically a crown/star icon near player slot
        # This is a simplified check
        x1, y1, x2, y2 = self._scale_roi(self._PLAYER_SLOT_ROI, sx, sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return False

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # Look for bright crown-like shape (indicates leader)
        _, bright = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 50 < area < 500:
                return True

        return False

    def _scale_roi(self, roi: tuple[float, float, float, float], sx: float, sy: float) -> tuple[int, int, int, int]:
        """Scale ROI from reference resolution."""
        x1, y1, x2, y2 = roi
        return (
            int(x1 * sx * self._REF_W),
            int(y1 * sy * self._REF_H),
            int(x2 * sx * self._REF_W),
            int(y2 * sy * self._REF_H),
        )