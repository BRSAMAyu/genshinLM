"""Tests for BackendFactory — Phase 2 input backend creation."""
from __future__ import annotations

import pytest

from execution.backend_factory import BackendFactory
from execution.console_backend import ConsoleInputBackend


class TestBackendFactory:
    def test_console_mode_returns_console_backend(self) -> None:
        backend = BackendFactory.create("console")
        assert isinstance(backend, ConsoleInputBackend)

    def test_console_mode_with_timebase(self) -> None:
        from core.timebase import Timebase
        tb = Timebase()
        backend = BackendFactory.create("console", timebase=tb)
        assert isinstance(backend, ConsoleInputBackend)

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend mode"):
            BackendFactory.create("nonexistent_mode")

    def test_safe_window_requires_title(self) -> None:
        with pytest.raises(ValueError, match="target_window_title"):
            BackendFactory.create("safe_window", target_window_title="")
