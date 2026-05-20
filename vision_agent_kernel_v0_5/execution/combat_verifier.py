from __future__ import annotations

import numpy as np

from execution.verifier_base import VerifierContext, VerifierResult, ensure_context


class CombatVerifier:
    verifier_id = "combat_verifier"

    def verify(self, context: VerifierContext | dict) -> VerifierResult:
        ctx = ensure_context(context)
        state = ctx.state
        hp_ratio = float(state.get("target_hp_ratio", _hp_ratio_from_frame(ctx.frame)))
        track = ctx.target_track or (ctx.observation.target_track if ctx.observation else None)
        target_missing = track is None or track.state in {"LOST", "DEAD"} or track.confidence <= 0.05
        defeated = bool(state.get("target_defeated") or state.get("reward_seen") or hp_ratio <= 0.05 or (target_missing and state.get("combat_started", False)))
        evidence = {"target_hp_ratio": hp_ratio, "target_missing": target_missing, "state": state}
        return VerifierResult(defeated, self.verifier_id, 0.9 if defeated else 0.35, "target defeated" if defeated else "target still active", evidence)


def _hp_ratio_from_frame(frame: np.ndarray | None) -> float:
    if frame is None or frame.size == 0:
        return 1.0
    # Testbed HP bars are red-dominant. Count red pixels in the top HUD strip.
    strip = frame[: max(1, min(frame.shape[0], 80)), :, :]
    red = strip[..., 0]
    green = strip[..., 1]
    blue = strip[..., 2]
    mask = (red > 140) & (green < 110) & (blue < 110)
    if not mask.any():
        return 1.0
    xs = np.where(mask)[1]
    return float((xs.max() - xs.min() + 1) / max(1, strip.shape[1]))
