from __future__ import annotations

from typing import Any

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context


class DangerClearVerifier:
    """Verifier that checks whether the danger level has dropped below a safe
    threshold after a reflex dodge maneuver.

    Danger score is read generically from:
    * ``observation.extensions["danger_score"]`` if an observation is present
    * ``context.state["danger_score"]`` as a fallback
    """

    verifier_id: str = "danger_clear_verifier"

    def __init__(self, danger_threshold: float = 0.15) -> None:
        self._threshold = danger_threshold

    def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
        ctx = ensure_context(context)

        danger_score: float | None = None
        frame_id: int | None = None

        # Prefer observation.extensions
        obs = ctx.observation
        if obs is not None:
            frame_id = obs.frame_id
            ext_danger = obs.extensions.get("danger_score")
            if ext_danger is not None:
                danger_score = float(ext_danger)

        # Fallback to state dict
        if danger_score is None:
            state_danger = ctx.state.get("danger_score")
            if state_danger is not None:
                danger_score = float(state_danger)

        # If we cannot determine danger, fail safe (not clear)
        if danger_score is None:
            return VerifierResult(
                ok=False,
                verifier_id=self.verifier_id,
                confidence=0.0,
                reason="danger_score unavailable",
                evidence={},
                frame_id=frame_id,
            )

        ok = danger_score < self._threshold
        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=1.0 - danger_score if ok else danger_score,
            reason="danger below threshold" if ok else "danger above threshold",
            evidence={"danger_score": danger_score, "threshold": self._threshold},
            frame_id=frame_id,
        )
