"""Computer Use controller — VLM-guided UI automation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

if TYPE_CHECKING:
    from llm.vision_provider import ImageInput, UIGroundingResult
    from execution.input_backend_base import InputBackendBase

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GroundingTarget:
    screen_x: int
    screen_y: int
    confidence: float


class ComputerUseController:
    """Act like a human using mouse: look at the screen, find the target, click it."""

    def __init__(
        self,
        backend: InputBackendBase,
        vlm_provider: object,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> None:
        self._backend = backend
        self._vlm = vlm_provider
        self._screen_w = screen_width
        self._screen_h = screen_height

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_target(
        self,
        frame: np.ndarray,
        query: str,
    ) -> tuple[int, int, float] | None:
        """Find UI element matching `query` in the given frame.

        Returns (screen_x, screen_y, confidence) of the highest-confidence
        candidate, or None if no candidates are returned.
        """
        image = _frame_to_image_input(frame)
        result = self._vlm.ground_ui(image, query)
        target = _best_candidate(result, self._screen_w, self._screen_h)
        return target

    def move_to_target(
        self,
        frame: np.ndarray,
        query: str,
        reason: str = "",
    ) -> bool:
        """Move mouse cursor to the target found by `find_target`.

        Returns True on success, False if no candidate found or if
        mouse_move_to raises an exception.
        """
        found = self.find_target(frame, query)
        if found is None:
            return False
        screen_x, screen_y, _ = found
        try:
            self._backend.mouse_move_to(screen_x, screen_y, reason)
            return True
        except Exception as exc:
            log.warning("move_to_target failed: %s", exc)
            return False

    def click_target(
        self,
        frame: np.ndarray,
        query: str,
        reason: str = "",
    ) -> bool:
        """Move to and click the target found by `find_target`.

        Returns True on success, False if any step fails.
        """
        if not self.move_to_target(frame, query, reason):
            return False
        try:
            self._backend.left_click(reason)
            return True
        except Exception as exc:
            log.warning("click_target failed: %s", exc)
            return False

    def interact_with_query(
        self,
        frame: np.ndarray,
        query: str,
        reason: str = "",
        action: Literal["click", "hover"] = "click",
    ) -> bool:
        """Click (or hover) target with a 0.3 s settle delay after moving the cursor.

        Returns True if the action succeeded, False otherwise.
        """
        if not self.move_to_target(frame, query, reason):
            return False
        time.sleep(0.3)
        if action == "click":
            try:
                self._backend.left_click(reason)
                return True
            except Exception as exc:
                log.warning("interact_with_query click failed: %s", exc)
                return False
        # hover — cursor moved, no click
        return True

    def execute_until_success(
        self,
        frame: np.ndarray,
        query: str,
        action: Literal["click", "hover"] = "click",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> bool:
        """Retry `interact_with_query` up to `max_retries` times.

        Uses the same frame on every attempt (caller may re-grab between
        calls if needed).  Action ``hover`` only moves the cursor without
        clicking.

        Returns True if any attempt succeeds.
        """
        for _ in range(max_retries):
            ok = self.interact_with_query(
                frame, query,
                reason=f"execute_until_success({action})",
                action=action,
            )
            if ok:
                return True
            time.sleep(retry_delay)
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ground_ui(self, image: ImageInput, query: str) -> UIGroundingResult:
        return self._vlm.ground_ui(image, query)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _frame_to_image_input(frame: np.ndarray) -> ImageInput:
    """Convert a numpy frame (HWC, BGR or RGB uint8) to an ImageInput."""
    from llm.vision_provider import ImageInput as II

    if frame.dtype != np.uint8:
        frame = frame.astype(np.uint8)

    # Encode as PNG so mime_type is always consistent.
    import cv2

    if frame.ndim == 3 and frame.shape[2] == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)

    encoded = cv2.imencode(".png", frame)
    if not encoded:
        raise RuntimeError("cv2.imencode failed")
    return II(data=bytes(encoded[1]), mime_type="image/png")


def _best_candidate(
    result: UIGroundingResult,
    screen_w: int | None,
    screen_h: int | None,
) -> tuple[int, int, float] | None:
    """Return the screen-pixel centre of the highest-confidence candidate."""
    candidates = result.candidates
    if not candidates:
        return None

    # Pick highest-confidence entry.
    best: dict[str, object] | None = None
    best_conf = -1.0
    for c in candidates:
        conf = float(c.get("confidence", 0.0))
        if conf > best_conf:
            best_conf = conf
            best = c

    if best is None:
        return None

    raw_bbox = best.get("bbox_norm")
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None

    bbox = tuple(float(v) for v in raw_bbox)
    x, y, w, h = bbox

    sw = screen_w if screen_w is not None else 1920
    sh = screen_h if screen_h is not None else 1080

    # Centre of the bounding box in pixel coordinates.
    screen_x = int((x + w / 2) * sw)
    screen_y = int((y + h / 2) * sh)

    return (screen_x, screen_y, best_conf)