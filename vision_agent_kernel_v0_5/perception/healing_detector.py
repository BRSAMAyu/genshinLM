"""Healing detector for Genshin Impact party member HP restoration.

P-54: Detects healer skill effects and healing numbers.
Identifies green damage numbers and healing wave effects.

Visual indicators:
- Green floating damage numbers (healing)
- Healing wave/particles around characters
- HP bar green fill animation
- Healer character skill effects (Qiqi, Bennett, Barbara, etc.)
"""
from __future__ import annotations

import logging
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HealingEvent:
    """Single healing event."""
    value: int
    position: tuple[float, float]
    healer_name: str | None  # Estimated from effect type
    timestamp: float
    frame_id: int


@dataclass(frozen=True, slots=True)
class HealingDetection:
    """P-54: Healing effect detection result."""
    is_healing: bool
    intensity: float                    # 0.0-1.0 healing strength
    heal_events: tuple[HealingEvent, ...]
    total_healed: int                  # Total HP restored this frame
    estimated_hps: float              # Healing per second
    healer_active: str | None          # Active healer character
    confidence: float
    frame_id: int


@dataclass(frozen=True, slots=True)
class HealingStatus:
    """Overall healing status."""
    active_healing: HealingDetection | None
    party_hp_change: int               # Estimated HP change
    healer_in_use: str | None
    recommended_action: str


class HealingDetector:
    """Detect healing effects in Genshin combat.

    Features:
    - Green healing number detection
    - Healing wave/particle analysis
    - Per-character healing pattern recognition
    - Party-wide healing tracking

    Detection: Green color (HP recovery) + healing particle effects
    """

    _REF_W = 1920
    _REF_H = 1080

    # Healing effect colors (bright green)
    _HEAL_GREEN_LOW = np.array([40, 100, 150])
    _HEAL_GREEN_HIGH = np.array([85, 255, 255])

    # Healing wave colors (light green/teal)
    _WAVE_GREEN_LOW = np.array([50, 80, 150])
    _WAVE_GREEN_HIGH = np.array([85, 200, 255])

    # Healing particle (small bright dots)
    _PARTICLE_LOW = np.array([45, 50, 200])
    _PARTICLE_HIGH = np.array([80, 255, 255])

    # Character healing patterns
    _HEALER_PATTERNS = {
        "barbara": {"wave_color": True, "particles": True, "skill_duration": 90},
        "qiqi": {"freeze_effect": True, "particles": True, "skill_duration": 120},
        "bennett": {"field_visible": True, "damage_numbers": True, "skill_duration": 90},
        "kokomi": {"hydro_aura": True, "heal_tick": True, "skill_duration": 120},
        "diona": {"shield_heal": True, "particles": True, "skill_duration": 90},
        "kuki": {"electro_aura": True, "heal_tick": True, "skill_duration": 120},
        "yaoyao": {"radish": True, "heal_debuff": True, "skill_duration": 150},
    }

    # Detection parameters
    MIN_HEAL_PIXELS = 300
    MIN_WAVE_PIXELS = 200
    MIN_PARTICLE_COUNT = 10

    def __init__(self, now_fn=None) -> None:
        """Initialize healing detector.

        Args:
            now_fn: Time function (default: time.perf_counter)
        """
        self._now_fn = now_fn or time.perf_counter
        self._healing_events: list[HealingEvent] = []
        self._heal_history: deque[tuple[float, int]] = deque(maxlen=180)  # 3 seconds
        self._active_healer: str | None = None
        self._last_detection: HealingDetection | None = None
        self._frame_count: int = 0

    @property
    def last_detection(self) -> HealingDetection | None:
        """Get last healing detection."""
        return self._last_detection

    def detect(
        self,
        frame: np.ndarray,
        frame_id: int,
    ) -> HealingDetection:
        """Detect healing effects in frame.

        Args:
            frame: BGR frame from screen capture
            frame_id: Current frame ID

        Returns:
            HealingDetection with healing information
        """
        if cv2 is None or frame.size == 0:
            return HealingDetection(
                is_healing=False,
                intensity=0.0,
                heal_events=(),
                total_healed=0,
                estimated_hps=0.0,
                healer_active=None,
                confidence=0.0,
                frame_id=frame_id,
            )

        now = self._now_fn()
        self._frame_count = frame_id

        # Analyze healing indicators
        heal_numbers = self._detect_heal_numbers(frame)
        healing_wave = self._detect_healing_wave(frame)
        particles = self._detect_healing_particles(frame)

        # Calculate overall intensity
        intensity = min(
            (heal_numbers * 0.5 + healing_wave * 0.3 + particles * 0.2) * 2,
            1.0,
        )

        is_healing = (
            heal_numbers > 0.1 or
            healing_wave > 0.2 or
            particles > 0.15
        )

        # Estimate total healed
        total_healed = self._estimate_total_healed(heal_numbers)

        # Track healing over time
        self._heal_history.append((now, total_healed))

        # Calculate healing per second
        estimated_hps = self._calculate_hps()

        # Identify active healer
        healer = self._identify_healer(healing_wave, particles)

        # Create heal events
        events = self._create_heal_events(heal_numbers, frame_id, now)

        self._last_detection = HealingDetection(
            is_healing=is_healing,
            intensity=intensity,
            heal_events=tuple(events),
            total_healed=total_healed,
            estimated_hps=estimated_hps,
            healer_active=healer,
            confidence=min(intensity * 2, 1.0),
            frame_id=frame_id,
        )

        return self._last_detection

    def _detect_heal_numbers(self, frame: np.ndarray) -> float:
        """Detect green healing numbers."""
        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Focus on damage number area (above enemies)
        x1 = int(0.25 * sx * self._REF_W)
        y1 = int(0.20 * sy * self._REF_H)
        x2 = int(0.75 * sx * self._REF_W)
        y2 = int(0.65 * sy * self._REF_H)

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Green healing numbers
        heal_mask = cv2.inRange(hsv, self._HEAL_GREEN_LOW, self._HEAL_GREEN_HIGH)
        heal_pixels = cv2.countNonZero(heal_mask)

        return min(heal_pixels / 1000.0, 1.0)

    def _detect_healing_wave(self, frame: np.ndarray) -> float:
        """Detect healing wave effect."""
        h, w = frame.shape[:2]

        # Center area for wave effects
        cx, cy = w // 2, h // 2
        radius = min(w, h) // 3

        x1 = max(0, cx - radius)
        y1 = max(0, cy - radius)
        x2 = min(w, cx + radius)
        y2 = min(h, cy + radius)

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        wave_mask = cv2.inRange(hsv, self._WAVE_GREEN_LOW, self._WAVE_GREEN_HIGH)
        wave_pixels = cv2.countNonZero(wave_mask)

        return min(wave_pixels / 2000.0, 1.0)

    def _detect_healing_particles(self, frame: np.ndarray) -> float:
        """Detect small healing particles."""
        # Particles appear all over - sample different regions
        h, w = frame.shape[:2]

        # Sample multiple regions
        regions = [
            (0.0, 0.5, 0.3, 0.8),   # Left
            (0.7, 0.5, 1.0, 0.8),   # Right
            (0.3, 0.3, 0.7, 0.7),   # Center
        ]

        total_particles = 0

        for rx1, ry1, rx2, ry2 in regions:
            x1 = int(rx1 * w)
            y1 = int(ry1 * h)
            x2 = int(rx2 * w)
            y2 = int(ry2 * h)

            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

            particle_mask = cv2.inRange(hsv, self._PARTICLE_LOW, self._PARTICLE_HIGH)

            # Count distinct particle regions (small contours)
            contours, _ = cv2.findContours(particle_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            total_particles += len([c for c in contours if cv2.contourArea(c) < 50])

        return min(total_particles / 50.0, 1.0)

    def _estimate_total_healed(self, heal_numbers: float) -> int:
        """Estimate total HP restored."""
        if heal_numbers < 0.1:
            return 0

        # Each green number cluster represents a heal
        # Estimate based on intensity
        heal_clusters = int(heal_numbers * 10)

        # Average heal per event varies by healer
        if self._active_healer in self._HEALER_PATTERNS:
            base_heal = 500  # Base heal per tick
        else:
            base_heal = 300

        return heal_clusters * base_heal

    def _calculate_hps(self) -> float:
        """Calculate healing per second."""
        if len(self._heal_history) < 2:
            return 0.0

        # Sum recent heals
        recent_heals = sum(h for _, h in self._heal_history[-30:])  # Last 0.5 seconds
        return recent_heals * 2  # Extrapolate to per second

    def _identify_healer(
        self,
        wave_intensity: float,
        particle_intensity: float,
    ) -> str | None:
        """Identify which healer is active."""
        if wave_intensity > 0.3:
            return "barbara"  # Barbara's song has strong wave
        elif particle_intensity > 0.5 and wave_intensity > 0.1:
            return "qiqi"  # Qiqi has many particles
        elif wave_intensity > 0.2:
            return "kokomi"  # Kokomi hydro aura
        elif particle_intensity > 0.3:
            return "bennett"  # Bennett field
        else:
            return None

    def _create_heal_events(
        self,
        intensity: float,
        frame_id: int,
        timestamp: float,
    ) -> list[HealingEvent]:
        """Create healing event records."""
        if intensity < 0.1:
            return []

        # Estimate number of heal events based on intensity
        num_events = max(1, int(intensity * 5))
        events = []

        h, w = self._heal_history[-1][1] if self._heal_history else 0
        center_x, center_y = w // 2, h // 2

        for i in range(num_events):
            # Spread positions around center
            offset_x = random.randint(-100, 100)
            offset_y = random.randint(-80, 80)

            event = HealingEvent(
                value=random.randint(300, 800),
                position=(center_x + offset_x, center_y + offset_y),
                healer_name=self._active_healer,
                timestamp=timestamp,
                frame_id=frame_id,
            )
            events.append(event)

        self._healing_events.extend(events)

        # Keep bounded
        if len(self._healing_events) > 100:
            self._healing_events = self._healing_events[-100:]

        return events

    def get_healing_status(self, frame_id: int) -> HealingStatus:
        """Get overall healing status."""
        return HealingStatus(
            active_healing=self._last_detection,
            party_hp_change=self._last_detection.total_healed if self._last_detection else 0,
            healer_in_use=self._active_healer,
            recommended_action=self._get_recommended_action(),
        )

    def _get_recommended_action(self) -> str:
        """Get recommended action based on healing state."""
        if self._last_detection is None or not self._last_detection.is_healing:
            return "normal_combat"

        if self._last_detection.estimated_hps > 1000:
            return "focus_dps"  # Strong healing, focus on damage

        return "maintain_combat"

    def is_healer_active(self) -> bool:
        """Check if a healer is currently active."""
        return self._last_detection is not None and self._last_detection.is_healing

    def get_total_healed(self) -> int:
        """Get total HP healed in recent history."""
        return sum(h for _, h in self._heal_history)

    def reset(self) -> None:
        """Reset detector state."""
        self._healing_events.clear()
        self._heal_history.clear()
        self._active_healer = None
        self._last_detection = None
        self._frame_count = 0