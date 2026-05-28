# Round 1 Audit Report: Skill OS and Skill Induction Pipeline

**Auditor:** Senior Code Auditor (Automated)
**Date:** 2026-05-27
**Scope:** `skills/` package, `learning/skill_induction/` package, associated tests
**Tests:** 58/58 passing (34 + 24)

---

## Summary

The Skill OS and Skill Induction pipeline is well-structured, correctly implements the core promotion ladder mechanics, and has strong test coverage of the happy paths. The thread safety model is sound. Serialization round-trips correctly. However, there are several findings ranging from a missing hard-rule enforcement (CRITICAL) to a design gap in the pipeline's multi-tier promotion path (HIGH).

---

## Findings

### CRITICAL

#### C1: "No verifier = no unattended" hard rule is NOT enforced

**Files:** `skills/promotion.py`, `learning/skill_induction/promotion_gate.py`
**Lines:** `promotion.py:38-85`, `promotion_gate.py:32-67`

The `__init__.py` docstrings in both packages and the promotion module docstring state the hard rule:

> "Skills without verifiers on terminal claims cannot be unattended"

Neither `can_promote_to()` nor `PromotionGate.try_promote()` checks whether produced claims have `verifier_recipe` set. A skill with `produced_claims` containing empty `verifier_recipe` strings can freely promote to `candidate`, `stable`, and `trusted` tiers. There is no "unattended" execution concept or check anywhere in the codebase.

**Impact:** This is a stated safety hard rule that is completely unenforced. Skills without verification recipes could be executed in production without any validation that they actually achieved their claimed effects.

**Recommendation:** Add a check in `can_promote_to()` (for candidate+) or in `PromotionGate` that requires all produced claims to have non-empty `verifier_recipe` before allowing promotion beyond `experimental`.

---

### HIGH

#### H1: Wilson lower bound not checked in `can_promote_to()` for stable/trusted tiers

**File:** `skills/promotion.py`
**Lines:** 68-83

The `can_promote_to()` function checks `execution_stats.success_count` for `stable` tier promotion (line 71-73) and `verified_profiles` for `trusted` (line 78-82), but does NOT check the Wilson lower bound. Wilson checking only happens in `PromotionGate.try_promote()` (lines 55-61 of `promotion_gate.py`).

This means `can_promote_to()` reports success for `stable`/`trusted` promotion even when reliability is below the Wilson threshold. Any code that calls `can_promote_to()` directly (bypassing `PromotionGate`) will miss this reliability gate.

**Impact:** Inconsistent enforcement depending on which API is called. The lower-level function provides a weaker guarantee than the higher-level gate.

**Recommendation:** Move the Wilson threshold check into `can_promote_to()` itself, or document clearly that `can_promote_to()` is a necessary-but-not-sufficient check and `PromotionGate` must always be used for actual promotion decisions.

#### H2: Pipeline cannot promote skills more than one tier in a single `process_session` call

**File:** `learning/skill_induction/pipeline.py`
**Lines:** 69-79

When `target_tier` is set to `candidate` or above, the pipeline calls `gate.try_promote(result.skill, target_tier)` which invokes `can_promote_to()`. Since skills produced by `AnchorBinder` start at `draft` tier, requesting `candidate` requires a two-tier jump (draft -> experimental -> candidate), which `can_promote_to()` correctly rejects with "cannot skip tiers."

As a result, `process_session(session, target_tier="candidate")` always fails promotion and returns `skills_produced=0` even though the skill IS registered in the registry. The only working `target_tier` values are `raw_trace`, `draft`, and `experimental`.

**Impact:** The `target_tier` parameter creates a false contract. Callers expecting `candidate` or higher will never see it work. Skills still get registered (at `draft`), so data is not lost, but the return value is misleading.

**Recommendation:** Either implement iterative promotion (try each tier sequentially up to `target_tier`) or restrict `target_tier` to valid single-step values and validate the input.

#### H3: `can_promote_to()` allows `raw_trace -> draft` with any steps, even coordinate-only

**File:** `skills/promotion.py`
**Lines:** 52-56

The `raw_trace -> draft` check only verifies `skill.steps` is non-empty (line 54). It does not distinguish between semantic (anchor-based) steps and coordinate-only steps. A `raw_trace` skill with coordinate-only steps would pass this check.

`PromotionGate` compensates by blocking ALL `raw_trace` promotions (line 48-52 of `promotion_gate.py`), but this creates an inconsistency: `can_promote_to()` says "yes" while `PromotionGate` says "no". The "coordinate-only" check in `PromotionGate` is based purely on `tier == "raw_trace"`, not on actual step content.

**Impact:** The two layers have conflicting semantics. If `PromotionGate` is ever bypassed or a new code path uses `can_promote_to()` directly, coordinate-only skills could promote past `raw_trace`.

**Recommendation:** Add a `coordinate_only` property or field to `SkillDef` so the check can be content-based rather than tier-based. Alternatively, move the coordinate-only check into `can_promote_to()`.

---

### MEDIUM

#### M1: `TraceSession` is mutable (not frozen) - no data integrity protection

**File:** `learning/skill_induction/trace_recorder.py`
**Lines:** 28-38

`TraceSession` uses `@dataclass(slots=True)` without `frozen=True`. Its `actions` list is mutable and can be modified externally, including with incorrectly typed data. The `success`, `ended_at`, and other fields can also be mutated after recording.

**Impact:** Session data integrity is not guaranteed. External code could corrupt session state, leading to malformed skills in the induction pipeline.

**Recommendation:** Either freeze `TraceSession` (with a builder pattern for mutations) or add runtime guards to the mutation paths.

#### M2: `AnchorBinder._normalize_action_type()` allows invalid action types through

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 83-97

The normalization map handles 11 known action types but returns unknown types unchanged (line 97). This means `SkillStep.action` can be set to any arbitrary string, violating the `StepAction` Literal type constraint defined in `schema.py`.

**Impact:** Skills created with unknown action types will pass through the pipeline and registry without error. Downstream execution engines may fail at runtime with unrecognized actions.

**Recommendation:** Either raise an error for unknown action types, or map them to a default like `"interact"`.

#### M3: `AnchorBinder._infer_claim()` only handles "dialogue" and "combat" screen states

**File:** `learning/skill_induction/anchor_binder.py`
**Lines:** 99-114

The claim inference only recognizes screen states containing "dialogue", "dialog", or "combat". All other screen states produce no claim (`return None`). This means skills induced from non-combat, non-dialogue episodes will have empty `produced_claims` and can never reach `candidate` tier.

**Impact:** This is a significant functional limitation. The induction pipeline can only produce promotable skills for dialogue and combat contexts. All other contexts produce skills capped at `experimental`.

**Recommendation:** Consider a generic claim inference strategy (e.g., `f"{state}_action_completed"`) or make claim inference pluggable.

#### M4: `find_by_tier()` uses `list.index()` inside a loop - O(n*m) performance

**File:** `skills/registry.py`
**Lines:** 57-67

The `find_by_tier()` method calls `tier_order.index(s.tier)` inside the comprehension loop (line 66). For n skills, this is O(n * 6). While the constant is small (6 tiers), this could be improved.

**Recommendation:** Pre-compute a `dict[PromotionTier, int]` (as done in `promotion.py` `_TIER_INDEX`) and reuse it, or cache the index computation.

#### M5: Episode segmenter treats empty first-action `screen_state` as a valid segment

**File:** `learning/skill_induction/episode_segmenter.py`
**Lines:** 42-43

When the first action has `screen_state=""`, the segmenter creates an episode with `screen_state=""`. While it correctly splits when a non-empty state follows, the initial empty-state episode is still produced. This could lead to skills with empty applicability constraints.

**Impact:** Minor. Skills with empty screen state are "universal" by convention, which may not be the intended behavior for partially-labeled traces.

---

### LOW

#### L1: `PromotionGate.evaluate()` accesses private `_TIER_ORDER` and `_TIER_INDEX` from `skills.promotion`

**File:** `learning/skill_induction/promotion_gate.py`
**Line:** 79

The `evaluate()` method imports and uses `_TIER_ORDER` and `_TIER_INDEX` which are module-level private variables (prefixed with underscore). This is a minor encapsulation violation.

**Recommendation:** Export `TIER_ORDER` and `TIER_INDEX` as public, or add a public `next_tier()` helper to `skills.promotion`.

#### L2: Duplicate `tier_order` list in `registry.py`

**File:** `skills/registry.py`
**Lines:** 59, 80

The tier ordering list `["raw_trace", "draft", "experimental", "candidate", "stable", "trusted"]` is duplicated inside two methods (`find_by_tier` and `find_applicable`) instead of being a module-level constant shared with `promotion.py`.

**Recommendation:** Define the tier ordering once and share it across modules.

#### L3: `AnchorBinder.bind()` creates fallbacks with a list comprehension over `[1]`

**File:** `learning/skill_induction/anchor_binder.py`
**Line:** 72-73

```python
fallbacks=tuple(SkillFallback(recovery_recipe="UI_LOST_RECOVERY")
                for _ in [1]) if not coordinate_only else (),
```

This is an unusual pattern. A simple conditional tuple would be clearer:
```python
fallbacks=(SkillFallback(recovery_recipe="UI_LOST_RECOVERY"),) if not coordinate_only else (),
```

#### L4: No `__all__` exports in package `__init__.py` files

**Files:** `skills/__init__.py`, `learning/skill_induction/__init__.py`

Neither package init defines `__all__`, so `from skills import *` would import everything including internal symbols.

---

## Audit Focus Questions - Answers

### Does the promotion ladder correctly enforce all hard rules?

**Partially.** Three of four hard rules are enforced:
- Coordinate-only stays `raw_trace`: **YES**, enforced by `PromotionGate` (but see H3 - enforcement is tier-based, not content-based)
- No `produced_claims` = no `candidate`: **YES**, enforced at `promotion.py:63-66`
- No verifier = no unattended: **NO**, completely unenforced (see C1)
- Priors are for ranking only: **YES**, no safety gating based on priors exists in the code

### Is Wilson lower bound formula correct?

**YES.** The formula at `promotion.py:88-97` correctly implements the standard Wilson score interval lower bound. Verified manually against the mathematical definition:
- `(p_hat + z^2/(2n) - z*sqrt((p_hat*(1-p_hat) + z^2/(4n))/n)) / (1 + z^2/n)`
- Edge case `n=0` returns `0.0` (correct)
- Known values verified: `wilson_lower_bound(10, 0) ~ 0.722`, `wilson_lower_bound(5, 5) ~ 0.237`

### Does the registry handle concurrent register/unregister safely?

**YES.** `SkillRegistry` uses `threading.Lock()` (line 22) and all public methods acquire the lock. Tested with 8 concurrent threads (4 registering, 4 unregistering) with no errors. The lock is non-reentrant, which is appropriate since no method calls another public method.

### Does the applicability scorer correctly handle skills with no constraints?

**YES.** Skills with empty `applicability` (no screen states, no claims, no anchors) score a perfect 1.0. The scoring logic at `applicability.py:40-62` correctly treats empty constraints as "always matching":
- `not skill.applicability.screen_states` -> True -> `screen_match = True`
- `not required_claims` -> True -> `claims_ok = True`
- `not required_anchors` -> True -> `anchors_ok = True`

### Can the anchor binder produce skills with empty steps?

**NO.** The `bind()` method returns `BindingResult(skill=None, ...)` for empty episodes (line 35-36). For non-empty episodes, every action produces a step. There is no path to produce a `SkillDef` with empty `steps`.

### Does the pipeline correctly handle failed sessions?

**YES.** `pipeline.py:48-49` returns `InductionResult(0, 0, ())` immediately for non-success sessions. No skills are registered.

### Is the episode segmenter correct for consecutive same-state actions?

**YES.** The segmenter only splits when `action.screen_state != current_state AND action.screen_state != ""` (line 47). Consecutive actions with the same screen state are grouped into a single episode. Actions with empty `screen_state` are appended to the current episode without triggering a split.

### Does SkillDef round-trip serialization preserve ALL fields including metadata?

**YES.** Verified all 13 fields: `skill_id`, `version`, `capsule_id`, `kind`, `risk_level`, `tier`, `applicability`, `steps` (including `params`, `wait_until`, `timeout_ms`), `produced_claims`, `belief_templates`, `fallbacks`, `promotion`, and `metadata` (including nested dicts). Full equality `skill == restored` returns `True` after round-trip.

---

## Test Coverage Assessment

- **58 tests, all passing.** Good coverage of happy paths.
- **Missing test cases:**
  - No test for the "no verifier = no unattended" rule (because it is unenforced)
  - No test for multi-tier promotion via pipeline (revealing H2)
  - No test for `can_promote_to()` vs `PromotionGate` inconsistency (H3)
  - No concurrency tests for registry (manually verified during audit)
  - No test for unknown action types passing through normalization (M2)
  - No test for `PromotionGate.evaluate()` with Wilson threshold interaction

---

## Risk Summary

| ID | Severity | Component | Summary |
|----|----------|-----------|---------|
| C1 | CRITICAL | promotion | "No verifier = no unattended" hard rule unenforced |
| H1 | HIGH | promotion | Wilson check missing from `can_promote_to()` |
| H2 | HIGH | pipeline | Cannot promote >1 tier in single session |
| H3 | HIGH | promotion | Coordinate-only check is tier-based, not content-based |
| M1 | MEDIUM | trace_recorder | TraceSession is mutable, no data integrity |
| M2 | MEDIUM | anchor_binder | Unknown action types pass through |
| M3 | MEDIUM | anchor_binder | Claim inference only covers dialogue/combat |
| M4 | MEDIUM | registry | O(n*m) tier lookup in loop |
| M5 | MEDIUM | segmenter | Empty screen_state on first action produces universal skill |
| L1 | LOW | promotion_gate | Accesses private `_TIER_ORDER` |
| L2 | LOW | registry | Duplicate tier order list |
| L3 | LOW | anchor_binder | Unusual list-comprehension pattern for fallbacks |
| L4 | LOW | packages | No `__all__` exports |
