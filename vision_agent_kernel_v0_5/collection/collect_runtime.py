from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from collection.collectable_detector import CollectableDetector
from collection.collect_route_policy import CollectRoutePolicy
from collection.collect_verifier import CollectVerifier
from collection.interaction_prompt_detector import InteractionPromptDetector


@dataclass(frozen=True, slots=True)
class CollectRuntimeResult:
    status: str
    action: str
    verifier_ok: bool
    reason: str
    alignment_error_px: tuple[float, float] = (0.0, 0.0)


class CollectRuntime:
    def __init__(self) -> None:
        self._detector = CollectableDetector()
        self._prompt = InteractionPromptDetector()
        self._policy = CollectRoutePolicy()
        self._verifier = CollectVerifier()

    def tick(self, frame: np.ndarray, ocr_text: str = "", state: dict | None = None) -> CollectRuntimeResult:
        state = state or {}
        target = self._policy.choose_next(self._detector.detect(frame))
        if target is None:
            return CollectRuntimeResult("SEARCH", "rotate_search_small_angle", False, "collectable not visible")
        h, w = frame.shape[:2]
        alignment_error = (target.center[0] - w / 2.0, target.center[1] - h / 2.0)
        if abs(alignment_error[0]) > w * 0.08 or abs(alignment_error[1]) > h * 0.08:
            return CollectRuntimeResult("ALIGN", "align_interaction_prompt", False, "collectable not centered", alignment_error)
        prompt = self._prompt.detect(ocr_text, visual_hint=bool(state.get("interaction_prompt_visible", False)))
        if not prompt["visible"]:
            return CollectRuntimeResult("APPROACH", "approach_collectable", False, "prompt not visible", alignment_error)
        verified = self._verifier.verify(state)
        if verified.ok:
            return CollectRuntimeResult("SUCCESS", "next_collectable", True, verified.reason, alignment_error)
        return CollectRuntimeResult("INTERACT", "press_interact", False, "waiting for item disappearance or gain popup", alignment_error)
