from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import numpy as np

from llm.provider_base import ProviderRequestError, ProviderUnavailable
from perception.ocr_base import OcrResult, ProviderStatus

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GlmOcrConfig:
    api_key: str | None = None
    model: str = "glm-ocr"
    base_url: str = "https://open.bigmodel.cn/api/paas/v4/layout_parsing"
    timeout_sec: float = 30.0


class GlmOcrProvider:
    """Cloud OCR via Zhipu GLM-OCR layout parsing API."""

    name = "glm_ocr"

    def __init__(self, config: GlmOcrConfig | None = None) -> None:
        cfg = config or GlmOcrConfig()
        self._api_key = cfg.api_key or os.getenv("ZHIPU_API_KEY", "")
        self._model = cfg.model
        self._base_url = cfg.base_url
        self._timeout = cfg.timeout_sec

    def detect_text(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[OcrResult]:
        if not self._api_key:
            raise ProviderUnavailable("ZHIPU_API_KEY not configured for GLM-OCR")
        target = self._crop_roi(image, roi) if roi else image
        png_b64 = self._encode_image(target)
        payload = {
            "model": self._model,
            "file": f"data:image/png;base64,{png_b64}",
        }
        started = time.perf_counter()
        data = self._request(payload)
        latency_ms = (time.perf_counter() - started) * 1000.0
        results = self._parse_response(data)
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
        log.info("GLM-OCR: %d results in %.0fms", len(results), latency_ms)
        return results

    def status(self) -> ProviderStatus:
        if not self._api_key:
            return ProviderStatus(self.name, False, message="ZHIPU_API_KEY not configured")
        return ProviderStatus(self.name, True, message="configured")

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            raise ProviderRequestError(f"GLM-OCR API call failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderRequestError(f"GLM-OCR invalid response: {exc}") from exc

    @staticmethod
    def _encode_image(frame: np.ndarray) -> str:
        try:
            import cv2
            success, encoded = cv2.imencode(".png", frame)
            if success:
                return base64.b64encode(encoded.tobytes()).decode("ascii")
        except ImportError:
            pass
        from PIL import Image
        import io
        rgb = frame[:, :, ::-1] if frame.shape[-1] == 3 else frame
        img = Image.fromarray(rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    @staticmethod
    def _crop_roi(image: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
        x1, y1, x2, y2 = roi
        h, w = image.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return image
        return image[y1:y2, x1:x2]

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> list[OcrResult]:
        results: list[OcrResult] = []
        layout_details = data.get("layout_details")
        if layout_details and isinstance(layout_details, list):
            for page in layout_details:
                if not isinstance(page, list):
                    continue
                for item in page:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("label", ""))
                    if label in ("figure", "page_header", "page_footer"):
                        continue
                    content = str(item.get("content", "")).strip()
                    if not content:
                        continue
                    bbox_2d = item.get("bbox_2d")
                    if isinstance(bbox_2d, (list, tuple)) and len(bbox_2d) == 4:
                        x1, y1, x2, y2 = (int(v) for v in bbox_2d)
                    else:
                        x1, y1, x2, y2 = 0, 0, 0, 0
                    results.append(
                        OcrResult(
                            text=content,
                            confidence=0.9,
                            bbox=(x1, y1, x2, y2),
                            source="glm_ocr",
                        )
                    )
        if not results:
            md = data.get("md_results", "")
            if md and isinstance(md, str):
                for line in md.splitlines():
                    stripped = line.strip()
                    if stripped:
                        results.append(
                            OcrResult(
                                text=stripped,
                                confidence=0.7,
                                bbox=(0, 0, 0, 0),
                                source="glm_ocr_md",
                            )
                        )
        return results
