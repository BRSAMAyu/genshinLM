from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class CoOpDetection:
    teammate_visible: bool
    teammate_count: int
    teammate_bboxes: list[tuple[int, int, int, int]]
    interference_score: float


class CoOpFilter:
    """Filter out visual interference from Co-Op teammates."""

    def __init__(self) -> None:
        self._coop_active = False
        self._teammate_colors: list[tuple[int, int, int]] = []

    def detect_coop_mode(self, frame: np.ndarray) -> bool:
        """Detect if we're in Co-Op mode."""
        if frame.ndim != 3 or frame.shape[2] < 3:
            self._coop_active = False
            return False
        nameplates = self._detect_nameplates(frame)
        active = len(nameplates) >= 1
        self._coop_active = active
        return active

    def filter_teammate_detections(
        self,
        detections: list[tuple[int, int, int, int, float, str]],
        frame: np.ndarray,
    ) -> list[tuple[int, int, int, int, float, str]]:
        """Filter out teammate detections from YOLO output."""
        if not self._coop_active:
            return list(detections)
        teammate_bboxes = self.detect_teammate_positions(frame)
        if not teammate_bboxes:
            return list(detections)
        filtered: list[tuple[int, int, int, int, float, str]] = []
        for det in detections:
            x1, y1, x2, y2, conf, cls = det
            det_box = (x1, y1, x2, y2)
            is_teammate = False
            for tb in teammate_bboxes:
                iou = self._iou(det_box, tb)
                if iou > 0.3:
                    is_teammate = True
                    break
            if not is_teammate:
                filtered.append(det)
        return filtered

    def filter_hp_bars(
        self,
        hp_roi: np.ndarray,
        enemy_count: int = 1,
    ) -> np.ndarray:
        """Filter HP bar ROI to exclude teammate HP bars."""
        if hp_roi.size == 0 or hp_roi.ndim < 2:
            return hp_roi
        h = hp_roi.shape[0]
        if h <= enemy_count * 2:
            return hp_roi
        segment_h = h // (enemy_count + 1)
        end_row = min(segment_h * enemy_count, h)
        return hp_roi[:end_row, :]

    def detect_teammate_positions(self, frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Detect teammate character positions in frame."""
        return self._detect_nameplates(frame)

    def compute_interference_score(
        self,
        target_bbox: tuple[int, int, int, int] | None,
        teammate_bboxes: list[tuple[int, int, int, int]],
    ) -> float:
        """Compute how much teammates interfere with target tracking."""
        if target_bbox is None or not teammate_bboxes:
            return 0.0
        max_iou = max(self._iou(target_bbox, tb) for tb in teammate_bboxes)
        return min(1.0, max_iou)

    @property
    def coop_active(self) -> bool:
        return self._coop_active

    def _detect_nameplates(self, frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Detect player nameplates (blue colored text above characters)."""
        if frame.ndim != 3 or frame.shape[2] < 3:
            return []
        hsv = np.zeros_like(frame[:, :, :1])
        try:
            import cv2  # type: ignore[import-not-found]
            hsv_full = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        except (ImportError, Exception):
            b = frame[:, :, 0].astype(np.int16)
            g = frame[:, :, 1].astype(np.int16)
            r = frame[:, :, 2].astype(np.int16)
            blue_mask = (b > 150) & (g < 100) & (r < 100)
            return self._mask_to_bboxes(blue_mask.astype(np.uint8))

        blue_mask = cv2.inRange(hsv_full, (100, 80, 80), (130, 255, 255))
        return self._mask_to_bboxes(blue_mask)

    def _mask_to_bboxes(self, mask: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Convert a binary mask to a list of bounding boxes."""
        try:
            import cv2  # type: ignore[import-not-found]
            labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(
                mask.astype(np.uint8), connectivity=8
            )
            bboxes: list[tuple[int, int, int, int]] = []
            for i in range(1, labels_count):
                area = int(stats[i, cv2.CC_STAT_AREA])
                if area < 100:
                    continue
                x = int(stats[i, cv2.CC_STAT_LEFT])
                y = int(stats[i, cv2.CC_STAT_TOP])
                w = int(stats[i, cv2.CC_STAT_WIDTH])
                h = int(stats[i, cv2.CC_STAT_HEIGHT])
                bboxes.append((x, y, x + w, y + h))
            del labels
            return bboxes
        except ImportError:
            ys, xs = np.where(mask > 0)
            if len(xs) == 0:
                return []
            return [(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))]

    def _iou(self, a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        """Compute intersection over union between two boxes."""
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
        area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
        union = area_a + area_b - inter
        if union <= 0:
            return 0.0
        return inter / union
