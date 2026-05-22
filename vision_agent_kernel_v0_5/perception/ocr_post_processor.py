from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.state_bus import StateBus
from core.types import Observation
from perception.ocr_base import OCRProvider

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OcrScanRegion:
    roi_id: str
    roi: tuple[int, int, int, int]
    high_value: bool = False
    claim_type: str = ""


@dataclass(frozen=True, slots=True)
class OcrPostProcessorConfig:
    interval_sec: float = 1.0
    scan_regions: tuple[OcrScanRegion, ...] = ()


class OcrPostProcessor:
    """FramePostProcessor that runs OCR on configured ROIs and publishes
    results to ``observation.extensions["ocr_blocks"]``.
    """

    def __init__(
        self,
        ocr_provider: OCRProvider,
        config: OcrPostProcessorConfig | None = None,
    ) -> None:
        self._provider = ocr_provider
        self._config = config or OcrPostProcessorConfig()
        self._last_call_time: float = 0.0
        self._cached_blocks: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def process(
        self, frame: np.ndarray, observation: Observation, state_bus: StateBus
    ) -> None:
        now = time.perf_counter()
        with self._lock:
            cached = list(self._cached_blocks)
            should_call = (now - self._last_call_time) >= self._config.interval_sec

        observation.extensions["ocr_blocks"] = cached

        if should_call:
            with self._lock:
                self._last_call_time = now
            thread = threading.Thread(
                target=self._async_scan,
                args=(frame.copy(), observation.frame_id, observation.viewport_size),
                daemon=True,
            )
            thread.start()

    def _async_scan(
        self,
        frame: np.ndarray,
        frame_id: int,
        viewport: tuple[int, int],
    ) -> None:
        blocks: list[dict[str, Any]] = []
        vw, vh = viewport
        for region in self._config.scan_regions:
            try:
                results = self._provider.detect_text(frame, roi=region.roi)
                for idx, r in enumerate(results):
                    x1, y1, x2, y2 = r.bbox
                    blocks.append({
                        "id": f"ocr:{region.roi_id}:{frame_id}:{idx}",
                        "roi_id": region.roi_id,
                        "text": r.text,
                        "confidence": r.confidence,
                        "bbox_norm": [x1 / vw, y1 / vh, (x2 - x1) / vw, (y2 - y1) / vh],
                        "source": r.source,
                        "frame_id": frame_id,
                        "timestamp": time.perf_counter(),
                    })
            except Exception as exc:
                log.warning("OCR scan failed for roi_id=%s: %s", region.roi_id, exc)
        with self._lock:
            self._cached_blocks = blocks
