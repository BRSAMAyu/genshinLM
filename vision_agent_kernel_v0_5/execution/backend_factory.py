"""BackendFactory: formal factory for input backend creation.

Replaces the ad-hoc _build_backend() function in scripts/run_kernel.py.
Supports console (dry-run), safe_window (real input), and background modes.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from core.state_bus import StateBus
from core.timebase import Timebase
from execution.console_backend import ConsoleInputBackend
from execution.safe_window_backend import SafeWindowInputBackend

if TYPE_CHECKING:
    from execution.input_backend_base import InputBackend


class BackendFactory:
    """Factory for creating input backends with consistent initialization."""

    @staticmethod
    def create(
        mode: str,
        timebase: Timebase | None = None,
        state_bus: StateBus | None = None,
        target_window_title: str = "原神",
        pixels_per_degree: float = 8.0,
        alt_window_titles: list[str] | None = None,
    ) -> InputBackend:
        """Create an input backend by mode.

        Parameters
        ----------
        mode : str
            "console" (dry-run, print-only), "safe_window" (real OS input),
            or "background" (non-interactive safe mode).
        timebase : Timebase | None
            Time source. Defaults to Timebase().
        state_bus : StateBus | None
            State bus for focus monitoring.
        target_window_title : str
            Window title for SafeWindowInputBackend.
        pixels_per_degree : float
            Mouse sensitivity for SafeWindowInputBackend.
        alt_window_titles : list[str] | None
            Alternative window titles to try.

        Returns
        -------
        InputBackend
            The appropriate backend instance.

        Raises
        ------
        ValueError
            If mode is unknown or SafeWindowInputBackend cannot find the window.
        """
        tb = timebase or Timebase()
        alt = alt_window_titles or []

        if mode == "console":
            return ConsoleInputBackend(timebase=tb)

        if mode == "background":
            backend = SafeWindowInputBackend(
                target_window_title=target_window_title,
                pixels_per_degree=pixels_per_degree,
                timebase=tb,
                alt_window_titles=alt,
            )
            backend._released = True
            return backend

        if mode == "safe_window":
            if not target_window_title:
                raise ValueError("safe_window mode requires target_window_title")

            os.environ.setdefault("AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW", "1")
            return SafeWindowInputBackend(
                target_window_title=target_window_title,
                pixels_per_degree=pixels_per_degree,
                timebase=tb,
                alt_window_titles=alt,
            )

        raise ValueError(f"Unknown backend mode: {mode!r}. Valid: console, safe_window, background")