from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from core.events import Interrupt
from core.state_bus import StateBus
from core.timebase import Timebase
from core.types import TargetCandidate


@dataclass(frozen=True, slots=True)
class YoloDetectorConfig:
    model_path: str
    conf_threshold: float = 0.35
    iou_threshold: float = 0.5
    device: str | None = None
    half: bool = False
    classes: list[int] | None = None


class YoloDetector:
    def __init__(
        self,
        config: YoloDetectorConfig,
        state_bus: StateBus | None = None,
        timebase: Timebase | None = None,
        model: Any | None = None,
    ) -> None:
        self._config = config
        self._state_bus = state_bus
        self._timebase = timebase or Timebase()
        self._model = model

    def detect(self, frame: np.ndarray, frame_id: int) -> list[TargetCandidate]:
        try:
            model = self._load_model()
            results = model.predict(
                frame,
                conf=self._config.conf_threshold,
                iou=self._config.iou_threshold,
                device=self._config.device,
                half=self._config.half,
                classes=self._config.classes,
                verbose=False,
            )
            candidates = self._results_to_candidates(results, frame_id)
            print(
                "[YoloDetector] "
                f"frame_id={frame_id} candidates={len(candidates)} "
                f"conf_threshold={self._config.conf_threshold}",
                flush=True,
            )
            return candidates
        except Exception as exc:
            self._publish_error(frame_id=frame_id, exc=exc)
            return []

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed") from exc
        self._model = YOLO(self._config.model_path)
        print(f"[YoloDetector] loaded model_path={self._config.model_path}", flush=True)
        return self._model

    def _results_to_candidates(self, results: Any, frame_id: int) -> list[TargetCandidate]:
        if not results:
            return []
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        names = getattr(result, "names", None) or getattr(self._load_model(), "names", {})
        candidates: list[TargetCandidate] = []
        for box in boxes:
            xyxy_values = self._to_float_list(box.xyxy[0])
            confidence = float(self._to_float_list(box.conf)[0])
            class_index = int(self._to_float_list(box.cls)[0])
            class_id = str(names.get(class_index, class_index)) if isinstance(names, dict) else str(class_index)
            x1, y1, x2, y2 = xyxy_values
            width = max(0.0, x2 - x1)
            height = max(0.0, y2 - y1)
            area = width * height
            aspect_ratio = width / height if height > 0.0 else 0.0
            candidates.append(
                TargetCandidate(
                    frame_id=frame_id,
                    class_id=class_id,
                    bbox_xyxy=(x1, y1, x2, y2),
                    confidence=confidence,
                    center_px=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                    area_px=area,
                    aspect_ratio=aspect_ratio,
                )
            )
        return candidates

    def _to_float_list(self, value: Any) -> list[float]:
        if hasattr(value, "detach"):
            value = value.detach()
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        return np.asarray(value, dtype=float).reshape(-1).tolist()

    def _publish_error(self, frame_id: int, exc: Exception) -> None:
        now = self._timebase.now()
        print(
            "[YoloDetector] "
            f"{now:.6f} detector error frame_id={frame_id} error={exc!r}",
            flush=True,
        )
        if self._state_bus is None:
            return
        self._state_bus.publish_interrupt(
            Interrupt(
                priority=1,
                timestamp=now,
                code="DETECTOR_ERROR",
                source="yolo_detector",
                frame_id=frame_id,
                payload={"error": repr(exc)},
                recoverable=True,
            )
        )
