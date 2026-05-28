# Round 1 Audit Report: MissionGraph v4, ActionMask, ScreenStateTree, MainlineRunner

**Auditor:** Claude Code (automated)
**Date:** 2026-05-27
**Branch:** codex/pre-realworld-closure
**Scope:** 8 source + test files (mission_graph_v4.py, mission_graph_validator_v4.py, action_mask.py, screen_state_tree.py, mainline_runner.py, and 3 test files)

---

## Executive Summary

Overall the codebase is well-structured and follows project conventions (frozen dataclasses, slots, Literal types, Claim contracts). The audit identified **5 CRITICAL**, **6 HIGH**, **4 MEDIUM**, and **4 LOW** issues across the 8 files. The most concerning findings are: (1) `MainlineRunner` silently drops nodes from execution without any log or error when `get_node` returns None mid-execution, (2) `MainlineRunner` has a TOCTOU window in its predecessor-failure cascade, (3) `add_node` duplicate replacement silently destroys edges from the old node's adjacency, (4) `topological_order` breaks determinism for diamond DAGs at equal-insertion-time nodes, and (5) the validator's serialization check silently swallows all exceptions at warning level, masking potentially critical data loss.

---

## Findings by Severity

### CRITICAL

#### C1. MainlineRunner silently drops nodes when get_node returns None
**File:** `planning/mainline/mainline_runner.py` line 100-102
**Category:** Logic bug / data loss

```python
node = graph.get_node(node_id)
if node is None:
    continue
```

When `topological_order()` returns a node_id but `get_node()` returns None, the runner silently skips the node without recording it in `skipped_nodes`, `failed_nodes`, or `node_results`. This can happen if the graph is mutated concurrently during execution (no thread-safety guard), or if there is a subtle inconsistency in the graph's internal state. The node is simply lost from the run report, making post-mortem debugging impossible.

**Impact:** Nodes silently disappear from execution with no audit trail.
**Fix:** Log a warning and record a NodeResult with status "skipped" or "error".

#### C2. MainlineRunner TOCTOU in predecessor failure check
**File:** `planning/mainline/mainline_runner.py` lines 105-109
**Category:** Thread safety / TOCTOU

```python
# Check if predecessors completed
preds = graph.predecessors(node_id)
if any(p in failed for p in preds):
```

If the graph is mutated between the `topological_order()` call (line 87) and each node's predecessor check, the predecessor set may have changed. The doc comment on MissionGraphV4 says "Thread-safe for reads. Mutations should be done during construction," but MainlineRunner does not enforce that the graph is frozen or immutable before starting execution. There is no defensive copy or snapshot.

**Impact:** In theory, a concurrent mutation could cause a node to execute despite a failed predecessor, or skip a node whose predecessor was just repaired.
**Fix:** Take a snapshot of the graph structure at the start of `run()`, or at minimum document that the graph MUST NOT be mutated during execution.

#### C3. add_node with duplicate ID silently destroys adjacency data
**File:** `planning/mainline/mission_graph_v4.py` lines 149-155
**Category:** Data corruption

```python
def add_node(self, node: MissionNodeV4) -> None:
    if node.node_id in self._nodes:
        self._node_order = [nid for nid in self._node_order if nid != node.node_id]
    self._nodes[node.node_id] = node
    self._node_order.append(node.node_id)
    self._edges.setdefault(node.node_id, set())
    self._reverse_edges.setdefault(node.node_id, set())
```

When a duplicate node_id is added, the code replaces the node in `_nodes` and reorders `_node_order`, but it does NOT update `_edges`, `_reverse_edges`, or `_edge_conditions`. The old node's adjacency sets are preserved as-is, which may be incorrect for the new node. More critically, the `_node_order` list comprehension creates a new list object, and if the replacement happens while another thread is iterating `_node_order` (unlikely given the doc comment, but still), it is not atomic.

Furthermore, the replacement silently changes the node's insertion order position (moves it to the end of `_node_order`). This could alter topological ordering for nodes at the same depth.

**Impact:** Replacing a node changes its position but preserves stale edges, potentially leading to incorrect execution order.
**Fix:** Either explicitly reject duplicates (raise ValueError) or fully update adjacency structures. The current test `test_duplicate_node_id_replaced` only checks that `node_count` and `node_type` are correct -- it does not verify edges are preserved or cleared.

#### C4. topological_order breaks insertion-order determinism for diamond DAGs
**File:** `planning/mainline/mission_graph_v4.py` lines 216
**Category:** Determinism

```python
for succ in sorted(self._edges.get(node, set())):
```

Kahn's algorithm uses `sorted()` on successor sets, which means it uses **lexicographic** ordering, NOT **insertion** ordering. This breaks the contract in `to_dict()` which serializes edges in insertion order. For a diamond DAG `A -> B, A -> C, B -> D, C -> D`, the topological order depends on whether B or C comes first alphabetically, not on insertion order. If node IDs are auto-generated (e.g., `mg4_xxxx`), this could cause non-deterministic behavior across runs.

**Impact:** Round-trip serialization preserves edge order, but topological execution order may differ from the serialization order for diamond DAGs. The test `test_diamond_graph_valid` only checks first and last nodes, not the relative order of B vs C.
**Fix:** Use insertion-ordered iteration instead of `sorted()`, or document that topological order is always lexicographic within a level.

#### C5. Validator swallows exceptions at "warning" level during serialization check
**File:** `planning/mainline/mission_graph_validator_v4.py` lines 154-158
**Category:** Security / data integrity

```python
except Exception as exc:
    issues.append(ValidationIssue(
        "", "serialization",
        f"Serialization failed: {exc}", "error",
    ))
```

While exceptions are correctly reported as "error", the non-exception path (lines 144-153) reports mismatches as "warning" only. If `to_dict()` produces data that doesn't round-trip through `from_dict()` correctly (e.g., a node's metadata contains non-serializable objects, or float precision issues), the validator merely warns. A graph that cannot be faithfully serialized means audit logs are unreliable.

**Impact:** Graphs with serialization mismatches pass `is_valid()`, potentially leading to un-auditable executions.
**Fix:** Consider making serialization mismatches "error" severity, or at minimum provide a strict validation mode.

---

### HIGH

#### H1. MainlineRunner does not verify input_claims before node execution
**File:** `planning/mainline/mainline_runner.py` line 112
**Category:** Logic bug / missing feature

The docstring on line 54 states: "1. Check input_claims are satisfied (skip if not)". However, the `_execute_node` method does not check input_claims at all. The `claim_check_fn` parameter exists (line 66) but is never used in `_execute_node`. Nodes execute regardless of whether their input claims are satisfied.

**Impact:** A node's preconditions are not verified, violating the claim-gated execution contract.
**Fix:** Implement input claim checking in `_execute_node` using `self._claim_check`.

#### H2. MainlineRunner empty graph returns success=False with no diagnostic
**File:** `planning/mainline/mainline_runner.py` lines 133-134
**Category:** Edge case

```python
terminals = set(graph.terminal_nodes())
result.success = terminals.issubset(completed) if terminals else bool(completed)
```

For an empty graph, `terminals` is empty, so `success = bool(completed)`. Since `completed` is also empty, `success = False`. However, an empty graph could arguably be considered "trivially successful" (nothing to do = nothing to fail). The test `test_empty_graph` asserts `not result.success`, so this is intentional but worth documenting. More importantly, there is no `node_results` entry explaining why it failed.

**Impact:** Ambiguous semantics for empty graphs.
**Fix:** Add a log message explaining empty graph behavior, or return a special status.

#### H3. Edge references to non-existent nodes silently added
**File:** `planning/mainline/mission_graph_v4.py` lines 157-160
**Category:** Data integrity

```python
def add_edge(self, edge: MissionEdgeV4) -> None:
    self._edges.setdefault(edge.from_node, set()).add(edge.to_node)
    self._reverse_edges.setdefault(edge.to_node, set()).add(edge.from_node)
    self._edge_conditions[(edge.from_node, edge.to_node)] = edge.condition
```

`add_edge` does not verify that `from_node` or `to_node` exist in the graph. A typo in a node ID creates phantom edges. The validator catches this (rule `edge_reference`), but only if validation is run. The graph itself silently accepts invalid edges, and `topological_order` will ignore the phantom node (since it's not in `_nodes`), potentially causing the `in_degree` to never reach 0 for the valid endpoint.

**Impact:** Phantom edges can cause `topological_order` to return a truncated result without any cycle, or `terminal_nodes()` to miss actual terminals because `_reverse_edges` has phantom entries.
**Fix:** Validate node existence in `add_edge`, or at least log a warning.

#### H4. Validator _check_unique_ids is now dead code
**File:** `planning/mainline/mission_graph_validator_v4.py` lines 52-57
**Category:** Logic bug / dead code

```python
def _check_unique_ids(self, graph: MissionGraphV4, issues: list[ValidationIssue]) -> None:
    seen: set[str] = set()
    for nid in graph.node_ids:
        if nid in seen:
            issues.append(...)
        seen.add(nid)
```

Since `add_node` replaces duplicates (C3 above), `graph.node_ids` will never contain duplicates. This check is dead code and will never fire. The test suite has no test for it. If duplicate detection is desired, it must happen before `add_node` replaces.

**Impact:** False sense of security -- the validator claims to check for duplicates but cannot detect them.
**Fix:** Either remove the check or move detection to a different mechanism (e.g., raise on duplicate in `add_node`).

#### H5. MainlineRunner retry loop has unreachable final return
**File:** `planning/mainline/mainline_runner.py` lines 140-161
**Category:** Logic bug

```python
def _execute_node(self, node: MissionNodeV4, completed: set[str]) -> NodeResult:
    for attempt in range(self._max_node_retries + 1):
        ...
        if self._skill_execute is not None:
            try:
                ...
                return NodeResult(node.node_id, "completed", ...)
            except Exception as exc:
                ...
                if attempt == self._max_node_retries:
                    return NodeResult(node.node_id, "failed", ...)
                continue
        else:
            ...
            return NodeResult(node.node_id, "completed", ...)

    return NodeResult(node.node_id, "failed", error="max_retries_exceeded")
```

The final `return` on line 161 is unreachable. When `skill_execute_fn` is set, every iteration of the loop either returns "completed" or returns "failed" (on the last attempt). When `skill_execute_fn` is None, it returns "completed" on the first iteration. The `continue` on line 154 correctly goes to the next attempt. The final return is defensive but unreachable -- not a bug, but misleading.

**Impact:** No functional impact. The "max_retries_exceeded" error message will never appear.
**Fix:** Remove the dead return or restructure to make it reachable.

#### H6. ScreenStateTree to_dict does not serialize elements, text_blocks, or regions
**File:** `perception/screen_state_tree.py` lines 139-150
**Category:** Missing feature / API gap

```python
def to_dict(self) -> dict[str, Any]:
    return {
        ...
        "element_count": len(self.elements),
        "text_block_count": len(self.text_blocks),
        "active_modal": self.active_modal.modal_type if self.active_modal else None,
        ...
    }
```

`to_dict()` serializes counts but not the actual element data. There is no `from_dict()` classmethod, so ScreenStateTree has no round-trip serialization. This is inconsistent with MissionGraphV4 which has full serialization support. Elements, text_blocks, regions, and evidence_refs are all lost in the dict representation.

**Impact:** Any consumer expecting to reconstruct a ScreenStateTree from its dict will lose all element data.
**Fix:** Either serialize full element data or rename the method to `summary_dict()` to clarify its limited scope.

---

### MEDIUM

#### M1. ActionMask does not validate that custom masks avoid forbidden action IDs
**File:** `planning/action_mask.py` lines 167-170
**Category:** Security gap

```python
def __init__(self, custom_masks: dict[str, tuple[MaskedAction, ...]] | None = None) -> None:
    self._masks = {**_PAGE_MASKS}
    if custom_masks:
        self._masks.update(custom_masks)
```

If a caller passes `custom_masks` containing a MaskedAction with `action_id="raw_coordinate_click"` or `"bypass_safety"`, the `is_action_allowed` method will still reject it (because it checks `_FORBIDDEN_ACTION_IDS` first). However, the custom mask is accepted without validation. A caller who inspects `allowed_actions()` directly (without going through `is_action_allowed`) would see forbidden actions in the list. This is a defense-in-depth gap.

**Impact:** Custom masks can include forbidden action IDs that appear in `allowed_actions()` output.
**Fix:** Validate custom masks in `__init__` to reject forbidden action IDs.

#### M2. NormalizedRect has no validation for degenerate or inverted bounds
**File:** `perception/screen_state_tree.py` lines 34-56
**Category:** Edge case

`NormalizedRect` does not validate that `left < right`, `top < bottom`, or that values are in [0, 1]. A degenerate rect (left == right) has zero area, and an inverted rect (left > right) has negative area and a misleading center calculation.

**Impact:** Downstream code that relies on area > 0 or valid centers may behave unexpectedly.
**Fix:** Add a `__post_init__` validation, or at least clamp values.

#### M3. MissionNodeV4.to_dict does not preserve risk_level ordering guarantees
**File:** `planning/mainline/mission_graph_v4.py` line 103
**Category:** Serialization gap

The `to_dict` method serializes `risk_level` as a plain string. The `from_dict` method reads it back with `nd.get("risk_level", "medium")`. If an older version of the code writes a graph with a risk_level value that is later removed from the Literal type, deserialization will still produce a node with that invalid value. The validator will catch it, but the graph object itself will be in an inconsistent state.

**Impact:** Forward compatibility risk.
**Fix:** Validate risk_level during deserialization in `from_dict`.

#### M4. Combat actions allowed in world_viewport may be unintended
**File:** `planning/action_mask.py` line 198
**Category:** Logic / design decision

```python
def combat_allowed(self, page_id: str) -> bool:
    return page_id in ("world_viewport", "combat", "boss_fight", "domain")
```

The `combat_allowed` method says combat is allowed in `world_viewport`. However, the `_WORLD_ACTIONS` tuple includes `start_combat` (risk_level="medium") but NOT the full combat actions (`normal_attack`, `e_skill`, etc.). So `combat_allowed("world_viewport")` returns True, but `is_action_allowed("world_viewport", "normal_attack")` returns False. This is inconsistent -- either world_viewport should not report as combat-allowed, or the method should check the actual mask.

**Impact:** `combat_allowed()` and `is_action_allowed()` give contradictory answers for world_viewport.
**Fix:** Either remove `world_viewport` from `combat_allowed()`, or align it with the actual action mask.

---

### LOW

#### L1. _VALID_RISK_LEVELS and _VALID_CLAIM_ROLES are frozenset but could be Literal
**File:** `planning/mainline/mission_graph_v4.py` lines 29-30
**Category:** Style

```python
_VALID_RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
_VALID_CLAIM_ROLES = frozenset({"informational", "local", "dependency", "terminal"})
```

These duplicate the Literal types `RiskLevel` and `ClaimContractRole`. They exist for runtime validation but could be derived from the Literal types to avoid drift.

#### L2. Inconsistent use of `from_node`/`to_node` vs `from`/`to` in edge serialization
**File:** `planning/mainline/mission_graph_v4.py` lines 228-232

`MissionEdgeV4` uses `from_node`/`to_node`, but `to_dict()` serializes as `from`/`to`. This is fine for JSON compatibility but slightly confusing when reading code.

#### L3. Test file references `_fallback_to_dict` private helper
**File:** `tests/test_mission_graph_v4_contract.py` lines 396-399
**Category:** Style

The test imports the private function `_fallback_to_dict` directly. This works but creates a coupling to implementation details.

#### L4. Domain actions include "start_challenge" with risk_level="high" but no fallback mechanism
**File:** `planning/action_mask.py` line 125
**Category:** Naming / consistency

The `start_challenge` action in `_DOMAIN_ACTIONS` has `risk_level="high"` but ActionMask itself has no mechanism to enforce fallback requirements for high-risk actions. This is an ActionMask concern (UI-level gating), not a MissionGraph concern, but the two systems should ideally be aligned on what "high risk" means.

---

## Test Coverage Assessment

### test_mission_graph_v4_contract.py (39 tests)
- **Well covered:** Node construction, edge management, cycle detection, topological sort, serialization round-trip, validator rules (terminal claims, high-risk fallbacks, cycles, belief templates, invalid risk levels, invalid claim roles, edge references).
- **Missing coverage:**
  - No test for `add_edge` with a non-existent `from_node` (only `to_node` phantom is tested via edge_reference).
  - No test for the `from_json` classmethod with malformed JSON (only valid round-trip is tested).
  - No test for concurrent reads during mutation.
  - No test for topological order determinism (B vs C ordering in diamond DAG).

### test_screen_state_tree_and_action_mask.py (22 tests)
- **Well covered:** Rect geometry, element lookup, clickable filtering, dialog/quest element extraction, modal state, action allow/deny per page, forbidden actions, custom masks.
- **Missing coverage:**
  - No test for empty ScreenStateTree (no elements) -- the code handles it (empty tuple iterates fine), but no test verifies it.
  - No test for `TextBlock` or `RegionNode` functionality.
  - No test for `to_dict()` completeness (only checks page_id and element_count).
  - No test for `categories()` method.
  - No negative test for `find_element_by_text` with no matches.

### test_mainline_runner.py (12 tests)
- **Well covered:** Linear execution, invalid/cyclic graph rejection, skill execution success/failure, predecessor cascade, duration budget, sentinel integration, empty/single/diamond graphs.
- **Missing coverage:**
  - No test for `claim_check_fn` usage (it's passed but never used in the runner).
  - No test for sentinel intervention triggering (only verifies 0 interventions in healthy case).
  - No test for node retry behavior (max_node_retries > 0 with transient failures).
  - No test for concurrent execution or graph mutation during run.

---

## Summary Table

| ID | Severity | File | Line(s) | Issue |
|----|----------|------|---------|-------|
| C1 | CRITICAL | mainline_runner.py | 100-102 | Silent node drop when get_node returns None |
| C2 | CRITICAL | mainline_runner.py | 87,105-109 | TOCTOU in predecessor check (no graph snapshot) |
| C3 | CRITICAL | mission_graph_v4.py | 149-155 | add_node duplicate destroys edges, changes insertion order |
| C4 | CRITICAL | mission_graph_v4.py | 216 | topological_order uses sorted() not insertion order |
| C5 | CRITICAL | mission_graph_validator_v4.py | 144-153 | Serialization mismatch only warning, not error |
| H1 | HIGH | mainline_runner.py | 112 | input_claims never checked before execution |
| H2 | HIGH | mainline_runner.py | 133-134 | Empty graph semantics unclear, no diagnostic |
| H3 | HIGH | mission_graph_v4.py | 157-160 | add_edge accepts phantom nodes silently |
| H4 | HIGH | mission_graph_validator_v4.py | 52-57 | _check_unique_ids is dead code (duplicates silently replaced) |
| H5 | HIGH | mainline_runner.py | 161 | Unreachable final return in _execute_node |
| H6 | HIGH | screen_state_tree.py | 139-150 | to_dict loses all element/text/region data, no from_dict |
| M1 | MEDIUM | action_mask.py | 167-170 | Custom masks not validated against forbidden IDs |
| M2 | MEDIUM | screen_state_tree.py | 34-56 | NormalizedRect has no bounds validation |
| M3 | MEDIUM | mission_graph_v4.py | 103,262 | from_dict does not validate risk_level |
| M4 | MEDIUM | action_mask.py | 198 | combat_allowed("world_viewport") contradicts actual mask |
| L1 | LOW | mission_graph_v4.py | 29-30 | Duplicated Literal types as frozensets |
| L2 | LOW | mission_graph_v4.py | 228-232 | Inconsistent edge field naming (from_node vs from) |
| L3 | LOW | test_mission_graph_v4_contract.py | 396-399 | Test imports private helper |
| L4 | LOW | action_mask.py | 125 | High-risk action in mask with no fallback enforcement |

---

## Recommendations (Priority Order)

1. **Add snapshot or freeze semantics** to MainlineRunner.run() to prevent TOCTOU (C2). At minimum, document that the graph must not be mutated.
2. **Log and record skipped nodes** when get_node returns None in MainlineRunner (C1).
3. **Decide on add_node duplicate policy**: either raise on duplicate or fully replace edges (C3).
4. **Fix or document topological_order determinism** (C4). If lexicographic is intended, document it; if insertion order is intended, change `sorted()` to insertion-ordered iteration.
5. **Elevate serialization mismatch to error** in validator (C5).
6. **Implement input_claims checking** in MainlineRunner._execute_node (H1).
7. **Validate edges in add_edge** against existing nodes (H3).
8. **Remove dead _check_unique_ids** or make it useful (H4).
9. **Add full serialization** to ScreenStateTree.to_dict and implement from_dict (H6).
10. **Validate custom masks** against forbidden action IDs in ActionMask.__init__ (M1).
