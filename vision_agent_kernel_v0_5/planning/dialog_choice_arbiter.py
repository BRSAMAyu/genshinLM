"""DialogChoiceArbiter: VLM arbitration for dialog branch selection.

Per AUTONOMY_RUNTIME_CONTRACT.md §8 (VLM Usage Contract):
  - VLM is called when DialogBranchAnalyzer confidence < 0.7
  - Produces DialogChoiceClaim per contract §1.9
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import numpy as np
    from interaction.dialog_branch_analyzer import DialogBranchAnalyzer


log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DialogChoice:
    """Per AUTONOMY_RUNTIME_CONTRACT.md §1.9."""

    index: int
    text: str
    bbox_norm: tuple[float, float, float, float]
    clickable: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class DialogChoiceClaim:
    """Per AUTONOMY_RUNTIME_CONTRACT.md §1.9."""

    claim_id: str
    frame_id: int
    timestamp: float
    choices: tuple[DialogChoice, ...] = ()
    selected_index: int = -1
    confidence: float = 0.0


class DialogChoiceArbiter:
    """Selects dialog branch via VLM when DialogBranchAnalyzer confidence is low."""

    __slots__ = ("_analyzer", "_vlm_fn", "_vlm_threshold", "_vlm_call_count", "_vlm_call_limit")

    def __init__(
        self,
        branch_analyzer: DialogBranchAnalyzer | None = None,
        vlm_arbiter_fn: Callable[[np.ndarray, dict[str, Any]], str] | None = None,
        vlm_confidence_threshold: float = 0.7,
    ) -> None:
        self._analyzer = branch_analyzer
        self._vlm_fn = vlm_arbiter_fn
        self._vlm_threshold = vlm_confidence_threshold
        self._vlm_call_count = 0
        self._vlm_call_limit = 20

    def select_choice(
        self,
        frame: Any,
        choices: list[DialogChoice],
        context: dict[str, Any] | None = None,
    ) -> DialogChoiceClaim:
        """Select a dialog choice.

        Strategy:
        1. Ask DialogBranchAnalyzer for selection + confidence
        2. If confidence >= threshold: use analyzer's choice
        3. Otherwise: call VLM arbiter and re-select
        4. Track VLM usage (max 20 calls per mission)
        """
        import time
        claim_id = f"dlg_claim_{int(time.time() * 1000)}"
        frame_id = getattr(frame, "frame_id", 0) if hasattr(frame, "frame_id") else 0
        ctx = context or {}

        # Step 1: Analyzer selection (DialogBranchAnalyzer may not have select_choice)
        # If it does, try it; otherwise skip to VLM
        analyzer_ok = False
        if self._analyzer is not None:
            try:
                if hasattr(self._analyzer, "select_choice"):
                    result = self._analyzer.select_choice(choices, ctx or {})
                    if result is not None:
                        selected_index, confidence = result
                        if confidence >= self._vlm_threshold:
                            return DialogChoiceClaim(
                                claim_id=claim_id,
                                frame_id=frame_id,
                                timestamp=time.perf_counter(),
                                choices=tuple(choices),
                                selected_index=selected_index,
                                confidence=confidence,
                            )
                        analyzer_ok = True
            except Exception as exc:
                log.debug("[DialogChoiceArbiter] analyzer failed: %s", exc)

        # Step 2: VLM fallback
        if self._vlm_fn is None or self._vlm_call_count >= self._vlm_call_limit:
            # No VLM available or limit reached: pick first choice
            return DialogChoiceClaim(
                claim_id=claim_id,
                frame_id=frame_id,
                timestamp=time.perf_counter(),
                choices=tuple(choices),
                selected_index=0,
                confidence=0.3,
            )

        self._vlm_call_count += 1
        try:
            vlm_result = self._vlm_fn(frame, {
                "context": "Which dialog option should be selected?",
                "choices": [f"{i}: {c.text}" for i, c in enumerate(choices)],
                "quest_id": ctx.get("quest_id", "unknown"),
            })

            # Parse VLM response: try to extract choice index
            selected = self._parse_vlm_response(vlm_result, len(choices))
            return DialogChoiceClaim(
                claim_id=claim_id,
                frame_id=frame_id,
                timestamp=time.perf_counter(),
                choices=tuple(choices),
                selected_index=selected,
                confidence=0.5,
            )
        except Exception as exc:
            log.debug("[DialogChoiceArbiter] VLM arbiter failed: %s", exc)
            return DialogChoiceClaim(
                claim_id=claim_id,
                frame_id=frame_id,
                timestamp=time.perf_counter(),
                choices=tuple(choices),
                selected_index=0,
                confidence=0.2,
            )

    def _parse_vlm_response(self, response: str, choice_count: int) -> int:
        """Parse VLM text response to extract choice index."""
        response_lower = response.lower().strip()

        # Try "choose option X" pattern
        for i in range(choice_count):
            if response_lower.startswith(str(i)) or f"option {i}" in response_lower:
                return i

        # Try keyword extraction
        for i, c in enumerate(str(response) for _ in [0]):
            if str(i) in response_lower[:5]:
                return i

        return 0

    @property
    def vlm_call_count(self) -> int:
        return self._vlm_call_count

    def reset_vlm_counter(self) -> None:
        self._vlm_call_count = 0