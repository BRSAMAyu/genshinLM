# Phase 1 Audit: BAGEL Session Boundary and Lifecycle Management

**Commit**: `1f15751` — "Phase 1: BAGEL session boundary and lifecycle management"
**Branch**: `codex/pre-realworld-closure`
**Auditor**: Claude Opus automated review
**Date**: 2026-05-28
**Files changed**: 7 source files, 556 insertions, 41 deletions

---

## Finding: BFS `pop(0)` replaced with `deque.popleft()` — correct (SEVERITY: N/A, positive)

**Files**: `bagel/fig_schema.py` lines 529-530, `bagel/safe_revision.py` lines 233-237

Both `FalsifiableInterventionGraph.downstream_beliefs()` and `SafeRevisionEngine._downstream_from_snapshot()` were changed from `list.pop(0)` (O(n) per pop) to `deque.popleft()` (O(1)). The `from collections import deque` import was added to both files. The `deque` is constructed correctly with `deque([belief_id])`.

**Verdict**: Correct. No issues.

---

## Finding: `evict_terminated()` — action eviction may orphan actions with mixed belief states (SEVERITY: HIGH)

**File**: `bagel/fig_schema.py` lines 416-472

The method correctly finds terminal beliefs older than `max_age_sec` and evicts them. It then evicts actions where **ALL** driving beliefs are evicted (`all(bid in to_evict for bid in action.belief_ids)`). This is correct for actions driven solely by evicted beliefs.

However, consider this scenario: an action is driven by beliefs `[A, B]`. Belief A is terminal and evicted. Belief B is still active. The action is correctly retained. But the action now references a belief (`A`) that no longer exists in `self.beliefs`. The action's `belief_ids` tuple contains a dangling reference. Any future code that iterates `action.belief_ids` and looks up each belief in `self.beliefs` must handle `None` returns gracefully.

Looking at `_propose_action_unlocked()` (line 338), it validates beliefs exist at proposal time but there is no invariant enforcement after eviction. The `actions_for_belief()` query method at line 506-508 will simply not match the evicted belief ID, which is fine. But any code that does `self.beliefs[bid]` on an action's belief_ids without a `.get()` guard could KeyError.

**Impact**: Not a crash today — all query methods use `.get()` or `in`. But it is a latent invariant violation. Future code may not be as careful.

**Recommendation**: Either (a) filter `action.belief_ids` to remove evicted IDs when some but not all beliefs are evicted, or (b) document the invariant that `action.belief_ids` may contain IDs not in `self.beliefs` after partial eviction.

---

## Finding: `evict_terminated()` — edges from condensed nodes not cleaned (SEVERITY: MEDIUM)

**File**: `bagel/fig_schema.py` lines 454-458

The edge cleanup removes edges where `source_id` or `target_id` is in `evicted_all`. However, `condensed_from` edges have `source_id = condensed_id` and `target_id = source_node_id`. If a belief is in `to_evict` and was part of a condensed node, the `condensed_from` edge targeting that belief will be removed. But the condensed node itself is NOT removed unless the belief transitioned to terminal via `update_belief()` (which calls `_invalidate_condensed_unlocked`).

In `evict_terminated()`, the beliefs are already terminal (they were marked terminal in a prior `update_belief()` call, which would have already called `_invalidate_condensed_unlocked`). So condensed nodes referencing terminal beliefs should already have been invalidated. This means the edge cleanup in `evict_terminated()` is a safety net, which is fine.

**Verdict**: Correct by design. The condensed nodes are invalidated at transition time, not at eviction time.

---

## Finding: `evict_terminated()` with `max_age_sec=0.0` evicts all terminal beliefs regardless of age (SEVERITY: LOW)

**File**: `bagel/fig_schema.py` line 429

The check is `age >= max_age_sec`. When `max_age_sec=0.0`, `age >= 0.0` is always true (since `now - belief.updated_at` is always non-negative with `perf_counter()`). This means ALL terminal beliefs are evicted immediately.

In `quest_transition()` at runtime.py line 613, `evict_terminated(max_age_sec=0.0)` is called explicitly to force-evict everything. This is intentional behavior for quest transitions.

**Verdict**: Correct. The `>=` comparison with 0.0 is the desired "evict all" semantics.

---

## Finding: `evict_terminated()` — feedback eviction only targets evicted actions, not evicted beliefs directly (SEVERITY: LOW)

**File**: `bagel/fig_schema.py` lines 443-445

Feedbacks are only evicted if their `action_id` is in `action_to_evict`. If a feedback references an action that was NOT evicted (because it has some non-evicted beliefs), the feedback survives even though it may be conceptually tied to an evicted belief. This is correct because the feedback's contract is with the action, not the belief directly.

**Verdict**: Correct by design.

---

## Finding: `_invalidate_condensed_unlocked()` — removes edges by `source_id` only, missing `target_id` (SEVERITY: MEDIUM)

**File**: `bagel/fig_schema.py` lines 474-482

The method removes condensed nodes where `belief_id in node.source_node_ids`, then removes edges where `e.source_id != cid`. But condensed nodes generate `condensed_from` edges with `source_id = condensed_id` (set in `add_condensed_node()` at line 380). The cleanup `e.source_id != cid` correctly removes these edges.

However, it does NOT check `target_id`. If any other edge type references the condensed node as a target, it would survive. Looking at the codebase, condensed nodes are only sources in `condensed_from` edges, so this is fine in practice.

**Verdict**: Correct for current usage. Minor fragility if new edge types are added.

---

## Finding: `update_belief()` — terminal transition cleans ordering lock and invalidates condensed (SEVERITY: N/A, positive)

**File**: `bagel/fig_schema.py` lines 408-413

When `update_belief()` is called with a lifecycle in `_TERMINAL_LIFECYCLES`, it:
1. Pops the belief from `_ordering_lock`
2. Calls `_invalidate_condensed_unlocked(belief_id)` to remove condensed nodes referencing this belief
3. Bumps version

This is correct. The lock is held for the entire `update_belief()` method, so `_invalidate_condensed_unlocked` runs under the FIG lock.

**Verdict**: Correct.

---

## Finding: `EvidenceSignal.timestamp` with `__post_init__` default — correct but semantically surprising with `frozen=True` (SEVERITY: LOW)

**File**: `bagel/evidence_matrix.py` lines 50-54

The `EvidenceSignal` dataclass is `frozen=True, slots=True`. The `__post_init__` uses `object.__setattr__` to set the timestamp, which is the correct pattern for frozen dataclasses. The default of `0.0` is used as a sentinel to trigger auto-assignment.

One subtle issue: if a signal is deserialized from JSON with `timestamp=0.0` (meaning the original timestamp was lost), the `__post_init__` will overwrite it with the current time, corrupting the original timestamp. This matters for `reconstruct_fig` scenarios where events are replayed from disk.

**Recommendation**: Use a different sentinel (e.g., `-1.0`) to distinguish "not set" from "explicitly set to 0.0". Or better, always serialize timestamps.

---

## Finding: `signal_horizon_sec` filtering in `score_belief()` — correct but filtered signals still counted in `signal_count` (SEVERITY: MEDIUM)

**File**: `bagel/evidence_matrix.py` lines 150-223

The `score_belief()` method:
1. Acquires lock, copies signals list (line 153)
2. Iterates signals, skipping those older than `signal_horizon_sec` (line 168)
3. Computes `c_i`, `s_i`, `r_i` from non-filtered signals
4. Returns `signal_count=len(signals)` (line 219) — this is the TOTAL count including filtered signals

The `signal_count` in `EvidenceScore` includes filtered/expired signals. Downstream code in `arbiter.py` uses `score.signal_count < 2` (line 106) as a condition for provisional retirement. If a belief has 5 old signals and 0 recent ones, `signal_count=5` would prevent retirement even though no recent evidence exists.

**Impact**: Beliefs with only stale evidence could avoid provisional retirement. Not catastrophic but semantically misleading.

**Recommendation**: Either (a) count only non-filtered signals in `signal_count`, or (b) add a separate `active_signal_count` field.

---

## Finding: `clear_for_beliefs()` — correct O(n) removal (SEVERITY: N/A, positive)

**File**: `bagel/evidence_matrix.py` lines 241-247

Simple, correct. Pops each belief's signal list and counts removed items.

**Verdict**: Correct.

---

## Finding: `evict_signals_before()` — correct, cleans up empty belief entries (SEVERITY: N/A, positive)

**File**: `bagel/evidence_matrix.py` lines 249-259

Iterates a snapshot of keys (`list(self._signals.keys())`), filters signals, and deletes empty entries. The `list()` copy prevents `RuntimeError` from dict mutation during iteration.

**Verdict**: Correct.

---

## Finding: Arbiter oscillation dampening — counter reset logic may be incorrect (SEVERITY: HIGH)

**File**: `bagel/arbiter.py` lines 137-154

The oscillation detection logic:

```python
prev = self._last_lifecycle.get(belief.belief_id)
if prev == new and old != new:
    count = self._oscillation_counts.get(belief.belief_id, 0) + 1
    self._oscillation_counts[belief.belief_id] = count
    if count >= self._max_oscillations:
        self._last_lifecycle[belief.belief_id] = old
        return ArbitrationResult(new_lifecycle=old, reason="oscillation_dampened")
elif old != new:
    self._oscillation_counts[belief.belief_id] = 0
self._last_lifecycle[belief.belief_id] = new
```

**Bug**: The detection checks `prev == new` (the _recommended_ new lifecycle matches the _previous_ recommended lifecycle). But oscillation is about the belief **bouncing back and forth** between two states. Consider:

- Cycle 1: old=committed, new=suspect. `prev=None`. `else` branch: count=0. `_last_lifecycle=suspect`.
- Cycle 2: old=suspect, new=committed. `prev=suspect`. `suspect != committed`, so `else` branch: count=0. `_last_lifecycle=committed`.
- Cycle 3: old=committed, new=suspect. `prev=committed`. `committed != suspect`, so `else` branch: count=0. `_last_lifecycle=suspect`.

The oscillation count NEVER increments in this scenario because `prev` (the previous recommendation) is always different from `new` (the current recommendation). The count only increments when the arbiter recommends the SAME lifecycle twice in a row on a belief that keeps getting changed back by something else. This is not true oscillation detection — it detects "the arbiter keeps recommending X but the belief keeps getting reset to something else."

For actual oscillation (A -> B -> A -> B), the counter would never fire.

**Impact**: The oscillation dampening mechanism will not catch the primary oscillation pattern it was designed to prevent. It will only catch the case where the arbiter's own recommendation is stable but an external force keeps reverting it.

**Recommendation**: Track the actual lifecycle sequence, not just the previous recommendation. For example:
```python
# Track actual old lifecycle sequence
key = (belief.belief_id, old, new)
# count how many times this specific transition repeats
```
Or more simply, track `(old, new)` pairs and count repeated patterns.

---

## Finding: Arbiter `_last_lifecycle` updated even when oscillation is dampened (SEVERITY: LOW)

**File**: `bagel/arbiter.py` line 154

Line 154 (`self._last_lifecycle[belief.belief_id] = new`) executes unconditionally, including after the early return at line 150 for oscillation dampening. Wait — the early return at line 150 means line 154 is NOT reached. Let me re-check.

Actually, the return at line 145-151 exits the function, so line 154 is NOT executed for dampened oscillations. But for the case where oscillation count is incremented but NOT yet at max (line 142: `count >= self._max_oscillations` is False), the code falls through to line 154 and sets `_last_lifecycle = new`. This is correct — it records the latest recommendation.

**Verdict**: No bug here. The early return prevents the `_last_lifecycle` update only for fully dampened cases, which is correct (the dampened result returns `old` as the lifecycle, and `_last_lifecycle` is already set to the dampened `old` on line 143).

Wait — line 143 sets `_last_lifecycle[belief.belief_id] = old` inside the dampened block, BEFORE the return. Then if we look at the flow:
- Dampened: sets `_last_lifecycle = old`, returns early (line 145-151). Line 154 not reached. Correct.
- Not yet dampened (count < max): falls through to line 154, sets `_last_lifecycle = new`. Correct.

**Verdict**: Correct flow, no bug.

---

## Finding: Arbiter age-aware provisional retirement — uses `belief.updated_at` not `belief.created_at` (SEVERITY: MEDIUM)

**File**: `bagel/arbiter.py` lines 104-114

The provisional retirement check uses:
```python
age = now - belief.updated_at
if age > self._provisional_max_age_sec and score.signal_count < 2:
```

This measures age from `updated_at`, not `created_at`. If a provisional belief has been updated (e.g., confidence changed, metadata modified), the age timer resets. A belief could remain provisional indefinitely if it receives minor updates.

**Impact**: A belief could avoid provisional retirement by receiving trivial updates that don't change its lifecycle.

**Recommendation**: Use `created_at` instead of `updated_at` for age calculation, or add a dedicated `lifecycle_entered_at` field.

---

## Finding: Probe policy `_taboo_probe_families` changed from `set[str]` to `dict[str, float]` — correct (SEVERITY: N/A, positive)

**File**: `bagel/probe_policy.py` line 53

The type change from `set[str]` to `dict[str, float]` stores timestamps for TTL-based expiry. The `degrade_non_decidable()` method now stores `time.perf_counter()` as the value (line 217), and `is_probe_family_taboo()` checks expiry (lines 220-227).

**Verdict**: Correct.

---

## Finding: `is_probe_family_taboo()` — deletes from dict during read, potential iteration issues (SEVERITY: LOW)

**File**: `bagel/probe_policy.py` lines 220-227

The method deletes expired entries inline:
```python
del self._taboo_probe_families[family]
```

This is fine for a single-key lookup. But if someone iterates `_taboo_probe_families` and calls `is_probe_family_taboo()` for each key, it could cause issues. The `expire_taboos()` method correctly builds a list of expired keys first, then deletes them. The inline delete in `is_probe_family_taboo()` is only for single lookups, which is safe.

**Verdict**: Correct for current usage. The inline cleanup is a nice optimization.

---

## Finding: `generate_probes()` — pending probe check is correct (SEVERITY: N/A, positive)

**File**: `bagel/probe_policy.py` lines 69-73

The method checks for existing probes in statuses `("generated", "sanity_checked", "approved", "executing")` and skips beliefs that already have a pending probe. This prevents probe starvation where the same belief gets repeated probes.

**Verdict**: Correct. Also correctly uses `snap` for consistent reads.

---

## Finding: `generate_probes()` — `expire_taboos()` called before iteration, but `is_probe_family_taboo()` is never called in `generate_probes()` (SEVERITY: LOW)

**File**: `bagel/probe_policy.py` lines 76-77

The `expire_taboos()` call at line 76 cleans up expired entries. But `_create_probe()` does not call `is_probe_family_taboo()` to check whether the probe family is taboo. The taboo mechanism is only checked externally by whatever calls `is_probe_family_taboo()`. This means `generate_probes()` could generate probes for taboo families.

**Impact**: Probe generation may create probes for families that have been marked taboo. The taboo mechanism is advisory, not enforced at generation time.

**Recommendation**: Add a taboo check in `_create_probe()` or `generate_probes()` to skip beliefs whose falsification condition matches a taboo family.

---

## Finding: `reset_taboo()` also clears `_cluster_counts` — correct (SEVERITY: N/A, positive)

**File**: `bagel/probe_policy.py` lines 229-232

Both `_taboo_probe_families` and `_cluster_counts` are cleared on quest transition. This is correct since cluster counts are quest-scoped.

**Verdict**: Correct.

---

## Finding: `quest_transition()` — carry_forward logic has double-eviction race (SEVERITY: HIGH)

**File**: `bagel/runtime.py` lines 618-624

```python
if carry_forward_beliefs is not None:
    carry_set = set(carry_forward_beliefs)
    for bid in list(self.fig.snapshot()["beliefs"].keys()):
        if bid not in carry_set:
            self.fig.update_belief(bid, lifecycle="retired")
    self.fig.evict_terminated(max_age_sec=0.0)
```

**Bug 1**: The loop calls `self.fig.snapshot()` to get belief keys, but each `update_belief()` call acquires the FIG lock and modifies state. The snapshot is taken once at the start, so it reflects the state BEFORE the loop begins modifying beliefs. This is actually correct — iterating a snapshot while mutating the underlying dict is the right pattern. No race condition here.

**Bug 2**: The `update_belief()` call for non-carry beliefs sets `lifecycle="retired"`. But `update_belief()` (fig_schema.py line 404) returns `None` and does nothing if the belief is ALREADY in a terminal lifecycle (retired, posthoc_invalid, falsified). This means beliefs that were already terminal from the earlier `evict_terminated()` call at line 613 are silently skipped. This is fine — they were already evicted.

**Bug 3**: After retiring non-carry beliefs, `evict_terminated(max_age_sec=0.0)` is called again. But the first `evict_terminated()` at line 613 already removed all terminal beliefs. The second call will find the newly-retired beliefs and evict them. However, the beliefs retired in the loop at line 623 have `updated_at = time.perf_counter()` (set by `update_belief()`), so their age is ~0 which passes `age >= 0.0`. This is correct.

**Actual issue**: If a carry_forward belief ID doesn't exist in the FIG (typo, already evicted, etc.), it's silently ignored. The method doesn't validate that carry_forward IDs actually exist. This could lead to data loss if a caller expects certain beliefs to survive.

**Verdict**: Functionally correct but could be more defensive. Not a bug per se.

---

## Finding: `quest_transition()` — `evict_signals_before(0.0)` evicts ALL signals (SEVERITY: LOW)

**File**: `bagel/runtime.py` line 616

`self.matrix.evict_signals_before(0.0)` removes all signals with `timestamp >= 0.0`... wait, the filter is `s.timestamp >= cutoff`, which means it KEEPS signals with `timestamp >= 0.0` and REMOVES signals with `timestamp < 0.0`. Since `perf_counter()` always returns positive values, this would remove NO signals.

Wait, re-reading the method:

```python
self._signals[bid] = [s for s in self._signals[bid] if s.timestamp >= cutoff]
```

This KEEPS signals where `timestamp >= 0.0`. All signals have positive timestamps from `perf_counter()`. So `evict_signals_before(0.0)` actually removes nothing.

**Bug**: The intent is to clear ALL signals on quest transition, but `evict_signals_before(0.0)` keeps everything because `perf_counter()` timestamps are always positive.

**Impact**: Evidence signals from the old quest persist into the new quest, polluting attribution.

**Recommendation**: Use `self.matrix.clear()` instead, or use `evict_signals_before(float('inf'))` to actually remove all signals. Alternatively, add an explicit `clear()` call before the quest transition completes.

Actually, wait — `evict_signals_before` removes signals where `timestamp < cutoff`, keeping those where `timestamp >= cutoff`. So:
- `evict_signals_before(0.0)` keeps `s.timestamp >= 0.0`, which is ALL signals.
- To clear all, you'd need `evict_signals_before(float('inf'))`.

This IS a bug. The `signals_cleared` return value will be 0 every time.

**Severity upgrade**: **CRITICAL** — evidence contamination across quest boundaries.

---

## Finding: `quest_transition()` — `now` variable unused (SEVERITY: LOW)

**File**: `bagel/runtime.py` line 595

`now = time.perf_counter()` is assigned but never used in the method.

**Verdict**: Dead code. Minor.

---

## Finding: `quest_transition()` — FIG snapshot archived in event may be huge (SEVERITY: LOW)

**File**: `bagel/runtime.py` lines 607-610

The entire FIG snapshot (all beliefs, actions, feedbacks, probes, edges, bridges, condensed_nodes) is serialized into the event payload using a nested dict comprehension. For large FIGs, this could produce very large event payloads.

**Verdict**: Functional but potentially a memory/disk concern for long sessions.

---

## Finding: `score_delayed_feedback()` — `math.exp(-0.01 * age)` decays too slowly (SEVERITY: MEDIUM)

**File**: `bagel/runtime.py` lines 300-301

```python
age = time.perf_counter() - belief.updated_at
freshness = math.exp(-0.01 * age)
```

The decay constant `0.01` means:
- At age=100s (1.7 min): freshness = 0.37
- At age=230s (3.8 min): freshness = 0.10
- At age=460s (7.7 min): freshness = 0.01

For a quest-based system where sessions can last minutes to hours, this means feedback stays "fresh" for a very long time. A belief updated 5 minutes ago still has 5% freshness. This may be intentional for long-range attribution, but could also mean stale beliefs accumulate significant bridge scores.

**Impact**: Delayed feedback may have outsized influence on beliefs that haven't been updated recently.

**Verdict**: Design choice. The terminal lifecycle guard (`freshness = 0.0` for stale/retired/posthoc_invalid/falsified) provides a safety net.

---

## Finding: `score_delayed_feedback()` — `falsified` added to terminal check (SEVERITY: N/A, positive)

**File**: `bagel/runtime.py` line 303

The previous code only checked `("stale", "retired", "posthoc_invalid")`. The new code adds `"falsified"`. This prevents bridges from scoring against falsified beliefs.

**Verdict**: Correct and important.

---

## Finding: `compute_feedback_shift()` — guard for terminal beliefs is correct (SEVERITY: N/A, positive)

**File**: `bagel/runtime.py` lines 326-336

The guard checks `belief.lifecycle not in ("falsified", "retired", "posthoc_invalid")` before calling `update_belief()`. This prevents the feedback shift computation from resurrecting terminal beliefs.

**Verdict**: Correct.

---

## Finding: `reset_phase()` — no event logged for phase reset (SEVERITY: LOW)

**File**: `bagel/runtime.py` lines 656-659

The method resets the FIG phase to "execution" and clears the frozen snapshot, but does NOT log an event. This means the audit trail has a gap: the `AttributionSnapshotFrozen` event is recorded, but if the phase is reset via this recovery path, there's no corresponding event. The `ExecutionPhaseEntered` event that follows in `run_attribution_cycle()` will record the normal re-entry, but the forced reset is invisible.

**Impact**: Harder to debug stuck attribution cycles from the event log.

**Recommendation**: Log a recovery event (e.g., `"AttributionPhaseReset"`) with the reason.

---

## Finding: `shutdown()` with `atexit` — potential double-close (SEVERITY: LOW)

**File**: `bagel/runtime.py` lines 93, 661-665

`atexit.register(self.shutdown)` is called in `__post_init__`. If the runtime is used as a context manager or explicitly shut down, `shutdown()` could be called multiple times. The `close()` method on `BagelEventStore` is idempotent (checks `self._file is not None`), so this is safe.

However, `atexit` keeps a strong reference to `self`, preventing garbage collection of the runtime until process exit. For long-running processes, this is a minor memory concern.

**Verdict**: Safe due to idempotent close, but atexit is a slightly heavy pattern.

---

## Finding: `run_attribution_cycle()` — phase reset guard could lose frozen snapshot data (SEVERITY: MEDIUM)

**File**: `bagel/runtime.py` lines 389-390

```python
if self.fig.phase == "attribution_frozen":
    self.reset_phase(trace_id)
```

If a previous attribution cycle crashed after freezing but before committing, the next call will reset the phase and start fresh. The frozen snapshot (`self._frozen_snapshot`) is set to `None` in `reset_phase()`. This means any data that was computed from the frozen snapshot is lost.

**Impact**: Recovery from stuck attribution is correct in behavior (prevents permanent stuck state), but any partial computation from the previous frozen snapshot is discarded. This is acceptable for a recovery path.

**Verdict**: Correct recovery behavior.

---

## Finding: `_bump()` bypasses FIG lock (SEVERITY: MEDIUM)

**File**: `bagel/runtime.py` line 653

```python
def _bump(self) -> None:
    self.fig.version += 1
```

This directly increments `self.fig.version` without acquiring the FIG lock. In `quest_transition()`, this is called after `fig.mission_id = new_mission_id` (line 630), both without the FIG lock. Meanwhile, `fig.set_phase()` and `fig.update_belief()` acquire the FIG lock and call `self._bump()` internally.

**Impact**: If `quest_transition()` runs concurrently with other FIG operations, the version counter could have a race condition. However, `quest_transition()` is meant to be called during a session boundary where no other operations should be running. The FIG lock is not held for the carry_forward loop, which calls `update_belief()` (which acquires the lock per-call).

**Verdict**: Unsafe under concurrent access, but acceptable if quest transitions are guaranteed to be single-threaded.

---

## Finding: `quest_transition()` modifies `fig.mission_id` directly without lock (SEVERITY: MEDIUM)

**File**: `bagel/runtime.py` line 630

```python
self.fig.mission_id = new_mission_id
```

This modifies a field on the FIG dataclass without acquiring `fig._lock`. If any reader is accessing `fig.mission_id` concurrently (e.g., `to_dict()` or `snapshot()`), they could see a partially-transitioned state.

**Verdict**: Same concern as `_bump()` above. Safe if quest transitions are single-threaded.

---

## Finding: `BagelEventStore.__enter__`/`__exit__` — context manager does not auto-open file (SEVERITY: LOW)

**File**: `bagel/event_store.py` lines 110-114

The context manager returns `self` but does not pre-open the file. The file is opened lazily on first `append()`. This is fine — the `close()` in `__exit__` will clean up. But if the store is used as a context manager and no events are appended, `close()` is a no-op (since `_file` is `None`).

**Verdict**: Correct.

---

## Finding: Event store `__exit__` uses `*args` — correct (SEVERITY: N/A, positive)

**File**: `bagel/event_store.py` line 113

`def __exit__(self, *args: Any) -> None:` correctly accepts the `(exc_type, exc_val, exc_tb)` arguments and ignores them, just calling `close()`.

**Verdict**: Correct.

---

## Finding: `QuestArchived` and `QuestTransition` event types added (SEVERITY: N/A, positive)

**File**: `bagel/event_store.py` lines 48-49

Two new event types are added to the `EventType` Literal. The `reconstruct_fig()` method does not handle these events (they fall through without error), which is correct — they are lifecycle events, not FIG mutations.

**Verdict**: Correct.

---

## Finding: `safe_revision.py` BFS deque fix — inline import (SEVERITY: LOW)

**File**: `bagel/safe_revision.py` line 232

```python
from collections import deque
```

The import is inside the static method `_downstream_from_snapshot()`. This is a function-level import, which is slightly slower than module-level but acceptable for an infrequently-called method. It keeps the module's top-level imports clean.

**Verdict**: Correct, minor style note.

---

## Finding: `quest_transition()` carry_forward may interact poorly with evict_terminated (SEVERITY: LOW)

**File**: `bagel/runtime.py` lines 613-624

Sequence:
1. `evict_terminated(max_age_sec=0.0)` — removes all terminal beliefs and their orphaned entities
2. `evict_signals_before(0.0)` — intended to clear all signals (but doesn't, see CRITICAL finding)
3. For non-carry beliefs: `update_belief(bid, lifecycle="retired")`
4. `evict_terminated(max_age_sec=0.0)` — removes the newly-retired beliefs

If a carry_forward belief has associated actions, those actions are NOT retired/evicted. Only the non-carry beliefs' actions are orphaned. But the action eviction logic only removes actions where ALL driving beliefs are evicted. If an action is driven by both a carry and a non-carry belief, it survives the first eviction (step 4) because the carry belief is still active.

After step 3, the non-carry belief is retired. After step 4, the action is checked again: `all(bid in to_evict for bid in action.belief_ids)` — the carry belief is NOT in `to_evict`, so the action survives. The action now has a dangling reference to the retired (and evicted) non-carry belief.

**Impact**: Same as the HIGH finding on `evict_terminated()` — dangling belief references in action.belief_ids.

---

## Summary of Findings

| # | Severity | File | Summary |
|---|----------|------|---------|
| 1 | **CRITICAL** | runtime.py:616 | `evict_signals_before(0.0)` does NOT clear signals — all `perf_counter()` timestamps are positive, so filter `s.timestamp >= 0.0` keeps everything |
| 2 | **HIGH** | arbiter.py:138-154 | Oscillation dampening does not detect A->B->A oscillation; only detects repeated same-recommendation |
| 3 | **HIGH** | fig_schema.py:436-439 | Actions with mixed (evicted + active) beliefs retain dangling belief IDs after eviction |
| 4 | **MEDIUM** | evidence_matrix.py:219 | `signal_count` includes filtered/expired signals, misleading downstream logic |
| 5 | **MEDIUM** | arbiter.py:104-106 | Provisional retirement uses `updated_at` not `created_at`, allowing trivial updates to reset the age timer |
| 6 | **MEDIUM** | runtime.py:630,653 | `_bump()` and `mission_id` assignment bypass FIG lock |
| 7 | **MEDIUM** | runtime.py:300-301 | CausalBridge decay constant `0.01` may be too slow for practical quest durations |
| 8 | **MEDIUM** | fig_schema.py:474-482 | `_invalidate_condensed_unlocked` only removes edges by `source_id`, fragile for future edge types |
| 9 | **LOW** | runtime.py:595 | `now` variable assigned but unused |
| 10 | **LOW** | runtime.py:656-659 | `reset_phase()` does not log a recovery event |
| 11 | **LOW** | evidence_matrix.py:50-54 | `timestamp=0.0` sentinel conflicts with deserialization |
| 12 | **LOW** | probe_policy.py:76 | `is_probe_family_taboo()` not checked during probe generation |

---

## Recommendations (Priority Order)

1. **Fix CRITICAL**: Change `self.matrix.evict_signals_before(0.0)` to `self.matrix.clear()` in `quest_transition()`, or use `self.matrix.evict_signals_before(float('inf'))`.
2. **Fix HIGH (oscillation)**: Redesign oscillation detection to track actual `(old, new)` transition patterns, not just previous recommendations.
3. **Fix HIGH (dangling refs)**: After eviction, filter surviving actions' `belief_ids` to remove evicted IDs, or document the invariant explicitly.
4. **Fix MEDIUM (signal_count)**: Count only active (non-filtered) signals in `EvidenceScore.signal_count`.
5. **Fix MEDIUM (lock)**: Acquire FIG lock in `quest_transition()` for `mission_id` update and `_bump()`, or document single-threaded requirement.
