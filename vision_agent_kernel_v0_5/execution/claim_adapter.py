from __future__ import annotations

from dataclasses import replace
from typing import Any

from execution.verifier_base import VerifierResult
from runtime.claim_runtime import ObservationClaim, StateDeltaClaim, _clamp


class ClaimProducingAdapter:
    """Bridge from legacy VerifierResult to the new Claim pipeline.

    Maps old verifier output into ObservationClaims suitable for ClaimAdjudicator.
    Existing verifiers work unchanged; adapter translates their results.

    Section 17.6: Universal wrapper with explicit metadata requirement.
    """

    LEGACY_SOURCE_FAMILY = "legacy_unknown"
    LEGACY_CONFIDENCE_CAP = 0.5

    def __init__(self, *, source_family_override: str | None = None) -> None:
        self._source_family_override = source_family_override

    def adapt(
        self,
        *,
        result: VerifierResult,
        claim: StateDeltaClaim,
        observation_id: str = "",
        frame_id: int | None = None,
        roi_id: str = "",
        graph_node_refs: list[str] | None = None,
    ) -> ObservationClaim:
        source_family = self._resolve_source_family(result)
        confidence_cap = self.LEGACY_CONFIDENCE_CAP if source_family == self.LEGACY_SOURCE_FAMILY else 1.0
        signal_quality = _clamp(result.confidence * confidence_cap)

        alt_support = any(s.supports_ok and s.confidence > 0.6 for s in result.alternative_signals)
        if result.ok:
            polarity = "support"
        elif alt_support:
            polarity = "support"
            signal_quality = _clamp(signal_quality * 0.7)
        else:
            polarity = "refute"

        return ObservationClaim(
            observation_id=observation_id or f"obs_{claim.claim_id}_{result.verifier_id}",
            claim_id=claim.claim_id,
            source_family=source_family,
            polarity=polarity,
            signal_quality=signal_quality,
            frame_id=frame_id or result.frame_id,
            roi_id=roi_id or (result.roi_ids[0] if result.roi_ids else ""),
            graph_node_refs=graph_node_refs or [],
            verifier_id=result.verifier_id,
            confidence=result.confidence,
            metadata={
                "adapted_from": "VerifierResult",
                "false_negative_likelihood": result.false_negative_likelihood,
                "re_verify_recommended": result.re_verify_recommended,
                "alternative_signal_count": len(result.alternative_signals),
            },
        )

    def adapt_to_skill_result_update(
        self,
        *,
        result: VerifierResult,
        claim: StateDeltaClaim,
    ) -> dict[str, Any]:
        return {
            "claim_id": claim.claim_id,
            "claim_status": claim.status,
            "verifier_ok": result.ok,
            "verifier_confidence": result.confidence,
            "false_negative_likelihood": result.false_negative_likelihood,
        }

    def _resolve_source_family(self, result: VerifierResult) -> str:
        if self._source_family_override:
            return self._source_family_override
        known_verifiers = {
            "observation_graph_ui": "ui_graph",
            "navigation_progress": "navigation",
            "combat_danger_cleared": "combat_danger",
        }
        return known_verifiers.get(result.verifier_id, self.LEGACY_SOURCE_FAMILY)
