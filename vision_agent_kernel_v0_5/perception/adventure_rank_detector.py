from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


class AdventureRankDetector:
    """Detect Adventure Rank (AR) from HUD or menu in Genshin Impact."""

    _REF_W = 1920
    _REF_H = 1080

    def __init__(self, viewport: tuple[int, int] = (1920, 1080)) -> None:
        self._sx = viewport[0] / self._REF_W
        self._sy = viewport[1] / self._REF_H
        # AR number below player name in top-left HUD
        self._hud_ar_roi = (10, 30, 140, 55)

    def detect_from_hud(self, frame: np.ndarray) -> int | None:
        """Detect AR indicator presence from the HUD overlay.

        Returns the AR number if bright text is detected in the AR region,
        or None if the region is absent or unreadable.
        Precise OCR requires calibration; for now returns 1 as placeholder
        when the indicator region is present.
        """
        if cv2 is None:
            return None
        x1, y1, x2, y2 = self._scale_roi(self._hud_ar_roi, self._sx, self._sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        # Threshold to isolate bright text
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

        bright_ratio = float(np.sum(binary > 0)) / binary.size
        if bright_ratio < 0.02:
            return None

        # Placeholder: AR indicator is present but precise digit reading
        # requires OCR calibration. Return 1 to indicate detection.
        return 1

    def detect_from_menu(self, frame: np.ndarray) -> int | None:
        """Detect AR from the Paimon menu context.

        The menu shows AR as a number near the player profile card.
        Uses similar text detection as HUD mode but in a menu-specific ROI.
        """
        if cv2 is None:
            return None
        # Menu AR region: slightly different position in Paimon menu overlay
        menu_ar_roi = (80, 60, 250, 90)
        x1, y1, x2, y2 = self._scale_roi(menu_ar_roi, self._sx, self._sy)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

        bright_ratio = float(np.sum(binary > 0)) / binary.size
        if bright_ratio < 0.02:
            return None

        # Placeholder: same as HUD, precise OCR needs calibration
        return 1

    @staticmethod
    def _scale_roi(
        roi: tuple[int, int, int, int], sx: float, sy: float,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
