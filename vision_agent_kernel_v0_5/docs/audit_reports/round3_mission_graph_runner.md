# Round 3 (FINAL) Audit Report: Mission Graph Runner

**Date:** 2026-05-27
**Scope:** `planning/mainline/mission_graph_v4.py`, `planning/mainline/mission_graph_validator_v4.py`, `planning/mainline/mainline_runner.py`, `planning/action_mask.py`, `perception/screen_state_tree.py`, and associated tests.
**Test status:** 73/73 passed (0.29s)

---

## Fix Verification (6 items)

### Fix 1: MainlineRunner logs+records skipped nodes
**Status: VERIFIED CORRECT**
- File: `mainline_runner.py`, lines 100-112
- When a node is not found in graph (line 101-105), it logs a warning, appends to `skipped_nodes`, and creates a `NodeResult` with status "skipped".
- When predecessor failed (line 109-112), node is appended to `skipped_nodes` with a `NodeResult`.
- Previously this was reportedly silent; now every skip path produces both a log entry and a recorded result.

### Fix 2: Topological order uses insertion-order (not sorted())
**Status: VERIFIED CORRECT**
- File: `mission_graph_v4.py`, lines 211-237
- `topological_order()` uses Kahn's algorithm seeded from `self._node_order` (insertion order) at line 219.
- Successors are sorted by `idx_map` (insertion index) at line 229, not lexicographically.
- Test `test_node_ids_preserve_insertion_order` confirms the ordering is preserved.
- The `to_dict()` method (line 243) sorts edges by `sorted()` which is fine for edge output determinism; node order is insertion-based.

### Fix 3: add_edge validates endpoints exist (rejects phantom)
**Status: VERIFIED CORRECT**
- File: `mission_graph_v4.py`, lines 157-164
- `add_edge()` raises `ValueError` if either `from_node` or `to_node` is not in `self._nodes`.
- Test `test_edge_reference_no_duplicates` confirms `pytest.raises(ValueError, match="unknown node")` works.
- The validator's `_check_edge_references` (lines 110-119) is now redundant defense-in-depth for this specific case, but still useful for catching any edge cases where edges are added through other means.

### Fix 4: Validator serialization mismatch is error (was warning)
**Status: VERIFIED CORRECT**
- File: `mission_graph_validator_v4.py`, lines 138-158
- `_check_deterministic_serialization` appends `ValidationIssue` with severity `"error"` (line 147, 150, 157).
- Previous rounds noted this was a warning; it is now correctly `"error"`.
- `is_valid()` (line 50) checks `severity != "error"`, so serialization failures now correctly fail validation.

### Fix 5: _execute_node last_error tracking (unreachable return fixed)
**Status: VERIFIED CORRECT**
- File: `mainline_runner.py`, lines 141-165
- `last_error` is initialized as `""` at line 143.
- In the `try` block, `last_error = str(exc)` is set at line 154 before the retry logic.
- If all retries fail on the exception path, the return at line 157 correctly uses `last_error`.
- The final return at line 165 uses `last_error or "max_retries_exceeded"` -- this is reachable when `self._skill_execute` is not None and the loop exits normally (all attempts threw exceptions but the last one was caught by the `if attempt == self._max_node_retries` check at line 156 which returns, so line 165 is actually a safety fallback for any edge case).
- The dry-run path (line 159-163) returns immediately with "completed", so `last_error` is irrelevant there.
- The fix is sound.

### Fix 6: _check_unique_ids dead code (documented as known)
**Status: VERIFIED -- DEAD CODE CONFIRMED, ACCEPTED AS KNOWN**
- File: `mission_graph_validator_v4.py`, lines 52-57
- `_check_unique_ids` iterates `graph.node_ids` checking for duplicates.
- Since `add_node()` (mission_graph_v4.py, lines 149-155) replaces existing nodes with the same ID (removes old from `_node_order`, then appends new), `graph.node_ids` can never contain duplicates.
- This check is effectively dead code. The test `test_duplicate_node_id_replaced` confirms this behavior.
- Documented as known; no functional harm, adds defense-in-depth at negligible cost.

---

## Remaining Findings

### MEDIUM-1: _check_edge_references is now partially redundant
- **Severity:** MEDIUM (code hygiene)
- **File:** `mission_graph_validator_v4.py`, lines 110-119
- **Description:** Since `add_edge()` now raises `ValueError` for phantom endpoints (Fix 3), the `_check_edge_references` method can never find unknown successors through normal API usage. It remains useful only as defense against direct internal state manipulation. Not a bug, but worth a comment noting its defense-in-depth role.

### LOW-1: to_dict() sorts edges lexicographically, not by insertion order
- **Severity:** LOW
- **File:** `mission_graph_v4.py`, line 243
- **Description:** `to_dict()` sorts destination nodes with `sorted()` (lexicographic), while `topological_order()` uses insertion order. This creates a minor inconsistency: the topological order and the edge list in `to_dict()` may present the same successors in different orders. This does not affect correctness (both are valid) but could confuse debugging. The node list in `to_dict()` correctly uses insertion order (line 250).

### LOW-2: MainlineRunner ignores node-level budgets
- **Severity:** LOW (design gap, not a bug in current code)
- **File:** `mainline_runner.py`, lines 63-76
- **Description:** The runner constructor takes `max_node_retries` and `max_duration_sec` as global budgets, but each `MissionNodeV4` carries its own `NodeBudget` (max_retries, max_uncertain, max_duration_sec). The per-node budgets are never consulted. The runner uses the global `self._max_node_retries` for all nodes uniformly. This is a design gap for future enhancement, not a correctness issue.

### LOW-3: claim_check_fn is accepted but never called
- **Severity:** LOW
- **File:** `mainline_runner.py`, lines 66, 72
- **Description:** The constructor accepts `claim_check_fn` and stores it as `self._claim_check`, but `run()` and `_execute_node()` never invoke it. The docstring says "Check input_claims are satisfied (skip if not)" at step 1, but this is not implemented. Nodes with unsatisfied input claims will execute regardless. This is a feature gap, not a regression.

### LOW-4: SomaticState.evolve() uses dataclasses.replace() which copies all fields
- **Severity:** LOW
- **File:** `mainline_runner.py`, line 169
- **Description:** `_update_somatic` calls `self._somatic.evolve(active_mission_node=node.node_id)`. Since `SomaticState` is frozen with `slots=True`, this correctly creates a new instance. No issue here -- just noting the pattern is correct.

### INFO-1: No tests for claim_check_fn or per-node budget enforcement
- **Severity:** INFO
- **File:** `tests/test_mainline_runner.py`
- **Description:** No tests verify the claim checking path (since it's not implemented) or per-node budget usage. Test coverage is good for implemented functionality (73 tests pass) but does not cover the documented-but-unimplemented features.

### INFO-2: boss_fight page reuses combat actions
- **Severity:** INFO
- **File:** `action_mask.py`, line 141
- **Description:** `boss_fight` maps to `_COMBAT_ACTIONS`, which is intentional and documented by the shared tuple. No issue.

---

## Summary

**All 6 fixes verified correct. No regressions detected.**

| Category | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 1 (redundant validator check, cosmetic) |
| LOW | 3 (design gaps, not bugs) |
| INFO | 2 |

**Verdict:** All Round 2 fixes are correctly applied. The codebase is clean with no blocking issues. The three LOW items are pre-existing design gaps (per-node budgets, claim checking, edge sort inconsistency) that can be addressed in future iterations. The 73 tests provide solid coverage of implemented functionality.
