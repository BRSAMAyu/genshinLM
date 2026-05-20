from __future__ import annotations

import numpy as np

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context


class CollectionVerifier:
    verifier_id = "collection_verifier"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        state = ctx.state
        item_visible = _green_visible(ctx.frame)
        collected = bool(state.get("item_disappeared") or state.get("gain_popup") or state.get("count_delta", 0) > 0 or (state.get("collection_started", False) and not item_visible))
        evidence = {"item_visible": item_visible, "ocr_text": ctx.ocr_text, "state": state}
        return VerifierResult(collected, self.verifier_id, 0.86 if collected else 0.32, "collection verified" if collected else "collection not verified", evidence)


def _green_visible(frame: np.ndarray | None) -> bool:
    if frame is None or frame.size == 0:
        return True
    green = frame[..., 1]
    red = frame[..., 0]
    blue = frame[..., 2]
    return bool(((green > 150) & (red < 120) & (blue < 140)).sum() > 16)
