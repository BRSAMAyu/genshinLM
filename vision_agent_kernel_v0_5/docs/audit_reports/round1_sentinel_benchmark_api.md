# Round 1 Audit Report: Sentinel Recovery, Benchmark Curriculum, Cockpit API

**Auditor**: Automated Code Audit (Round 1)
**Date**: 2026-05-27
**Scope**: `control/sentinel/`, `benchmarks/mainline_curriculum/`, `app_service/mainline_api.py`, associated tests

---

## Summary

12 files audited. 21 findings: 2 CRITICAL, 5 HIGH, 8 MEDIUM, 6 LOW.

---

## CRITICAL Findings

### C1. Budget Race Condition in `SentinelRuntime.intervene()`
**File**: `control/sentinel/sentinel_runtime.py`, lines 80-116
**Severity**: CRITICAL

`detect_anomaly()` at line 85 runs *outside* the lock. Two concurrent threads calling `intervene()` can both pass `detect_anomaly()`, both see `budget_remaining > 0`, and then both enter the `with self._lock:` block at line 89. The budget check at line 90 will pass for both since the second thread hasn't incremented yet. This allows the global budget to be exceeded by up to (N-1) where N is the number of concurrent callers.

```
Thread A: detect_anomaly() -> recipe found
Thread B: detect_anomaly() -> recipe found
Thread A: acquire lock, budget_used=0 < max_budget=1, execute, budget_used=1, release lock
Thread B: acquire lock, budget_used=1 >= max_budget=1 -> BUDGET_EXHAUSTED (correct if max=1)
```

But with `max_global_budget=2`, two threads can both see 0 < 2 and both increment, resulting in budget_used=2. A third thread would be rejected. The real issue is that when budget is at `max_budget - 1`, N threads can all pass the anomaly check simultaneously, and all enter the lock sequentially -- all would be allowed since the check is `>= max_budget`. The total used can reach `max_budget + N - 1`.

**Fix**: Move `detect_anomaly()` inside the lock, or use an atomic compare-and-increment pattern. Alternatively, check budget *before* calling detect_anomaly and re-check inside the lock.

### C2. `start()` Releases Lock Before `runner.run()` Completes -- `pause()`/`stop()` Have No Effect During Execution
**File**: `app_service/mainline_api.py`, lines 95-112
**Severity**: CRITICAL

The `start()` method acquires `self._lock` at line 97, sets `runner_state = "running"`, and then **releases the lock** before calling `self._runner.run(graph)` at line 105. The `run()` call is blocking and can take minutes. During this time:
- `pause()` at line 114 will acquire the lock, see `runner_state == "running"`, set it to "paused", and return `{"ok": True}`. But the runner is still executing inside `run()` -- the pause is a no-op because `MainlineRunner.run()` never checks for a pause signal.
- `stop()` at line 122 similarly sets `runner_state = "stopped"` but doesn't actually stop the running execution.
- A second `start()` call will correctly be rejected since `runner_state` is still "running".

This is a design gap rather than a data corruption bug, but the API contract (pause/stop during execution) is broken.

**Fix**: Either run `runner.run()` in a background thread and have the loop check a cancellation flag, or document that start() is synchronous and pause/stop are only effective between runs.

---

## HIGH Findings

### H1. `CombatDefeatRecovery.check_precondition` is Too Broad -- False Positive on Non-Combat Anomalies
**File**: `control/sentinel/recipes.py`, lines 113-115
**Severity**: HIGH

```python
def check_precondition(self, snapshot: SomaticState) -> bool:
    return not snapshot.is_healthy()
```

`is_healthy()` returns `False` only when ALL team members have HP = 0.0 (line 70 in somatic_state.py). This is correct for detecting a wipe. However, `is_healthy()` also returns `True` when `hp_ratios` is empty (unknown state). This means `CombatDefeatRecovery` only fires when hp_ratios is populated AND all are zero. This is actually narrow enough.

The real issue is **recipe ordering**: since `detect_anomaly()` (line 73-78 in sentinel_runtime.py) returns the FIRST matching recipe, and `CombatDefeatRecovery` (index 4 in `default_recipes()`) comes AFTER `LowHealthRecovery` (index 5 in the list -- wait, no). Let me re-examine: the order in `default_recipes()` at recipes.py line 207-217 is:

1. UILostRecovery
2. StuckRecovery
3. TargetLostRecovery
4. LoadingTimeoutRecovery
5. CombatDefeatRecovery
6. LowHealthRecovery
7. DriftRecovery
8. ModelProviderFailureRecovery

If a team has all HP=0.0, `CombatDefeatRecovery` fires (index 4). But `LowHealthRecovery` (index 5) never gets a chance because `CombatDefeatRecovery` already matched `not is_healthy()`. This is correct -- defeat takes priority over low health.

However, consider a snapshot where `is_stuck=True` AND `is_target_lost=True`. Only `StuckRecovery` fires (index 1), and `TargetLostRecovery` is never tried. This is a design decision (first-match wins) but it means co-occurring anomalies are only partially recovered. The sentinel doesn't loop to find additional matching recipes.

**Impact**: Multiple simultaneous anomalies only have the first one recovered. This is a partial mitigation gap.

### H2. `LoadingTimeoutRecovery` Fires on Transient Loading States
**File**: `control/sentinel/recipes.py`, lines 85-106
**Severity**: HIGH

The precondition `snapshot.is_loading` has no duration check. Normal loading screens in games last 5-30 seconds. If the sentinel polls every second, it will trigger `LoadingTimeoutRecovery` during a perfectly normal loading screen. The precondition should also check that loading has persisted beyond a threshold (e.g., 60 seconds).

**Fix**: Add a `loading_start_time` field to SomaticState and check duration in the precondition, or pass a time-in-loading parameter.

### H3. `BudgetReport.bottleneck_task` Returns Wrong Result When Multiple Tasks Have TSR=0
**File**: `benchmarks/mainline_curriculum/metrics.py`, lines 82-86
**Severity**: HIGH

```python
@property
def bottleneck_task(self) -> str:
    if not self.task_metrics:
        return ""
    return min(self.task_metrics, key=lambda m: m.tsr).task_id
```

When multiple tasks have `tsr=0.0`, `min()` returns the first one in insertion order. If tasks were added out of order (e.g., C6 first, then C0), the bottleneck would be reported as C6 even though C0 is easier and failing. More importantly, `bottleneck_task` should ideally return ALL zero-TSR tasks, or at minimum the one with the lowest task_id for determinism.

**Fix**: Sort by (tsr, task_id) for deterministic tie-breaking.

### H4. `MainlineAPI.get_claims()` and `get_bagel()` Not Thread-Safe
**File**: `app_service/mainline_api.py`, lines 129-153
**Severity**: HIGH

`get_claims()` at line 129 and `get_bagel()` at line 136 access `self._claim_graph` and `self._fig` without holding `self._lock`. If another thread calls `stop()` (which calls `self._sentinel.reset()`) or `start()` concurrently, the claim graph or FIG could be in an inconsistent state.

For `get_bagel()`, iterating `self._fig.beliefs`, `self._fig.actions`, etc. without the FIG's own lock is also potentially unsafe if another thread is mutating the FIG.

**Fix**: Acquire `self._lock` in `get_claims()` and `get_bagel()`.

### H5. `MainlineAPI.start()` Accesses `graph.mission_id` Outside Lock
**File**: `app_service/mainline_api.py`, lines 97-103
**Severity**: HIGH

```python
with self._lock:
    if self._state.runner_state == "running":
        return {"ok": False, "reason": "already_running"}
    self._state.runner_state = "running"
    self._state.mission_id = graph.mission_id if graph else ""
```

This is actually safe because `graph.mission_id` is read inside the lock. However, the return at line 99 happens while still holding the lock, which is fine. The real issue is at line 102: `graph.mission_id if graph else ""` -- but `graph` is checked for `None` later at line 104. If `graph` is `None`, `mission_id` is set to `""` and `runner_state` is set to `"running"`, but then line 104 checks `if graph is not None` and falls through to `return {"ok": False, "reason": "no_graph"}`. The state is now stuck at `runner_state = "running"` with no way to recover (no background thread will complete it).

**Fix**: Don't set `runner_state = "running"` if `graph` is None. Move the None check before state mutation.

---

## MEDIUM Findings

### M1. `LowHealthRecovery.check_precondition` Has Redundant Guard
**File**: `control/sentinel/recipes.py`, lines 137-141
**Severity**: MEDIUM

```python
def check_precondition(self, snapshot: SomaticState) -> bool:
    if not snapshot.team_state.hp_ratios:
        return False
    active_hp = snapshot.team_state.hp_ratios[0] if snapshot.team_state.hp_ratios else 1.0
    return active_hp < 0.2
```

The guard at line 138 returns `False` if `hp_ratios` is empty. The ternary at line 140 `if snapshot.team_state.hp_ratios else 1.0` is dead code -- it can never be reached because the function already returned at line 139. Not harmful, but indicates copy-paste from an earlier version without the guard.

### M2. `MetricSnapshot.to_dict()` Omits `timestamp` Field
**File**: `benchmarks/mainline_curriculum/metrics.py`, lines 44-60
**Severity**: MEDIUM

The `timestamp` field is set in `__post_init__` (line 42) but is not included in `to_dict()` output. This means serialized metrics lose their timestamp, making it impossible to reconstruct temporal ordering from exported data. The `to_json()` method delegates to `to_dict()`, so it also lacks the timestamp.

### M3. `MetricSnapshot` Not Frozen -- Mutable by Design
**File**: `benchmarks/mainline_curriculum/metrics.py`, lines 21-38
**Severity**: MEDIUM

Unlike `SomaticState` and `RecoveryResult`, `MetricSnapshot` uses `@dataclass(slots=True)` without `frozen=True`. This means metrics can be accidentally mutated after creation. For a benchmark metric that should be an immutable record, this is inconsistent with the rest of the codebase's immutability patterns.

### M4. `BenchmarkReport` Not Thread-Safe
**File**: `benchmarks/mainline_curriculum/metrics.py`, lines 66-98
**Severity**: MEDIUM

`BenchmarkReport.add()` appends to `self.task_metrics` without any locking. If the report is shared across threads (e.g., multiple benchmark tasks running in parallel), the list append is not atomic in CPython for all implementations.

### M5. `SentinelRuntime.intervene()` Records BUDGET_EXHAUSTED Events in History
**File**: `control/sentinel/sentinel_runtime.py`, lines 89-98
**Severity**: MEDIUM

When budget is exhausted, the method creates a `SentinelEvent` with `BUDGET_EXHAUSTED` and returns it, but does NOT append it to `self._history`. The `self._history.append(event)` at line 114 is only reached in the non-exhausted path. This means budget exhaustion events are invisible in the intervention history. Callers can see the returned event, but `sentinel.interventions` won't show it.

Looking more carefully: the budget-exhausted path returns early at line 92-98, BEFORE `self._history.append(event)` at line 114. So exhausted events are NOT recorded.

**Impact**: If monitoring code only checks `interventions` for budget exhaustion, it will never find it.

### M6. `SentinelEvent` Not Frozen but Contains Frozen `SomaticState`
**File**: `control/sentinel/sentinel_runtime.py`, lines 26-38
**Severity**: MEDIUM

`SentinelEvent` is `@dataclass(slots=True)` without `frozen=True`, and its `__post_init__` uses `object.__setattr__` to set `timestamp`. This works correctly. However, `result` is mutable (can be set at line 107), and `budget_used` is also mutable (set at line 113). Since the event records history, mutability after creation is risky -- a caller could modify `event.result` and corrupt the history entry.

### M7. `RecoveryRecipe.max_budget` Is a Class Attribute, Not Enforced
**File**: `control/sentinel/recovery_recipe.py`, line 41; `control/sentinel/recipes.py`
**Severity**: MEDIUM

Each recipe declares `max_budget` (e.g., `max_budget = 3`), but `SentinelRuntime.intervene()` never checks or enforces this per-recipe budget. Only the global budget is enforced. A recipe with `max_budget=1` could theoretically be executed 10 times as long as the global budget allows.

### M8. `run_benchmark()` Does Not Actually Execute Benchmarks
**File**: `app_service/mainline_api.py`, lines 164-173
**Severity**: MEDIUM

```python
def run_benchmark(self, task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        return {"ok": False, "reason": f"unknown task: {task_id}"}
    metric = MetricSnapshot(task_id=task_id, tsr=0.0)
    self._benchmark_report.add(metric)
    return {"ok": True, "task_id": task_id, "metric": metric.to_dict()}
```

The comment says "Placeholder: real implementation would run the task". The `tsr` is hardcoded to 0.0. This means every benchmark "succeeds" with 0% success rate, and the bottleneck will always be whatever was run most recently. The test at `test_mainline_api.py` line 101-103 asserts `result["ok"]` is True, which passes trivially.

---

## LOW Findings

### L1. `event_id` Collision Risk
**File**: `control/sentinel/sentinel_runtime.py`, lines 93, 100
**Severity**: LOW

`event_id` is generated as `f"sentinel_{int(time.perf_counter())}"`. If two events occur within the same `perf_counter()` tick (sub-microsecond on most platforms), they will have the same ID. For a history list this is not a correctness issue, but it makes event identification ambiguous.

### L2. `MetricSnapshot.__post_init__` Modifies Frozen-Style Dataclass
**File**: `benchmarks/mainline_curriculum/metrics.py`, lines 40-42
**Severity**: LOW

`MetricSnapshot` is not frozen, so `object.__setattr__` is unnecessary -- a direct `self.timestamp = time.perf_counter()` would work. The `object.__setattr__` pattern is used for frozen dataclasses where direct assignment is prohibited. This is not a bug but is misleading about the dataclass's mutability.

### L3. `BenchmarkTask` Default `time_limit_sec` Is 300s
**File**: `benchmarks/mainline_curriculum/tasks.py`, line 25
**Severity**: LOW

The default `time_limit_sec=300.0` is used as a fallback, but all 12 tasks override it explicitly (range 30s to 7200s). This is fine but the default is never exercised in practice.

### L4. `BenchmarkReport.overall_tsr` Returns Simple Average
**File**: `benchmarks/mainline_curriculum/metrics.py`, lines 76-79
**Severity**: LOW

The overall TSR is a simple arithmetic mean. For a curriculum where tasks have varying difficulty (1-5), a weighted average (e.g., weighted by difficulty) would be more meaningful. A failure on C10 (difficulty 5) counts the same as a failure on C0 (difficulty 1).

### L5. `_group_by_tier` Has Un Typed `skills` Parameter
**File**: `app_service/mainline_api.py`, line 175
**Severity**: LOW

```python
def _group_by_tier(self, skills: list) -> dict[str, int]:
```

The parameter type is bare `list` instead of `list[SkillDef]`. This is inconsistent with the type-annotated codebase style.

### L6. Test `test_start_twice_fails` Has Misleading Name and Weak Assertion
**File**: `tests/test_mainline_api.py`, lines 44-50
**Severity**: LOW

The test is named `test_start_twice_fails` but actually passes because `start()` is synchronous -- the first call completes before the second starts. The comment at line 47 acknowledges this. The assertion at line 50 `assert result["ok"]` verifies that the second start succeeds (because the first already completed), which is the opposite of what the test name suggests.

---

## Audit Criteria Summary

| Criterion | Status | Notes |
|---|---|---|
| Global budget enforcement | FAIL (C1) | Race condition allows budget overrun |
| Recipe preconditions (false positives) | MOSTLY OK (H2) | LoadingTimeout fires on normal loads |
| SomaticState immutability / evolve() | PASS | `frozen=True` + `dataclasses.replace` is correct |
| Concurrent intervene() safety | FAIL (C1) | detect_anomaly outside lock |
| Recovery results in history | PARTIAL (M5) | BUDGET_EXHAUSTED not recorded |
| Benchmark task difficulty/limits | PASS | Reasonable progression, explicit overrides |
| MetricSnapshot computation | PARTIAL (M2) | Missing timestamp in serialization |
| MainlineAPI integration | PARTIAL (H4, H5) | Missing lock in getters, stuck state bug |
| start()/pause()/stop() race | FAIL (C2, H5) | Pause/stop no-op during execution |
| API works without full deps | PASS | All deps have default constructors |

---

## Positive Observations

1. **SomaticState immutability** is well-implemented with `frozen=True` and `evolve()` via `dataclasses.replace()`. This is the correct pattern.
2. **SomaticState.is_healthy()** correctly handles the unknown case (empty hp_ratios = assume healthy), which is a sensible default for partial observability.
3. **RecoveryRecipe** base class design is clean -- protocol-like ABC with clear separation of check/execute/verify.
4. **BenchmarkTask** uses `frozen=True` with `tuple` for success_criteria, preventing accidental mutation.
5. **SentinelRuntime** uses `threading.Lock` for state mutations, showing awareness of concurrency concerns even if coverage is incomplete.
6. **MainlineAPI** accepts optional dependencies in `__init__`, allowing testing without a full system.
7. **Test coverage** is reasonable: 25 + 14 + 11 = 50 tests covering happy paths and edge cases.

---

## Recommended Fix Priority

1. **C1** -- Move budget check inside lock or use atomic pattern
2. **H5** -- Fix start() to not set "running" when graph is None
3. **C2** -- Document synchronous start() or add background thread support
4. **H4** -- Add lock to get_claims() and get_bagel()
5. **H2** -- Add duration check to LoadingTimeoutRecovery
6. **M5** -- Record BUDGET_EXHAUSTED in history
7. **M2** -- Add timestamp to to_dict()
8. **H3** -- Deterministic tie-breaking in bottleneck_task
