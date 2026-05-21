from __future__ import annotations

from typing import Any

from capsules.capsule_protocol import CapsuleManifest
from interaction.ui_anchor import NormalizedRect, UIAnchor, UIAnchorMatcher


def anchors_from_manifest(manifest: CapsuleManifest) -> list[UIAnchor]:
    return [_anchor_from_dict(item) for item in manifest.ui_anchors]


def _anchor_from_dict(item: dict[str, Any]) -> UIAnchor:
    return UIAnchor(
        anchor_id=str(item["anchor_id"]),
        screen_state=str(item.get("screen_state", "")),
        semantic_role=str(item.get("semantic_role", "")),
        candidate_roi=_rect(item.get("candidate_roi", [0.0, 0.0, 1.0, 1.0])),
        resolution_policy=str(item.get("resolution_policy", "allow_fallback")),
        matchers=[_matcher(matcher) for matcher in item.get("matchers", [])],
        click_policy=dict(item.get("click_policy", {})),
        post_action_verifier=str(item.get("post_action_verifier", "")),
        fallback_policy=dict(item.get("fallback_policy", {})),
        requires_confirmation_below=float(item.get("requires_confirmation_below", 0.75)),
    )


def _matcher(item: dict[str, Any]) -> UIAnchorMatcher:
    return UIAnchorMatcher(
        kind=str(item["kind"]),
        value=str(item.get("value", "")),
        weight=float(item.get("weight", 1.0)),
        roi=_rect(item["roi"]) if "roi" in item else None,
        min_confidence=float(item.get("min_confidence", 0.5)),
    )


def _rect(value: list[float] | tuple[float, float, float, float]) -> NormalizedRect:
    x, y, w, h = value
    return NormalizedRect(float(x), float(y), float(w), float(h)).clamp()
