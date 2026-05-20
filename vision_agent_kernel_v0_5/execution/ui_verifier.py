from __future__ import annotations

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context


class UIVerifier:
    verifier_id = "ui_verifier"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        state = ctx.state
        visible = bool(state.get("ui_visible", state.get("success", False)) or ctx.ocr_text)
        frame_id = ctx.observation.frame_id if ctx.observation is not None else None
        return VerifierResult(
            ok=visible,
            verifier_id=self.verifier_id,
            confidence=0.85 if visible else 0.3,
            reason="ui visible" if visible else "ui not visible",
            evidence={"state": state, "ocr_text": ctx.ocr_text},
            frame_id=frame_id,
            detection_confidence=0.85 if visible else 0.3,
            roi_ids=["ui_hud"] if visible else [],
        )
