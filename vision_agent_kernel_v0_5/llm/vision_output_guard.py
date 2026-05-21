from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_BLOCKED_TERMS = (
    "click",
    "press",
    "type",
    "execute",
    "powershell",
    "cmd",
    "driver",
    "inject",
    "memory",
    "点击",
    "按下",
    "输入",
    "执行",
    "注入",
    "内存",
)


@dataclass(frozen=True, slots=True)
class GuardedCandidate:
    candidate: dict[str, object]
    ok: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GuardedGrounding:
    accepted: list[dict[str, object]]
    rejected: list[GuardedCandidate]


class VisionOutputGuard:
    """Validate VLM visual outputs before they can influence controllers.

    The VLM may propose UI elements, but it cannot issue physical-action
    instructions. This guard accepts bounded geometry and rejects action-like
    or prompt-injected content.
    """

    def __init__(self, min_confidence: float = 0.5, max_label_len: int = 80, max_reason_len: int = 240) -> None:
        self.min_confidence = min_confidence
        self.max_label_len = max_label_len
        self.max_reason_len = max_reason_len

    def validate_grounding_candidates(self, candidates: list[dict[str, object]]) -> GuardedGrounding:
        accepted: list[dict[str, object]] = []
        rejected: list[GuardedCandidate] = []
        for candidate in candidates:
            checked = self.validate_candidate(candidate)
            if checked.ok:
                accepted.append(checked.candidate)
            else:
                rejected.append(checked)
        return GuardedGrounding(accepted, rejected)

    def validate_candidate(self, candidate: dict[str, object]) -> GuardedCandidate:
        reasons: list[str] = []
        sanitized: dict[str, object] = {}
        label = str(candidate.get("label", ""))[: self.max_label_len]
        reason = str(candidate.get("reason", ""))[: self.max_reason_len]
        confidence = self._float(candidate.get("confidence", 0.0))
        bbox = candidate.get("bbox_norm")

        if not label:
            reasons.append("missing_label")
        if self._contains_action_directive(label) or self._contains_action_directive(reason):
            reasons.append("action_directive_in_text")
        if confidence < self.min_confidence or confidence > 1.0:
            reasons.append("confidence_out_of_range")
        bbox_ok, normalized_bbox = self._normalize_bbox(bbox)
        if not bbox_ok:
            reasons.append("invalid_bbox_norm")

        sanitized["label"] = label
        sanitized["bbox_norm"] = normalized_bbox
        sanitized["confidence"] = max(0.0, min(1.0, confidence))
        sanitized["reason"] = reason
        return GuardedCandidate(sanitized, not reasons, reasons)

    def validate_screen_state(self, screen_state: str, allowed: list[str], confidence: float) -> tuple[str, float, list[str]]:
        state = str(screen_state)
        conf = max(0.0, min(1.0, self._float(confidence)))
        errors: list[str] = []
        if state not in allowed:
            errors.append("screen_state_not_allowed")
            state = "unknown"
        if conf < self.min_confidence:
            errors.append("screen_state_low_confidence")
        return state, conf, errors

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_bbox(value: Any) -> tuple[bool, list[float]]:
        if not isinstance(value, list) or len(value) != 4:
            return False, [0.0, 0.0, 0.0, 0.0]
        try:
            x, y, w, h = [float(item) for item in value]
        except (TypeError, ValueError):
            return False, [0.0, 0.0, 0.0, 0.0]
        if x < 0.0 or y < 0.0 or w <= 0.0 or h <= 0.0 or x + w > 1.0 or y + h > 1.0:
            return False, [x, y, w, h]
        return True, [x, y, w, h]

    @staticmethod
    def _contains_action_directive(text: str) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in _BLOCKED_TERMS)
