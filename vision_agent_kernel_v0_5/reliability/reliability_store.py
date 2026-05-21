from __future__ import annotations

import json
import math
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


# --- Wilson lower bound ---

def _wilson(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    phat = successes / total
    denom = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    return max(0.0, min(1.0, (centre - margin) / denom))


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


# --- ContextKeyBuilder (Section 17.8) ---

@dataclass(frozen=True, slots=True)
class ContextDimensions:
    capsule_id: str = ""
    skill_id: str = ""
    screen_state: str = ""
    mission_phase: str = ""
    target_class: str = ""
    profile_bucket: str = ""
    game_specific: str = ""


class ContextKeyBuilder:
    SOURCE_MAP = {
        "capsule_id": "capsule_id",
        "skill_id": "skill_id",
        "screen_state": "screen_state",
        "mission_phase": "mission_phase",
        "target_class": "target_class",
        "profile_bucket": "profile_bucket",
        "game_specific": "game_specific",
    }

    def build(self, context: dict[str, str], level: int) -> tuple[str, ...]:
        if level == 0:
            return ("global",)
        parts: list[str] = []
        if level >= 1:
            parts.append(context.get("capsule_id", ""))
            parts.append(context.get("skill_id", ""))
        if level >= 2:
            parts.append(context.get("screen_state", ""))
            parts.append(context.get("mission_phase", ""))
        if level >= 3:
            parts.append(context.get("target_class", ""))
        if level >= 4:
            parts.append(context.get("profile_bucket", ""))
        if level >= 5:
            parts.append(context.get("game_specific", ""))
        return tuple(parts)

    def parse(self, raw: dict[str, str]) -> ContextDimensions:
        return ContextDimensions(
            capsule_id=raw.get("capsule_id", ""),
            skill_id=raw.get("skill_id", ""),
            screen_state=raw.get("screen_state", ""),
            mission_phase=raw.get("mission_phase", ""),
            target_class=raw.get("target_class", ""),
            profile_bucket=raw.get("profile_bucket", ""),
            game_specific=raw.get("game_specific", ""),
        )


# --- Layer 1: VerifierReliability (Section 7.1) ---

@dataclass(frozen=True, slots=True)
class VerifierReliabilityEntry:
    verifier_id: str
    source_family: str
    context_key: tuple[str, ...]
    support_correct: int = 0
    support_wrong: int = 0
    refute_correct: int = 0
    refute_wrong: int = 0
    contaminated_count: int = 0
    total: int = 0
    false_positive_estimate: float = 0.0
    false_negative_estimate: float = 0.0
    last_updated: float = 0.0

    @property
    def wilson(self) -> float:
        correct = self.support_correct + self.refute_correct
        return _wilson(correct, self.total)

    @property
    def false_positive_rate(self) -> float:
        return self.support_wrong / max(1, self.total)

    @property
    def false_negative_rate(self) -> float:
        return self.refute_wrong / max(1, self.total)


class VerifierReliability:
    def __init__(self, context_key_builder: ContextKeyBuilder | None = None, default_level: int = 2) -> None:
        self._builder = context_key_builder or ContextKeyBuilder()
        self._default_level = default_level
        self._entries: dict[tuple[str, str, tuple[str, ...]], VerifierReliabilityEntry] = {}

    def record(
        self,
        verifier_id: str,
        source_family: str,
        context: dict[str, str],
        polarity: Literal["support", "refute"],
        was_correct: bool,
    ) -> VerifierReliabilityEntry:
        ctx_key = self._builder.build(context, self._default_level)
        key = (verifier_id, source_family, ctx_key)
        entry = self._entries.get(key, VerifierReliabilityEntry(
            verifier_id=verifier_id, source_family=source_family, context_key=ctx_key,
        ))
        total = entry.total + 1
        if polarity == "support":
            support_correct = entry.support_correct + (1 if was_correct else 0)
            support_wrong = entry.support_wrong + (0 if was_correct else 1)
            entry = VerifierReliabilityEntry(
                verifier_id=verifier_id, source_family=source_family, context_key=ctx_key,
                support_correct=support_correct, support_wrong=support_wrong,
                refute_correct=entry.refute_correct, refute_wrong=entry.refute_wrong,
                total=total, last_updated=time.time(),
            )
        else:
            refute_correct = entry.refute_correct + (1 if was_correct else 0)
            refute_wrong = entry.refute_wrong + (0 if was_correct else 1)
            entry = VerifierReliabilityEntry(
                verifier_id=verifier_id, source_family=source_family, context_key=ctx_key,
                support_correct=entry.support_correct, support_wrong=entry.support_wrong,
                refute_correct=refute_correct, refute_wrong=refute_wrong,
                total=total, last_updated=time.time(),
            )
        self._entries[key] = entry
        return entry

    def record_contaminated(self, verifier_id: str, source_family: str, context: dict[str, str]) -> VerifierReliabilityEntry:
        ctx_key = self._builder.build(context, self._default_level)
        key = (verifier_id, source_family, ctx_key)
        entry = self._entries.get(key, VerifierReliabilityEntry(
            verifier_id=verifier_id, source_family=source_family, context_key=ctx_key,
        ))
        entry = VerifierReliabilityEntry(
            verifier_id=verifier_id, source_family=source_family, context_key=ctx_key,
            support_correct=entry.support_correct, support_wrong=entry.support_wrong,
            refute_correct=entry.refute_correct, refute_wrong=entry.refute_wrong,
            contaminated_count=entry.contaminated_count + 1,
            total=entry.total, last_updated=time.time(),
        )
        self._entries[key] = entry
        return entry

    def get(self, verifier_id: str, source_family: str, context: dict[str, str]) -> VerifierReliabilityEntry | None:
        ctx_key = self._builder.build(context, self._default_level)
        return self._entries.get((verifier_id, source_family, ctx_key))

    def get_reliability(self, verifier_id: str, source_family: str, context: dict[str, str]) -> float:
        entry = self.get(verifier_id, source_family, context)
        if entry is None or entry.total < 3:
            return 0.5  # unknown, neutral prior
        return entry.wilson


# --- Layer 2: RecipeReliability (Section 7.1) ---

@dataclass(frozen=True, slots=True)
class RecipeReliabilityEntry:
    claim_type: str
    recipe_id: str
    capsule_id: str
    context_key: tuple[str, ...]
    adjudicated_verified: int = 0
    adjudicated_rejected: int = 0
    delayed_audit_matched: int = 0
    delayed_audit_mismatch: int = 0
    disputed_count: int = 0
    uncertain_count: int = 0
    total: int = 0
    last_updated: float = 0.0

    @property
    def wilson(self) -> float:
        return _wilson(self.adjudicated_verified + self.delayed_audit_matched, self.total)

    @property
    def disputed_rate(self) -> float:
        return self.disputed_count / max(1, self.total)


class RecipeReliability:
    def __init__(self, context_key_builder: ContextKeyBuilder | None = None, default_level: int = 2) -> None:
        self._builder = context_key_builder or ContextKeyBuilder()
        self._default_level = default_level
        self._entries: dict[tuple[str, str, str, tuple[str, ...]], RecipeReliabilityEntry] = {}

    def record_verified(
        self, claim_type: str, recipe_id: str, capsule_id: str, context: dict[str, str],
    ) -> RecipeReliabilityEntry:
        return self._update(claim_type, recipe_id, capsule_id, context, "verified")

    def record_rejected(
        self, claim_type: str, recipe_id: str, capsule_id: str, context: dict[str, str],
    ) -> RecipeReliabilityEntry:
        return self._update(claim_type, recipe_id, capsule_id, context, "rejected")

    def record_audit(
        self, claim_type: str, recipe_id: str, capsule_id: str, context: dict[str, str], matched: bool,
    ) -> RecipeReliabilityEntry:
        return self._update(claim_type, recipe_id, capsule_id, context, "audit_matched" if matched else "audit_mismatch")

    def record_uncertain(
        self, claim_type: str, recipe_id: str, capsule_id: str, context: dict[str, str],
    ) -> RecipeReliabilityEntry:
        return self._update(claim_type, recipe_id, capsule_id, context, "uncertain")

    def get(
        self, claim_type: str, recipe_id: str, capsule_id: str, context: dict[str, str],
    ) -> RecipeReliabilityEntry | None:
        ctx_key = self._builder.build(context, self._default_level)
        return self._entries.get((claim_type, recipe_id, capsule_id, ctx_key))

    def get_reliability(
        self, claim_type: str, recipe_id: str, capsule_id: str, context: dict[str, str],
    ) -> float:
        entry = self.get(claim_type, recipe_id, capsule_id, context)
        if entry is None or entry.total < 3:
            return 0.5
        return entry.wilson

    def _update(
        self,
        claim_type: str,
        recipe_id: str,
        capsule_id: str,
        context: dict[str, str],
        event: str,
    ) -> RecipeReliabilityEntry:
        ctx_key = self._builder.build(context, self._default_level)
        key = (claim_type, recipe_id, capsule_id, ctx_key)
        entry = self._entries.get(key, RecipeReliabilityEntry(
            claim_type=claim_type, recipe_id=recipe_id,
            capsule_id=capsule_id, context_key=ctx_key,
        ))
        total = entry.total + 1
        kw: dict[str, int] = {}
        if event == "verified":
            kw["adjudicated_verified"] = entry.adjudicated_verified + 1
        elif event == "rejected":
            kw["adjudicated_rejected"] = entry.adjudicated_rejected + 1
        elif event == "audit_matched":
            kw["delayed_audit_matched"] = entry.delayed_audit_matched + 1
        elif event == "audit_mismatch":
            kw["delayed_audit_mismatch"] = entry.delayed_audit_mismatch + 1
        elif event == "uncertain":
            kw["uncertain_count"] = entry.uncertain_count + 1
        entry = RecipeReliabilityEntry(
            claim_type=claim_type, recipe_id=recipe_id, capsule_id=capsule_id,
            context_key=ctx_key, total=total, last_updated=time.time(),
            adjudicated_verified=kw.get("adjudicated_verified", entry.adjudicated_verified),
            adjudicated_rejected=kw.get("adjudicated_rejected", entry.adjudicated_rejected),
            delayed_audit_matched=kw.get("delayed_audit_matched", entry.delayed_audit_matched),
            delayed_audit_mismatch=kw.get("delayed_audit_mismatch", entry.delayed_audit_mismatch),
            disputed_count=entry.disputed_count,
            uncertain_count=kw.get("uncertain_count", entry.uncertain_count),
        )
        self._entries[key] = entry
        return entry


# --- Layer 3: SkillClaimReliability (Section 7.1) ---

@dataclass(frozen=True, slots=True)
class SkillClaimReliabilityEntry:
    skill_id: str
    claim_type: str
    recipe_id: str
    context_key: tuple[str, ...]
    claim_verified: int = 0
    claim_rejected: int = 0
    claim_demoted: int = 0
    delayed_audit_matched: int = 0
    delayed_audit_mismatch: int = 0
    cascade_invalidated: int = 0
    total: int = 0
    last_updated: float = 0.0

    @property
    def wilson(self) -> float:
        return _wilson(self.claim_verified + self.delayed_audit_matched, self.total)

    @property
    def demotion_rate(self) -> float:
        return self.claim_demoted / max(1, self.total)


class SkillClaimReliability:
    def __init__(self, context_key_builder: ContextKeyBuilder | None = None, default_level: int = 3) -> None:
        self._builder = context_key_builder or ContextKeyBuilder()
        self._default_level = default_level
        self._entries: dict[tuple[str, str, str, tuple[str, ...]], SkillClaimReliabilityEntry] = {}

    def record(
        self,
        skill_id: str,
        claim_type: str,
        recipe_id: str,
        context: dict[str, str],
        event: Literal["verified", "rejected", "demoted", "audit_matched", "audit_mismatch", "cascade_invalidated"],
    ) -> SkillClaimReliabilityEntry:
        ctx_key = self._builder.build(context, self._default_level)
        key = (skill_id, claim_type, recipe_id, ctx_key)
        entry = self._entries.get(key, SkillClaimReliabilityEntry(
            skill_id=skill_id, claim_type=claim_type,
            recipe_id=recipe_id, context_key=ctx_key,
        ))
        total = entry.total + 1
        kw: dict[str, int] = {}
        if event == "verified":
            kw["claim_verified"] = entry.claim_verified + 1
        elif event == "rejected":
            kw["claim_rejected"] = entry.claim_rejected + 1
        elif event == "demoted":
            kw["claim_demoted"] = entry.claim_demoted + 1
        elif event == "audit_matched":
            kw["delayed_audit_matched"] = entry.delayed_audit_matched + 1
        elif event == "audit_mismatch":
            kw["delayed_audit_mismatch"] = entry.delayed_audit_mismatch + 1
        elif event == "cascade_invalidated":
            kw["cascade_invalidated"] = entry.cascade_invalidated + 1
        entry = SkillClaimReliabilityEntry(
            skill_id=skill_id, claim_type=claim_type, recipe_id=recipe_id,
            context_key=ctx_key, total=total, last_updated=time.time(),
            claim_verified=kw.get("claim_verified", entry.claim_verified),
            claim_rejected=kw.get("claim_rejected", entry.claim_rejected),
            claim_demoted=kw.get("claim_demoted", entry.claim_demoted),
            delayed_audit_matched=kw.get("delayed_audit_matched", entry.delayed_audit_matched),
            delayed_audit_mismatch=kw.get("delayed_audit_mismatch", entry.delayed_audit_mismatch),
            cascade_invalidated=kw.get("cascade_invalidated", entry.cascade_invalidated),
        )
        self._entries[key] = entry
        return entry

    def get(
        self, skill_id: str, claim_type: str, recipe_id: str, context: dict[str, str],
    ) -> SkillClaimReliabilityEntry | None:
        ctx_key = self._builder.build(context, self._default_level)
        return self._entries.get((skill_id, claim_type, recipe_id, ctx_key))

    def get_reliability(
        self, skill_id: str, claim_type: str, recipe_id: str, context: dict[str, str],
    ) -> float:
        entry = self.get(skill_id, claim_type, recipe_id, context)
        if entry is None or entry.total < 3:
            return 0.0  # Zero-sample: Option A from Section 16.3
        return entry.wilson


# --- Combined Three-Layer Store (Section 7.2) ---

@dataclass(frozen=True, slots=True)
class ExecutionTrust:
    recipe_trust: float
    skill_claim_trust: float
    dependency_health: float
    overall: float

    @staticmethod
    def compute(
        recipe_trust: float,
        skill_claim_trust: float,
        dependency_health: float = 1.0,
    ) -> ExecutionTrust:
        overall = min(recipe_trust, skill_claim_trust, dependency_health)
        return ExecutionTrust(
            recipe_trust=recipe_trust,
            skill_claim_trust=skill_claim_trust,
            dependency_health=dependency_health,
            overall=overall,
        )


class ThreeLayerReliabilityStore:
    """Unified three-layer reliability with JSONL event log persistence (Section 17.7)."""

    def __init__(self, persistence_path: str = "") -> None:
        self.verifier = VerifierReliability()
        self.recipe = RecipeReliability()
        self.skill_claim = SkillClaimReliability()
        self._persistence_path = persistence_path
        self._drift_demoted_skills: set[str] = set()
        if persistence_path:
            self._load_from_jsonl()

    def record_adjudication(
        self,
        *,
        skill_id: str,
        claim_type: str,
        recipe_id: str,
        capsule_id: str,
        verifier_id: str,
        source_family: str,
        context: dict[str, str],
        adjudication_status: str,
        was_correct: bool,
    ) -> None:
        polarity: Literal["support", "refute"] = "support" if adjudication_status == "verified" else "refute"
        self.verifier.record(verifier_id, source_family, context, polarity, was_correct)

        if adjudication_status == "verified":
            self.recipe.record_verified(claim_type, recipe_id, capsule_id, context)
            self.skill_claim.record(skill_id, claim_type, recipe_id, context, "verified")
        elif adjudication_status == "rejected":
            self.recipe.record_rejected(claim_type, recipe_id, capsule_id, context)
            self.skill_claim.record(skill_id, claim_type, recipe_id, context, "rejected")
        elif adjudication_status == "demoted":
            self.skill_claim.record(skill_id, claim_type, recipe_id, context, "demoted")
        else:
            self.recipe.record_uncertain(claim_type, recipe_id, capsule_id, context)

        if self._persistence_path:
            self._append_event({
                "type": "adjudication",
                "skill_id": skill_id, "claim_type": claim_type, "recipe_id": recipe_id,
                "verifier_id": verifier_id, "source_family": source_family,
                "adjudication_status": adjudication_status, "was_correct": was_correct,
                "context": context, "timestamp": time.time(),
            })

    def record_audit(
        self,
        *,
        skill_id: str,
        claim_type: str,
        recipe_id: str,
        capsule_id: str,
        context: dict[str, str],
        matched: bool,
    ) -> None:
        self.recipe.record_audit(claim_type, recipe_id, capsule_id, context, matched)
        self.skill_claim.record(
            skill_id, claim_type, recipe_id, context,
            "audit_matched" if matched else "audit_mismatch",
        )
        if self._persistence_path:
            self._append_event({
                "type": "audit",
                "skill_id": skill_id, "claim_type": claim_type, "recipe_id": recipe_id,
                "capsule_id": capsule_id, "matched": matched,
                "context": context, "timestamp": time.time(),
            })

    def mark_version_drift(self, skill_id: str) -> None:
        self._drift_demoted_skills.add(skill_id)

    def is_drift_demoted(self, skill_id: str) -> bool:
        return skill_id in self._drift_demoted_skills

    def execution_trust(
        self,
        *,
        skill_id: str,
        claim_type: str,
        recipe_id: str,
        capsule_id: str,
        context: dict[str, str],
        dependency_health: float = 1.0,
    ) -> ExecutionTrust:
        recipe_trust = self.recipe.get_reliability(claim_type, recipe_id, capsule_id, context)
        skill_trust = self.skill_claim.get_reliability(skill_id, claim_type, recipe_id, context)
        if skill_id in self._drift_demoted_skills:
            skill_trust *= 0.5
        return ExecutionTrust.compute(
            recipe_trust=recipe_trust,
            skill_claim_trust=skill_trust,
            dependency_health=dependency_health,
        )

    def _append_event(self, event: dict[str, Any]) -> None:
        try:
            with open(self._persistence_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _load_from_jsonl(self) -> None:
        if not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._replay_event(event)
        except OSError:
            pass

    def _replay_event(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        ctx = event.get("context", {})
        if etype == "adjudication":
            was_correct = event.get("was_correct", False)
            adj_status = event.get("adjudication_status", "uncertain")
            polarity: Literal["support", "refute"] = "support" if adj_status == "verified" else "refute"
            self.verifier.record(
                event.get("verifier_id", ""), event.get("source_family", ""), ctx, polarity, was_correct,
            )
            if adj_status == "verified":
                self.recipe.record_verified(
                    event.get("claim_type", ""), event.get("recipe_id", "default"),
                    event.get("capsule_id", ""), ctx,
                )
                self.skill_claim.record(
                    event.get("skill_id", ""), event.get("claim_type", ""),
                    event.get("recipe_id", "default"), ctx, "verified",
                )
            elif adj_status == "rejected":
                self.recipe.record_rejected(
                    event.get("claim_type", ""), event.get("recipe_id", "default"),
                    event.get("capsule_id", ""), ctx,
                )
                self.skill_claim.record(
                    event.get("skill_id", ""), event.get("claim_type", ""),
                    event.get("recipe_id", "default"), ctx, "rejected",
                )
        elif etype == "audit":
            matched = event.get("matched", False)
            self.recipe.record_audit(
                event.get("claim_type", ""), event.get("recipe_id", "default"),
                event.get("capsule_id", ""), ctx, matched,
            )
            self.skill_claim.record(
                event.get("skill_id", ""), event.get("claim_type", ""),
                event.get("recipe_id", "default"), ctx,
                "audit_matched" if matched else "audit_mismatch",
            )
