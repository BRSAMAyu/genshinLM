from __future__ import annotations

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context


class UIVerifier:
    verifier_id = "ui_verifier"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        state = ctx.state
        visible = bool(state.get("ui_visible", state.get("success", False)) or ctx.ocr_text)
        return VerifierResult(visible, self.verifier_id, 0.85 if visible else 0.3, "ui visible" if visible else "ui not visible", {"state": state, "ocr_text": ctx.ocr_text})
