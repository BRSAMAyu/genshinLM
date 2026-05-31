"""Tests for runtime/content_versioning.py: version detection, compatibility states, health checks."""
from __future__ import annotations

import time

from runtime.content_versioning import (
    ChangeType,
    CompatibilityState,
    ContentVersionManager,
    GameVersion,
    VersionChange,
    VersionChangeRecord,
    VersionConfig,
)


# ---------------------------------------------------------------------------
# GameVersion
# ---------------------------------------------------------------------------

class TestGameVersion:
    def test_parse_standard(self):
        v = GameVersion.parse("5.7")
        assert v.major == 5
        assert v.minor == 7

    def test_parse_major_only(self):
        v = GameVersion.parse("5")
        assert v.major == 5
        assert v.minor == 0

    def test_parse_with_whitespace(self):
        v = GameVersion.parse("  4.8  ")
        assert v.major == 4
        assert v.minor == 8

    def test_str(self):
        v = GameVersion(major=5, minor=3)
        assert str(v) == "5.3"

    def test_lt(self):
        assert GameVersion(4, 8) < GameVersion(5, 0)
        assert GameVersion(5, 2) < GameVersion(5, 7)
        assert not (GameVersion(5, 7) < GameVersion(5, 2))

    def test_le(self):
        assert GameVersion(5, 0) <= GameVersion(5, 0)
        assert GameVersion(4, 9) <= GameVersion(5, 0)
        assert not (GameVersion(5, 1) <= GameVersion(5, 0))

    def test_frozen(self):
        v = GameVersion(major=5, minor=7)
        mutated = False
        try:
            v.major = 6  # type: ignore[misc]
        except AttributeError:
            mutated = True
        assert mutated


# ---------------------------------------------------------------------------
# VersionChange / VersionChangeRecord
# ---------------------------------------------------------------------------

class TestVersionChange:
    def test_defaults(self):
        vc = VersionChange(
            change_type=ChangeType.UI,
            description="button moved",
        )
        assert vc.severity == "low"
        assert vc.affected_capabilities == ()
        assert vc.change_type == ChangeType.UI

    def test_frozen(self):
        vc = VersionChange(change_type=ChangeType.MECHANIC, description="x")
        mutated = False
        try:
            vc.description = "y"  # type: ignore[misc]
        except AttributeError:
            mutated = True
        assert mutated


class TestVersionChangeRecord:
    def test_defaults(self):
        change = VersionChange(change_type=ChangeType.CONTENT, description="new region")
        rec = VersionChangeRecord(change=change)
        assert not rec.resolved
        assert rec.resolution == ""

    def test_resolve(self):
        change = VersionChange(change_type=ChangeType.UI, description="menu_shift")
        rec = VersionChangeRecord(change=change)
        rec.resolved = True
        rec.resolution = "auto_calibrated"
        assert rec.resolved
        assert rec.resolution == "auto_calibrated"


# ---------------------------------------------------------------------------
# VersionConfig
# ---------------------------------------------------------------------------

class TestVersionConfig:
    def test_defaults(self):
        vc = VersionConfig(version=GameVersion(5, 7))
        assert vc.ui_element_offsets == {}
        assert vc.elemental_reactions == {}
        assert vc.regions == []
        assert vc.characters == []

    def test_with_data(self):
        vc = VersionConfig(
            version=GameVersion(5, 7),
            ui_element_offsets={"menu_btn": (10, 20)},
            regions=["mondstadt", "liyue"],
            characters=["zhongli", "raiden"],
        )
        assert vc.ui_element_offsets["menu_btn"] == (10, 20)
        assert len(vc.regions) == 2
        assert len(vc.characters) == 2


# ---------------------------------------------------------------------------
# ContentVersionManager
# ---------------------------------------------------------------------------

class TestContentVersionManager:
    def test_default_version(self):
        mgr = ContentVersionManager()
        assert mgr.current_version == GameVersion(5, 7)

    def test_custom_version(self):
        mgr = ContentVersionManager("4.8")
        assert mgr.current_version == GameVersion(4, 8)

    def test_starts_green(self):
        mgr = ContentVersionManager()
        assert mgr.compatibility_state == CompatibilityState.GREEN
        assert mgr.pending_changes == []

    def test_check_ui_change(self):
        mgr = ContentVersionManager()
        change = mgr.check_ui_change("button moved", ("menu_nav",), "medium")
        assert change.change_type == ChangeType.UI
        assert change.description == "button moved"
        assert change.affected_capabilities == ("menu_nav",)
        assert change.severity == "medium"
        assert mgr.compatibility_state == CompatibilityState.YELLOW

    def test_check_mechanic_change(self):
        mgr = ContentVersionManager()
        change = mgr.check_mechanic_change("reaction rework", ("combat",))
        assert change.change_type == ChangeType.MECHANIC
        assert change.severity == "high"
        assert mgr.compatibility_state == CompatibilityState.YELLOW

    def test_check_content_change(self):
        mgr = ContentVersionManager()
        change = mgr.check_content_change("new region", ("exploration",))
        assert change.change_type == ChangeType.CONTENT
        assert change.severity == "low"
        assert mgr.compatibility_state == CompatibilityState.YELLOW

    def test_critical_change_goes_red(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("critical UI break", severity="critical")
        assert mgr.compatibility_state == CompatibilityState.RED

    def test_two_high_changes_goes_red(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("high issue 1", severity="high")
        assert mgr.compatibility_state == CompatibilityState.YELLOW
        mgr.check_mechanic_change("high issue 2")
        assert mgr.compatibility_state == CompatibilityState.RED

    def test_resolve_change(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("button moved", severity="medium")
        assert mgr.compatibility_state == CompatibilityState.YELLOW
        resolved = mgr.resolve_change("button moved")
        assert resolved is True
        assert mgr.compatibility_state == CompatibilityState.GREEN
        assert mgr.pending_changes == []

    def test_resolve_nonexistent(self):
        mgr = ContentVersionManager()
        assert mgr.resolve_change("nothing") is False

    def test_resolve_already_resolved(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("shift")
        assert mgr.resolve_change("shift") is True
        assert mgr.resolve_change("shift") is False

    def test_stats(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("a")
        mgr.check_ui_change("b")
        mgr.resolve_change("a")
        stats = mgr.stats
        assert stats["total_changes"] == 2
        assert stats["resolved"] == 1
        assert stats["pending"] == 1

    def test_pending_changes(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("p1")
        mgr.check_content_change("p2")
        mgr.resolve_change("p1")
        pending = mgr.pending_changes
        assert len(pending) == 1
        assert pending[0].description == "p2"

    def test_health_check_needed(self):
        mgr = ContentVersionManager()
        assert not mgr.health_check_needed()

    def test_health_check_needed_after_interval(self):
        mgr = ContentVersionManager()
        mgr._last_health_check = time.perf_counter() - 2000.0
        assert mgr.health_check_needed()

    def test_record_health_check(self):
        mgr = ContentVersionManager()
        mgr._last_health_check = 0.0
        mgr.record_health_check()
        assert mgr._last_health_check > 0.0

    def test_partial_resolve_stays_yellow(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("a", severity="medium")
        mgr.check_ui_change("b", severity="medium")
        assert mgr.compatibility_state == CompatibilityState.YELLOW
        mgr.resolve_change("a")
        # Still one pending → YELLOW
        assert mgr.compatibility_state == CompatibilityState.YELLOW

    def test_mixed_severity_with_resolve(self):
        mgr = ContentVersionManager()
        mgr.check_ui_change("critical issue", severity="critical")
        assert mgr.compatibility_state == CompatibilityState.RED
        mgr.resolve_change("critical issue")
        assert mgr.compatibility_state == CompatibilityState.GREEN

    def test_known_versions_tuple(self):
        mgr = ContentVersionManager()
        assert "5.7" in mgr._KNOWN_VERSIONS
        assert "3.0" in mgr._KNOWN_VERSIONS
        assert len(mgr._KNOWN_VERSIONS) >= 20
