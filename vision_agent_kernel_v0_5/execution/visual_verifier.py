from __future__ import annotations

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context


class VisualVerifier:
    verifier_id = "visual_verifier"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        state = ctx.state
        track = ctx.target_track or (ctx.observation.target_track if ctx.observation else None)
        ok = bool(state.get("target_visible") or state.get("visual_trigger_detected") or (track is not None and track.confidence > 0.2 and track.state != "LOST"))
        return VerifierResult(ok, self.verifier_id, 0.8 if ok else 0.25, "visual condition satisfied" if ok else "visual condition missing", {"state": state, "track": track})
