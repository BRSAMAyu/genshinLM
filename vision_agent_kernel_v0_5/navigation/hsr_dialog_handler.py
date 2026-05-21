from __future__ import annotations

import logging
from dataclasses import dataclass, field

_log = logging.getLogger("HSRDialogHandler")


@dataclass(slots=True)
class HSRDialogState:
    in_dialog: bool = False
    dialog_text: str = ""
    options: list[str] = field(default_factory=list)
    option_click_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    can_skip: bool = False
    can_auto: bool = False


class HSRDialogHandler:
    """Detect and handle HSR dialog flows."""

    _SKIP_ZONE = (1500, 100, 1800, 200)
    _CHOICE_Y_BASE = 700
    _CHOICE_HEIGHT = 50
    _CHOICE_SPACING = 10

    def detect_dialog(self, frame, screen_state: str) -> HSRDialogState:
        if screen_state != "dialog":
            return HSRDialogState()

        # In real implementation, would OCR dialog text and detect choice options
        return HSRDialogState(
            in_dialog=True,
            dialog_text="",
            options=[],
            option_click_zones=[],
            can_skip=True,
            can_auto=False,
        )

    def advance_dialog(self) -> dict:
        return {
            "input_type": "click",
            "target": self._SKIP_ZONE,
            "label": "skip_or_advance_dialog",
        }

    def select_choice(self, choice_index: int) -> dict:
        y = self._CHOICE_Y_BASE + choice_index * (self._CHOICE_HEIGHT + self._CHOICE_SPACING)
        zone = (800, y, 1100, y + self._CHOICE_HEIGHT)
        return {
            "input_type": "click",
            "target": zone,
            "label": f"select_choice_{choice_index}",
        }
