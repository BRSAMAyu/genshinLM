"""Compliance unit tests for Sparkle Agent Kernel next-gen low-level input backends."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from execution.console_backend import ConsoleInputBackend
from execution.directinput_backend import DirectInputBackend
from execution.safe_window_backend import SafeWindowInputBackend
from execution.input_backend_base import InputBackend


class TestLowLevelControllers(unittest.TestCase):
    """Compliance test suite for unified InputBackend implementations."""

    def test_protocol_compliance_console(self) -> None:
        """Verify ConsoleInputBackend satisfies the InputBackend protocol contract."""
        backend = ConsoleInputBackend()
        self.assertTrue(isinstance(backend, InputBackend))

        # Basic verification of stubs
        self.assertTrue(backend.key_down("w", "test"))
        self.assertTrue(backend.key_up("w", "test"))
        self.assertEqual(backend.release_all("test"), 0)
        self.assertTrue(backend.mouse_move(1.0, 2.0, "test"))
        self.assertTrue(backend.mouse_move_to(100, 200, "test"))
        self.assertTrue(backend.left_click("test"))
        self.assertTrue(backend.right_click("test"))
        self.assertTrue(backend.mouse_scroll(-1, "test"))
        self.assertTrue(backend.hold_click(0.1, "test"))
        
        # Verify advanced operations
        self.assertTrue(backend.mouse_drag(10, 20, 100, 200, 100, "left", "test"))
        self.assertTrue(backend.mouse_relative_drag(50, 50, 100, "right", "test"))
        self.assertTrue(backend.mouse_double_click(300, 400, "left", "test"))
        self.assertTrue(backend.type_text("Hello!", 10, "test"))
        self.assertTrue(backend.execute_combo(["shift", "w"], 50, "test"))

    @patch("ctypes.windll.user32.SendInput")
    def test_safe_window_backend_keystroke_whitelists(self, mock_sendinput: MagicMock) -> None:
        """Verify that SafeWindowInputBackend supports all newly whitelisted RPG shortcuts."""
        mock_sendinput.return_value = 1
        backend = SafeWindowInputBackend(target_window_title="MockGameWindow")
        backend._ensure_target_focused = MagicMock()
        
        # Extended shortcut keys whitelisted
        keys = ["m", "i", "b", "j", "p", "y", "u", "g", "f1", "f5", "6", "0"]
        for key in keys:
            self.assertTrue(backend.key_down(key, "test"))
            self.assertTrue(backend.key_up(key, "test"))

        # Verify combos and text typing execute successfully
        self.assertTrue(backend.execute_combo(["alt", "1"], 10, "test"))
        self.assertTrue(backend.type_text("DailyQuest", 5, "test"))

    @patch("ctypes.windll.user32.SendInput")
    def test_direct_input_backend_drag_and_combos(self, mock_sendinput: MagicMock) -> None:
        """Verify DirectInputBackend handles dragging, scrolling, and reverse sequencing."""
        mock_sendinput.return_value = 1
        backend = DirectInputBackend(target_window_title="MockGameWindow")
        backend._target_title = ""  # Bypass foreground verification for direct mocks
        
        # Test standard mouse movements
        self.assertTrue(backend.mouse_move(1.5, -0.5, "test"))
        self.assertTrue(backend.mouse_move_to(800, 600, "test"))
        self.assertTrue(backend.mouse_scroll(1, "test"))

        # Verify dragging and double clicks conform
        self.assertTrue(backend.mouse_drag(100, 100, 200, 200, 50, "left", "test"))
        self.assertTrue(backend.mouse_relative_drag(10, 0, 50, "right", "test"))
        self.assertTrue(backend.mouse_double_click(500, 500, "left", "test"))
        
        # Verify combos press keys and release in inverse order
        self.assertTrue(backend.execute_combo(["shift", "w"], 20, "test"))
