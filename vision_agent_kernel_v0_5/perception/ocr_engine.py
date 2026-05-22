from __future__ import annotations

import logging
import re

import numpy as np

from perception.ocr_base import OcrConfig, OcrResult, ProviderStatus

__all__ = ["OcrEngine", "PaddleOcrProvider", "OcrResult", "OcrConfig"]

log = logging.getLogger(__name__)


class PaddleOcrProvider:
    """PaddleOCR backend implementing the OCRProvider protocol."""

    name = "paddle_ocr"

    def __init__(self, config: OcrConfig | None = None) -> None:
        self._config = config or OcrConfig()
        self._ocr: object | None = None
        self._initialized = False
        self._available = True

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self._config.language,
                use_gpu=self._config.use_gpu,
                det_limit_side_len=self._config.det_limit_side_len,
                rec_batch_num=self._config.rec_batch_num,
                enable_mkldnn=self._config.enable_mkldnn,
                show_log=False,
            )
        except Exception:
            self._ocr = None
            self._available = False
            log.warning("PaddleOCR not available — OCR features will return empty results")

    def detect_text(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[OcrResult]:
        self._ensure_initialized()
        if not self._available or self._ocr is None:
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
        else:
            results = [OcrResult(r.text, r.confidence, r.bbox, self.name) for r in results]
        return results

    def status(self) -> ProviderStatus:
        self._ensure_initialized()
        return ProviderStatus(
            provider=self.name,
            ok=self._available,
            message="ready" if self._available else "PaddleOCR not available",
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

    def _run_ocr(self, image: np.ndarray) -> list[list[list | tuple]]:
        assert self._ocr is not None
        result = self._ocr.ocr(image, cls=True)
        if not result or result[0] is None:
            return []
        return result[0]

    @staticmethod
    def _parse_results(raw: list[list[list | tuple]]) -> list[OcrResult]:
        out: list[OcrResult] = []
        for item in raw:
            if len(item) != 2:
                continue
            bbox_pts, info = item
            if not isinstance(bbox_pts, (list, tuple)) or len(bbox_pts) < 4:
                continue
            if not isinstance(info, (list, tuple)) or len(info) < 2:
                continue
            text = str(info[0])
            confidence = float(info[1])
            xs = [int(p[0]) for p in bbox_pts]
            ys = [int(p[1]) for p in bbox_pts]
            out.append(
                OcrResult(
                    text=text,
                    confidence=confidence,
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                )
            )
        return out


class OcrEngine(PaddleOcrProvider):
    """Backward-compatible wrapper preserving the original OcrEngine API."""

    def detect_text_roi(
        self, image: np.ndarray, roi: tuple[int, int, int, int]
    ) -> list[OcrResult]:
        return self.detect_text(image, roi=roi)

    def read_number(self, image: np.ndarray) -> int | None:
        results = self.detect_text(image)
        for r in results:
            digits = re.sub(r"\D", "", r.text)
            if digits:
                return int(digits)
        return None

    def contains_text(self, image: np.ndarray, keywords: list[str]) -> tuple[bool, str]:
        results = self.detect_text(image)
        joined = " ".join(r.text.strip() for r in results).lower()
        for keyword in keywords:
            if keyword.strip().lower() in joined:
                return (True, keyword)
        return (False, "")
