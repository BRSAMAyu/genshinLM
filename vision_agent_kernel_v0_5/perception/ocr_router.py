from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from perception.ocr_base import OcrResult, ProviderStatus

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OcrRouterConfig:
    confidence_threshold: float = 0.7
    escalation_enabled: bool = True
    high_value_roi_ids: tuple[str, ...] = (
        "dialog_text",
        "quest_text",
        "reward_claim",
        "inventory_item",
        "cooldown_number",
        "notification_text",
    )
    high_value_claim_types: tuple[str, ...] = (
        "reward_claimed",
        "quest_complete",
        "level_up",
    )


class OCRProvider(Protocol):
    name: str

    def detect_text(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[OcrResult]: ...

    def status(self) -> ProviderStatus: ...


class OcrRouter:
    """Routes OCR requests between a fast local provider and an accurate cloud fallback.

    Implements the OCRProvider protocol so it is a drop-in replacement.
    Escalation to the fallback provider happens asynchronously — primary results
    are always returned immediately, and escalated results are merged on the next
    call for the same roi_id.
    """

    name = "ocr_router"

    def __init__(
        self,
        primary: OCRProvider,
        fallback: OCRProvider | None = None,
        config: OcrRouterConfig | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._config = config or OcrRouterConfig()
        self._lock = threading.Lock()
        self._escalation_results: dict[str, list[OcrResult]] = {}

    def detect_text(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
        *,
        roi_id: str = "",
        claim_type: str = "",
        force_fallback: bool = False,
    ) -> list[OcrResult]:
        results = self._primary.detect_text(image, roi=roi)

        key = roi_id or "default"
        with self._lock:
            escalated = self._escalation_results.pop(key, None)
        if escalated is not None:
            return self._merge(results, escalated)

        if self._should_escalate(results, roi_id, claim_type, force_fallback):
            self._escalate_async(image, roi, key, results)

        return results

    def status(self) -> ProviderStatus:
        primary = self._primary.status()
        parts = [f"primary={primary.ok}"]
        if self._fallback:
            fallback = self._fallback.status()
            parts.append(f"fallback={fallback.ok}")
        return ProviderStatus(
            provider=self.name,
            ok=primary.ok,
            message="; ".join(parts),
        )

    def _should_escalate(
        self,
        results: list[OcrResult],
        roi_id: str,
        claim_type: str,
        force: bool,
    ) -> bool:
        if force:
            return True
        if not self._config.escalation_enabled:
            return False
        if self._fallback is None or not self._fallback.status().ok:
            return False
        if not results:
            return True
        min_confidence = min(r.confidence for r in results)
        if min_confidence >= self._config.confidence_threshold:
            return False
        is_high_value = (
            roi_id in self._config.high_value_roi_ids
            or claim_type in self._config.high_value_claim_types
        )
        return is_high_value

    def _escalate_async(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None,
        key: str,
        original: list[OcrResult],
    ) -> None:
        assert self._fallback is not None

        def _run() -> None:
            try:
                escalated = self._fallback.detect_text(image, roi=roi)
                with self._lock:
                    self._escalation_results[key] = escalated
            except Exception as exc:
                log.warning("OCR escalation failed for roi_id=%s: %s", key, exc)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    @staticmethod
    def _merge(
        primary: list[OcrResult],
        fallback: list[OcrResult],
    ) -> list[OcrResult]:
        if not fallback:
            return primary
        if not primary:
            return fallback

        merged = list(fallback)
        fb_bboxes = [r.bbox for r in fallback]

        for pr in primary:
            overlapping = False
            for fb_bbox in fb_bboxes:
                if _iou(pr.bbox, fb_bbox) > 0.3:
                    overlapping = True
                    break
            if not overlapping:
                merged.append(pr)

        merged.sort(key=lambda r: r.confidence, reverse=True)
        return merged


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return inter / (area_a + area_b - inter)
