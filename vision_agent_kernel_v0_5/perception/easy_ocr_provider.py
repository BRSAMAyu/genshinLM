from __future__ import annotations

import logging
from typing import Any

import numpy as np

from perception.ocr_base import OcrConfig, OcrResult, ProviderStatus

__all__ = ["EasyOcrProvider", "OcrResult", "OcrConfig"]

log = logging.getLogger(__name__)


class EasyOcrProvider:
    """EasyOCR backend for local multilingual OCR (Chinese + numbers).

    No API key required, runs entirely on local CPU/GPU.
    Supports: Chinese (ch_sim), English, numbers.
    """

    name = "easyocr"

    def __init__(self, config: OcrConfig | None = None) -> None:
        self._config = config or OcrConfig()
        self._reader: Any | None = None
        self._initialized = False
        self._available = True

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        try:
            import easyocr  # type: ignore[import-untyped]

            langs = ["en"]
            if "ch" in self._config.language:
                langs.insert(0, "ch_sim")

            self._reader = easyocr.Reader(
                langs,
                gpu=self._config.use_gpu,
                verbose=False,
            )
            log.info("[EasyOCR] initialized with languages: %s", langs)
        except Exception as exc:
            self._reader = None
            self._available = False
            log.warning("[EasyOCR] not available — OCR features will return empty results: %s", exc)

    def detect_text(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[OcrResult]:
        self._ensure_initialized()
        if not self._available or self._reader is None:
            return []
        target = self._crop_roi(image, roi) if roi else image
        raw = self._run_ocr(target)
        results = self._parse_results(raw)
        if roi:
            x1, y1 = roi[0], roi[1]
            results = [
                OcrResult(
                    text=r.text,
                    confidence=r.confidence,
                    bbox=(r.bbox[0] + x1, r.bbox[1] + y1, r.bbox[2] + x1, r.bbox[3] + y1),
                    source=self.name,
                )
                for r in results
            ]
        return results

    def status(self) -> ProviderStatus:
        self._ensure_initialized()
        return ProviderStatus(
            provider=self.name,
            ok=self._available,
            message="ready" if self._available else "EasyOCR not available",
        )

    @staticmethod
    def _crop_roi(image: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
        x1, y1, x2, y2 = roi
        h, w = image.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return image
        return image[y1:y2, x1:x2]

    def _run_ocr(self, image: np.ndarray) -> list[tuple]:
        assert self._reader is not None
        results = self._reader.readtext(image)
        return results

    @staticmethod
    def _parse_results(raw: list[tuple]) -> list[OcrResult]:
        out: list[OcrResult] = []
        for item in raw:
            if len(item) < 3:
                continue
            bbox, text_info, conf = item
            if isinstance(text_info, (list, tuple)):
                text = str(text_info[0]) if text_info else ""
                confidence = float(text_info[1]) if len(text_info) > 1 else float(conf)
            else:
                text = str(text_info)
                confidence = float(conf)
            # bbox is [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            out.append(
                OcrResult(
                    text=text,
                    confidence=min(max(confidence, 0.0), 1.0),
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                )
            )
        return out