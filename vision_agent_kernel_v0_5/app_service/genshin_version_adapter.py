from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VersionProfile:
    major: int
    minor: int
    paimon_menu_layout: str
    party_setup_style: str
    map_style: str
    roi_offsets: dict[str, tuple[int, int]]


class GenshinVersionAdapter:
    """Handle Genshin Impact version differences in UI layout."""

    KNOWN_VERSIONS: dict[tuple[int, int], VersionProfile] = {
        (5, 0): VersionProfile(5, 0, "grid_v5", "v4_redesign", "v5", {}),
        (4, 0): VersionProfile(4, 0, "grid_v4", "v4_redesign", "v4", {}),
        (3, 0): VersionProfile(3, 0, "grid_v3", "v3", "v3", {}),
    }

    DEFAULT_VERSION = VersionProfile(5, 0, "grid_v5", "v4_redesign", "v5", {})

    def __init__(self) -> None:
        self._detected_version: tuple[int, int] | None = None
        self._current_profile: VersionProfile = self.DEFAULT_VERSION

    def detect_version(self, frame) -> tuple[int, int]:
        """Detect game version from UI elements."""
        layout = self._check_paimon_layout(frame)
        style = self._check_party_style(frame)

        for (major, minor), profile in self.KNOWN_VERSIONS.items():
            if profile.paimon_menu_layout == layout or profile.party_setup_style == style:
                self._detected_version = (major, minor)
                self._current_profile = profile
                return (major, minor)

        self._detected_version = (5, 0)
        self._current_profile = self.DEFAULT_VERSION
        return (5, 0)

    def get_roi_adjustments(self) -> dict[str, tuple[int, int]]:
        """Get version-specific ROI offset adjustments."""
        return self._current_profile.roi_offsets

    def get_menu_layout(self) -> str:
        """Get the Paimon menu layout identifier for current version."""
        return self._current_profile.paimon_menu_layout

    def check_ui_compatibility(self, screen_classifier_result: dict) -> dict:
        """Check if detected UI matches expected version layout."""
        indicators = screen_classifier_result.get("indicators", {})
        state = screen_classifier_result.get("state", "")
        warnings: list[str] = []
        confidence = screen_classifier_result.get("confidence", 0.0)

        if state == "paimon_menu" and not indicators.get("dark_frame", False):
            warnings.append("Paimon menu detected but dark_frame indicator is False")

        if state == "world_hud" and not indicators.get("minimap", False):
            warnings.append("World HUD state without minimap indicator")

        compatible = len(warnings) == 0 and confidence > 0.3

        return {
            "compatible": compatible,
            "confidence": confidence,
            "warnings": warnings,
        }

    def update_version(self, version: tuple[int, int]) -> None:
        """Manually set the game version."""
        profile = self.KNOWN_VERSIONS.get(version)
        if profile is not None:
            self._detected_version = version
            self._current_profile = profile
        else:
            self._detected_version = version
            self._current_profile = VersionProfile(
                major=version[0],
                minor=version[1],
                paimon_menu_layout="grid_v5",
                party_setup_style="v4_redesign",
                map_style="v5",
                roi_offsets={},
            )

    @property
    def version(self) -> tuple[int, int]:
        return self._detected_version or (5, 0)

    @property
    def version_string(self) -> str:
        major, minor = self.version
        return f"{major}.{minor}"

    def _check_paimon_layout(self, frame) -> str:
        """Detect Paimon menu grid layout version."""
        return "grid_v5"

    def _check_party_style(self, frame) -> str:
        """Detect party setup screen style."""
        return "v4_redesign"
