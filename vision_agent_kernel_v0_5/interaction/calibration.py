from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from interaction.ui_anchor import (
    AnchorResolution,
    CalibrationProfile,
    UIAnchor,
    UIAnchorResolver,
    UIElement,
)


@dataclass(frozen=True, slots=True)
class CalibrationIssue:
    anchor_id: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    capsule_id: str
    profile_id: str
    ready: bool
    resolutions: list[AnchorResolution] = field(default_factory=list)
    issues: list[CalibrationIssue] = field(default_factory=list)


class CalibrationWizard:
    """Non-UI calibration workflow core for GUI/CLI wrappers.

    It validates declared anchors against currently detected UI elements and
    returns a decision-ready report. The frontend can render the report and ask
    the user to accept or adjust anchors.
    """

    def __init__(self, resolver: UIAnchorResolver | None = None) -> None:
        self._resolver = resolver or UIAnchorResolver()

    def build_profile(
        self,
        capsule_id: str,
        profile_id: str,
        viewport: tuple[int, int],
        anchors: Iterable[UIAnchor],
        metadata: dict[str, object] | None = None,
    ) -> CalibrationProfile:
        return CalibrationProfile(
            capsule_id=capsule_id,
            profile_id=profile_id,
            viewport=viewport,
            anchors={anchor.anchor_id: anchor for anchor in anchors},
            metadata=metadata or {},
        )

    def validate(
        self,
        profile: CalibrationProfile,
        elements: Iterable[UIElement],
        screen_state_by_anchor: dict[str, str] | None = None,
        min_ready_confidence: float = 0.75,
    ) -> CalibrationReport:
        resolutions: list[AnchorResolution] = []
        issues: list[CalibrationIssue] = []
        for anchor in profile.anchors.values():
            screen_state = (screen_state_by_anchor or {}).get(anchor.anchor_id, anchor.screen_state)
            resolution = self._resolver.resolve(anchor, elements, profile.viewport, screen_state=screen_state)
            resolutions.append(resolution)
            if not resolution.ok and resolution.requires_confirmation and resolution.confidence > 0.0:
                issues.append(
                    CalibrationIssue(
                        anchor_id=anchor.anchor_id,
                        code="low_confidence",
                        message=f"{anchor.anchor_id} confidence {resolution.confidence:.2f} requires confirmation",
                    )
                )
            elif not resolution.ok:
                issues.append(
                    CalibrationIssue(
                        anchor_id=anchor.anchor_id,
                        code=resolution.reason,
                        message=f"{anchor.anchor_id} is not ready: {resolution.reason}",
                    )
                )
            elif resolution.confidence < min_ready_confidence:
                issues.append(
                    CalibrationIssue(
                        anchor_id=anchor.anchor_id,
                        code="low_confidence",
                        message=f"{anchor.anchor_id} confidence {resolution.confidence:.2f} is below ready threshold",
                    )
                )
        return CalibrationReport(
            capsule_id=profile.capsule_id,
            profile_id=profile.profile_id,
            ready=not issues,
            resolutions=resolutions,
            issues=issues,
        )
