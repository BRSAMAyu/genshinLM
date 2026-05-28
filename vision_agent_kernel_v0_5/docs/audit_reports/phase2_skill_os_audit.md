# Phase 2 Skill OS Audit Report

**Commit:** 886c033
**Date:** 2026-05-29
**Scope:** Skill OS adaptive tier management + Phase 1 audit fixes
**Files audited:** 12 source files (skills/schema.py, skills/promotion.py, learning/evolution_engine.py, learning/decision_memory.py, control/sentinel/recipes.py, navigation/genshin_navigator.py, execution/console_backend.py, planning/mainline/mainline_runner.py, bagel/arbiter.py, bagel/evidence_matrix.py, bagel/fig_schema.py, bagel/runtime.py)

---

## CRITICAL Findings

### C-01: Unbound variable `signals_cleared` in `BagelRuntime.quest_transition()`
**File:** `bagel/runtime.py`, lines 615-650
**Description:** The method calls `self.matrix.clear()` on line 615 to clear all evidence signals, but never assigns the return value or any variable named `signals_cleared`. Lines 641 and 649 reference `signals_cleared` in the event payload and return dict respectively, causing an immediate `NameError` at runtime whenever `quest_transition()` is called.
**Impact:** Any quest boundary transition crashes with an unhandled `NameError`, halting the mainline autonomy loop.
**Recommendation:** Change line 615 from `self.matrix.clear()` to `signals_cleared = self.matrix.clear()` and have `EvidenceMatrix.clear()` return the count of cleared signals (or set `signals_cleared = -1` as a placeholder with a TODO if exact count is not available).

### C-02: Schema migration does not update version field to 2
**File:** `skills/schema.py`, lines 117, 228-230
**Description:** `_migrate_v1_to_v2()` uses `data.setdefault("version", 2)` on line 117. Since `setdefault` only sets the key when it is *absent*, a v1 dict that already has `version: 1` will NOT be updated to `version: 2`. In `from_dict()` (line 228), `version` is read BEFORE the migration call, and the migrated dict still has `version: 1`. The resulting `SkillDef` object therefore has `version=1` despite being v2-migrated.
**Impact:** Round-tripping a v1 skill through `to_dict()` -> `from_dict()` will trigger migration on every load (since version stays 1), wasting work. Any version-dependent logic that checks `skill.version >= 2` will incorrectly skip v2 features.
**Recommendation:** Change line 117 from `data.setdefault("version", 2)` to `data["version"] = 2`.

---

## HIGH Findings

### H-01: Oscillation dampening fails to detect A->B->A oscillation
**File:** `bagel/arbiter.py`, lines 137-156
**Description:** The dampening logic tracks exact `(old, new)` transition tuples and only increments the counter when the *same* transition repeats. For a true oscillation cycle `committed -> suspect -> committed -> suspect`, the transitions are `(committed, suspect)` then `(suspect, committed)` -- these are *different* tuples, so the counter resets to 1 on each alternation. The dampener only catches repeated identical transitions (e.g., provisional->suspect three times in a row), not the common ping-pong oscillation between two states.
**Impact:** Beliefs oscillating between `committed` and `suspect` (or `provisional` and `confirmed`) will never be dampened, causing unbounded re-arbitration cycles and wasted compute.
**Recommendation:** Track the *previous lifecycle state* (not the transition tuple) and detect when a belief returns to a state it recently left. A simpler approach: maintain a `deque[maxlen=4]` of the last N lifecycle states per belief and check if any state appears 3+ times in the window, or count the number of transitions (not matching transitions) per belief within a time window.

### H-02: Race condition in `DecisionMemory.close()` vs `_conn_ctx()`
**File:** `learning/decision_memory.py`, lines 67-76
**Description:** `close()` on line 67-70 reads and nullifies `self._conn` without acquiring `self._conn_lock`. Meanwhile, `_conn_ctx()` (line 72-76) acquires the lock to create a connection but then *returns the connection while no longer holding the lock*. A thread can call `_conn_ctx()`, get a connection reference, then another thread calls `close()` which closes that connection, causing the first thread's subsequent SQL operations to fail with `sqlite3.ProgrammingError: closed`.
**Impact:** In multi-threaded usage (which DecisionMemory supports via `_conn_lock`), concurrent `close()` + `record()`/`query()` causes crashes.
**Recommendation:** (1) Have `close()` acquire `_conn_lock`. (2) For stronger safety, use a per-operation pattern where each method acquires the lock, performs the SQL, and releases it, rather than handing out connection references.

### H-03: EvolutionEngine `_drain_failures` thread silently swallows exceptions
**File:** `learning/evolution_engine.py`, lines 101-107
**Description:** The `_drain_failures` daemon thread catches all exceptions from `handle_failure()` and only logs them. Since `handle_failure()` acquires `self._lock`, if it ever raises an unhandled exception while holding the lock (which should not happen due to the try/finally inside `handle_failure`, but could happen in edge cases like a `KeyboardInterrupt` in the thread), the lock would remain held and all future operations would deadlock.
**Impact:** The failure worker thread could silently die or deadlock the entire engine.
**Recommendation:** Add a re-raise or circuit-breaker pattern: if `handle_failure` raises an unexpected exception, increment a counter, and after N consecutive errors, pause the worker (e.g., `time.sleep(5)`) to avoid a tight error loop.

### H-04: `navigator.walk_fallback` publishes unimplemented action type
**File:** `navigation/genshin_navigator.py`, lines 237-253
**Description:** When a waypoint is not in the world graph, the navigator publishes a `navigate_walk` action via `sentinel.action_request`. However, no executor or consumer anywhere in the codebase handles the `navigate_walk` action type. The action is published and forgotten -- nothing actually walks to the destination.
**Impact:** Locked waypoints silently produce a no-op fallback. The agent believes it is navigating but nothing happens, potentially causing the sentinel to trigger stuck detection repeatedly.
**Recommendation:** Either implement a `navigate_walk` executor that uses minimap direction + WASD movement, or log this as a hard failure and trigger replan rather than pretending the action is actionable. At minimum, the `_fallback_to_walk` flag should be checked by callers to distinguish "published" from "actually handled."

---

## MEDIUM Findings

### M-01: EvolutionEngine cooldown check outside the lock
**File:** `learning/evolution_engine.py`, lines 112-117
**Description:** The cooldown check on lines 114-117 reads and conditionally returns without holding `self._lock`. The cooldown update on line 124 is inside the lock. This means two threads (or the failure worker processing queued items rapidly) could both pass the cooldown check for the same skill before either updates the cooldown map, leading to two concurrent repair sessions for the same skill.
**Impact:** Rare double-repair for the same skill within the cooldown window.
**Recommendation:** Move the cooldown check and update inside the `with self._lock:` block, or use an atomic check-and-set pattern.

### M-02: `windowed_wilson` truncation via `int()` may lose fractional signal weight
**File:** `skills/promotion.py`, lines 192-194
**Description:** `windowed_wilson` computes `effective_s` and `effective_f` as floating-point weighted blends, then passes them through `int()` before calling `wilson_lower_bound`. For small values, this truncation can significantly shift the effective ratio. For example, if `effective_s = 1.3`, `int(1.3) = 1`, losing 23% of the signal weight. Using `round()` would be more faithful, or better yet, pass floats and adapt `wilson_lower_bound` to accept floats.
**Impact:** Promotion reliability estimates are biased downward, especially for skills with few observations, making it harder for skills to promote.
**Recommendation:** Use `round()` instead of `int()`, or refactor `wilson_lower_bound` to accept float counts directly.

### M-03: `_compact` deletes from dict during iteration
**File:** `learning/evolution_engine.py`, lines 321-323
**Description:** `_compact` builds a list of stale session IDs and then deletes them from `self._repair_sessions`. Although the iteration is over a separate list (safe), the method comment says "do not re-acquire" the lock, meaning this is called inside the lock. However, `_compact` only checks `hasattr(s, '_events') and not s._events` -- if `RepairSession` does not have an `_events` attribute (e.g., a different constructor path), the session is silently skipped rather than handled.
**Impact:** Minor -- stale sessions may accumulate if RepairSession objects don't have `_events`.
**Recommendation:** Use `getattr(s, '_events', None)` instead of `hasattr` to be defensive against missing attributes.

### M-04: `EvidenceMatrix.signal_count` counts all signals, not active ones
**File:** `bagel/evidence_matrix.py`, lines 263-267
**Description:** `signal_count()` counts all signals in storage, including expired ones beyond `signal_horizon_sec`. The `score_belief` method correctly filters by horizon, but `signal_count` does not. This creates an inconsistency: `signal_count(belief_id)` could return 10 but `score_belief(belief_id).signal_count` returns 3 (only active signals).
**Impact:** Misleading metrics if external code uses `signal_count` to decide whether to score or arbitrate a belief.
**Recommendation:** Either rename `signal_count` to `stored_signal_count` or add horizon filtering to `signal_count` to match `score_belief` behavior.

### M-05: `fig_schema.evict_terminated` can leave actions with empty `belief_ids` tuple
**File:** `bagel/fig_schema.py`, lines 466-470
**Description:** The dangling belief IDs fix cleans surviving actions by removing evicted belief IDs. If *all* of an action's beliefs are evicted but the action itself was not in `action_to_evict` (because the eviction condition on line 438 requires ALL beliefs to be evicted), the action survives with an empty `belief_ids` tuple. This creates an orphaned action that references no beliefs, violating the FIG invariant that actions must be driven by beliefs.
**Impact:** Orphaned actions can cause downstream errors in `feedbacks_for_belief` (returns empty) and attribution cycles (belief-action chain is broken).
**Recommendation:** After cleaning `belief_ids`, check if the tuple is empty and add the action to `action_to_evict` if so, or log a warning.

### M-06: `BagelRuntime.quest_transition` directly mutates `fig.mission_id`
**File:** `bagel/runtime.py`, line 629
**Description:** `self.fig.mission_id = new_mission_id` bypasses the FIG's internal locking. If another thread is reading `mission_id` (e.g., via `snapshot()` or `to_dict()`), it could see a partially updated state.
**Impact:** Minor in practice since quest transitions are serialized, but violates the FIG's thread-safety contract.
**Recommendation:** Add a `set_mission_id` method to `FalsifiableInterventionGraph` that acquires the lock.

---

## LOW Findings

### L-01: `_next_version` parses filename stem without error handling
**File:** `learning/evolution_engine.py`, lines 329-335
**Description:** `_next_version` does `int(last.split("_v")[1])` which will throw `IndexError` if a file matches the glob but doesn't contain `_v` in the expected position (e.g., `skill_v2_backup.json`).
**Recommendation:** Wrap in a try/except and fall back to `v1` on parse failure.

### L-02: `demote_skill` records `demoted_from` but no corresponding field in `SkillDef`
**File:** `skills/promotion.py`, line 176
**Description:** `demote_skill` stores `demoted_from` in metadata, which is fine for a dict, but there is no typed field for it. Callers must remember to check `metadata["demoted_from"]` which is easy to forget.
**Recommendation:** Document the metadata key convention or add a typed field.

### L-03: Sentinel recipes always return success without verifying recovery
**File:** `control/sentinel/recipes.py`, all recipe classes
**Description:** Every recipe's `execute_recovery` returns a `RecoveryResult` with status `"success"` immediately after publishing the action request, regardless of whether the action was actually consumed or executed. The `verify_restabilized` methods always return `True`. This means the sentinel will always report successful recovery even when nothing happened.
**Recommendation:** Return a `"pending"` or `"requested"` status and have `verify_restabilized` do actual verification.

### L-04: `BagelArbiter._evaluate` age calculation uses `perf_counter` but `created_at` could be wall-clock
**File:** `bagel/arbiter.py`, line 105
**Description:** The arbiter computes `age = now - belief.created_at` using `time.perf_counter()` for `now`. If `belief.created_at` was set via `time.perf_counter()` (as it is in `BeliefNode.__post_init__`), this is correct. However, if beliefs are deserialized from storage where `created_at` was persisted as wall-clock, the age calculation will be wildly wrong.
**Recommendation:** Document the monotonic-clock invariant for `created_at` or add a conversion guard.

### L-05: `ConsoleInputBackend._record` print is not guarded by lock
**File:** `execution/console_backend.py`, line 69
**Description:** `print()` on line 69 is called outside the lock (the lock is released after `_record` returns, but `print` happens inside `_record` which is called within the lock). Actually, re-reading the code, `_record` IS called within `with self._lock:`, so the print is serialized. However, print with `flush=True` can block on I/O while holding the lock.
**Recommendation:** Move the print outside the lock by buffering and printing in a non-lock context, or accept the minor latency since this is the dry-run backend.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| CRITICAL | 2 | Unbound variable crash; schema migration version not updated |
| HIGH | 4 | Oscillation dampening logic flaw; thread safety in DB/lock; unimplemented fallback |
| MEDIUM | 6 | Cooldown TOCTOU; int truncation; signal count inconsistency; orphaned actions; lock bypass |
| LOW | 5 | Parse error handling; metadata convention; sentinel verification; clock invariant; I/O under lock |

**Top priority fixes:** C-01 (runtime crash) and C-02 (migration version) should be fixed immediately. H-01 (oscillation dampening) is a correctness issue that will cause infinite re-arbitration in real workloads. H-02 (DB thread safety) matters for any production multi-threaded usage.
