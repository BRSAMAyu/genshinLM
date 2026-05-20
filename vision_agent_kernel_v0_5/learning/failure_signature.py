from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class FailureSignature:
    failure_id: str
    node_type: str
    skill_id: str
    failure_code: str
    observation: dict[str, Any]
    context: dict[str, Any]
    suggested_patch: list[str] = field(default_factory=list)


class PrivacyMask:
    def mask(self, image: np.ndarray, allowed_roi: tuple[int, int, int, int], redacted_rois: list[tuple[int, int, int, int]] | None = None) -> np.ndarray:
        masked = np.zeros_like(image)
        x, y, w, h = allowed_roi
        masked[y : y + h, x : x + w] = image[y : y + h, x : x + w]
        for rx, ry, rw, rh in redacted_rois or []:
            masked[ry : ry + rh, rx : rx + rw] = 0
        return masked


class FailureSignatureBuilder:
    def build(self, node_type: str, skill_id: str, failure_code: str, observation: dict[str, Any], context: dict[str, Any]) -> FailureSignature:
        patches = []
        if observation.get("target_confidence_drop"):
            patches.append("increase_coasting_window")
            patches.append("add_reacquire_step")
        if observation.get("visual_pollution_high"):
            patches.append("tighten_roi_or_model_threshold")
        return FailureSignature(str(uuid.uuid4()), node_type, skill_id, failure_code, observation, context, patches)

