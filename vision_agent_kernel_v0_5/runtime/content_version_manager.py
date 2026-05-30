"""Content versioning system: game version tracking, change classification, compatibility matrix.

Implements the content versioning layer from GENSHIN_CONTENT_VERSIONING.md:
- 4 change types: UI, Mechanism, Content, System
- Version registry with known game versions and their adaptation status
- Change detection: startup version check, runtime anomaly detection
- Compatibility matrix for agent capabilities across versions
- Auto-recalibration trigger system
"""
from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


class ChangeType(enum.Enum):
    UI = "ui"                 # Button positions, icon styles, menu layouts
    MECHANISM = "mechanism"   # Element reactions, combat mechanics, new systems
    CONTENT = "content"       # New regions, characters, quests, bosses
    SYSTEM = "system"         # Performance, anti-cheat, protocol changes


class AdaptationStatus(enum.Enum):
    UNKNOWN = "unknown"       # Version not seen before
    UNVERIFIED = "unverified" # Known but not tested
    PARTIAL = "partial"       # Some capabilities adapted
    VERIFIED = "verified"     # All capabilities verified
    DEPRECATED = "deprecated" # Old version, no longer supported


class HealthGrade(enum.Enum):
    HEALTHY = "healthy"       # Score >= 80
    DEGRADED = "degraded"     # Score 50-79
    CRITICAL = "critical"     # Score < 50


# ---------------------------------------------------------------------------
# Version descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GameVersion:
    major: int
    minor: int
    patch: int = 0

    def __str__(self) -> str:
        if self.patch:
            return f"{self.major}.{self.minor}.{self.patch}"
        return f"{self.major}.{self.minor}"

    @classmethod
    def parse(cls, version_str: str) -> GameVersion:
        parts = version_str.strip().split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return cls(major=major, minor=minor, patch=patch)

    def __lt__(self, other: GameVersion) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: GameVersion) -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

    def __gt__(self, other: GameVersion) -> bool:
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other: GameVersion) -> bool:
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)


# ---------------------------------------------------------------------------
# Change record
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class VersionChange:
    change_id: str
    change_type: ChangeType
    game_version: GameVersion
    description: str = ""
    affected_capabilities: tuple[str, ...] = ()
    detection_source: str = ""  # "startup_check", "runtime_anomaly", "user_report", "external"
    severity: str = "medium"    # "low", "medium", "high", "critical"
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.perf_counter())


# ---------------------------------------------------------------------------
# Capability compatibility entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    capability: str
    version: GameVersion
    status: AdaptationStatus
    confidence: float = 1.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Health check result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    ui_visibility: int = 100       # Can core menus be opened
    detector_confidence: int = 100 # YOLO/OCR average confidence
    input_response: int = 100      # Input produces expected effects
    capture_health: int = 100      # Screen capture working
    clock_sync: int = 100          # Game time sync

    @property
    def average_score(self) -> float:
        return (self.ui_visibility + self.detector_confidence +
                self.input_response + self.capture_health + self.clock_sync) / 5.0

    @property
    def grade(self) -> HealthGrade:
        avg = self.average_score
        if avg >= 80:
            return HealthGrade.HEALTHY
        if avg >= 50:
            return HealthGrade.DEGRADED
        return HealthGrade.CRITICAL

    @property
    def failed_checks(self) -> list[str]:
        failed = []
        if self.ui_visibility < 70:
            failed.append("ui_visibility")
        if self.detector_confidence < 70:
            failed.append("detector_confidence")
        if self.input_response < 70:
            failed.append("input_response")
        if self.capture_health < 70:
            failed.append("capture_health")
        if self.clock_sync < 70:
            failed.append("clock_sync")
        return failed


# ---------------------------------------------------------------------------
# Known game versions (up to 5.7 as of 2026-05)
# ---------------------------------------------------------------------------

_KNOWN_VERSIONS: dict[str, AdaptationStatus] = {
    "1.0": AdaptationStatus.DEPRECATED,
    "2.0": AdaptationStatus.DEPRECATED,
    "3.0": AdaptationStatus.DEPRECATED,
    "4.0": AdaptationStatus.PARTIAL,
    "4.4": AdaptationStatus.PARTIAL,
    "5.0": AdaptationStatus.VERIFIED,
    "5.1": AdaptationStatus.VERIFIED,
    "5.2": AdaptationStatus.VERIFIED,
    "5.3": AdaptationStatus.VERIFIED,
    "5.4": AdaptationStatus.VERIFIED,
    "5.5": AdaptationStatus.VERIFIED,
    "5.6": AdaptationStatus.UNVERIFIED,
    "5.7": AdaptationStatus.UNVERIFIED,
}


# ---------------------------------------------------------------------------
# Version manager
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ContentVersionManager:
    """Track game version, detect changes, manage compatibility.

    Usage::

        mgr = ContentVersionManager()
        mgr.set_current_version("5.7")
        status = mgr.check_version_status()
        if status == AdaptationStatus.UNKNOWN:
            mgr.trigger_recalibration()
    """

    current_version: GameVersion | None = None
    last_known_version: GameVersion | None = None
    version_registry: dict[str, AdaptationStatus] = field(default_factory=lambda: dict(_KNOWN_VERSIONS))
    change_log: list[VersionChange] = field(default_factory=list)
    health_history: list[HealthCheckResult] = field(default_factory=list)
    failure_rate_window: dict[str, list[bool]] = field(default_factory=dict)
    failure_window_size: int = 20
    failure_threshold: float = 0.3
    _recalibration_needed: bool = False

    # ------------------------------------------------------------------
    # Version management
    # ------------------------------------------------------------------

    def set_current_version(self, version_str: str) -> AdaptationStatus:
        """Set current game version and return adaptation status."""
        self.last_known_version = self.current_version
        self.current_version = GameVersion.parse(version_str)
        status = self.get_adaptation_status(self.current_version)

        if self.last_known_version is not None and self.current_version != self.last_known_version:
            log.info("[ContentVersion] version changed: %s → %s", self.last_known_version, self.current_version)
            self._record_version_change()

        return status

    def get_adaptation_status(self, version: GameVersion | None = None) -> AdaptationStatus:
        if version is None:
            version = self.current_version
        if version is None:
            return AdaptationStatus.UNKNOWN
        key = str(version)
        if key in self.version_registry:
            return self.version_registry[key]
        # Check if any minor version of this major is known
        for v_key, status in self.version_registry.items():
            v = GameVersion.parse(v_key)
            if v.major == version.major and v.minor == version.minor:
                return AdaptationStatus.UNVERIFIED
        return AdaptationStatus.UNKNOWN

    def mark_version_verified(self, version: GameVersion | None = None) -> None:
        if version is None:
            version = self.current_version
        if version is not None:
            self.version_registry[str(version)] = AdaptationStatus.VERIFIED

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    def report_operation_result(self, operation: str, success: bool) -> None:
        """Report an operation result for runtime anomaly detection."""
        if operation not in self.failure_rate_window:
            self.failure_rate_window[operation] = []
        window = self.failure_rate_window[operation]
        window.append(success)
        if len(window) > self.failure_window_size:
            window.pop(0)

        if len(window) >= 5:
            failure_rate = 1.0 - sum(window) / len(window)
            if failure_rate > self.failure_threshold:
                self._record_runtime_anomaly(operation, failure_rate)

    def get_failure_rate(self, operation: str) -> float:
        window = self.failure_rate_window.get(operation, [])
        if not window:
            return 0.0
        return 1.0 - sum(window) / len(window)

    def run_health_check(self, **scores: int) -> HealthCheckResult:
        """Run a health check with provided scores."""
        result = HealthCheckResult(
            ui_visibility=scores.get("ui_visibility", 100),
            detector_confidence=scores.get("detector_confidence", 100),
            input_response=scores.get("input_response", 100),
            capture_health=scores.get("capture_health", 100),
            clock_sync=scores.get("clock_sync", 100),
        )
        self.health_history.append(result)
        if result.grade != HealthGrade.HEALTHY:
            log.warning("[ContentVersion] health check: %s (%.0f) — %s",
                        result.grade.value, result.average_score, result.failed_checks)
        return result

    def _record_version_change(self) -> None:
        if self.current_version is None or self.last_known_version is None:
            return
        change = VersionChange(
            change_id=f"vc_{self.current_version}",
            change_type=ChangeType.CONTENT,
            game_version=self.current_version,
            description=f"version changed from {self.last_known_version} to {self.current_version}",
            detection_source="startup_check",
            severity="medium",
        )
        self.change_log.append(change)
        self._recalibration_needed = True

    def _record_runtime_anomaly(self, operation: str, failure_rate: float) -> None:
        if self.current_version is None:
            return
        change = VersionChange(
            change_id=f"anomaly_{operation}_{int(time.perf_counter())}",
            change_type=ChangeType.UI,
            game_version=self.current_version,
            description=f"operation '{operation}' failure rate {failure_rate:.0%} exceeds threshold",
            affected_capabilities=(operation,),
            detection_source="runtime_anomaly",
            severity="high" if failure_rate > 0.5 else "medium",
        )
        self.change_log.append(change)

    # ------------------------------------------------------------------
    # Recalibration
    # ------------------------------------------------------------------

    @property
    def needs_recalibration(self) -> bool:
        return self._recalibration_needed

    def trigger_recalibration(self) -> None:
        self._recalibration_needed = True

    def complete_recalibration(self) -> None:
        self._recalibration_needed = False
        if self.current_version is not None:
            self.version_registry[str(self.current_version)] = AdaptationStatus.VERIFIED

    # ------------------------------------------------------------------
    # Compatibility queries
    # ------------------------------------------------------------------

    def get_compatible_capabilities(self) -> list[str]:
        """Return capabilities that are verified for current version."""
        if self.current_version is None:
            return []
        status = self.get_adaptation_status()
        if status == AdaptationStatus.VERIFIED:
            return ["all"]
        if status == AdaptationStatus.PARTIAL:
            return ["navigation", "combat_basic", "daily_routine"]
        return []

    def is_capability_safe(self, capability: str) -> bool:
        compat = self.get_compatible_capabilities()
        if not compat:
            return False
        if "all" in compat:
            return True
        return capability in compat

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def status_summary(self) -> dict[str, Any]:
        return {
            "current_version": str(self.current_version) if self.current_version else "unknown",
            "adaptation_status": self.get_adaptation_status().value,
            "needs_recalibration": self._recalibration_needed,
            "changes_detected": len(self.change_log),
            "health_grade": self.health_history[-1].grade.value if self.health_history else "no_data",
        }
