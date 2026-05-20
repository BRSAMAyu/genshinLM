from __future__ import annotations

from execution.verifier_base import VerifierResult


class CollectVerifier:
    verifier_id = "collect_verifier"

    def verify(self, state: dict) -> VerifierResult:
        ok = bool(state.get("item_disappeared") or state.get("gain_popup") or state.get("count_delta", 0) > 0)
        return VerifierResult(ok, self.verifier_id, 0.88 if ok else 0.3, "collected" if ok else "not collected", state)

