from __future__ import annotations

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context


class VisualVerifier:
    verifier_id = "visual_verifier"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        state = ctx.state
        track = ctx.target_track or (ctx.observation.target_track if ctx.observation else None)
        ok = bool(state.get("target_visible") or state.get("visual_trigger_detected") or (track is not None and track.confidence > 0.2 and track.state != "LOST"))
        frame_id = ctx.observation.frame_id if ctx.observation is not None else None
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=0.8 if ok else 0.25,
            reason="visual condition satisfied" if ok else "visual condition missing",
            evidence={"state": state, "track": track},
            frame_id=frame_id,
            detection_confidence=track.confidence if track is not None else (0.8 if ok else 0.25),
            roi_ids=["target_bbox"] if track is not None else [],
        )
