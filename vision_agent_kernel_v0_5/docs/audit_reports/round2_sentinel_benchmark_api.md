# Round 2 Audit Report: Sentinel, Benchmark, Mainline API

**Date:** 2026-05-27
**Auditor:** Round 2 (post-fix verification)
**Scope:** `control/sentinel/` (sentinel_runtime.py, somatic_state.py, recovery_recipe.py, recipes.py), `benchmarks/mainline_curriculum/` (tasks.py, metrics.py), `app_service/mainline_api.py`, and their test files.

---

## Executive Summary

Round 1 fixes are confirmed applied: `detect_anomaly()` is now inside the lock in `intervene()`, `BUDGET_EXHAUSTED` events are recorded in history, `start(None)` is rejected early, `get_claims()` and `get_bagel()` acquire the lock, `bottleneck_task` uses `(tsr, task_id)` tie-breaking, and `MetricSnapshot.to_dict()` includes `timestamp`. All 50 tests pass.

**The budget race is truly fixed.** Anomaly detection and budget decrement are now atomic under `_lock`.

However, the audit found **7 confirmed remaining issues** (3 High, 2 Medium, 2 Low) carried from Round 1, plus **2 new issues introduced by Round 1 fixes**. One Round 1 carryover (H2: LoadingTimeoutRecovery on transient loading) has been downgraded after re-analysis.

---

## Round 1 Fix Verification

| Fix | Status | Evidence |
|-----|--------|----------|
| `detect_anomaly()` inside lock | CONFIRMED | `sentinel_runtime.py:86-87` -- both `detect_anomaly()` and budget check are inside `with self._lock:` |
| BUDGET_EXHAUSTED in history | CONFIRMED | `sentinel_runtime.py:100` -- `self._history.append(event)` before return |
| `start(None)` rejected early | CONFIRMED | `mainline_api.py:98-99` -- early return before lock acquisition |
| `get_claims()` acquires lock | CONFIRMED | `mainline_api.py:132` -- `with self._lock:` |
| `get_bagel()` acquires lock | CONFIRMED | `mainline_api.py:140` -- `with self._lock:` |
| `bottleneck_task` tie-breaking | CONFIRMED | `metrics.py:87` -- `key=lambda m: (m.tsr, m.task_id)` |
| `to_dict()` includes timestamp | CONFIRMED | `metrics.py:60` -- `"timestamp": self.timestamp` |

---

## Confirmed Remaining Issues (from Round 1)

### H1. CombatDefeatRecovery first-match ordering misses co-occurring anomalies

- **Severity:** HIGH
- **File:** `control/sentinel/recipes.py` lines 108-129, `control/sentinel/sentinel_runtime.py` lines 86-87
- **Description:** `detect_anomaly()` iterates recipes in registration order and returns the first match. `default_recipes()` registers recipes in this order: UILost, Stuck, TargetLost, LoadingTimeout, CombatDefeat, LowHealth, Drift, ModelProviderFailure. When combat defeat occurs (`is_healthy() == False`), only `CombatDefeatRecovery` fires because `LowHealthRecovery` (which also checks `hp_ratios[0] < 0.2`) is never reached. If the active character is at 0.0 HP (defeated) AND another character is low, the recovery only addresses the defeat, not the low health. After CombatDefeatRecovery succeeds (simulated), the next call would need to re-detect the still-low health, but the snapshot is unchanged -- the recipes don't actually mutate state. This means: in a real system, CombatDefeat would consume budget without resolving the low-health co-anomaly.
- **Fix:** Either (a) change `detect_anomaly()` to return ALL matching recipes (not just first) and execute them in priority order, or (b) reorder recipes so more specific ones come before general ones and document that only one anomaly is addressed per cycle, or (c) after a successful recovery, re-evaluate with updated state.

### H3. `budget_remaining` and `interventions` properties read without lock

- **Severity:** HIGH
- **File:** `control/sentinel/sentinel_runtime.py` lines 60-66
- **Description:** The properties `budget_remaining` (line 61-62) and `interventions` (line 65-66) read `_global_budget_used` and `_history` without acquiring `_lock`. While `interventions` returns a copy of the list, the read of `_history` itself is not atomic -- another thread could be inside `intervene()` appending to the list. In CPython the GIL prevents corruption, but this is not guaranteed by the API contract and violates the class's own thread-safety claim. `budget_remaining` reads `_global_budget_used` non-atomically while `intervene()` may be incrementing it.
- **Fix:**
```python
@property
def budget_remaining(self) -> int:
    with self._lock:
        return self._max_global_budget - self._global_budget_used

@property
def interventions(self) -> list[SentinelEvent]:
    with self._lock:
        return list(self._history)
```

### H4. `get_skills()` and `run_benchmark()` access shared state without lock

- **Severity:** HIGH
- **File:** `app_service/mainline_api.py` lines 158-176
- **Description:** `get_skills()` (line 160) calls `self._skill_registry.all_skills()` without the lock. `run_benchmark()` (line 175) calls `self._benchmark_report.add(metric)` without the lock. Both access mutable shared state (`_skill_registry` and `_benchmark_report`). If `stop()` is called concurrently (which calls `self._sentinel.reset()` under lock), these methods could see torn reads. The Round 1 fix added locks to `get_claims()` and `get_bagel()`, but missed `get_skills()` and `run_benchmark()`.
- **Fix:**
```python
def get_skills(self) -> dict[str, Any]:
    with self._lock:
        skills = self._skill_registry.all_skills()
        return {
            "total": len(skills),
            "by_tier": self._group_by_tier(skills),
            "skills": [s.to_dict() for s in skills],
        }

def run_benchmark(self, task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        return {"ok": False, "reason": f"unknown task: {task_id}"}
    metric = MetricSnapshot(task_id=task_id, tsr=0.0)
    with self._lock:
        self._benchmark_report.add(metric)
    return {"ok": True, "task_id": task_id, "metric": metric.to_dict()}
```

### M3. MetricSnapshot is mutable (not frozen)

- **Severity:** MEDIUM
- **File:** `benchmarks/mainline_curriculum/metrics.py` lines 21-38
- **Description:** `MetricSnapshot` uses `@dataclass(slots=True)` but not `frozen=True`. Any field can be mutated after creation: `m.tsr = 999.0`. This is a data integrity risk for benchmark results that should be immutable records. The `__post_init__` uses `object.__setattr__` which would work with `frozen=True`.
- **Fix:** Change to `@dataclass(frozen=True, slots=True)`.

### M7. Per-recipe `max_budget` is declared but never enforced

- **Severity:** MEDIUM
- **File:** `control/sentinel/recovery_recipe.py` line 41, `control/sentinel/sentinel_runtime.py` lines 80-119
- **Description:** Each `RecoveryRecipe` declares `max_budget` (values 1-3 across recipes), but `SentinelRuntime.intervene()` only checks `_global_budget_used >= _max_global_budget`. It never tracks or checks per-recipe budget usage. A single recipe can fire unlimited times as long as the global budget is not exhausted. This defeats the purpose of having per-recipe limits (e.g., `LoadingTimeoutRecovery.max_budget = 1` should only fire once).
- **Fix:** Add a `_recipe_budget_used: dict[str, int]` counter to `SentinelRuntime`. In `intervene()`, after selecting a recipe, check `self._recipe_budget_used.get(recipe.recipe_id, 0) >= recipe.max_budget` and skip if exhausted. Increment the per-recipe counter alongside the global one.

---

## Downgraded Issues (Re-analyzed)

### H2 -> M8. LoadingTimeoutRecovery fires on transient loading states

- **Severity:** MEDIUM (downgraded from HIGH)
- **File:** `control/sentinel/recipes.py` lines 85-106
- **Description:** `LoadingTimeoutRecovery.check_precondition()` returns `True` whenever `snapshot.is_loading == True`. In real gameplay, loading screens are normal transients (teleports, domain entries). The recipe fires immediately on any loading frame rather than requiring a sustained loading duration. However, the sentinel only calls `intervene()` when explicitly invoked by the orchestrator -- the orchestrator should not call it during transient loading. The risk is moderate: if the orchestrator naively polls during loading, this triggers false recovery. The `max_budget = 1` mitigates repeated firing.
- **Fix (optional):** Add a `loading_duration_sec: float` field to `SomaticState` and check `snapshot.is_loading and snapshot.loading_duration_sec > 15.0`. Alternatively, document that the orchestrator must not call `intervene()` during known transients.

---

## New Issues Introduced by Round 1 Fixes

### N1. `execute_recovery()` and `verify_restabilized()` called while holding lock

- **Severity:** HIGH
- **File:** `control/sentinel/sentinel_runtime.py` lines 109-113
- **Description:** The Round 1 fix moved `detect_anomaly()` inside the lock, but this means the entire recovery execution (lines 109-113) now runs under `_lock`. `execute_recovery()` and `verify_restabilized()` are virtual methods that subclasses override. In a real implementation, these could perform I/O (send inputs, wait for screen changes) which would block the sentinel thread and prevent any other thread from calling `update_snapshot()`, `reset_budget()`, `reset()`, or `intervene()`. Even in the current stub implementation, this is an architectural hazard -- the lock is held for the entire duration of recovery, not just the critical section.
- **Fix:** Restructure to perform detection + budget check under the lock, release the lock, execute recovery, then re-acquire the lock to record results:
```python
def intervene(self, snapshot: SomaticState) -> SentinelEvent | None:
    with self._lock:
        recipe = self.detect_anomaly(snapshot)
        if recipe is None:
            return None
        if self._global_budget_used >= self._max_global_budget:
            # ... record BUDGET_EXHAUSTED under lock
            return event
        if self._recipe_budget_used.get(recipe.recipe_id, 0) >= recipe.max_budget:
            return None
        self._global_budget_used += 1
        # ... pre-register event
    # Execute recovery OUTSIDE the lock
    result = recipe.execute_recovery()
    if result.status == "success":
        recipe.verify_restabilized()
    with self._lock:
        event.result = result
        event.budget_used = self._global_budget_used
        self._history.append(event)
    return event
```

### N2. SentinelEvent mutated after construction (breaks immutability pattern)

- **Severity:** MEDIUM
- **File:** `control/sentinel/sentinel_runtime.py` lines 103-117
- **Description:** `SentinelEvent` is constructed on line 103 with `result=None`, then mutated on line 110 (`event.result = result`) and line 116 (`event.budget_used = self._global_budget_used`). The `__post_init__` uses `object.__setattr__` for timestamp (suggesting frozen-like intent), but the dataclass is not frozen. This means events in `_history` can be mutated by any holder of a reference, breaking the audit trail integrity. The `__post_init__` pattern with `object.__setattr__` is inconsistent with the rest of the class being mutable -- it suggests the developer intended frozen but did not apply it.
- **Fix:** Either make `SentinelEvent` frozen (with `frozen=True`) and construct it fully after recovery completes, or document that it is intentionally mutable and add a `finalized: bool` flag.

---

## Remaining Carryover Issues (Low Severity)

### L1. event_id collision risk

- **Severity:** LOW
- **File:** `control/sentinel/sentinel_runtime.py` lines 94, 104
- **Description:** `event_id` uses `f"sentinel_{int(time.perf_counter())}"`. If two interventions occur within the same millisecond (e.g., in tests or rapid polling), they produce identical IDs. The `int()` truncation makes this likely in automated tests.
- **Fix:** Use a monotonic counter or UUID: `f"sentinel_{self._next_event_id}"` with `self._next_event_id = 0` incremented under lock, or `uuid.uuid4().hex[:12]`.

### L6. `test_start_twice_fails` has misleading name and wrong semantics

- **Severity:** LOW
- **File:** `tests/test_mainline_api.py` lines 43-50
- **Description:** The test is named `test_start_twice_fails` but actually asserts `result["ok"]` is True on the second call (line 50). The first `start()` completes synchronously (state goes to "completed"), so the second `start()` finds state != "running" and proceeds. The test name implies it should fail, and a reader would expect the assertion to check for failure. The comment on line 47 acknowledges this but the name is still misleading.
- **Fix:** Rename to `test_start_after_completion_succeeds` or add a separate `test_start_while_running_fails` that actually tests the concurrent-running guard.

---

## Unchanged Issues (Not Repeated in Detail)

| ID | Severity | Status | Description |
|----|----------|--------|-------------|
| M4 | MEDIUM | UNFIXED | `BenchmarkReport` is not thread-safe -- `task_metrics` list is mutated without synchronization |
| M6 | MEDIUM | UNFIXED | `SentinelEvent` is not frozen but stores history records |
| M8 | LOW | UNFIXED | `run_benchmark` is a placeholder returning `tsr=0.0` |

---

## Answers to Specific Questions

### Is the budget race truly fixed now?

**Yes.** The TOCTOU race between `detect_anomaly()` and `_global_budget_used` increment is eliminated. Both are now inside `with self._lock:` in `intervene()` (lines 86-119). No thread can observe a stale budget between detection and decrement.

However, a new concern is introduced: `budget_remaining` (line 61-62) and `interventions` (line 65-66) still read without the lock, so external readers can see stale values. This does not affect the correctness of budget enforcement inside `intervene()`, but it violates the thread-safety contract for external observers.

### Are there any remaining thread safety issues?

**Yes, three:**

1. `budget_remaining` and `interventions` properties read without lock (H3 above)
2. `get_skills()` and `run_benchmark()` in MainlineAPI access shared state without lock (H4 above)
3. `BenchmarkReport.add()` is not synchronized (M4 from Round 1)

### Any NEW issues from Round 1 fixes?

**Yes, two:**

1. `execute_recovery()` now runs inside the lock (N1), which is a blocking hazard for real implementations
2. `SentinelEvent` mutation pattern is inconsistent with `__post_init__`'s frozen-like behavior (N2)

---

## Summary Table

| ID | Severity | File | Description |
|----|----------|------|-------------|
| H1 | HIGH | recipes.py:108-129, sentinel_runtime.py:86-87 | First-match recipe ordering misses co-occurring anomalies |
| H3 | HIGH | sentinel_runtime.py:60-66 | `budget_remaining` and `interventions` read without lock |
| H4 | HIGH | mainline_api.py:158-176 | `get_skills()` and `run_benchmark()` bypass lock |
| N1 | HIGH | sentinel_runtime.py:109-113 | Recovery execution runs under lock -- blocking hazard |
| M3 | MEDIUM | metrics.py:21-38 | MetricSnapshot is mutable (not frozen) |
| M7 | MEDIUM | recovery_recipe.py:41, sentinel_runtime.py:80-119 | Per-recipe max_budget declared but never enforced |
| N2 | MEDIUM | sentinel_runtime.py:103-117 | SentinelEvent mutated post-construction, inconsistent with __post_init__ pattern |
| L1 | LOW | sentinel_runtime.py:94,104 | event_id collision risk from int-truncated timestamp |
| L6 | LOW | test_mainline_api.py:43-50 | test_start_twice_fails is misleadingly named |
