"""Content versioning system: detect, classify, and adapt to game version changes.

Implements the version change detection from GENSHIN_CONTENT_VERSIONING.md:
- 4 change types: UI, mechanic, content, system
- 3 compatibility states: green (fully compatible), yellow (partial), red (incompatible)
- Auto-calibration via health checks
- Version-specific configuration registry
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


class ChangeType(str, Enum):
    UI = "ui"
    MECHANIC = "mechanic"
    CONTENT = "content"
    SYSTEM = "system"


class CompatibilityState(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass(frozen=True, slots=True)
class VersionChange:
    """A detected version change."""
    change_type: ChangeType
    description: str
    affected_capabilities: tuple[str, ...] = ()
    severity: str = "low"  # low, medium, high, critical
    detected_at: float = 0.0


@dataclass(frozen=True, slots=True)
class GameVersion:
    """Represents a game version like '5.7'."""
    major: int
    minor: int

    @staticmethod
    def parse(version_str: str) -> GameVersion:
        parts = version_str.strip().split(".")
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        return GameVersion(major=major, minor=minor)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"

    def __lt__(self, other: GameVersion) -> bool:
        return (self.major, self.minor) < (other.major, other.minor)

    def __le__(self, other: GameVersion) -> bool:
        return (self.major, self.minor) <= (other.major, other.minor)


@dataclass(slots=True)
class VersionChangeRecord:
    """Record of a detected and potentially resolved version change."""
    change: VersionChange
    resolved: bool = False
    resolution: str = ""
    detected_at: float = 0.0


@dataclass(slots=True)
class VersionConfig:
    """Version-specific configuration entry."""
    version: GameVersion
    ui_element_offsets: dict[str, tuple[int, int]] = field(default_factory=dict)
    elemental_reactions: dict[str, dict[str, str]] = field(default_factory=dict)
    regions: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)


class ContentVersionManager:
    """Detect game version changes and manage version-specific configurations.

    Tracks:
    - Current game version
    - Detected changes from previous version
    - Compatibility state per change type
    - Version-specific configurations

    Usage::

        mgr = ContentVersionManager(current_version="5.7")
        mgr.check_ui_change("button_moved", ["menu_navigation"])
        state = mgr.compatibility_state
        if state == CompatibilityState.RED:
            log.error("Incompatible version — halt operations")
    """

    _KNOWN_VERSIONS: tuple[str, ...] = (
        "3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8",
        "4.0", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8",
        "5.0", "5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7",
    )

    def __init__(self, current_version: str = "5.7") -> None:
        self._current = GameVersion.parse(current_version)
        self._config = VersionConfig(version=self._current)
        self._changes: list[VersionChangeRecord] = []
        self._health_check_interval: float = 1800.0  # 30 min
        self._last_health_check: float = time.perf_counter()

    @property
    def current_version(self) -> GameVersion:
        return self._current

    @property
    def compatibility_state(self) -> CompatibilityState:
        unresolved = [r for r in self._changes if not r.resolved]
        if not unresolved:
            return CompatibilityState.GREEN
        critical = [r for r in unresolved if r.change.severity == "critical"]
        if critical:
            return CompatibilityState.RED
        high = [r for r in unresolved if r.change.severity == "high"]
        if len(high) >= 2:
            return CompatibilityState.RED
        if high:
            return CompatibilityState.YELLOW
        return CompatibilityState.YELLOW

    def check_ui_change(
        self, description: str, affected: tuple[str, ...] = (), severity: str = "medium",
    ) -> VersionChange:
        change = VersionChange(
            change_type=ChangeType.UI,
            description=description,
            affected_capabilities=affected,
            severity=severity,
            detected_at=time.perf_counter(),
        )
        self._changes.append(VersionChangeRecord(change=change, detected_at=change.detected_at))
        log.info("[Versioning] UI change detected: %s (severity=%s)", description, severity)
        return change

    def check_mechanic_change(
        self, description: str, affected: tuple[str, ...] = (), severity: str = "high",
    ) -> VersionChange:
        change = VersionChange(
            change_type=ChangeType.MECHANIC,
            description=description,
            affected_capabilities=affected,
            severity=severity,
            detected_at=time.perf_counter(),
        )
        self._changes.append(VersionChangeRecord(change=change, detected_at=change.detected_at))
        log.warning("[Versioning] Mechanic change: %s (severity=%s)", description, severity)
        return change

    def check_content_change(
        self, description: str, affected: tuple[str, ...] = (),
    ) -> VersionChange:
        change = VersionChange(
            change_type=ChangeType.CONTENT,
            description=description,
            affected_capabilities=affected,
            severity="low",
            detected_at=time.perf_counter(),
        )
        self._changes.append(VersionChangeRecord(change=change, detected_at=change.detected_at))
        return change

    def resolve_change(self, description: str, resolution: str = "auto_calibrated") -> bool:
        for record in self._changes:
            if record.change.description == description and not record.resolved:
                record.resolved = True
                record.resolution = resolution
                log.info("[Versioning] resolved: %s (%s)", description, resolution)
                return True
        return False

    def health_check_needed(self) -> bool:
        return time.perf_counter() - self._last_health_check > self._health_check_interval

    def record_health_check(self) -> None:
        self._last_health_check = time.perf_counter()

    @property
    def pending_changes(self) -> list[VersionChange]:
        return [r.change for r in self._changes if not r.resolved]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_changes": len(self._changes),
            "resolved": sum(1 for r in self._changes if r.resolved),
            "pending": sum(1 for r in self._changes if not r.resolved),
        }
