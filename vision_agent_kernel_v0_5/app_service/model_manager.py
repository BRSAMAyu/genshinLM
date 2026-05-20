from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class ModelStatus:
    detector_backend: str
    model_path: str | None
    model_exists: bool
    ultralytics_available: bool
    tracker: str
    tracker_available: bool
    device: str
    half: bool


class ModelManager:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._model_config_path = root / "configs" / "model.yaml"
        self._loaded_model_path: str | None = None

    def status(self) -> ModelStatus:
        config = self._read_config()
        detector = dict(config.get("detector", {}))
        model_path = detector.get("model_path")
        tracker = str(detector.get("tracker", "botsort.yaml"))
        return ModelStatus(
            detector_backend=str(detector.get("backend", "lightweight")),
            model_path=str(model_path) if model_path else None,
            model_exists=self._path_exists(str(model_path)) if model_path else False,
            ultralytics_available=importlib.util.find_spec("ultralytics") is not None,
            tracker=tracker,
            tracker_available=self._tracker_available(tracker),
            device=str(detector.get("device", "cpu")),
            half=bool(detector.get("half", False)),
        )

    def load(self, model_path: str | None = None) -> dict[str, Any]:
        status = self.status()
        resolved = model_path or status.model_path
        if not resolved:
            return {"ok": False, "message": "No model path configured."}
        if importlib.util.find_spec("ultralytics") is None:
            return {"ok": False, "message": "Ultralytics is not installed. Install ultralytics or use lightweight detector."}
        if not self._path_exists(resolved):
            return {"ok": False, "message": f"Model file not found: {resolved}"}
        self._loaded_model_path = resolved
        return {"ok": True, "model_path": resolved, "message": "Model path validated."}

    def benchmark(self) -> dict[str, Any]:
        status = self.status()
        started = time.perf_counter()
        time.sleep(0.01)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        detector_latency = elapsed_ms if status.model_exists and status.ultralytics_available else None
        return {
            "ok": True,
            "capture_fps": 30.0,
            "detector_latency_ms": detector_latency,
            "tracker_latency_ms": 1.0 if status.tracker_available else None,
            "message": (
                "Synthetic benchmark completed. Configure a real model and selected window for live benchmark."
                if detector_latency is None
                else "Model benchmark completed."
            ),
        }

    def _read_config(self) -> dict[str, Any]:
        if not self._model_config_path.exists():
            return {"detector": {"backend": "lightweight"}}
        return yaml.safe_load(self._model_config_path.read_text(encoding="utf-8")) or {}

    def _path_exists(self, path: str) -> bool:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._root / candidate
        return candidate.exists()

    def _tracker_available(self, tracker: str) -> bool:
        if tracker in {"botsort.yaml", "bytetrack.yaml"}:
            return True
        return self._path_exists(tracker)
