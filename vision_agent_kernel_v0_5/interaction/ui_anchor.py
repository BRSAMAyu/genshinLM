from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal


MatcherKind = Literal["ocr", "template", "detector", "relative", "calibrated", "fallback_agent"]
ResolutionPolicy = Literal["strict", "allow_fallback", "requires_confirmation"]


@dataclass(frozen=True, slots=True)
class NormalizedRect:
    """A window-relative rectangle in [0, 1] coordinates."""

    x: float
    y: float
    w: float
    h: float

    def clamp(self) -> NormalizedRect:
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        w = min(max(self.w, 0.0), 1.0 - x)
        h = min(max(self.h, 0.0), 1.0 - y)
        return NormalizedRect(x, y, w, h)

    def center_norm(self) -> tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def center_px(self, viewport: tuple[int, int]) -> tuple[int, int]:
        cx, cy = self.center_norm()
        width, height = viewport
        return (round(cx * width), round(cy * height))

    @classmethod
    def from_px(cls, bbox: tuple[float, float, float, float], viewport: tuple[int, int]) -> NormalizedRect:
        width, height = viewport
        if width <= 0 or height <= 0:
            raise ValueError("viewport dimensions must be positive")
        x1, y1, x2, y2 = bbox
        return cls(x1 / width, y1 / height, max(0.0, x2 - x1) / width, max(0.0, y2 - y1) / height).clamp()

    def overlaps(self, other: NormalizedRect) -> bool:
        return not (
            self.x + self.w < other.x
            or other.x + other.w < self.x
            or self.y + self.h < other.y
            or other.y + other.h < self.y
        )


@dataclass(frozen=True, slots=True)
class UIElement:
    element_id: str
    role: str
    bbox: NormalizedRect
    confidence: float
    source: str
    text: str = ""
    icon_id: str = ""
    detector_class: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UIAnchorMatcher:
    kind: MatcherKind
    value: str = ""
    weight: float = 1.0
    roi: NormalizedRect | None = None
    min_confidence: float = 0.5


@dataclass(frozen=True, slots=True)
class UIAnchor:
    anchor_id: str
    screen_state: str
    semantic_role: str
    candidate_roi: NormalizedRect
    resolution_policy: ResolutionPolicy = "allow_fallback"
    matchers: list[UIAnchorMatcher] = field(default_factory=list)
    click_policy: dict[str, Any] = field(default_factory=dict)
    post_action_verifier: str = ""
    fallback_policy: dict[str, Any] = field(default_factory=dict)
    requires_confirmation_below: float = 0.75


@dataclass(frozen=True, slots=True)
class AnchorResolution:
    anchor_id: str
    ok: bool
    confidence: float
    click_point: tuple[int, int] | None
    bbox: NormalizedRect | None
    strategy: str
    reason: str
    candidates: list[UIElement] = field(default_factory=list)
    requires_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class ClickResult:
    anchor_id: str
    status: Literal["READY", "BLOCKED_LOW_CONFIDENCE", "BLOCKED_NOT_FOUND", "EXECUTED", "VERIFIER_FAILED"]
    resolution: AnchorResolution
    verifier_id: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    capsule_id: str
    profile_id: str
    viewport: tuple[int, int]
    anchors: dict[str, UIAnchor]
    version: str = "1"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), indent=2, ensure_ascii=False), encoding="utf-8")


class UIAnchorResolver:
    """Deterministic anchor resolver used before any fallback visual agent."""

    _ORDER: tuple[MatcherKind, ...] = ("ocr", "template", "detector", "relative", "calibrated", "fallback_agent")

    def resolve(
        self,
        anchor: UIAnchor,
        elements: Iterable[UIElement],
        viewport: tuple[int, int],
        screen_state: str | None = None,
    ) -> AnchorResolution:
        if screen_state and anchor.screen_state and screen_state != anchor.screen_state:
            return AnchorResolution(
                anchor_id=anchor.anchor_id,
                ok=False,
                confidence=0.0,
                click_point=None,
                bbox=None,
                strategy="screen_state",
                reason=f"screen_state_mismatch:{screen_state}!={anchor.screen_state}",
            )

        candidates = list(elements)
        best: tuple[float, UIElement, UIAnchorMatcher] | None = None
        for kind in self._ORDER:
            for matcher in [m for m in anchor.matchers if m.kind == kind]:
                for element in candidates:
                    score = self._score(anchor, matcher, element)
                    if score < matcher.min_confidence:
                        continue
                    if best is None or score > best[0]:
                        best = (score, element, matcher)
            if best is not None:
                break

        if best is None:
            return self._fallback(anchor, viewport)

        score, element, matcher = best
        requires_confirmation = score < anchor.requires_confirmation_below or anchor.resolution_policy == "requires_confirmation"
        return AnchorResolution(
            anchor_id=anchor.anchor_id,
            ok=not requires_confirmation,
            confidence=round(score, 4),
            click_point=element.bbox.center_px(viewport),
            bbox=element.bbox,
            strategy=matcher.kind,
            reason="matched",
            candidates=[element],
            requires_confirmation=requires_confirmation,
        )

    def _score(self, anchor: UIAnchor, matcher: UIAnchorMatcher, element: UIElement) -> float:
        if matcher.roi and not element.bbox.overlaps(matcher.roi):
            return 0.0
        if not element.bbox.overlaps(anchor.candidate_roi):
            return 0.0

        base = element.confidence * matcher.weight
        needle = matcher.value.lower().strip()
        if matcher.kind == "ocr":
            haystack = element.text.lower().strip()
            if not needle or needle not in haystack:
                return 0.0
            return min(1.0, base + 0.15)
        if matcher.kind == "template":
            return base if element.icon_id == matcher.value else 0.0
        if matcher.kind == "detector":
            return base if element.detector_class == matcher.value else 0.0
        if matcher.kind in {"relative", "calibrated"}:
            return base
        return 0.0

    def _fallback(self, anchor: UIAnchor, viewport: tuple[int, int]) -> AnchorResolution:
        calibrated = next((m for m in anchor.matchers if m.kind == "calibrated" and m.roi), None)
        if calibrated is not None and calibrated.roi is not None:
            bbox = calibrated.roi.clamp()
            confidence = min(1.0, max(0.0, calibrated.weight))
            requires_confirmation = confidence < anchor.requires_confirmation_below
            return AnchorResolution(
                anchor_id=anchor.anchor_id,
                ok=not requires_confirmation,
                confidence=confidence,
                click_point=bbox.center_px(viewport),
                bbox=bbox,
                strategy="calibrated",
                reason="calibrated_fallback",
                requires_confirmation=requires_confirmation,
            )
        if anchor.resolution_policy == "allow_fallback":
            bbox = anchor.candidate_roi.clamp()
            return AnchorResolution(
                anchor_id=anchor.anchor_id,
                ok=False,
                confidence=0.0,
                click_point=bbox.center_px(viewport),
                bbox=bbox,
                strategy="fallback_agent",
                reason="anchor_not_found_requires_fallback_agent",
                requires_confirmation=True,
            )
        return AnchorResolution(
            anchor_id=anchor.anchor_id,
            ok=False,
            confidence=0.0,
            click_point=None,
            bbox=None,
            strategy="none",
            reason="anchor_not_found",
        )


def distance_norm(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
