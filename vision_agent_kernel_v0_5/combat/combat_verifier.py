from __future__ import annotations

from execution.verifier_base import VerifierResult


class CombatRuntimeVerifier:
    verifier_id = "combat_runtime_verifier"

    def verify(self, state: dict) -> VerifierResult:
        hp = float(state.get("target_hp_ratio", 1.0))
        target_dead = bool(state.get("target_dead", False) or hp <= 0.05)
        combat_ended = bool(state.get("combat_ended", target_dead))
        ok = target_dead and combat_ended
        return VerifierResult(ok, self.verifier_id, 0.9 if ok else 0.4, "combat complete" if ok else "combat incomplete", state)
