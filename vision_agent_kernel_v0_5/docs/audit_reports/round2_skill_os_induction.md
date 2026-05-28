# Round 2 Audit Report: Skill OS and Skill Induction Pipeline

**Auditor:** Senior Code Auditor (Automated)
**Date:** 2026-05-27
**Scope:** `skills/` package (schema.py, registry.py, applicability.py, promotion.py), `learning/skill_induction/` package (trace_recorder.py, episode_segmenter.py, anchor_binder.py, promotion_gate.py, pipeline.py), associated test files
**Tests:** 58/58 passing -- but tests do not cover the broken verifier check path

---

## Summary

The Round 1 fix for the "no verifier = no unattended" rule (C1/H1) introduced a **new CRITICAL bug**: the verifier check references `c.claim_id` which does not exist on `SkillProducedClaim`, causing an `AttributeError` at runtime when any skill with a terminal claim attempts promotion to `candidate`. The check is dead code for the default `claim_role="local"` path, meaning the original C1 safety gap persists for the common case. Additionally, a new inconsistency between `evaluate()` and `try_promote()` was introduced by the raw_trace block.

Of the 6 carried-forward issues, all 6 remain unfixed.

---

## Findings

### CRITICAL

#### N1 (NEW): `can_promote_to()` verifier check crashes with `AttributeError` on terminal claims

**File:** `skills/promotion.py`
**Lines:** 72-73

```python
missing_verifiers = [
    c.claim_id for c in skill.produced_claims
    if c.claim_role == "terminal" and not c.verifier_recipe
]
```

`SkillProducedClaim` (defined in `skills/schema.py:46-51`) has fields: `claim_type`, `target`, `claim_role`, `verifier_recipe`. There is no `claim_id` attribute. This line raises `AttributeError: 'SkillProducedClaim' object has no attribute 'claim_id'` whenever a skill with `claim_role="terminal"` attempts promotion to `candidate`.

**Verified at runtime:** A skill with `produced_claims=(SkillProducedClaim(claim_type="x", claim_role="terminal"),)` and `tier="experimental"` crashes when calling `can_promote_to(skill, "candidate")`.

**Impact:** Complete promotion failure for any skill that has terminal claims. The error message would be opaque to callers.

**Fix:** Change `c.claim_id` to `c.claim_type` (or add a computed `claim_id` property to `SkillProducedClaim`).

---

#### N2 (NEW): Original C1 safety gap persists for non-terminal claims

**File:** `skills/promotion.py`
**Lines:** 67-78

The Round 1 fix only checks verifier recipes on claims where `claim_role == "terminal"`. However, the default `claim_role` is `"local"` (schema.py line 50). The anchor binder never produces claims with `claim_role="terminal"` -- it produces `"dependency"` for dialogue and `"local"` for combat (anchor_binder.py lines 103, 111). This means:

1. A skill with default `claim_role="local"` and empty `verifier_recipe` sails through the candidate check.
2. The `SkillProducedClaim` created by the binder for combat has no verifier_recipe at all.

**Verified at runtime:** `SkillDef` with `produced_claims=(SkillProducedClaim(claim_type="test"),)` (defaults: `claim_role="local"`, `verifier_recipe=""`) returns `(True, "has produced claims with verifiers")` for candidate promotion, even though no verifier exists.

**Impact:** The "no verifier = no unattended" hard rule remains effectively unenforced for the vast majority of skills that will pass through the pipeline.

**Fix:** The verifier check should cover ALL produced claims for candidate+ promotion, not just terminal ones. The docstring says "Skills without verifiers on terminal claims cannot be unattended" but the intent is clearly that ALL claims need verifiers for promotion to unattended tiers. At minimum, change the condition to check all claims or require explicit opt-out.

---

### HIGH

#### H2 (UNFIXED): Pipeline cannot promote more than one tier in a single `process_session` call

**File:** `learning/skill_induction/pipeline.py`
**Lines:** 69-79

The pipeline calls `gate.try_promote(result.skill, target_tier)` once with the full target tier. Since `AnchorBinder` creates skills at `draft` tier, requesting `candidate` (two tiers above) triggers `can_promote_to()`'s skip-prevention rule, returning `(False, "cannot skip tiers")`. The skill is registered but `skills_produced=0`.

**Verified at runtime:** `process_session(session, target_tier="candidate")` returns `skills_produced=0` with promotion_results showing the tier-skip rejection.

**Fix:** Implement iterative promotion: for each tier between current and target, attempt promotion sequentially. Stop at the first failure.

---

#### H3 (UNFIXED): Coordinate-only check is tier-based, not content-based

**Files:** `skills/promotion.py`, `learning/skill_induction/promotion_gate.py`

`PromotionGate.try_promote()` blocks promotion for ALL skills at `raw_trace` tier (line 48: `if skill.tier == "raw_trace"`), regardless of whether the skill actually has coordinate-only steps. Conversely, a skill at `draft` tier with coordinate-only steps (e.g., empty targets) can promote freely. The check is based purely on the tier label, not on step content.

**Fix:** Add a `coordinate_only` boolean to `SkillDef`, or check step content (e.g., whether targets reference anchors vs coordinates) in `can_promote_to()`.

---

### MEDIUM

#### N3 (NEW): `PromotionGate.evaluate()` is inconsistent with `try_promote()` for raw_trace skills

**File:** `learning/skill_induction/promotion_gate.py`
**Lines:** 61-82

`evaluate()` iterates tiers using `can_promote_to()` and returns the highest reachable tier. It does NOT apply the induction-specific raw_trace block that `try_promote()` applies at lines 48-52. As a result:

- `evaluate(skill_at_raw_trace)` returns `"draft"` (because `can_promote_to()` allows it)
- `try_promote(skill_at_raw_trace, "draft")` returns `PromotionResult(success=False, ...)`

**Verified at runtime:** Confirmed the discrepancy.

**Impact:** Callers using `evaluate()` to determine promotability will get incorrect results for raw_trace skills. The two public methods of `PromotionGate` disagree.

**Fix:** Apply the same raw_trace block in `evaluate()` before or after the `can_promote_to()` loop, or move the block into `can_promote_to()` itself so both methods are consistent.

---

#### M1 (UNFIXED): `TraceSession` is mutable -- no data integrity protection

**File:** `learning/skill_induction/trace_recorder.py`
**Lines:** 28-38

`TraceSession` uses `@dataclass(slots=True)` without `frozen=True`. External code can mutate `actions`, `success`, `ended_at`, and `screen_state` at any time. The `actions` list can be modified with incorrectly typed data.

**Fix:** Use `frozen=True` with a builder pattern, or add guards to mutation paths.

---

#### M2 (UNFIXED): `AnchorBinder._normalize_action_type()` allows unknown action types through

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 83-97

Unknown action types are returned unchanged (line 97: `return mapping.get(action_type, action_type)`). This violates the `StepAction` Literal constraint in `schema.py`. The `type: ignore` comment on line 45 suppresses the type error.

**Fix:** Raise `ValueError` for unknown types, or map them to a safe default like `"interact"`.

---

#### M3 (UNFIXED): `AnchorBinder._infer_claim()` only covers dialogue and combat

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 99-114

Claim inference returns `None` for any screen state that does not contain "dialogue", "dialog", or "combat". Skills produced from inventory, map, menu, or other contexts will have empty `produced_claims` and can never promote past `experimental`.

**Fix:** Add a generic fallback claim inference (e.g., `f"{state}_action_completed"`) or make claim inference pluggable via a strategy callback.

---

#### N4 (NEW): Dead variable `has_coordinate_only` in `AnchorBinder.bind()`

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 40, 54

`has_coordinate_only` is set to `True` on line 54 when an action has coordinates but no anchor, but is never read. The actual coordinate-only determination uses `len(unique_anchors) == 0` on line 57. This means a mixed episode (some anchored steps + some coordinate-only steps) is treated as fully anchored, which may be incorrect -- coordinate-only steps in an otherwise-anchored skill could fail at runtime.

**Fix:** Either remove the dead variable, or use it to flag mixed episodes (e.g., add a `has_unanchored_steps` metadata flag to the skill).

---

#### M4 (CARRIED FORWARD): `find_by_tier()` and `find_applicable()` use `list.index()` inside loops

**File:** `skills/registry.py`
**Lines:** 59-67, 80-97

Both methods call `tier_order.index(s.tier)` inside iteration loops. The `tier_order` list is also duplicated in both methods (see L2).

**Fix:** Use a pre-built dict mapping or import `_TIER_INDEX` from `skills.promotion`.

---

#### M5 (CARRIED FORWARD): Episode segmenter produces episodes with empty `screen_state`

**File:** `learning/skill_induction/episode_segmenter.py`
**Lines:** 42-43

When the first action has `screen_state=""`, an episode with empty `screen_state` is created. Skills derived from such episodes have empty `applicability.screen_states`, making them "universal" matchers.

**Fix:** Skip or merge episodes with empty screen states.

---

### LOW

#### L1 (CARRIED FORWARD): `PromotionGate.evaluate()` accesses private `_TIER_ORDER` and `_TIER_INDEX`

**File:** `learning/skill_induction/promotion_gate.py`
**Line:** 71

**Fix:** Export these as public symbols from `skills.promotion`, or provide a public `next_tier()` helper.

---

#### L2 (UNFIXED): Duplicate `tier_order` list in `registry.py`

**File:** `skills/registry.py`
**Lines:** 59, 80

The full tier ordering list is defined inline in both `find_by_tier()` and `find_applicable()` instead of being a shared module-level constant or imported from `skills.promotion`.

**Fix:** Define once at module level or import from `skills.promotion`.

---

#### L3 (CARRIED FORWARD): Unusual list-comprehension pattern for fallbacks

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 72-73

```python
fallbacks=tuple(SkillFallback(recovery_recipe="UI_LOST_RECOVERY")
                for _ in [1]) if not coordinate_only else (),
```

**Fix:** Replace with `(SkillFallback(recovery_recipe="UI_LOST_RECOVERY"),) if not coordinate_only else ()`.

---

#### L4 (CARRIED FORWARD): No `__all__` exports in package init files

**Files:** `skills/__init__.py`, `learning/skill_induction/__init__.py`

**Fix:** Add `__all__` to control public API surface.

---

## Audit Focus Questions -- Answers

### Does the verifier check work correctly?

**No.** The Round 1 fix introduced a crash bug (N1). The check references `c.claim_id` which does not exist on `SkillProducedClaim`. For non-terminal claims (the default), the check is bypassed entirely, so the original safety gap (C1) persists.

### Can a skill with empty `verifier_recipe` still promote to candidate?

**Yes.** A skill with default `claim_role="local"` and empty `verifier_recipe=""` passes the candidate check because the verifier check only applies to `claim_role == "terminal"` claims. Since the binder never produces terminal claims, this check is effectively dead for pipeline-produced skills.

### Are there new issues from the Round 1 fixes?

**Yes, three new issues:**

1. **N1 (CRITICAL):** `c.claim_id` AttributeError crash on terminal claims during promotion
2. **N2 (CRITICAL):** Verifier check only covers terminal claims, leaving the default "local" path unchecked
3. **N3 (MEDIUM):** `evaluate()` and `try_promote()` disagree on raw_trace skills
4. **N4 (MEDIUM):** Dead variable `has_coordinate_only` in AnchorBinder, indicating mixed episodes may not be handled correctly

### Is the Wilson lower bound formula correct?

**Yes.** Unchanged from Round 1. Correctly implements the standard Wilson score interval.

### Does the Round 1 fix for `can_promote_to()` accepting `successes`/`failures` work?

**Yes.** The function signature now correctly accepts `successes` and `failures` parameters (line 41-42), and `meets_wilson_threshold()` is called for stable and trusted tiers. `PromotionGate.try_promote()` correctly passes these through.

---

## Test Coverage Assessment

**58 tests pass** but critically do not exercise the broken verifier check path:

- **No test** creates a skill with `claim_role="terminal"` and calls `can_promote_to(skill, "candidate")`, so the `AttributeError` in N1 is never triggered.
- **No test** verifies that a skill with empty `verifier_recipe` and `claim_role="local"` is rejected at candidate tier (because it is not -- N2).
- **No test** calls `evaluate()` on a `raw_trace` skill to detect the N3 inconsistency.
- **No test** exercises `process_session()` with `target_tier="candidate"` or higher, so H2 is not detected.

**Recommended new tests:**
1. Test that terminal claim with empty `verifier_recipe` is rejected (currently crashes)
2. Test that non-terminal claim with empty `verifier_recipe` is rejected (currently passes)
3. Test `evaluate()` returns `None` for `raw_trace` skills
4. Test `process_session(target_tier="candidate")` fails gracefully
5. Test mixed anchored/unanchored episode binding behavior

---

## Risk Summary

| ID | Severity | Status | Component | Summary |
|----|----------|--------|-----------|---------|
| N1 | CRITICAL | NEW | promotion | `c.claim_id` AttributeError crash on terminal claims |
| N2 | CRITICAL | NEW | promotion | Verifier check bypassed for non-terminal (default) claims |
| H2 | HIGH | UNFIXED | pipeline | Cannot promote >1 tier in single session |
| H3 | HIGH | UNFIXED | promotion/gate | Coordinate-only check is tier-based, not content-based |
| N3 | MEDIUM | NEW | promotion_gate | `evaluate()` and `try_promote()` disagree on raw_trace |
| M1 | MEDIUM | UNFIXED | trace_recorder | TraceSession is mutable |
| M2 | MEDIUM | UNFIXED | anchor_binder | Unknown action types pass through |
| M3 | MEDIUM | UNFIXED | anchor_binder | Claim inference only covers dialogue/combat |
| N4 | MEDIUM | NEW | anchor_binder | Dead variable `has_coordinate_only`, mixed episodes mishandled |
| M4 | MEDIUM | CARRIED | registry | O(n*m) tier lookup in loop |
| M5 | MEDIUM | CARRIED | segmenter | Empty screen_state produces universal skill |
| L1 | LOW | CARRIED | promotion_gate | Accesses private `_TIER_ORDER` |
| L2 | LOW | UNFIXED | registry | Duplicate tier order list |
| L3 | LOW | CARRIED | anchor_binder | Unusual list-comprehension pattern |
| L4 | LOW | CARRIED | packages | No `__all__` exports |

**Previous C1 (CRITICAL):** Partially fixed -- check exists but is broken (N1) and incomplete (N2). Remains CRITICAL.
**Previous H1 (HIGH):** Fixed -- Wilson check now in `can_promote_to()` for stable/trusted tiers.
**Previous M4 (MEDIUM):** Carried forward unchanged.
**Previous M5 (MEDIUM):** Carried forward unchanged.
