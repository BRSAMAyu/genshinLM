"""Unified InputBackend base interface and protocol definition.

Defines the low-level physical capabilities required for 100% human-complete
computer use. All compliant keyboard/mouse simulation backends must satisfy
this contract.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class InputBackend(Protocol):
    """Protocol defining the complete human-like interface for game control."""

    def key_down(self, key: str, reason: str = "") -> bool:
        """Hold down a keyboard key. Returns True on success."""
        ...

    def key_up(self, key: str, reason: str = "") -> bool:
        """Release a keyboard key. Returns True on success."""
        ...

    def release_all(self, reason: str = "") -> int:
        """Force release all currently tracked keyboard keys and mouse buttons.
        
        Returns the number of keys successfully released.
        """
        ...

    def is_target_focused(self) -> bool:
        """Verify that the target game window currently possesses foreground focus."""
        ...

    # --- Standard Mouse Actions ---

    def mouse_move(self, dx: float, dy: float, reason: str = "") -> bool:
        """Inject relative mouse movement (used for continuous 3D camera servoing)."""
        ...

    def mouse_move_to(self, x: int, y: int, reason: str = "") -> bool:
        """Move mouse cursor instantly or smoothly to absolute pixel coordinate (x, y)."""
        ...

    def left_click(self, reason: str = "") -> bool:
        """Trigger a left mouse button down followed by a natural hold delay and release."""
        ...

    def right_click(self, reason: str = "") -> bool:
        """Trigger a right mouse button down followed by a natural hold delay and release."""
        ...

    def mouse_scroll(self, delta: int = -1, reason: str = "") -> bool:
        """Scroll mouse wheel. delta=-1 scrolls up/in, delta=1 scrolls down/out."""
        ...

    def hold_click(self, duration_sec: float = 0.5, reason: str = "") -> bool:
        """Hold the left mouse button down for a duration (e.g. charged attacks)."""
        ...

    # --- Next-Gen Computer Use Advanced Actions ---

    def mouse_drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 300,
        button: Literal["left", "right"] = "left",
        reason: str = "",
    ) -> bool:
        """Click down, drag cursor along a smooth biometrical trajectory, and release."""
        ...

    def mouse_relative_drag(
        self,
        dx: int,
        dy: int,
        duration_ms: int = 150,
        button: Literal["left", "right", "middle"] = "right",
        reason: str = "",
    ) -> bool:
        """Hold down mouse button, inject continuous relative dragging, and release."""
        ...

    def mouse_double_click(
        self,
        x: int,
        y: int,
        button: Literal["left", "right"] = "left",
        reason: str = "",
    ) -> bool:
        """Perform two rapid, calibrated clicks at absolute coordinate (x, y)."""
        ...

    # --- Advanced Keyboard Additions ---

    def type_text(self, text: str, delay_between_keys_ms: int = 50, reason: str = "") -> bool:
        """Simulate human typing of arbitrary text string with shift state conversions."""
        ...

    def execute_combo(self, keys: list[str], hold_time_ms: int = 100, reason: str = "") -> bool:
        """Press multiple keys concurrently, hold, and release in strict reverse sequence."""
        ...


# Alias for backward compatibility
InputBackendBase = InputBackend
