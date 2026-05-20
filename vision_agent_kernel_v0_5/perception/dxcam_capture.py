from __future__ import annotations

import threading
from typing import Any

import numpy as np

from core.timebase import Timebase
from perception.capture_base import CaptureConfig, FramePacket


class DxcamCaptureError(RuntimeError):
    pass


class DxcamCapturer:
    def __init__(
        self,
        config: CaptureConfig | None = None,
        timebase: Timebase | None = None,
        camera: Any | None = None,
    ) -> None:
        self._config = config or CaptureConfig()
        self._timebase = timebase or Timebase()
        self._camera = camera
        self._lock = threading.RLock()
        self._frame_id = 0
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if self._camera is None:
                try:
                    import dxcam  # type: ignore[import-not-found]
                except ImportError as exc:
                    raise DxcamCaptureError("dxcam is not installed") from exc
                self._camera = dxcam.create(output_color=self._config.output_color)
            self._camera.start(
                region=self._config.region,
                target_fps=int(self._config.target_fps),
            )
            self._started = True
            print(
                "[DxcamCapturer] "
                f"started target_fps={self._config.target_fps} "
                f"output_color={self._config.output_color}",
                flush=True,
            )

    def get_latest_frame(self) -> FramePacket | None:
        with self._lock:
            if not self._started or self._camera is None:
                raise DxcamCaptureError("capturer is not started")
            image = self._camera.get_latest_frame()
            if image is None:
                return None
            if not isinstance(image, np.ndarray):
                image = np.asarray(image)
            self._frame_id += 1
            height, width = image.shape[:2]
            return FramePacket(
                frame_id=self._frame_id,
                timestamp=self._timebase.now(),
                image=image,
                source_size=(width, height),
                color_format=self._config.output_color,
            )

    def stop(self) -> None:
        with self._lock:
            if not self._started or self._camera is None:
                return
            self._camera.stop()
            self._started = False
            print("[DxcamCapturer] stopped", flush=True)
