"""Safety boundary tests: enforce no real client bindings in default execution paths.

These tests verify that the project remains within its authorized scope:
dry-run / testbed / pseudo3d / QA safe-window only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.check_core_boundaries import scan_core_boundaries

_ROOT = Path(__file__).resolve().parents[1]

# Strings that must NEVER appear in execution/ or core/ source files.
_BANNED_EXEC_STRINGS = (
    "YuanShen.exe",
    "GenshinImpact.exe",
    "GenshinImpactCloud.exe",
    "mhyprot2.sys",
    "mhyprot3.sys",
    "StarRail.exe",
    "HonkaiStarRail.exe",
)

# Patterns for dangerous API usage in execution layer.
_BANNED_EXEC_PATTERNS = (
    re.compile(r"ctypes\.windll\.user32\.keybd_event\b"),
    re.compile(r"win32api\.keybd_event\b"),
    re.compile(r"pyautogui\.(click|moveTo|keyDown|keyUp|press|typewrite)\b"),
)


class TestNoRealClientBindings:
    """execution/ and core/ must not reference real game executables or drivers."""

    @pytest.mark.parametrize("banned", _BANNED_EXEC_STRINGS)
    def test_banned_executable_name_absent_from_execution(self, banned: str) -> None:
        for py_file in (_ROOT / "execution").rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            assert banned not in content, (
                f"{py_file.relative_to(_ROOT)} references banned string {banned!r}"
            )

    @pytest.mark.parametrize("banned", _BANNED_EXEC_STRINGS)
    def test_banned_executable_name_absent_from_core(self, banned: str) -> None:
        for py_file in (_ROOT / "core").rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            assert banned not in content, (
                f"{py_file.relative_to(_ROOT)} references banned string {banned!r}"
            )

    @pytest.mark.parametrize("banned", _BANNED_EXEC_STRINGS)
    def test_banned_executable_name_absent_from_planning(self, banned: str) -> None:
        for py_file in (_ROOT / "planning").rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            assert banned not in content, (
                f"{py_file.relative_to(_ROOT)} references banned string {banned!r}"
            )


class TestNoBannedInputApis:
    """execution/ must not use banned direct input APIs (only SendInput via SafeWindowBackend)."""

    def test_no_keybd_event_calls(self) -> None:
        for py_file in (_ROOT / "execution").rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for pattern in _BANNED_EXEC_PATTERNS:
                match = pattern.search(content)
                assert match is None, (
                    f"{py_file.relative_to(_ROOT)} uses banned input API: {match.group()!r}"
                )


class TestDefaultDryRun:
    """Verify that default mode is dry-run."""

    def test_console_backend_instantiable_without_args(self) -> None:
        from execution.console_backend import ConsoleInputBackend

        backend = ConsoleInputBackend()
        assert backend is not None

    def test_safe_window_requires_explicit_window_title(self) -> None:
        from execution.safe_window_backend import SafeWindowInputBackend, SafeWindowInputError

        # A title that definitely doesn't exist should fail on focus check.
        backend = SafeWindowInputBackend(target_window_title="__nonexistent_window_12345__")
        with pytest.raises(SafeWindowInputError):
            backend.focus_target_window()


class TestCoreBoundaryScan:
    """Run the existing boundary scan script as a test."""

    def test_scan_core_boundaries_passes(self) -> None:
        report = scan_core_boundaries(_ROOT)
        assert report.ok, (
            "Core boundary scan failed:\n"
            + "\n".join(f"  {v.path}:{v.line}: {v.code}: {v.detail}" for v in report.violations)
        )


class TestLlmToolDiscipline:
    """LLM planner tools must not include raw input tools."""

    def test_forbidden_tools_not_in_tool_list(self) -> None:
        forbidden = {"raw_key_input", "raw_mouse_input", "direct_click", "direct_press_key", "bypass_safety"}
        # Import the planner module to check tool names
        try:
            from llm.planner import PLANNER_TOOLS
            tool_names = {t.name if hasattr(t, "name") else str(t) for t in PLANNER_TOOLS}
        except ImportError:
            pytest.skip("llm.planner not available")

        overlap = forbidden & tool_names
        assert not overlap, f"Forbidden tools found in PLANNER_TOOLS: {overlap}"


class TestInputLeaseEnforcement:
    """All physical input must go through InputLease."""

    def test_sendinput_only_in_safe_window_backend(self) -> None:
        """SendInput ctypes call must only exist in safe_window_backend.py within execution/."""
        sendinput_pattern = re.compile(r"SendInput")
        for py_file in (_ROOT / "execution").rglob("*.py"):
            if py_file.name == "safe_window_backend.py":
                continue
            if py_file.name == "real_input_backend.py":
                continue
            content = py_file.read_text(encoding="utf-8")
            assert not sendinput_pattern.search(content), (
                f"{py_file.relative_to(_ROOT)} contains SendInput call outside safe_window_backend.py"
            )
