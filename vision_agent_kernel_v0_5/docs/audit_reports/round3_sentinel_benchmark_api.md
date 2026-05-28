# Round 3 (FINAL) Audit Report: Sentinel, Benchmark, Mainline API

**Date:** 2026-05-27
**Auditor:** Round 3 (final verification)
**Scope:** `control/sentinel/` (sentinel_runtime.py, somatic_state.py, recovery_recipe.py, recipes.py), `benchmarks/mainline_curriculum/` (tasks.py, metrics.py), `app_service/mainline_api.py`, and their test files.

---

## Executive Summary

All 11 fixes from Round 2 are **confirmed applied and correct**. The sentinel thread safety model is now structurally complete. All 50 tests pass.

The 3-phase lock pattern in `intervene()` is correct: detect+reserve under lock, execute outside, record under lock. Budget accounting is atomic. All API getters acquire the lock. Immutable dataclasses are properly frozen.

**4 remaining issues found** (0 Critical, 0 High, 2 Medium, 2 Low). None are blocking. The sentinel thread safety model is complete.

---

## Fix Verification (all 11 items)

### Fix 1: intervene() 3-phase lock pattern
- **Status:** CONFIRMED CORRECT
- **File:** `control/sentinel/sentinel_runtime.py` lines 85-137
- **Evidence:** Phase 1 (lines 92-119) acquires `self._lock` for anomaly detection and budget reservation. Phase 2 (lines 121-124) executes `recipe.execute_recovery()` and `recipe.verify_restabilized()` OUTSIDE the lock. Phase 3 (lines 126-135) re-acquires `self._lock` to append the event to `_history`. This is the correct pattern: the lock is held only for bookkeeping, not for I/O-bound recovery execution.
- **Correctness analysis:** Between Phase 1 and Phase 3, the budget has been reserved but the event is not yet in history. If the process crashes during Phase 2, the budget slot is lost (reserved but no event recorded). This is acceptable behavior -- budget exhaustion on crash is a safe failure mode. No event duplication is possible because `event_id` is generated separately in Phase 3.
- **Concurrency analysis:** Two threads calling `intervene()` concurrently with the same snapshot are safe. Thread A reserves budget in Phase 1, releases lock. Thread B enters Phase 1, may or may not find an anomaly (same snapshot, same recipes). If it does, it reserves the next budget slot. Both execute recovery concurrently (intentional -- recipes are stateless stubs). Both record events in Phase 3. The events will have different `event_id` values (UUID-based). Global budget correctly reflects 2 consumed. This is correct.

### Fix 2: Per-recipe budget enforced
- **Status:** CONFIRMED CORRECT
- **File:** `control/sentinel/sentinel_runtime.py` lines 58, 109-117, 143, 149
- **Evidence:** `_recipe_budget_used: dict[str, int]` initialized at line 58. Checked at lines 109-113 (if per-recipe budget exhausted, return None). Incremented at line 117. Cleared in `reset_budget()` (line 143) and `reset()` (line 149).
- **Edge case verified:** When per-recipe budget is exhausted but global budget remains, `intervene()` returns None (line 113). This is correct -- the recipe is simply skipped. The event is NOT recorded in history (silent skip), which is the documented behavior (log.info at line 112).

### Fix 3: SentinelEvent is frozen=True
- **Status:** CONFIRMED CORRECT
- **File:** `control/sentinel/sentinel_runtime.py` line 27
- **Evidence:** `@dataclass(frozen=True, slots=True)`. The `__post_init__` at line 37-39 uses `object.__setattr__` which is the correct pattern for initializing computed defaults on frozen dataclasses. No other code mutates SentinelEvent fields (verified by grepping for all SentinelEvent construction sites at lines 99-106 and 127-133 -- both construct complete events in a single expression).

### Fix 4: event_id uses UUID
- **Status:** CONFIRMED CORRECT
- **File:** `control/sentinel/sentinel_runtime.py` lines 100, 128
- **Evidence:** `uuid.uuid4().hex[:12]` provides 48 bits of entropy. Collision probability for 2 concurrent events is approximately 1 in 2.8 * 10^14 -- negligible. The `uuid` module is imported at line 16.

### Fix 5: budget_remaining and interventions acquire lock
- **Status:** CONFIRMED CORRECT
- **File:** `control/sentinel/sentinel_runtime.py` lines 63-71
- **Evidence:** Both properties use `with self._lock:`. `budget_remaining` returns the computed value atomically. `interventions` returns `list(self._history)` (a shallow copy), preventing external mutation of the internal list. The copy is made under the lock, so the returned list reflects a consistent snapshot.

### Fix 6: ALL API getters acquire lock
- **Status:** CONFIRMED CORRECT
- **File:** `app_service/mainline_api.py`
- **Evidence:**
  - `get_state()`: line 79 `with self._lock:`
  - `get_claims()`: line 132 `with self._lock:`
  - `get_bagel()`: line 140 `with self._lock:`
  - `get_skills()`: line 160 `with self._lock:`
  All four getters wrap their entire body in `with self._lock:`.

### Fix 7: run_benchmark acquires lock for report.add()
- **Status:** CONFIRMED CORRECT
- **File:** `app_service/mainline_api.py` lines 174-176
- **Evidence:** `self._benchmark_report.add(metric)` is inside `with self._lock:`. The `get_task()` call at line 170 is outside the lock (correct -- it is a pure function reading an immutable tuple).

### Fix 8: start(None) rejected early
- **Status:** CONFIRMED CORRECT
- **File:** `app_service/mainline_api.py` lines 98-99
- **Evidence:** `if graph is None: return {"ok": False, "reason": "no_graph"}` runs before any lock acquisition.

### Fix 9: MetricSnapshot is frozen=True
- **Status:** CONFIRMED CORRECT
- **File:** `benchmarks/mainline_curriculum/metrics.py` line 21
- **Evidence:** `@dataclass(frozen=True, slots=True)`. The `__post_init__` at line 40-42 uses `object.__setattr__` for timestamp initialization. No other code mutates MetricSnapshot fields.

### Fix 10: bottleneck_task uses (tsr, task_id) tie-breaking
- **Status:** CONFIRMED CORRECT
- **File:** `benchmarks/mainline_curriculum/metrics.py` line 87
- **Evidence:** `key=lambda m: (m.tsr, m.task_id)` provides deterministic tie-breaking. Since `task_id` values are strings like "C0"-"C11", lexicographic ordering gives deterministic results. For equal TSR, the task with the lexicographically smallest task_id is returned.

### Fix 11: to_dict() includes timestamp
- **Status:** CONFIRMED CORRECT
- **File:** `benchmarks/mainline_curriculum/metrics.py` line 60
- **Evidence:** `"timestamp": self.timestamp` is included in the returned dict. The `to_json()` method calls `to_dict()`, so JSON output also includes timestamp.

---

## Remaining Issues

### M1. Recipe failure_policy return type mismatch (type-safety)

- **Severity:** MEDIUM
- **File:** `control/sentinel/recipes.py` lines 34, 58, 81, 104, 128, 154, 177, 201
- **Description:** The base class `RecoveryRecipe.failure_policy` is typed as `-> RecoveryPolicy` (a `Literal["abort", "replan", "ask_user", "escalate"]`). All 8 concrete recipe subclasses declare `-> str` instead. This is an LSP violation -- mypy in strict mode would flag this as an incompatible override. The return values themselves are valid strings that happen to match the Literal options, but the type annotation is broader than the base contract. This means callers who expect `RecoveryPolicy` cannot rely on type narrowing.
- **Fix:** Change all subclass annotations from `-> str` to `-> RecoveryPolicy` (import `RecoveryPolicy` from `recovery_recipe.py`).

### M2. First-match recipe ordering misses co-occurring anomalies (design)

- **Severity:** MEDIUM
- **File:** `control/sentinel/sentinel_runtime.py` lines 78-83, `control/sentinel/recipes.py` lines 207-217
- **Description:** `detect_anomaly()` returns the FIRST matching recipe from the registration order. When multiple conditions are true simultaneously (e.g., `is_stuck=True` AND `is_target_lost=True`), only the first-registered matching recipe fires. The next intervention call would then need to re-detect the remaining anomaly. This works correctly in the current synchronous stub implementation where recipes don't actually change state, but in a real system where recipes take physical actions, the deferred anomaly could worsen while waiting for the next intervention cycle.
- **Impact:** Currently mitigated by (a) recipe registration order (specific conditions first), (b) per-recipe budget limits, and (c) the sentinel being called in a polling loop. Not a correctness bug, but a design limitation worth documenting.
- **Recommendation:** Either document that only one anomaly is addressed per cycle and callers must re-poll, or implement multi-recipe batch execution.

### L1. No concurrency tests for thread-safety claims

- **Severity:** LOW
- **File:** `tests/test_sentinel_recovery.py`, `tests/test_mainline_api.py`
- **Description:** Both `SentinelRuntime` and `MainlineAPI` document thread-safety in their docstrings. The code uses `threading.Lock` in 5 critical sections across the two classes. However, no test exercises concurrent access. The 50 tests are all single-threaded. Without concurrency tests, regressions in the lock protocol (e.g., someone removing a `with self._lock:` block) would not be caught.
- **Recommendation:** Add at minimum: (a) a test that spawns 10 threads calling `intervene()` concurrently with budget=10 and verifies exactly 10 events in history, (b) a test that calls `get_state()` concurrently with `start()` to verify no crash or torn read.

### L2. test_start_twice_fails name is misleading

- **Severity:** LOW
- **File:** `tests/test_mainline_api.py` lines 43-50
- **Description:** The test is named `test_start_twice_fails` but actually verifies that starting after a completed mission succeeds. The first `start()` completes synchronously (state goes to "completed"), so the second call does not find state=="running" and proceeds. The comment acknowledges this but the name suggests a different test than what runs.
- **Fix:** Rename to `test_start_after_completion_succeeds` and add a separate test for the actual concurrent-running rejection path (which would require mocking `_runner.run()` to not complete immediately).

---

## Answers to Specific Questions

### Is the sentinel thread safety model now complete?

**Yes.** The model is complete. All mutable shared state is protected:
- `_global_budget_used` and `_recipe_budget_used`: only read/written under `_lock`
- `_history`: only appended under `_lock`, copied on read under `_lock`
- `_last_snapshot`: only written under `_lock`
- API's `_state`, `_benchmark_report`, and wrapped objects: accessed under `_lock`

The 3-phase lock pattern in `intervene()` is the correct approach for the execute-outside-lock pattern. Budget reservation is atomic, recovery execution does not block other callers, and event recording is atomic.

### Is the 3-phase lock pattern correct?

**Yes.** The pattern is:
1. **Lock acquired:** detect anomaly, check budget, reserve budget slot, capture local variables
2. **Lock released:** execute recovery (potentially blocking I/O)
3. **Lock acquired:** record event in history

This is a standard "reserve-execute-commit" pattern. Potential concerns addressed:
- **Crash during Phase 2:** Budget slot is lost (reserved but no event). Safe failure mode -- the system becomes more conservative, not more aggressive.
- **Concurrent interventions:** Each thread reserves its own budget slot independently. Multiple recoveries may execute concurrently. This is acceptable because recipes are stateless stubs in the current implementation. In a real system with stateful recovery (e.g., keyboard input), the execution layer itself must provide serialization (which `InputLease` does per the architecture).
- **Event ordering:** Events are appended in Phase 3 completion order, not Phase 1 initiation order. This is correct -- the system records when recovery actually completed, not when it started.

### Any remaining CRITICAL issues?

**No.** There are zero CRITICAL or HIGH severity issues remaining. The 2 medium issues are type annotation mismatches (M1) and a design limitation that is already mitigated (M2). The 2 low issues are missing test coverage (L1) and a test naming issue (L2).

---

## Test Results

```
50 passed in 0.35s
  - test_sentinel_recovery.py: 25 passed
  - test_mainline_api.py: 12 passed
  - test_benchmark_curriculum.py: 13 passed
```

All tests pass. No import errors, no type errors at runtime, no assertion failures.

---

## Summary Table

| ID | Severity | File | Lines | Description | Status |
|----|----------|------|-------|-------------|--------|
| Fix 1 | -- | sentinel_runtime.py | 85-137 | 3-phase lock pattern | VERIFIED |
| Fix 2 | -- | sentinel_runtime.py | 58,109-117 | Per-recipe budget enforced | VERIFIED |
| Fix 3 | -- | sentinel_runtime.py | 27 | SentinelEvent frozen=True | VERIFIED |
| Fix 4 | -- | sentinel_runtime.py | 100,128 | event_id uses UUID | VERIFIED |
| Fix 5 | -- | sentinel_runtime.py | 63-71 | Properties acquire lock | VERIFIED |
| Fix 6 | -- | mainline_api.py | 79,132,140,160 | All getters acquire lock | VERIFIED |
| Fix 7 | -- | mainline_api.py | 174-176 | run_benchmark acquires lock | VERIFIED |
| Fix 8 | -- | mainline_api.py | 98-99 | start(None) rejected | VERIFIED |
| Fix 9 | -- | metrics.py | 21 | MetricSnapshot frozen=True | VERIFIED |
| Fix 10 | -- | metrics.py | 87 | bottleneck_task tie-breaking | VERIFIED |
| Fix 11 | -- | metrics.py | 60 | to_dict() includes timestamp | VERIFIED |
| M1 | MEDIUM | recipes.py | 34,58,81,104,128,154,177,201 | failure_policy return type `str` vs `RecoveryPolicy` | UNFIXED |
| M2 | MEDIUM | sentinel_runtime.py, recipes.py | 78-83, 207-217 | First-match ordering misses co-occurring anomalies (mitigated) | UNFIXED (design) |
| L1 | LOW | tests/ | -- | No concurrency tests for thread-safety claims | UNFIXED |
| L2 | LOW | test_mainline_api.py | 43-50 | test_start_twice_fails is misleadingly named | UNFIXED |
