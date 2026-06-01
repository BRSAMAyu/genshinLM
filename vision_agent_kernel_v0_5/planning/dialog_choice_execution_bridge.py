"""Dialog choice execution bridge.

Converts a DialogChoiceClaim into a physical click receipt and requires
post-click verification by default. Test and dry-run callers can opt into
``allow_unverified`` explicitly, but production paths should provide both a
click executor and a verifier.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from planning.dialog_choice_arbiter import DialogChoiceClaim

log = logging.getLogger(__name__)


class DialogClickExecutor(Protocol):
    """Click on a dialog choice."""

    def click_choice(self, choice_index: int, bbox_norm: tuple[float, float, float, float]) -> bool: ...


@dataclass(frozen=True, slots=True)
class DialogExecutionReceipt:
    """Physical receipt for dialog choice execution."""

    claim_id: str
    selected_index: int
    clicked: bool
    verified: bool
    timestamp: float = 0.0
    error: str = ""


class DialogChoiceExecutionBridge:
    """Bridge from DialogChoiceClaim to physical dialog click + verification."""

    __slots__ = ("_click_executor", "_verify_fn", "_allow_unverified", "_call_count")

    def __init__(
        self,
        click_executor: DialogClickExecutor | None = None,
        verify_fn: Callable[[int], bool] | None = None,
        allow_unverified: bool = False,
    ) -> None:
        self._click_executor = click_executor
        self._verify_fn = verify_fn
        self._allow_unverified = allow_unverified
        self._call_count = 0

    def execute_claim(self, claim: DialogChoiceClaim) -> DialogExecutionReceipt:
        """Click the selected dialog option and verify the dialog advanced."""
        self._call_count += 1

        if claim.selected_index < 0 or claim.selected_index >= len(claim.choices):
            return DialogExecutionReceipt(
                claim_id=claim.claim_id,
                selected_index=claim.selected_index,
                clicked=False,
                verified=False,
                timestamp=time.perf_counter(),
                error=f"invalid selected_index={claim.selected_index} for {len(claim.choices)} choices",
            )

        if self._click_executor is None:
            return DialogExecutionReceipt(
                claim_id=claim.claim_id,
                selected_index=claim.selected_index,
                clicked=False,
                verified=False,
                timestamp=time.perf_counter(),
                error="no_click_executor",
            )

        choice = claim.choices[claim.selected_index]
        try:
            clicked = self._click_executor.click_choice(
                choice_index=choice.index,
                bbox_norm=choice.bbox_norm,
            )
        except Exception as exc:
            log.warning("[DialogExecBridge] click failed: %s", exc)
            return DialogExecutionReceipt(
                claim_id=claim.claim_id,
                selected_index=claim.selected_index,
                clicked=False,
                verified=False,
                timestamp=time.perf_counter(),
                error=str(exc),
            )

        if not clicked:
            return DialogExecutionReceipt(
                claim_id=claim.claim_id,
                selected_index=claim.selected_index,
                clicked=False,
                verified=False,
                timestamp=time.perf_counter(),
                error="click_rejected",
            )

        verified = False
        if self._verify_fn is not None:
            try:
                verified = bool(self._verify_fn(claim.selected_index))
            except Exception as exc:
                log.debug("[DialogExecBridge] verify failed: %s", exc)
                return DialogExecutionReceipt(
                    claim_id=claim.claim_id,
                    selected_index=claim.selected_index,
                    clicked=True,
                    verified=False,
                    timestamp=time.perf_counter(),
                    error=str(exc),
                )
        elif self._allow_unverified:
            verified = True

        return DialogExecutionReceipt(
            claim_id=claim.claim_id,
            selected_index=claim.selected_index,
            clicked=True,
            verified=verified,
            timestamp=time.perf_counter(),
            error="" if verified else "no_verify_fn",
        )

    @property
    def call_count(self) -> int:
        return self._call_count
