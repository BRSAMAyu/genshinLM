# Final Convergence Audit

**Branch:** `codex/pre-realworld-closure`
**Scope:** Main autonomy loop + data flow (10 critical-path files)
**Goal:** Find any remaining bugs, logic errors, thread-safety issues, or correctness problems that could crash or corrupt data in a 30-minute autonomous session.

---

## Summary

After exhaustive line-by-line review of the entire critical path, I found **1 HIGH** issue, **4 MEDIUM** issues, and **5 LOW** issues. The codebase is in good shape overall. No crash-inducing unhandled exceptions or data-race conditions were found on the main happy path. The HIGH issue is a genuine resource leak that will slowly degrade performance in a long session.

---

## Findings

### F-01: HIGH -- ClaimGraph.compact() never removes AdjudicationEvents

- **File:** `runtime/claim_runtime.py`, line 389
- **Description:** `compact()` iterates terminal claims and tries `self._adjudications.pop(cid, None)`, but `_adjudications` is keyed by `adjudication_id` (e.g., `"adj:claim_x:uuid"`), not by `claim_id`. The pop always returns `None` because the key never matches. AdjudicationEvents accumulate without bound.
- **Impact:** In a 30-minute session with frequent claim adjudication, `_adjudications` grows linearly. `get_adjudications_for()` (line 276-277) scans all adjudications via a full-value iteration, so its cost grows with every added adjudication. Over hundreds of claims, this becomes noticeable. The dict itself also holds memory indefinitely.
- **Fix:** Change the compact method to remove adjudications whose `claim_id` is being compacted:

```python
# In compact(), replace line 389:
# self._adjudications.pop(cid, None)
# with:
adj_to_remove = [
    aid for aid, adj in self._adjudications.items()
    if adj.claim_id == cid
]
for aid in adj_to_remove:
    del self._adjudications[aid]
```

Alternatively, maintain a reverse index `_adjudications_by_claim: dict[str, list[str]]` for O(1) lookup.

---

### F-02: MEDIUM -- ClaimProducingExecutor._journal grows without bound

- **File:** `runtime/claim_runtime.py`, lines 996, 1073
- **Description:** `_journal: list[RunJournalEntry]` appends on every `produce_claim()` call with no cap. `summarize_for_llm()` scans the full list, and `journal` property copies the entire list.
- **Impact:** In a 30-minute session producing hundreds of claims, the list grows indefinitely. Memory leak is slow but real. If the session runs longer (multi-hour), this becomes a problem.
- **Fix:** Cap `_journal` to a reasonable window (e.g., last 200 entries):

```python
self._journal.append(journal_entry)
if len(self._journal) > 200:
    self._journal = self._journal[-100:]
```

---

### F-03: MEDIUM -- QuestContextPersistence accumulates versioned files without auto-pruning

- **File:** `planning/mainline/quest_context_persistence.py`, lines 50-70
- **Description:** `save()` writes a new file for every context version. `prune_old()` exists but is never called automatically. In a 30-minute session with frequent updates (every frame), this can create thousands of files in the `runs/` directory.
- **Impact:** Disk space exhaustion in long sessions; file system slowdown when listing/reading directory contents.
- **Fix:** Call `prune_old(keep_last=20)` at the end of `save()`, or have the caller invoke it periodically.

---

### F-04: MEDIUM -- BossCombatRuntime._combo_snapshot restoration after tick may cause stale step replay

- **File:** `combat/boss_combat_runtime.py`, lines 162-177
- **Description:** The snapshot is captured at line 172 *before* `executor.tick()` at line 174. If `tick()` returns `None` (no ready action) and internally advances `_current_step`, the next frame's combo_broken path restores the pre-tick snapshot, effectively re-executing the step that already produced no action. This can cause the executor to loop on a condition-failing step indefinitely.
- **Impact:** In rare cases where an action's condition never becomes true and combos break repeatedly, the combat loop can get stuck re-checking the same failing action. The `_combo_break_count > 3` guard eventually triggers a safe abort, so this is not a permanent hang, but it wastes up to 3 combat frames.
- **Fix:** Capture the snapshot *after* the tick succeeds (i.e., move line 172 to after line 176), or only capture when `action is not None`.

---

### F-05: MEDIUM -- MainlineAutonomyLoop.run_once() does not validate BAGEL belief commitment success

- **File:** `planning/mainline/mainline_runner.py`, lines 286-290
- **Description:** The `commit_beliefs` phase iterates all nodes and commits beliefs, but `commit_node_beliefs()` (line 213-231) calls `bagel.commit_belief()` without checking if the belief was actually committed (e.g., if FIG rejects a post-hoc belief). No exception is caught, and no status check is performed.
- **Impact:** If a belief commit fails silently, the node executes without its required nominal belief, violating the BAGEL invariant. This could lead to incorrect attribution later.
- **Fix:** Check the return value of `commit_belief()` and skip or flag nodes whose belief commitments failed.

---

### F-06: LOW -- SignalEvidence.timestamp uses time.time() instead of time.perf_counter()

- **File:** `runtime/claim_runtime.py`, line 51
- **Description:** `SignalEvidence.timestamp` defaults to `time.time()`. The project convention (per CLAUDE.md) is to use `time.perf_counter()` for all logic timestamps. `time.time()` can jump backwards on clock adjustments.
- **Impact:** If a system clock adjustment occurs during a session, `SignalEvidence` timestamps could be ordered incorrectly. In practice, these timestamps are used for audit/display, not logic, so the impact is minimal.
- **Fix:** Change default to `time.perf_counter()` for consistency.

---

### F-07: LOW -- QuestContextPersistence._saved_at uses time.time()

- **File:** `planning/mainline/quest_context_persistence.py`, line 197
- **Description:** `_saved_at: time.time()` in `_context_to_dict()` uses wall clock. Same convention concern as F-06.
- **Impact:** Cosmetic only -- this is a debug/audit field.
- **Fix:** Use `time.perf_counter()` or document this as intentional (persistence is a valid use of wall-clock time).

---

### F-08: LOW -- ClaimGraphWorker.submit() auto-starts on dead thread

- **File:** `runtime/claim_worker.py`, lines 86-88
- **Description:** If the worker thread dies (crash, unhandled exception), `submit()` silently restarts it. This could mask persistent failures and lose in-flight state.
- **Impact:** A crashed worker restarts with a fresh queue, losing any commands that were in-flight. The `graph` object is shared, so no data loss there, but in-flight commands are dropped.
- **Fix:** Log a warning when auto-restarting. Consider adding a `_crash_count` to prevent infinite restart loops.

---

### F-09: LOW -- MissionGraphV4.add_node() mutates _node_order via filter-reassignment

- **File:** `planning/mainline/mission_graph_v4.py`, lines 178-181
- **Description:** When re-adding an existing node, `_node_order` is rebuilt via list comprehension. This is O(n) and creates a new list. While the class docstring says mutations should be done during construction before sharing, this is a minor inefficiency.
- **Impact:** Negligible -- graphs are small (typically < 20 nodes) and mutation happens only during construction.
- **Fix:** No action needed. The existing behavior is correct.

---

### F-10: LOW -- MainlineRunner._execute_node() dry-run path does not respect claim gating

- **File:** `planning/mainline/mainline_runner.py`, lines 200-209
- **Description:** In dry-run mode (no `skill_execute_fn`), nodes always succeed without checking `input_claims`. The `run()` method does check predecessor completion (line 149-153), but does not validate `input_claims` contracts.
- **Impact:** Dry-run testing may pass for graphs that would fail in real execution due to unsatisfied claim preconditions. This is an intentional design trade-off (dry-run is for structure, not semantics).
- **Fix:** Add a log warning when skipping claim validation in dry-run mode, or add an optional `validate_claims_in_dry_run` flag.

---

## Positive Findings (no issues)

The following areas were reviewed and found to be correct:

1. **StateBus (core/state_bus.py):** All shared mutable state is properly protected by locks. `LatestSlot`, `RingBuffer`, and `PriorityEventQueue` all use `threading.RLock`. Subscriber list management is correctly snapshot-then-dispatch.

2. **ClaimGraphWorker (runtime/claim_worker.py):** Single-writer event loop pattern is correctly implemented. The exception handler at line 107-126 properly catches all exceptions, marks claims as error, and surfaces results without killing the worker.

3. **MissionGraphV4 (planning/mainline/mission_graph_v4.py):** Cycle detection and topological sort (Kahn's algorithm) are correctly implemented. Insertion-order determinism is preserved. `from_dict()`/`to_dict()` round-trip is lossless.

4. **ActiveQuestContext (planning/mainline/active_quest_context.py):** Immutable dataclass with `evolve()` correctly incrementing version. No thread-safety issues since all mutations produce new objects.

5. **QuestStateTrackerV2 (planning/mainline/quest_state_tracker_v2.py):** Confidence decay uses proper exponential decay formulas. `_compute_delta()` correctly detects no-change scenarios and returns None. The `_last_ocr_had_quest` flag prevents confidence from staying high after quest text disappears.

6. **BossCombatRuntime (combat/boss_combat_runtime.py):** State machine transitions are complete and cover all branches. `_safe_abort()` is reachable from every failure path. The `_target_lost_window` deque is bounded by `maxlen=10`. Reflex preemption and resume contracts are correctly handled.

7. **SentinelRuntime (control/sentinel/sentinel_runtime.py):** Budget enforcement is atomic under lock. Recovery execution runs outside the lock to avoid blocking. History is bounded by global budget (default 10).

8. **SomaticState (control/sentinel/somatic_state.py):** Immutable with `evolve()`. No shared mutable state.

9. **BagelRuntime.quest_transition():** Correctly evicts terminal beliefs, clears evidence matrix, resets probe taboos, and carries forward specified beliefs. No dangling references.

10. **ClaimGraph.compact():** Correctly removes claims, observations (by observation_id), children, evidence, and dependency gaps. Only the adjudication removal is broken (F-01 above).

---

## Conclusion

**1 HIGH issue found.** The `compact()` adjudication key mismatch (F-01) is the only issue that will cause measurable degradation in a 30-minute session. All other issues are MEDIUM or lower and represent minor correctness gaps, slow resource growth, or convention violations. The codebase is ready for a 30-minute autonomous session with the F-01 fix applied.
