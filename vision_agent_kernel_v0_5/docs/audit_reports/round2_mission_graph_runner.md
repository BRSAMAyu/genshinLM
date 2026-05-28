# Round 2 Audit Report: MissionGraph v4, MainlineRunner, ActionMask, ScreenStateTree

**Auditor:** Claude Code (automated)
**Date:** 2026-05-27
**Branch:** codex/pre-realworld-closure
**Scope:** `mission_graph_v4.py`, `mission_graph_validator_v4.py`, `mainline_runner.py`, `action_mask.py`, `screen_state_tree.py`, and their test files

---

## Executive Summary

Round 1 identified 19 issues (5 CRITICAL, 6 HIGH, 4 MEDIUM, 4 LOW). Of those, 5 were marked as fixed and 7 as "still unfixed, verify in Round 2." This audit confirms the Round 1 fixes are largely sound but identifies **1 test regression** caused by the H3 fix, **6 new issues** introduced or exposed by Round 1 changes, and confirms **5 previously identified issues remain unfixed**. All 73 tests pass except `test_edge_reference_no_duplicates` which fails due to the Round 1 `add_edge` validation.

**Key findings:**
1. Round 1's `add_edge` validation (fixing H3) broke test `test_edge_reference_no_duplicates` -- the test expects phantom edges to be silently accepted, but `add_edge` now raises `ValueError`.
2. Round 1's `topological_order` fix is correct and deterministic for a given insertion order.
3. Runner accepts but never invokes `claim_check_fn` (H1 persists), and never enforces per-node budgets.
4. `_check_edge_references` in the validator is now dead code since `add_edge` validates endpoints.

---

## Round 1 Fix Verification

### FIXED and Verified Correct

**C1 (silent node drop):** MainlineRunner now logs and records skipped nodes (lines 102-104). Correct.

**C5 (serialization mismatch severity):** Validator `_check_deterministic_serialization` now reports mismatches as `"error"` severity (lines 144, 149). Correct.

**C4 (topological order determinism):** `topological_order` now uses `idx_map` to sort successors by insertion order instead of lexicographic. Verified deterministic for diamond DAGs with a given insertion order. **Yes, topological order is now truly deterministic** for a given graph construction sequence.

**H5 (unreachable return):** `_execute_node` now uses `last_error` variable, and the final return at line 165 is a safety fallback with `last_error or "max_retries_exceeded"`. The logic is still structured so the final return is effectively unreachable (every loop path returns), but it is now a defensive fallback with a meaningful error message. Acceptable.

**H3 (add_edge phantom endpoints):** `add_edge` now raises `ValueError` on line 158-161 if either endpoint is not in `_nodes`. This is a correct fix. However, see NEW-1 below for the broken test.

### Still Unfixed -- Confirmed Present

| ID | Severity | Status | Notes |
|----|----------|--------|-------|
| C3 | CRITICAL | UNFIXED | `add_node` duplicate replacement preserves old edges (both outgoing and incoming). Replacing node `a` keeps edges `a->b` and `c->a`. |
| H1 | HIGH | UNFIXED | `input_claims` never checked. `claim_check_fn` stored but never called. |
| H4 | HIGH | UNFIXED | `_check_unique_ids` is dead code. `add_node` replaces duplicates, so `node_ids` never contains duplicates. |
| H6 | HIGH | UNFIXED | `ScreenStateTree.to_dict()` loses all element data, text block data, regions, and evidence_refs. Regions are not included at all (not even a count). |
| M2 | MEDIUM | UNFIXED | `NormalizedRect` accepts negative, inverted, and NaN values without validation. Inverted rects produce negative width/height. |
| M1 | MEDIUM | UNFIXED | `ActionMask.__init__` accepts custom masks containing forbidden action IDs. Runtime checks catch it via `is_action_allowed`, but `allowed_actions()` returns them. |

---

## New Findings in Round 2

### NEW-1. BROKEN TEST: test_edge_reference_no_duplicates fails with add_edge validation

**Severity:** HIGH
**File:** `tests/test_mission_graph_v4_contract.py` lines 403-413
**Related source:** `planning/mainline/mission_graph_v4.py` lines 157-161

The Round 1 fix to `add_edge` (H3) added endpoint validation that raises `ValueError` for phantom nodes. But the test `test_edge_reference_no_duplicates` still attempts to add an edge to a non-existent node (`"nonexistent"`) and expects it to succeed so the validator can catch it:

```python
def test_edge_reference_no_duplicates(self) -> None:
    g = MissionGraphV4()
    g.add_node(_node("a"))
    g.add_edge(MissionEdgeV4("a", "nonexistent"))  # NOW RAISES ValueError
    validator = MissionGraphValidatorV4()
    issues = validator.validate(g)
    ...
```

This test fails with `ValueError: Edge references unknown node(s): 'a' -> 'nonexistent'`.

**Impact:** 1 of 73 tests fails. CI would catch this.
**Fix:** The test should be updated to expect the `ValueError`:
```python
with pytest.raises(ValueError, match="nonexistent"):
    g.add_edge(MissionEdgeV4("a", "nonexistent"))
```
Or test that the validator's `_check_edge_references` still works by constructing the graph via internal API manipulation (though this is now dead code -- see NEW-2).

---

### NEW-2. Dead code: _check_edge_references can never fire after add_edge validation

**Severity:** MEDIUM
**File:** `planning/mainline/mission_graph_validator_v4.py` lines 110-119

Since `add_edge` now raises `ValueError` for phantom endpoints, it is impossible to construct a graph with edges referencing unknown nodes through the public API. The `_check_edge_references` validator method can only fire if someone directly manipulates `graph._edges` (a private attribute). This makes the validator method dead code.

**Impact:** Wasted computation during validation. False sense of coverage in the validator.
**Fix:** Either remove `_check_edge_references` from the validation pipeline (since `add_edge` enforces this invariant) or document that it exists as a defense-in-depth check for internal state corruption.

---

### NEW-3. Runner ignores per-node budgets (max_retries, max_duration_sec, max_uncertain)

**Severity:** HIGH
**File:** `planning/mainline/mainline_runner.py` lines 141-165

The `MissionNodeV4.budgets` field declares per-node execution limits (`max_retries`, `max_uncertain`, `max_duration_sec`), but `_execute_node` uses `self._max_node_retries` (the runner's global setting) for retry count. It never checks `node.budgets.max_retries`, never enforces `node.budgets.max_duration_sec` as a per-node timeout, and never tracks `node.budgets.max_uncertain`.

Verified: a node with `budgets=NodeBudget(max_retries=0)` executed 6 times when the runner was configured with `max_node_retries=5`.

```python
def _execute_node(self, node: MissionNodeV4, completed: set[str]) -> NodeResult:
    last_error = ""
    for attempt in range(self._max_node_retries + 1):  # Uses global, not node.budgets
        ...
```

**Impact:** Per-node budget declarations are meaningless. A node declared as "no retries allowed" can still be retried if the runner's global setting permits it.
**Fix:** Use `node.budgets.max_retries` instead of `self._max_node_retries` in `_execute_node`, with `self._max_node_retries` as a global ceiling. Add per-node timeout enforcement using `node.budgets.max_duration_sec`.

---

### NEW-4. Runner's output_claims verification is declared but never implemented

**Severity:** HIGH
**File:** `planning/mainline/mainline_runner.py` lines 53-61

The `MainlineRunner` class docstring declares 7 steps including "5. Verify output_claims." The `_execute_node` method stores `claim_data` from `skill_execute_fn` in the `NodeResult`, but never validates it against the node's `output_claims`. If a skill returns data that doesn't match the declared output claims, the node still reports as "completed."

```python
# Line 152: claim_data is stored but never validated against node.output_claims
return NodeResult(node.node_id, "completed", duration, claim_data or {})
```

**Impact:** A node can report success without producing the claims it promised, violating the claim-gated contract.
**Fix:** Add output claim verification after skill execution, comparing returned `claim_data` against `node.output_claims`.

---

### NEW-5. combat_allowed("domain") returns True but domain has no combat actions

**Severity:** MEDIUM
**File:** `planning/action_mask.py` line 199

```python
def combat_allowed(self, page_id: str) -> bool:
    return page_id in ("world_viewport", "combat", "boss_fight", "domain")
```

`combat_allowed("domain")` returns `True`, but `_DOMAIN_ACTIONS` only contains `observe`, `advance_dialogue`, `start_challenge`, and `leave_domain`. None of these are combat actions (`normal_attack`, `e_skill`, etc.). `is_action_allowed("domain", "normal_attack")` returns `False`. This is contradictory.

Additionally, `combat_allowed("world_viewport")` returns `True` but `_WORLD_ACTIONS` only includes `start_combat` (not the full combat set). This was noted as M4 in Round 1 but persists.

**Impact:** Callers relying on `combat_allowed()` may assume full combat capability that doesn't exist for domain or world_viewport pages.
**Fix:** Align `combat_allowed()` with actual action masks, or document that it means "combat-initiation allowed" rather than "combat-actions available."

---

### NEW-6. Frozen dataclasses with mutable dict fields (metadata)

**Severity:** LOW
**File:** `perception/screen_state_tree.py` line 71, `planning/mainline/mission_graph_v4.py` line 93

Both `UIElementNode` and `MissionNodeV4` are declared `frozen=True` with a `metadata: dict[str, Any]` field using `field(default_factory=dict)`. Since `frozen=True` prevents reassignment but not mutation of the dict object itself, the metadata can be modified in-place:

```python
e1.metadata["key"] = "modified"  # Succeeds despite frozen=True
```

This violates the thread-safety intent stated in the `MissionGraphV4` docstring ("Thread-safe for reads") and the `ScreenStateTree` docstring ("Frozen for thread safety").

**Impact:** In a multi-threaded context, concurrent mutation of metadata dicts could cause data races despite the frozen declaration.
**Fix:** Use `@dataclass(frozen=True)` with `metadata: dict[str, Any]` converted to a `types.MappingProxyType` in `__post_init__`, or document that metadata mutation is the caller's responsibility.

---

### NEW-7. to_dict edge destination sorting is lexicographic, not insertion-ordered

**Severity:** LOW
**File:** `planning/mainline/mission_graph_v4.py` line 240

```python
for dst in sorted(self._edges.get(src, set())):
```

While the Round 1 fix made `topological_order` use insertion order, `to_dict` still sorts edge destinations lexicographically via `sorted()`. This is not a bug (round-trip serialization is stable since both directions use the same sort), but it creates an inconsistency with the node ordering philosophy. Nodes are insertion-ordered, edges are lexicographic-ordered.

**Impact:** Cosmetic inconsistency. Serialization is deterministic and round-trip stable.
**Fix:** If full insertion-order consistency is desired, change `sorted()` to insertion-order iteration. Otherwise document the difference.

---

## Answers to Specific Questions

### Are there NEW issues from Round 1 fixes?

Yes. The `add_edge` validation (H3 fix) introduced a test regression (NEW-1) and made the validator's `_check_edge_references` dead code (NEW-2). No logic regressions in the source code itself -- the fixes are sound.

### Is topological order now truly deterministic?

**Yes.** For a given graph construction sequence (same insertion order of nodes and edges), `topological_order()` now produces a deterministic result. It uses an `idx_map` derived from `_node_order` (insertion order) to sort successors at each level. Verified with diamond DAGs where insertion order differs from lexicographic order. The only caveat: if the same graph is constructed with a different insertion order, the topological order will differ, which is expected and correct behavior.

---

## Updated Summary Table

| ID | Severity | File | Lines | Issue | Status |
|----|----------|------|-------|-------|--------|
| C3 | CRITICAL | mission_graph_v4.py | 149-155 | add_node duplicate preserves old edges (bidirectional) | UNFIXED |
| NEW-1 | HIGH | test_mission_graph_v4_contract.py | 403-413 | test_edge_reference_no_duplicates broken by add_edge validation | NEW |
| NEW-3 | HIGH | mainline_runner.py | 141-165 | Per-node budgets ignored (retries, duration, uncertain) | NEW |
| NEW-4 | HIGH | mainline_runner.py | 53-61 | output_claims verification declared but not implemented | NEW |
| H1 | HIGH | mainline_runner.py | 112 | input_claims never checked, claim_check_fn never invoked | UNFIXED |
| H4 | HIGH | mission_graph_validator_v4.py | 52-57 | _check_unique_ids is dead code | UNFIXED |
| H6 | HIGH | screen_state_tree.py | 139-150 | to_dict loses all element/text/region/evidence data | UNFIXED |
| M1 | MEDIUM | action_mask.py | 167-170 | Custom masks not validated against forbidden IDs | UNFIXED |
| M2 | MEDIUM | screen_state_tree.py | 34-56 | NormalizedRect no bounds validation | UNFIXED |
| NEW-2 | MEDIUM | mission_graph_validator_v4.py | 110-119 | _check_edge_references now dead code | NEW |
| NEW-5 | MEDIUM | action_mask.py | 199 | combat_allowed("domain") contradicts actual mask | NEW |
| NEW-6 | LOW | screen_state_tree.py, mission_graph_v4.py | 71, 93 | Frozen dataclasses with mutable metadata dicts | NEW |
| NEW-7 | LOW | mission_graph_v4.py | 240 | to_dict edge sorting lexicographic vs insertion-ordered | NEW |

---

## Priority Recommendations

1. **Fix broken test** (NEW-1): Update `test_edge_reference_no_duplicates` to expect `ValueError` or test the validator directly.
2. **Implement per-node budget enforcement** (NEW-3): Use `node.budgets.max_retries` and `node.budgets.max_duration_sec` in `_execute_node`.
3. **Implement input_claims checking** (H1): Call `self._claim_check` before execution.
4. **Implement output_claims verification** (NEW-4): Validate returned `claim_data` against declared `output_claims`.
5. **Decide on duplicate node policy** (C3): Either raise on duplicate, clear edges on replacement, or document the current behavior.
6. **Remove or document dead code** (H4, NEW-2): Clean up `_check_unique_ids` and `_check_edge_references`.
7. **Add ScreenStateTree full serialization** (H6): Serialize elements, text_blocks, regions, and evidence_refs in `to_dict()`.
8. **Validate NormalizedRect bounds** (M2): Add `__post_init__` validation for [0,1] range and left < right, top < bottom.
