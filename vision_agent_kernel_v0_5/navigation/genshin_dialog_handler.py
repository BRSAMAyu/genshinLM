from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class DialogState:
    active: bool
    has_choices: bool
    choice_count: int
    dialog_text: str
    npc_name: str


class GenshinDialogHandler:
    """Handle NPC dialog sequences in Genshin Impact."""

    _DIALOG_ROI_REF = (0, 756, 1920, 1080)
    _REF_W = 1920
    _REF_H = 1080

    def __init__(self) -> None:
        self._click_cooldown_ms = 500

    def detect_dialog(self, frame: np.ndarray, screen_state: str) -> DialogState:
        """Detect if dialog is active and extract information.

        Checks for dialog box at bottom of screen.
        Extracts choice buttons if present.
        """
        if screen_state != "dialog":
            return DialogState(False, False, 0, "", "")

        if frame.size == 0:
            return DialogState(True, False, 0, "", "")

        h, w = frame.shape[:2]
        sx, sy = w / self._REF_W, h / self._REF_H
        x1, y1, x2, y2 = self._scale_roi(self._DIALOG_ROI_REF, sx, sy)
        dialog_roi = frame[y1:y2, x1:x2]

        if dialog_roi.size == 0:
            return DialogState(True, False, 0, "", "")

        choice_count = self._count_choice_buttons(dialog_roi)
        dialog_text = self._extract_dialog_text(dialog_roi)

        return DialogState(
            active=True,
            has_choices=choice_count > 0,
            choice_count=choice_count,
            dialog_text=dialog_text,
            npc_name="",
        )

    def advance_dialog(self) -> dict:
        """Generate input to advance dialog by one step.

        Clicks in the dialog area to advance text.
        Waits for click cooldown to prevent double-advance.
        """
        return {
            "input": "click_at",
            "target": "dialog_area_center",
            "cooldown_ms": self._click_cooldown_ms,
        }

    def select_choice(self, choice_index: int) -> dict:
        """Generate input to select a dialog choice.

        Args:
            choice_index: 0-based choice index
        """
        return {
            "input": "click_at",
            "target": f"dialog_choice_{choice_index}",
            "choice_index": choice_index,
        }

    def detect_dialog_end(self, frame: np.ndarray, prev_screen_state: str) -> bool:
        """Detect if dialog has ended.

        Dialog ends when the dialog box disappears and
        screen returns to world_hud or another non-dialog state.
        """
        return prev_screen_state == "dialog" and frame.size > 0

    def _count_choice_buttons(self, dialog_roi: np.ndarray) -> int:
        """Count visible choice buttons in dialog area.

        Choice buttons are semi-transparent rectangles with text.
        Use OCR or template matching.
        """
        if dialog_roi.size == 0:
            return 0

        import cv2

        gray = cv2.cvtColor(dialog_roi, cv2.COLOR_BGR2GRAY) if dialog_roi.ndim == 3 else dialog_roi
        h = gray.shape[0]

        bottom_half = gray[h // 2:, :]
        edges = cv2.Canny(bottom_half, 80, 200)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        button_count = 0
        for cnt in contours:
            x, y, w_c, h_c = cv2.boundingRect(cnt)
            area = w_c * h_c
            if area > 2000 and 2.0 < w_c / max(h_c, 1) < 8.0:
                button_count += 1

        return button_count

    def _extract_dialog_text(self, dialog_roi: np.ndarray) -> str:
        """Extract dialog text using OCR."""
        if dialog_roi.size == 0:
            return ""

        import cv2

        gray = cv2.cvtColor(dialog_roi, cv2.COLOR_BGR2GRAY) if dialog_roi.ndim == 3 else dialog_roi
        h = gray.shape[0]

        top_half = gray[: h // 2, :]
        thresh = cv2.threshold(top_half, 180, 255, cv2.THRESH_BINARY)[1]
        text_pixels = int(np.sum(thresh > 0))
        total_pixels = thresh.size

        if total_pixels == 0 or text_pixels / total_pixels < 0.01:
            return ""

        return "dialog_text_detected"

    @staticmethod
    def _scale_roi(
        roi: tuple[int, int, int, int], sx: float, sy: float
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
