from __future__ import annotations

from typing import Any, List, Union

from execution.verifier_base import Verifier, VerifierContext, VerifierResult, ensure_context


class AndVerifier:
    """Evaluates ALL child verifiers. Fails if any fail."""

    def __init__(self, verifiers: List[Verifier], verifier_id: str = "composed_and") -> None:
        self.verifiers = verifiers
        self.verifier_id = verifier_id

    def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
        ctx = ensure_context(context)
        results: List[VerifierResult] = []
        for v in self.verifiers:
            results.append(v.verify(ctx))

        ok = all(r.ok for r in results)
        failed_list = [r.verifier_id for r in results if not r.ok]
        
        # Minimum confidence among children, or 0.0 if empty
        confidence = min((r.confidence for r in results), default=1.0)
        
        reason = "AND verifier passed"
        if not ok:
            reason = f"AND verifier failed. Fails in sub-verifiers: {', '.join(failed_list)}"

        # Compile evidence
        evidence = {
            "composed_type": "AND",
            "sub_results": [
                {
                    "verifier_id": r.verifier_id,
                    "ok": r.ok,
                    "confidence": r.confidence,
                    "reason": r.reason,
                    "evidence": r.evidence,
                }
                for r in results
            ]
        }

        # Frame ID from first sub-result that has it
        frame_id = next((r.frame_id for r in results if r.frame_id is not None), None)

        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            frame_id=frame_id,
        )


class OrVerifier:
    """Evaluates ALL child verifiers. Passes if any pass."""

    def __init__(self, verifiers: List[Verifier], verifier_id: str = "composed_or") -> None:
        self.verifiers = verifiers
        self.verifier_id = verifier_id

    def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
        ctx = ensure_context(context)
        results: List[VerifierResult] = []
        for v in self.verifiers:
            results.append(v.verify(ctx))

        ok = any(r.ok for r in results)
        passed_list = [r.verifier_id for r in results if r.ok]
        
        # Max confidence among children, or 0.0 if empty
        confidence = max((r.confidence for r in results), default=0.0)
        
        reason = "OR verifier failed. All sub-verifiers failed."
        if ok:
            reason = f"OR verifier passed. Passes in sub-verifiers: {', '.join(passed_list)}"

        evidence = {
            "composed_type": "OR",
            "sub_results": [
                {
                    "verifier_id": r.verifier_id,
                    "ok": r.ok,
                    "confidence": r.confidence,
                    "reason": r.reason,
                    "evidence": r.evidence,
                }
                for r in results
            ]
        }

        frame_id = next((r.frame_id for r in results if r.frame_id is not None), None)

        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            frame_id=frame_id,
        )


class NotVerifier:
    """Negates the child verifier's outcome."""

    def __init__(self, verifier: Verifier, verifier_id: str = "composed_not") -> None:
        self.verifier = verifier
        self.verifier_id = verifier_id

    def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
        ctx = ensure_context(context)
        res = self.verifier.verify(ctx)

        ok = not res.ok
        confidence = res.confidence
        reason = f"NOT verifier passed (negated {res.verifier_id})"
        if not ok:
            reason = f"NOT verifier failed (negated {res.verifier_id} was True)"

        evidence = {
            "composed_type": "NOT",
            "sub_result": {
                "verifier_id": res.verifier_id,
                "ok": res.ok,
                "confidence": res.confidence,
                "reason": res.reason,
                "evidence": res.evidence,
            }
        }

        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            frame_id=res.frame_id,
        )


class VoteVerifier:
    """Passes if at least k of the child verifiers pass."""

    def __init__(self, verifiers: List[Verifier], k: int, verifier_id: str = "composed_vote") -> None:
        if k <= 0:
            raise ValueError("VoteVerifier k must be positive")
        if not verifiers:
            raise ValueError("VoteVerifier requires at least one child verifier")
        if k > len(verifiers):
            raise ValueError("VoteVerifier k cannot exceed the number of child verifiers")
        self.verifiers = verifiers
        self.k = k
        self.verifier_id = verifier_id

    def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
        ctx = ensure_context(context)
        results: List[VerifierResult] = []
        for v in self.verifiers:
            results.append(v.verify(ctx))

        passed_count = sum(1 for r in results if r.ok)
        ok = passed_count >= self.k
        passed_list = [r.verifier_id for r in results if r.ok]
        
        # Average confidence of passed verifiers
        if passed_count > 0:
            confidence = sum(r.confidence for r in results if r.ok) / passed_count
        else:
            confidence = sum(r.confidence for r in results) / len(results) if results else 0.0
            
        reason = f"VOTE failed. Required {self.k} passes, but only got {passed_count} passes."
        if ok:
            reason = f"VOTE passed. Got {passed_count}/{len(results)} passes (required {self.k}). Passes: {', '.join(passed_list)}"

        evidence = {
            "composed_type": "VOTE",
            "k": self.k,
            "passed_count": passed_count,
            "sub_results": [
                {
                    "verifier_id": r.verifier_id,
                    "ok": r.ok,
                    "confidence": r.confidence,
                    "reason": r.reason,
                    "evidence": r.evidence,
                }
                for r in results
            ]
        }

        frame_id = next((r.frame_id for r in results if r.frame_id is not None), None)

        return VerifierResult(
            ok=ok,
            verifier_id=self.verifier_id,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            frame_id=frame_id,
        )
