"""Q-29: Elemental target detector for elemental puzzle activation.

Detects elemental targets (torches, pressure plates, etc.) that
need specific elements to solve puzzles.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class ElementType(str, Enum):
    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    ANEMO = "anemo"
    GEO = "geo"
    DENDRO = "dendro"


class TargetState(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    CHARGING = "charging"  # Partially activated
    LOCKED = "locked"


class TargetType(str, Enum):
    TORCH = "torch"
    PRESSURE_PLATE = "pressure_plate"
    SEAL = "seal"
    DEVICE = "device"
    SLIME = "slime"  # Elemental slimes that are targets


@dataclass(frozen=True, slots=True)
class ElementalTarget:
    """Detected elemental target."""
    target_id: str
    target_type: TargetType
    position: tuple[int, int]  # screen position
    required_element: ElementType | None
    current_element: ElementType | None
    state: TargetState
    confidence: float


@dataclass(frozen=True, slots=True)
class TargetDetection:
    """Result of target detection scan."""
    targets: list[ElementalTarget]
    inactive_count: int
    active_count: int
    all_activated: bool
    recommended_element: ElementType | None


class ElementalTargetDetector:
    """Detect and track elemental activation targets."""

    _REF_W = 1920
    _REF_H = 1080

    # Element colors in HSV
    _ELEMENT_COLORS: dict[ElementType, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
        ElementType.PYRO: ((0, 100, 100), (20, 255, 255)),       # Orange-red
        ElementType.HYDRO: ((90, 80, 80), (130, 255, 255)),      # Blue
        ElementType.ELECTRO: ((130, 80, 80), (170, 255, 255)),  # Purple
        ElementType.CRYO: ((85, 50, 100), (110, 255, 255)),      # Cyan
        ElementType.ANEMO: ((35, 60, 60), (85, 255, 255)),      # Green
        ElementType.GEO: ((10, 60, 60), (30, 255, 255)),        # Brown
        ElementType.DENDRO: ((25, 80, 80), (85, 255, 255)),     # Yellow-green
    }

    # Inactive/unlit torch colors (gray/dark)
    _INACTIVE_LOW = np.array([0, 0, 30], dtype=np.uint8)
    _INACTIVE_HIGH = np.array([180, 30, 100], dtype=np.uint8)

    def __init__(
        self,
        on_target_activated: Any = None,
        on_all_targets_ready: Any = None,
    ) -> None:
        self._targets: dict[str, ElementalTarget] = {}
        self._on_target_activated = on_target_activated
        self._on_all_targets_ready = on_all_targets_ready
        self._last_scan_frame_id = -1

    def scan_targets(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
        expected_count: int | None = None,
    ) -> TargetDetection:
        """Scan for elemental targets in frame.

        Args:
            frame: BGR image from screen capture
            frame_id: Current frame ID
            expected_count: Expected number of targets (for validation)

        Returns:
            TargetDetection with found targets
        """
        if cv2 is None:
            return TargetDetection(
                targets=[],
                inactive_count=0,
                active_count=0,
                all_activated=False,
                recommended_element=None,
            )

        if frame_id == self._last_scan_frame_id:
            # Return cached results
            return self._build_detection_from_cache()

        self._last_scan_frame_id = frame_id
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Find inactive targets (unlit torches)
        inactive_mask = cv2.inRange(hsv, self._INACTIVE_LOW, self._INACTIVE_HIGH)
        inactive_contours, _ = cv2.findContours(inactive_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        targets: list[ElementalTarget] = []

        # Process inactive targets
        for i, contour in enumerate(inactive_contours):
            area = cv2.contourArea(contour)
            if 200 < area < 5000:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    target_id = f"target_{i}_{cx}_{cy}"

                    targets.append(ElementalTarget(
                        target_id=target_id,
                        target_type=TargetType.TORCH,
                        position=(cx, cy),
                        required_element=None,  # Unknown
                        current_element=None,
                        state=TargetState.INACTIVE,
                        confidence=0.6,
                    ))

        # Check for active element glows
        for element, (lower, upper) in self._ELEMENT_COLORS.items():
            element_mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
            element_contours, _ = cv2.findContours(element_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in element_contours:
                area = cv2.contourArea(contour)
                if 200 < area < 3000:
                    M = cv2.moments(contour)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])

                        # Check if this is near an existing inactive target
                        matched = False
                        for t in targets:
                            dx = t.position[0] - cx
                            dy = t.position[1] - cy
                            if dx * dx + dy * dy < 10000:  # Within 100 pixels
                                t.position = (cx, cy)
                                t.current_element = element
                                t.state = TargetState.ACTIVE
                                t.confidence = 0.8
                                matched = True
                                break

                        if not matched:
                            target_id = f"active_{element.value}_{cx}_{cy}"
                            targets.append(ElementalTarget(
                                target_id=target_id,
                                target_type=TargetType.TORCH,
                                position=(cx, cy),
                                required_element=None,
                                current_element=element,
                                state=TargetState.ACTIVE,
                                confidence=0.8,
                            ))

        # Update internal target list
        self._targets = {t.target_id: t for t in targets}

        # Build detection result
        return self._build_detection_from_cache()

    def _build_detection_from_cache(self) -> TargetDetection:
        """Build detection result from cached targets."""
        targets = list(self._targets.values())
        inactive = sum(1 for t in targets if t.state == TargetState.INACTIVE)
        active = sum(1 for t in targets if t.state == TargetState.ACTIVE)

        # Determine recommended element
        recommended = None
        if inactive > 0 and active > 0:
            # Find pattern in active elements
            active_elements = [t.current_element for t in targets if t.current_element]
            if active_elements:
                recommended = active_elements[0]

        return TargetDetection(
            targets=targets,
            inactive_count=inactive,
            active_count=active,
            all_activated=inactive == 0 and active > 0,
            recommended_element=recommended,
        )

    def mark_target_activated(
        self,
        target_id: str,
        element_used: ElementType,
    ) -> TargetDetection:
        """Mark a target as activated.

        Args:
            target_id: Target to mark
            element_used: Element that was used

        Returns:
            Updated TargetDetection
        """
        if target_id in self._targets:
            target = self._targets[target_id]
            self._targets[target_id] = ElementalTarget(
                target_id=target.target_id,
                target_type=target.target_type,
                position=target.position,
                required_element=element_used,
                current_element=element_used,
                state=TargetState.ACTIVE,
                confidence=target.confidence,
            )

            log.info("[ElementalTarget] Target %s activated with %s", target_id, element_used.value)

            if self._on_target_activated:
                try:
                    self._on_target_activated(target_id, element_used)
                except Exception as exc:
                    log.warning("[ElementalTarget] Activation callback failed: %s", exc)

        detection = self._build_detection_from_cache()

        if detection.all_activated and self._on_all_targets_ready:
            try:
                self._on_all_targets_ready()
            except Exception as exc:
                log.warning("[ElementalTarget] All ready callback failed: %s", exc)

        return detection

    def get_nearest_inactive_target(self, position: tuple[int, int]) -> ElementalTarget | None:
        """Get nearest inactive target to a position."""
        inactive = [t for t in self._targets.values() if t.state == TargetState.INACTIVE]
        if not inactive:
            return None

        px, py = position
        closest = min(
            inactive,
            key=lambda t: (t.position[0] - px) ** 2 + (t.position[1] - py) ** 2
        )
        return closest

    def get_activation_order(self) -> list[ElementalTarget]:
        """Get recommended activation order for targets."""
        # Sort by position (left to right, top to bottom)
        targets = list(self._targets.values())
        targets.sort(key=lambda t: (t.position[1], t.position[0]))
        return targets

    def reset(self) -> None:
        """Reset detector state."""
        self._targets = {}
        self._last_scan_frame_id = -1
        log.info("[ElementalTargetDetector] Detector reset")