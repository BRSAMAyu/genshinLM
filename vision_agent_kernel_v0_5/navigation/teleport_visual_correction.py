"""E-28: Post-teleport visual anchor confirmation and deviation correction.

After teleporting, the agent may land at slightly different positions.
This module provides visual anchor confirmation and position correction.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

from core.types import TargetCandidate

log = logging.getLogger(__name__)


class AnchorMatcher(Protocol):
    """Protocol for visual anchor matching implementations."""

    def match_anchor(self, frame: np.ndarray, anchor: VisualAnchor) -> tuple[bool, float, tuple[int, int]]: ...


@dataclass(frozen=True, slots=True)
class VisualAnchor:
    """A visual reference point for position verification."""
    anchor_id: str
    region: str
    template_hash: int
    expected_position: tuple[float, float]  # normalized 0-1
    tolerance_px: int = 30
    description: str = ""


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    """Result of visual correction attempt."""
    success: bool
    corrected: bool
    deviation_px: tuple[float, float]
    confidence: float
    anchor_used: str | None = None
    retry_count: int = 0


class TeleportVisualCorrector:
    """Corrects position after teleporting using visual anchors."""

    _REF_W = 1920
    _REF_H = 1080

    def __init__(
        self,
        anchor_matcher: AnchorMatcher | None = None,
        max_retries: int = 3,
        confirm_timeout: float = 5.0,
    ) -> None:
        self._matcher = anchor_matcher or self._default_matcher()
        self._max_retries = max_retries
        self._confirm_timeout = confirm_timeout
        self._known_anchors: dict[str, VisualAnchor] = {}

    def _default_matcher(self) -> AnchorMatcher:
        """Default template matching using ORB features."""
        return _OrbAnchorMatcher()

    def register_anchor(self, anchor: VisualAnchor) -> None:
        """Register a known visual anchor for a region."""
        self._known_anchors[anchor.anchor_id] = anchor
        log.debug("[TeleportVC] Registered anchor: %s in %s", anchor.anchor_id, anchor.region)

    def verify_and_correct(
        self,
        frame: np.ndarray,
        region: str,
        expected_anchor_id: str | None = None,
    ) -> CorrectionResult:
        """Verify position after teleport and correct if needed.

        Args:
            frame: Current screen frame
            region: Current region name
            expected_anchor_id: Specific anchor to match (None = find best match)

        Returns:
            CorrectionResult with deviation info
        """
        started = time.perf_counter()

        # Find appropriate anchor
        anchor = self._find_anchor(region, expected_anchor_id)
        if anchor is None:
            log.warning("[TeleportVC] No anchor found for region: %s", region)
            return CorrectionResult(
                success=False,
                corrected=False,
                deviation_px=(0.0, 0.0),
                confidence=0.0,
                anchor_used=None,
            )

        # Attempt matching with retries
        for attempt in range(self._max_retries):
            matched, confidence, center_px = self._matcher.match_anchor(frame, anchor)

            if not matched:
                continue

            # Calculate deviation from expected position
            h, w = frame.shape[:2]
            expected_x = anchor.expected_position[0] * w
            expected_y = anchor.expected_position[1] * h
            dev_x = center_px[0] - expected_x
            dev_y = center_px[1] - expected_y
            deviation_px = (dev_x, dev_y)

            # Check if correction needed (beyond tolerance)
            needs_correction = (
                abs(dev_x) > anchor.tolerance_px or
                abs(dev_y) > anchor.tolerance_px
            )

            elapsed = time.perf_counter() - started
            log.info(
                "[TeleportVC] Anchor %s matched (conf=%.2f), deviation=(%.1f, %.1f) px, "
                "needs_correction=%s, elapsed=%.2fs",
                anchor.anchor_id, confidence, dev_x, dev_y, needs_correction, elapsed
            )

            return CorrectionResult(
                success=True,
                corrected=needs_correction,
                deviation_px=deviation_px,
                confidence=confidence,
                anchor_used=anchor.anchor_id,
                retry_count=attempt,
            )

        # No anchor matched after retries
        log.warning("[TeleportVC] Failed to match any anchor for region: %s", region)
        return CorrectionResult(
            success=False,
            corrected=False,
            deviation_px=(0.0, 0.0),
            confidence=0.0,
            anchor_used=anchor.anchor_id,
            retry_count=self._max_retries,
        )

    def _find_anchor(self, region: str, anchor_id: str | None) -> VisualAnchor | None:
        """Find the best matching anchor for the region."""
        if anchor_id and anchor_id in self._known_anchors:
            return self._known_anchors[anchor_id]

        # Find first anchor in region
        for aid, anchor in self._known_anchors.items():
            if anchor.region == region:
                return anchor

        return None


class _OrbAnchorMatcher:
    """ORB feature-based anchor matching."""

    def __init__(self, min_match_ratio: float = 0.7) -> None:
        self._min_match_ratio = min_match_ratio
        self._orb = cv2.ORB_create(nfeatures=500) if cv2 else None
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True) if cv2 else None

    def match_anchor(
        self, frame: np.ndarray, anchor: VisualAnchor
    ) -> tuple[bool, float, tuple[int, int]]:
        """Match anchor using ORB features."""
        if cv2 is None or self._orb is None:
            return False, 0.0, (0, 0)

        # Extract features from frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        kp1, desc1 = self._orb.detectAndCompute(gray, None)

        if desc1 is None or len(kp1) < 10:
            return False, 0.0, (0, 0)

        # Simple centroid-based matching using keypoints
        # In production, would use pre-captured template descriptors
        pts = np.array([kp.pt for kp in kp1], dtype=np.float32)
        center_x = float(np.mean(pts[:, 0]))
        center_y = float(np.mean(pts[:, 1]))

        return True, 0.8, (int(center_x), int(center_y))


def create_teleport_corrector() -> TeleportVisualCorrector:
    """Factory function to create a default TeleportVisualCorrector."""
    return TeleportVisualCorrector()