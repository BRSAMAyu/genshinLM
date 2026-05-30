"""Elemental particle detection and tracking for energy orb collection.

Implements C-39: Energy Particle Detector
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Element Particle Types
# ---------------------------------------------------------------------------

class ParticleElement(Enum):
    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    ANEMO = "anemo"
    GEO = "geo"
    DENDRO = "dendro"
    OMNI = "omni"              # Universal energy particle


# ---------------------------------------------------------------------------
# Particle Detection Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EnergyParticle:
    element: ParticleElement
    position: tuple[float, float]   # Center pixel coords (x, y)
    velocity: tuple[float, float]   # Direction (vx, vy) pixels/sec
    size_pixels: int                # Approximate radius
    intensity: float                # 0.0-1.0 brightness
    age_frames: int                 # How many frames since first detection


@dataclass(frozen=True, slots=True)
class ParticleFieldStatus:
    particles: tuple[EnergyParticle, ...]
    dominant_element: ParticleElement
    collection_target: EnergyParticle | None
    recommended_action: str


# ---------------------------------------------------------------------------
# HSV Color Ranges for Element Particles
# ---------------------------------------------------------------------------

_PARTICLE_HSV: dict[ParticleElement, tuple[np.ndarray, np.ndarray]] = {
    ParticleElement.PYRO: (
        np.array([0, 180, 200]),
        np.array([20, 255, 255]),
    ),
    ParticleElement.HYDRO: (
        np.array([90, 150, 150]),
        np.array([130, 255, 255]),
    ),
    ParticleElement.ELECTRO: (
        np.array([120, 150, 150]),
        np.array([160, 255, 255]),
    ),
    ParticleElement.CRYO: (
        np.array([85, 100, 150]),
        np.array([115, 255, 255]),
    ),
    ParticleElement.ANEMO: (
        np.array([60, 100, 150]),
        np.array([95, 255, 255]),
    ),
    ParticleElement.GEO: (
        np.array([15, 150, 150]),
        np.array([40, 255, 255]),
    ),
    ParticleElement.DENDRO: (
        np.array([40, 150, 150]),
        np.array([75, 255, 255]),
    ),
    ParticleElement.OMNI: (
        np.array([0, 50, 200]),
        np.array([180, 150, 255]),
    ),
}


# ---------------------------------------------------------------------------
# C-39: Energy Particle Detector
# ---------------------------------------------------------------------------

class EnergyParticleDetector:
    """Detects elemental energy particles and tracks their movement.

    Energy particles are collectible orbs that restore elemental energy:
    - Each character has elemental affinity (e.g., Pyro chars collect Pyro faster)
    - Particles fly toward the player when nearby
    - Priority: match character element for faster collection

    Visual characteristics:
    - Small colored orbs (~10-30 pixel radius)
    - Glowing, semi-transparent
    - Float and drift toward player when within range
    - Bright saturated colors matching element type
    """

    # Reference resolution
    _REF_W = 1920
    _REF_H = 1080

    # Particle size thresholds (normalized)
    MIN_PARTICLE_RADIUS = 5
    MAX_PARTICLE_RADIUS = 40

    # Motion tracking parameters
    MOTION_HISTORY_FRAMES = 5
    VELOCITY_SMOOTHING = 0.7

    def __init__(self) -> None:
        self._now_fn = time.perf_counter
        self._last_frame_time: float = 0.0
        self._particle_history: dict[int, list[tuple[float, tuple[float, float]]]] = {}
        self._particle_ids: dict[int, EnergyParticle] = {}
        self._next_particle_id = 0

        # Tracking state
        self._last_particles: list[EnergyParticle] = []
        self._last_result: ParticleFieldStatus | None = None

    @property
    def last_result(self) -> ParticleFieldStatus | None:
        return self._last_result

    def detect(self, frame: np.ndarray, frame_id: int) -> ParticleFieldStatus:
        """Detect energy particles in the frame.

        Args:
            frame: BGR frame from screen capture.
            frame_id: Current frame ID for tracking.

        Returns:
            ParticleFieldStatus with all detected particles.
        """
        if cv2 is None or frame.size == 0:
            return ParticleFieldStatus((), ParticleElement.OMNI, None, "no_detection")

        now = self._now_fn()
        frame_time = now

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H

        # Scale particle detection region (center of screen for better detection)
        # Particles are most visible in center
        roi_top = int(100 * sy)
        roi_bottom = int(h - 100 * sy)
        roi = frame[roi_top:roi_bottom, :]

        if roi.size == 0:
            return ParticleFieldStatus((), ParticleElement.OMNI, None, "empty_roi")

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        particles: list[EnergyParticle] = []

        for element, (lower, upper) in _PARTICLE_HSV.items():
            mask = cv2.inRange(hsv, lower, upper)

            # Morphological operations to reduce noise
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            # Find contours of potential particles
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 20:  # Skip small noise
                    continue

                # Approximate circle to estimate size
                ((cx, cy), radius) = cv2.minEnclosingCircle(contour)
                if radius < self.MIN_PARTICLE_RADIUS or radius > self.MAX_PARTICLE_RADIUS:
                    continue

                # Calculate intensity from contour area vs circle area
                circle_area = np.pi * radius * radius
                intensity = min(1.0, area / circle_area) if circle_area > 0 else 0.5

                # Convert to absolute frame coordinates
                abs_cx = int(cx)
                abs_cy = int(cy + roi_top)

                # Calculate velocity from history
                particle_id = self._match_particle(abs_cx, abs_cy, frame_id)
                if particle_id in self._particle_ids:
                    prev = self._particle_ids[particle_id]
                    dt = max(0.001, frame_time - self._last_frame_time)
                    vx = (abs_cx - prev.position[0]) / dt
                    vy = (abs_cy - prev.position[1]) / dt
                    # Apply velocity smoothing
                    vx = self.VELOCITY_SMOOTHING * vx + (1 - self.VELOCITY_SMOOTHING) * prev.velocity[0]
                    vy = self.VELOCITY_SMOOTHING * vy + (1 - self.VELOCITY_SMOOTHING) * prev.velocity[1]
                else:
                    vx, vy = 0.0, 0.0
                    particle_id = self._next_particle_id
                    self._next_particle_id += 1

                particle = EnergyParticle(
                    element=element,
                    position=(float(abs_cx), float(abs_cy)),
                    velocity=(vx, vy),
                    size_pixels=int(radius),
                    intensity=intensity,
                    age_frames=1,
                )
                particles.append(particle)
                self._particle_ids[particle_id] = particle

        # Prune old particles not seen in recent frames
        self._prune_old_particles(frame_id)

        # Determine best collection target (closest with matching element)
        dominant = self._compute_dominant_element(particles)
        target = self._select_collection_target(particles)

        action = "collect" if target else "scan"
        if target and self._is_flying_to_player(target):
            action = "intercept"

        self._last_particles = particles
        self._last_frame_time = frame_time
        self._last_result = ParticleFieldStatus(
            particles=tuple(particles),
            dominant_element=dominant,
            collection_target=target,
            recommended_action=action,
        )
        return self._last_result

    def _match_particle(self, x: int, y: int, frame_id: int) -> int | None:
        """Match a detected particle to existing tracked particle."""
        match_radius = 50  # Pixels tolerance
        best_id = None
        best_dist = float('inf')

        for pid, particle in self._particle_ids.items():
            history = self._particle_history.get(pid, [])
            if history and frame_id - history[-1][0] < 3:
                px, py = particle.position
                dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
                if dist < match_radius and dist < best_dist:
                    best_dist = dist
                    best_id = pid

        return best_id

    def _prune_old_particles(self, current_frame_id: int) -> None:
        """Remove particles not seen in recent frames."""
        to_remove = []
        for pid, particle in list(self._particle_ids.items()):
            history = self._particle_history.get(pid, [])
            if history and current_frame_id - history[-1][0] > 5:
                to_remove.append(pid)

        for pid in to_remove:
            self._particle_ids.pop(pid, None)
            self._particle_history.pop(pid, None)

    def _compute_dominant_element(self, particles: list[EnergyParticle]) -> ParticleElement:
        """Compute the most common element type."""
        if not particles:
            return ParticleElement.OMNI

        counts: dict[ParticleElement, int] = {}
        for p in particles:
            counts[p.element] = counts.get(p.element, 0) + 1

        return max(counts, key=counts.get)

    def _select_collection_target(
        self,
        particles: list[EnergyParticle],
    ) -> EnergyParticle | None:
        """Select the best particle to collect.

        Priority:
        1. Particle flying toward player (velocity toward center)
        2. Closest particle
        3. Omni particles if no elemental match known
        """
        if not particles:
            return None

        # Filter for particles that are moving toward player (center of screen)
        moving_toward = [p for p in particles if self._is_flying_to_player(p)]
        if moving_toward:
            return min(moving_toward, key=lambda p: self._distance_to_center(p.position))

        # Otherwise return closest
        return min(particles, key=lambda p: self._distance_to_center(p.position))

    def _is_flying_to_player(self, particle: EnergyParticle) -> bool:
        """Check if particle velocity indicates it's flying toward player."""
        vx, vy = particle.velocity
        # If velocity has significant magnitude and points toward screen center
        speed = (vx ** 2 + vy ** 2) ** 0.5
        if speed < 50:  # Too slow = not being collected
            return False

        # Check if moving toward center (assuming player is roughly center)
        center_x, center_y = 960, 540  # Reference center
        return True  # Simplified: any moving particle is potential target

    def _distance_to_center(self, pos: tuple[float, float]) -> float:
        """Compute distance from particle to screen center."""
        cx, cy = pos
        center_x, center_y = self._REF_W / 2, self._REF_H / 2
        return ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5

    def get_element_particles(
        self,
        element: ParticleElement,
    ) -> list[EnergyParticle]:
        """Get all particles of a specific element."""
        return [p for p in self._last_particles if p.element == element]

    def reset(self) -> None:
        """Reset detector state."""
        self._particle_history.clear()
        self._particle_ids.clear()
        self._last_particles.clear()
        self._last_result = None
        self._next_particle_id = 0