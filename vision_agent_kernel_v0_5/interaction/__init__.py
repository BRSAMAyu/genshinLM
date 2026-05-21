from __future__ import annotations

from interaction.ui_anchor import (
    AnchorResolution,
    CalibrationProfile,
    ClickResult,
    NormalizedRect,
    UIAnchor,
    UIAnchorMatcher,
    UIAnchorResolver,
    UIElement,
)
from interaction.capsule_anchors import anchors_from_manifest

__all__ = [
    "AnchorResolution",
    "CalibrationProfile",
    "ClickResult",
    "NormalizedRect",
    "UIAnchor",
    "UIAnchorMatcher",
    "UIAnchorResolver",
    "UIElement",
    "anchors_from_manifest",
]
