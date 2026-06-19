"""Tests for HotReloadManager."""
from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

from runtime.hot_reload_manager import HotReloadConfig, HotReloadManager, ReloadEvent


class TestHotReloadManager:
    def test_watch_unknown_module(self) -> None:
        mgr = HotReloadManager()
        mgr.watch("nonexistent_module_xyz_12345")
        assert "nonexistent_module_xyz_12345" not in mgr.watched_modules

    def test_watch_real_module(self) -> None:
        mgr = HotReloadManager()
        mgr.watch("json")
        assert "json" in mgr.watched_modules

    def test_unwatch(self) -> None:
        mgr = HotReloadManager()
        mgr.watch("json")
        mgr.unwatch("json")
        assert "json" not in mgr.watched_modules

    def test_tick_no_changes(self) -> None:
        mgr = HotReloadManager()
        mgr.watch("json")
        events = mgr.tick()
        assert len(events) == 0

    def test_reload_all(self) -> None:
        mgr = HotReloadManager()
        mgr.watch("json")
        events = mgr.reload_all()
        assert len(events) == 1
        assert events[0].module_name == "json"
        assert events[0].success

    def test_history_recorded(self) -> None:
        mgr = HotReloadManager()
        mgr.watch("json")
        mgr.reload_all()
        assert len(mgr.history) == 1
        assert mgr.history[0].success

    def test_disabled_skips_tick(self) -> None:
        mgr = HotReloadManager(config=HotReloadConfig(enabled=False))
        mgr.watch("json")
        events = mgr.tick()
        assert events == []

    def test_reload_event_frozen(self) -> None:
        event = ReloadEvent(module_name="test", file_path="test.py", timestamp=0.0, success=True)
        try:
            event.success = False  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass
