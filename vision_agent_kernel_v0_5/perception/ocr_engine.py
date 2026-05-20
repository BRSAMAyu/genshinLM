from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class OcrConfig:
    language: str = "ch"
    use_gpu: bool = False
    det_limit_side_len: int = 960
    rec_batch_num: int = 6
    enable_mkldnn: bool = True


class OcrEngine:
    """PaddleOCR wrapper with lazy initialization and ROI-based scanning."""

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

    def detect_text(self, image: np.ndarray) -> list[OcrResult]:
        self._ensure_initialized()
        if not self._available or self._ocr is None:
            return []
        raw = self._run_ocr(image)
        return self._parse_results(raw)

    def detect_text_roi(
        self, image: np.ndarray, roi: tuple[int, int, int, int]
    ) -> list[OcrResult]:
        x1, y1, x2, y2 = roi
        h, w = image.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return []
        cropped = image[y1:y2, x1:x2]
        results = self.detect_text(cropped)
        return [
            OcrResult(
                text=r.text,
                confidence=r.confidence,
                bbox=(r.bbox[0] + x1, r.bbox[1] + y1, r.bbox[2] + x1, r.bbox[3] + y1),
            )
            for r in results
        ]

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

    def _run_ocr(self, image: np.ndarray) -> list[list[list | tuple]]:
        assert self._ocr is not None
        result = self._ocr.ocr(image, cls=True)
        if not result or result[0] is None:
            return []
        return result[0]

    def _parse_results(self, raw: list[list[list | tuple]]) -> list[OcrResult]:
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
