from __future__ import annotations

import base64
import threading
import time
from typing import Any

import numpy as np

from core.state_bus import StateBus
from core.types import Observation
from llm.vision_provider import ImageInput


class VLMPostProcessor:
    """Calls VLM on selected frames and publishes results to observation.extensions.

    Runs VLM analysis in a background thread to avoid blocking the perception
    pipeline. Results are published under observation.extensions["vlm_analysis"].
    """

    def __init__(
        self,
        vlm_provider: Any,
        interval_sec: float = 3.0,
        prompt: str = "",
    ) -> None:
        self._vlm = vlm_provider
        self._interval = interval_sec
        self._prompt = prompt or (
            "Analyze this game screenshot. Return JSON with screen_state, "
            "visible_objects, and suggested_action."
        )
        self._last_call_time: float = 0.0
        self._cached_result: dict[str, Any] = {}
        self._lock = threading.Lock()

    def process(self, frame: np.ndarray, observation: Observation, state_bus: StateBus) -> None:
        now = time.perf_counter()
        with self._lock:
            cached = dict(self._cached_result)
            should_call = (now - self._last_call_time) >= self._interval

        observation.extensions["vlm_analysis"] = cached

        if should_call:
            with self._lock:
                self._last_call_time = now
            thread = threading.Thread(
                target=self._async_analyze,
                args=(frame.copy(), observation.frame_id),
                daemon=True,
            )
            thread.start()

    def _async_analyze(self, frame: np.ndarray, frame_id: int) -> None:
        try:
            png_bytes = self._encode_frame(frame)
            image_input = ImageInput(data=png_bytes, mime_type="image/png", frame_id=frame_id)
            result = self._vlm.describe_image(image_input, self._prompt)
            analysis = {
                "text": result.text,
                "latency_ms": result.latency_ms,
                "model": result.model,
                "frame_id": frame_id,
                "timestamp": time.perf_counter(),
            }
            with self._lock:
                self._cached_result = analysis
        except Exception as exc:
            with self._lock:
                self._cached_result = {"error": str(exc), "frame_id": frame_id}

    @staticmethod
    def _encode_frame(frame: np.ndarray) -> bytes:
        try:
            import cv2
            success, encoded = cv2.imencode(".png", frame)
            if success:
                return encoded.tobytes()
        except ImportError:
            pass
        from PIL import Image
        import io
        rgb = frame[:, :, ::-1] if frame.shape[-1] == 3 else frame
        img = Image.fromarray(rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
