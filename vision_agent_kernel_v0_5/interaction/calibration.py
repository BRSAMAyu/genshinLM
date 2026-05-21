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


@dataclass(frozen=True, slots=True)
class ProfilePreflightReport:
    capsule_id: str
    profile_id: str
    ready_for_unattended: bool
    ready_for_supervised: bool
    checklist: dict[str, bool]
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

    def preflight(
        self,
        profile: CalibrationProfile,
        elements: Iterable[UIElement],
        *,
        required_anchors: Iterable[str],
        required_metadata: Iterable[str] = ("language", "window_mode", "scale", "capsule_version"),
        screen_state_by_anchor: dict[str, str] | None = None,
    ) -> ProfilePreflightReport:
        validation = self.validate(profile, elements, screen_state_by_anchor=screen_state_by_anchor)
        required_anchor_set = set(required_anchors)
        missing_anchor_defs = sorted(anchor_id for anchor_id in required_anchor_set if anchor_id not in profile.anchors)
        metadata_keys = set(profile.metadata.keys())
        missing_metadata = sorted(key for key in required_metadata if key not in metadata_keys)
        issues = list(validation.issues)
        issues.extend(
            CalibrationIssue(anchor_id=anchor_id, code="missing_anchor_definition", message=f"{anchor_id} is not declared in profile")
            for anchor_id in missing_anchor_defs
        )
        issues.extend(
            CalibrationIssue(anchor_id="profile", code="missing_profile_metadata", message=f"missing metadata: {key}")
            for key in missing_metadata
        )
        checklist = {
            "viewport_recorded": bool(profile.viewport[0] > 0 and profile.viewport[1] > 0),
            "required_anchors_declared": not missing_anchor_defs,
            "required_metadata_present": not missing_metadata,
            "anchors_validated": validation.ready,
            "normalized_coordinates": all(
                0.0 <= anchor.candidate_roi.x <= 1.0
                and 0.0 <= anchor.candidate_roi.y <= 1.0
                and 0.0 < anchor.candidate_roi.w <= 1.0
                and 0.0 < anchor.candidate_roi.h <= 1.0
                for anchor in profile.anchors.values()
            ),
        }
        ready_for_supervised = checklist["viewport_recorded"] and checklist["required_anchors_declared"] and checklist["normalized_coordinates"]
        ready_for_unattended = ready_for_supervised and checklist["required_metadata_present"] and checklist["anchors_validated"]
        return ProfilePreflightReport(
            capsule_id=profile.capsule_id,
            profile_id=profile.profile_id,
            ready_for_unattended=ready_for_unattended,
            ready_for_supervised=ready_for_supervised,
            checklist=checklist,
            issues=issues,
        )
