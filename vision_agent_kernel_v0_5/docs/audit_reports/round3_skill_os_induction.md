# Round 3 (FINAL) Audit Report: Skill OS and Skill Induction Pipeline

**Auditor:** Senior Code Auditor (Automated)
**Date:** 2026-05-27
**Scope:** `skills/` package (schema.py, registry.py, applicability.py, promotion.py), `learning/skill_induction/` package (trace_recorder.py, episode_segmenter.py, anchor_binder.py, promotion_gate.py, pipeline.py), test files
**Tests:** 58/58 passing

---

## Executive Summary

Both CRITICAL bugs from Round 2 are **verified fixed**:

1. **N1 (AttributeError on `c.claim_id`): FIXED.** The verifier check now uses `c.claim_type` (promotion.py line 73).
2. **N2 (Verifier check only covered terminal claims): FIXED.** The check now iterates ALL `produced_claims` regardless of `claim_role` (promotion.py lines 72-75). Verified: a skill with `claim_role="local"` and empty `verifier_recipe` is correctly blocked from candidate tier.

**The verifier check is now correct and effectively blocks skills without verifiers.** No regressions detected in the 58 existing tests.

Four issues remain from previous rounds (2 HIGH, 2 MEDIUM carried forward). One MEDIUM issue (N3 -- evaluate/try_promote disagreement) remains unfixed. No new issues found.

---

## Fix Verification Matrix

| Fix | Status | Evidence |
|-----|--------|----------|
| F1: `can_promote_to()` takes `successes`/`failures` params | VERIFIED | Signature at promotion.py:38-42; used for stable (line 86) and trusted (line 97) |
| F2: Verifier check on ALL produced_claims (not just terminal) | VERIFIED | promotion.py:72-75 iterates all claims; no `claim_role` filter. Runtime test confirms `claim_role="local"` with empty verifier is blocked |
| F3: `claim_id` bug fixed to `claim_type` | VERIFIED | promotion.py:73 uses `c.claim_type` |
| F4: `PromotionGate` passes `successes`/`failures` to `can_promote_to()` | VERIFIED | promotion_gate.py:43 passes through |
| F5: `PromotionGate.evaluate()` no longer duplicates Wilson check | VERIFIED | promotion_gate.py:61-82 delegates entirely to `can_promote_to()` |
| F6: Test helper `_claim()` includes `verifier_recipe` | VERIFIED | test_skill_os_mvp.py:32 sets `verifier_recipe="verify_dialogue"` |

---

## Remaining Findings

### HIGH

#### H2 (CARRIED FORWARD): Pipeline cannot promote more than one tier in a single `process_session` call

**File:** `learning/skill_induction/pipeline.py`
**Lines:** 69-79

The pipeline calls `gate.try_promote(result.skill, target_tier)` once with the full target tier. Since `AnchorBinder` creates skills at `draft` tier, requesting `target_tier="candidate"` triggers `can_promote_to()`'s skip-prevention rule (promotion.py line 54), returning `(False, "cannot skip tiers")`. The skill is registered at draft but `skills_produced=0`.

**Verified at runtime:** `process_session(session, target_tier="candidate")` returns `skills_produced=0` with promotion failure.

**Fix:** Implement iterative promotion: for each tier between current and target, attempt promotion sequentially. Stop at the first failure.

---

#### H3 (CARRIED FORWARD): Coordinate-only check is tier-based, not content-based

**File:** `learning/skill_induction/promotion_gate.py`
**Lines:** 47-52

`try_promote()` blocks ALL skills at `raw_trace` tier (line 48: `if skill.tier == "raw_trace"`), regardless of whether the skill actually has coordinate-only steps. The check is purely tier-label-based. A `draft` tier skill with coordinate-only steps (empty targets, no anchors) can promote freely through `can_promote_to()`.

**Mitigated by current architecture:** `AnchorBinder` correctly assigns `raw_trace` only to coordinate-only episodes and `draft` to anchored episodes. The issue would surface if skills enter the pipeline from other sources.

**Fix:** Add a `coordinate_only` boolean flag to `SkillDef`, or inspect step content in `can_promote_to()`.

---

### MEDIUM

#### N3 (CARRIED FORWARD): `PromotionGate.evaluate()` inconsistent with `try_promote()` for raw_trace skills

**File:** `learning/skill_induction/promotion_gate.py`
**Lines:** 61-82 vs 47-52

`evaluate()` iterates tiers using `can_promote_to()` only. It does NOT apply the induction-specific `raw_trace` block that `try_promote()` applies at lines 48-52.

**Verified at runtime:**
- `evaluate(skill_at_raw_trace)` returns `"draft"`
- `try_promote(skill_at_raw_trace, "draft")` returns `PromotionResult(success=False, ...)`

The two public methods disagree on whether a raw_trace skill can promote.

**Impact:** Any caller that uses `evaluate()` to determine promotability before calling `try_promote()` will get incorrect results for raw_trace skills.

**Fix:** Apply the same raw_trace block in `evaluate()`, or refactor to move the block into `can_promote_to()` itself.

---

#### M3 (CARRIED FORWARD): `AnchorBinder._infer_claim()` only covers dialogue and combat

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 99-114

Claim inference returns `None` for any screen state that does not contain "dialogue", "dialog", or "combat". Skills produced from inventory, map, menu, or other contexts will have empty `produced_claims` and can never promote past `experimental`.

The combat claim (`claim_type="combat_action_completed"`) also lacks a `verifier_recipe`, which means combat skills will be correctly blocked from promoting to `candidate` until a verifier is manually added. This is actually correct safety behavior but could be documented.

**Fix:** Add a generic fallback claim inference or make claim inference pluggable.

---

#### M5 (CARRIED FORWARD): Episode segmenter produces episodes with empty `screen_state`

**File:** `learning/skill_induction/episode_segmenter.py`
**Lines:** 42-43

When the first action has `screen_state=""`, an episode with empty `screen_state` is created. Skills derived from such episodes get empty `applicability.screen_states`, making them "universal" matchers that apply to any screen context.

**Fix:** Skip or merge episodes with empty screen states, or inherit from the session-level state.

---

#### M4 (CARRIED FORWARD): O(n*m) tier lookup in `find_by_tier()` and `find_applicable()`

**File:** `skills/registry.py`
**Lines:** 59-67, 80-97

Both methods call `tier_order.index(s.tier)` inside iteration loops. The tier order list is also duplicated inline in both methods (see L2).

**Fix:** Use a pre-built dict or import `_TIER_INDEX` from `skills.promotion`.

---

### LOW

#### L1 (CARRIED FORWARD): `PromotionGate.evaluate()` accesses private `_TIER_ORDER` and `_TIER_INDEX`

**File:** `learning/skill_induction/promotion_gate.py`
**Line:** 71

Imports private symbols from `skills.promotion`.

**Fix:** Export public constants or provide a `next_tier()` helper.

---

#### L2 (CARRIED FORWARD): Duplicate tier order list in `registry.py`

**File:** `skills/registry.py`
**Lines:** 59, 80

The full tier ordering list is defined inline in both `find_by_tier()` and `find_applicable()` instead of being a shared constant.

**Fix:** Define once at module level or import from `skills.promotion`.

---

#### L3 (CARRIED FORWARD): Unusual list-comprehension pattern for fallbacks

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 72-73

```python
fallbacks=tuple(SkillFallback(recovery_recipe="UI_LOST_RECOVERY")
                for _ in [1]) if not coordinate_only else (),
```

This could be simplified to `(SkillFallback(recovery_recipe="UI_LOST_RECOVERY"),) if not coordinate_only else ()`.

---

#### L4 (CARRIED FORWARD): No `__all__` exports in package init files

**Files:** `skills/__init__.py`, `learning/skill_induction/__init__.py`

---

## Resolved Issues (for reference)

| ID | Round | Severity | Resolution |
|----|-------|----------|------------|
| C1/N1 | R1/R2 | CRITICAL | **FIXED.** `c.claim_id` -> `c.claim_type`; check covers ALL claims |
| C1/N2 | R2 | CRITICAL | **FIXED.** Verifier check no longer filters by `claim_role` |
| H1 | R1 | HIGH | **FIXED.** `can_promote_to()` accepts `successes`/`failures`; Wilson check in stable/trusted |
| M2 | R1 | MEDIUM | No change needed -- `type: ignore` is acceptable for extensible action types |
| N4 | R2 | MEDIUM | Dead variable `has_coordinate_only` -- cosmetic, no functional impact |

---

## Test Coverage Assessment

**58 tests pass.** Coverage of the fixed paths is adequate:

- `test_experimental_to_candidate_with_claims` tests claims WITH verifiers pass (uses `_claim()` helper which now has `verifier_recipe`)
- `test_experimental_to_candidate_needs_claims` tests claims ABSENT fail
- `test_evaluate_candidate_reachable` tests claims WITH verifier_recipe can reach candidate via `evaluate()`

**Remaining test gaps:**

1. No explicit test that claims WITHOUT `verifier_recipe` are blocked from candidate (the fix is verified via runtime check in this audit, but no dedicated test exists in the test suite)
2. No test for `evaluate()` on `raw_trace` skills (N3 gap)
3. No test for `process_session(target_tier="candidate")` or higher (H2 gap)
4. No test for combat-inferred claims blocking at candidate tier

---

## Answer to Audit Questions

### Is the verifier check correct now?

**Yes.** The verifier check at `skills/promotion.py:72-77` correctly:
- Iterates ALL `produced_claims` (no `claim_role` filter)
- Uses `c.claim_type` (not the non-existent `c.claim_id`)
- Collects claims where `verifier_recipe` is falsy (empty string or None)
- Returns `(False, "claims missing verifiers: [...]")` when any claim lacks a verifier

### Does it actually block skills without verifiers?

**Yes.** Verified at runtime:
- `SkillProducedClaim("x", claim_role="terminal")` -- blocked (no verifier)
- `SkillProducedClaim("y", claim_role="local")` -- blocked (no verifier)
- `SkillProducedClaim("z", verifier_recipe="check_z")` -- passes

### Any remaining CRITICAL issues?

**No.** All CRITICAL issues from Rounds 1-2 are resolved. The highest remaining severity is HIGH (H2: pipeline multi-tier promotion, H3: tier-based coordinate check).

### Any regressions?

**No.** All 58 existing tests pass. The fixes are backward-compatible: `can_promote_to()` defaults `successes=0, failures=0`, maintaining the previous behavior for callers that don't supply these parameters.

---

## Risk Summary

| ID | Severity | Status | Component | Summary |
|----|----------|--------|-----------|---------|
| H2 | HIGH | CARRIED | pipeline | Cannot promote >1 tier in single process_session call |
| H3 | HIGH | CARRIED | promotion_gate | Coordinate-only check is tier-based, not content-based |
| N3 | MEDIUM | CARRIED | promotion_gate | evaluate() and try_promote() disagree on raw_trace |
| M3 | MEDIUM | CARRIED | anchor_binder | Claim inference only covers dialogue/combat |
| M5 | MEDIUM | CARRIED | segmenter | Empty screen_state produces universal skill |
| M4 | MEDIUM | CARRIED | registry | O(n*m) tier lookup in loop |
| L1 | LOW | CARRIED | promotion_gate | Accesses private _TIER_ORDER |
| L2 | LOW | CARRIED | registry | Duplicate tier order list |
| L3 | LOW | CARRIED | anchor_binder | Unusual list-comprehension for fallbacks |
| L4 | LOW | CARRIED | packages | No __all__ exports |

**CRITICAL count: 0** (down from 2 in Round 2)
**HIGH count: 2** (unchanged from Round 2)
**MEDIUM count: 4** (down from 6 in Round 2, N4 resolved)
**LOW count: 4** (unchanged from Round 2)
