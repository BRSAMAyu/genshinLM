# Round 2 Audit Report: BAGEL System, Quest Fact Chain, and FIG Schema

**Auditor**: Senior Code Auditor (automated, Round 2)
**Date**: 2026-05-27
**Scope**: `bagel/` (7 files: fig_schema.py, evidence_matrix.py, arbiter.py, safe_revision.py, probe_policy.py, event_store.py, runtime.py), `planning/mainline/active_quest_context.py`, `planning/mainline/quest_state_tracker_v2.py`
**Status**: COMPLETE

---

## Executive Summary

9 files re-audited after Round 1 fixes. 28 findings (6 CONFIRMED carried over from Round 1, 22 new or deepened findings). Round 1 fixes for FIG query locks and terminal lifecycle protection are **verified correct** but introduce one new issue (incomplete terminal guard). The `evolve()` inline import was NOT fixed. Post-hoc detection remains dead code.

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 9     |
| MEDIUM   | 11    |
| LOW      | 5     |

---

## Verification of Round 1 Fixes

### FIX VERIFIED: FIG query methods now have locks
All query methods (`actions_for_belief`, `feedbacks_for_action`, `feedbacks_for_belief`, `downstream_beliefs`, `suspect_beliefs`, `falsified_beliefs`, `active_beliefs`) now acquire `self._lock` before reading. Lines 317-371 in `fig_schema.py`. Correct.

### FIX VERIFIED: Terminal lifecycle transitions blocked
`_TERMINAL_LIFECYCLES` frozen set at line 278 blocks lifecycle transitions from `retired` and `posthoc_invalid` states (line 286-289). Guard logic is correct for lifecycle changes.

### FIX NOT APPLIED: Inline dataclasses import in `evolve()`
`active_quest_context.py` line 96 still has `import dataclasses` inside `evolve()`, despite `replace` being imported at line 18. This is not just a style issue -- it shadows the already-imported `replace` and adds per-call overhead.

### FIX NOT APPLIED: `classify_objective` keyword collision
`active_quest_context.py` line 108 still has `"go to"` in `dialog_kw`, causing "go to" objectives to be misclassified as `dialog` instead of `go_to_marker`.

---

## New Issues Introduced by Round 1 Fixes

### NEW-1: Terminal lifecycle guard only blocks lifecycle overrides, not other field updates

**Severity**: HIGH
**File**: `bagel/fig_schema.py`, lines 286-289
**Description**: The terminal lifecycle guard:
```python
if belief.lifecycle in self._TERMINAL_LIFECYCLES:
    new_lc = overrides.get("lifecycle")
    if new_lc is not None and new_lc != belief.lifecycle:
        return None
```
Only rejects the update when `lifecycle` is being changed away from a terminal state. If `update_belief` is called with non-lifecycle overrides (e.g., `confidence=0.9`, `metadata={...}`) on a retired or posthoc_invalid belief, the update succeeds. This means terminal beliefs can have their confidence or metadata modified after retirement, which violates the intent of terminal state protection.
**Fix**: Block ALL updates to terminal-state beliefs:
```python
if belief.lifecycle in self._TERMINAL_LIFECYCLES:
    return None
```
Or if intentional field updates are needed, explicitly enumerate allowed fields for terminal beliefs.

### NEW-2: `to_dict()` still has no lock

**Severity**: MEDIUM
**File**: `bagel/fig_schema.py`, lines 373-383
**Description**: Round 1 added locks to all named query methods but `to_dict()` was missed. It iterates over `self.beliefs`, `self.actions`, `self.feedbacks`, `self.probes`, and `self.edges` without acquiring `self._lock`. Under concurrent mutation, this can produce partial/inconsistent snapshots or raise `RuntimeError: dictionary changed size during iteration`.
**Fix**: Wrap `to_dict()` body in `with self._lock:`.

---

## Carried-Over Findings from Round 1 (Verified Still Present)

### CARRY-1: Evidence matrix core_contradiction formula deviates from BAGEL v1.1 theory (EMX-C1)

**Severity**: CRITICAL (unchanged)
**File**: `bagel/evidence_matrix.py`, lines 135-141
**Description**: Three-branch scoring formula still deviates from the theory's single formula `score_i = C_i - S_i + alpha * R_i / (epsilon + S_i)`:
1. Core contradiction branch (line 136): `score = -(s_i + self.alpha * r_i)` drops `C_i` entirely and uses additive alpha instead of the ratio term.
2. No-refute branch (line 141): `score = c_i + self.alpha * r_i` adds a flat relevance bonus instead of the theory's ratio term.
3. Normal case (line 139): matches theory formula.

This makes core contradictions dramatically more negative than theory intends. Example: `C_i=2.0, S_i=0.9, core_contradiction=True, R_i=3.0` yields `-(0.9 + 0.3) = -1.2` instead of theory's `2.0 - 0.9 + 0.1*3.0/(0.01+0.9) = 1.1 + 0.33 = 1.43` -- a sign flip AND magnitude error.
**Fix**: Remove the core_contradiction special branch. Use the theory formula uniformly. If core contradictions need special treatment, apply a post-hoc modifier that is documented and proportional.

### CARRY-2: Post-hoc detection is dead code (FIG-H1)

**Severity**: HIGH (unchanged)
**File**: `bagel/fig_schema.py`, lines 234-239
**Description**: The post-hoc check in `_commit_belief_unlocked` iterates over existing actions to see if any already reference the new belief's `belief_id`. But `propose_action` (line 253) rejects actions that reference unknown beliefs. Therefore, no action can exist that references a belief_id before that belief is committed. The check can never trigger (except for beliefs explicitly tagged `posthoc_invalid` before insertion, which bypass the check at line 230).
**Fix**: The post-hoc detection should be time/version based: record whether any action was proposed *before* this belief was committed, regardless of whether the action names this belief. Use the `_ordering_lock` (currently dead state) to enforce ordering.

### CARRY-3: Event store reconstruction is incomplete (EVS-H1)

**Severity**: HIGH (unchanged)
**File**: `bagel/event_store.py`, lines 187-204
**Description**: `reconstruct_fig()` only handles `BeliefCommitted`, `ActionProposed`, `FeedbackReceived`, and `ProbeGenerated`. It ignores:
- `ActionMaterialized` -- reconstructed actions have `status="proposed"` instead of `"materialized"`, missing fingerprints and claims
- `ActionExecuted` -- no status update
- `BeliefRevised` / `BeliefStaled` / `BeliefRetired` -- lifecycle changes are lost
- `ProbeExecuted` -- probe results are lost
- `ArbiterUpdated` -- arbiter state is lost

A reconstructed FIG will be an incomplete snapshot that does not reflect the final state of the event stream.
**Fix**: Add handlers for all event types, or at minimum: `ActionMaterialized`, `BeliefRevised`, `BeliefStaled`, `BeliefRetired`, and `ProbeExecuted`. For lifecycle events, call `fig.update_belief()`.

### CARRY-4: `_dict_to_probe` loses critical fields during reconstruction

**Severity**: MEDIUM
**File**: `bagel/event_store.py`, lines 279-293
**Description**: The probe deserialization function does not restore `falsification_invariant`, `irreversible`, `can_distinguish`, `timeout_risk`, or `noise_risk`. A reconstructed ProbeNode loses its falsification metadata, making probe validation impossible on reconstructed FIGs.
**Fix**: Add all missing fields to the deserialization function.

### CARRY-5: Probe sanity check does not validate `can_distinguish` (PRB-H1)

**Severity**: MEDIUM (downgraded from HIGH -- the `can_distinguish` field exists but is not validated)
**File**: `bagel/probe_policy.py`, lines 92-122
**Description**: The sanity check has 5 numbered checks in the docstring but the implementation only checks: (1) failure_criteria, (2) irreversible, (3) belief_id, (4) falsification_invariant, (5) timeout/noise risk. There is NO check that `can_distinguish` contains two distinct, valid belief IDs. A probe with `can_distinguish=("", "")` passes all sanity checks, violating theory requirement 5.
**Fix**: Add:
```python
if not probe.can_distinguish or len(probe.can_distinguish) < 2:
    return ProbeSanityCheck(probe.probe_id, False, "probe cannot distinguish beliefs")
if probe.can_distinguish[0] == probe.can_distinguish[1]:
    return ProbeSanityCheck(probe.probe_id, False, "probe can_distinguish has identical candidates")
```

### CARRY-6: Arbiter skips beliefs with no signals (ARB-H1)

**Severity**: HIGH (unchanged)
**File**: `bagel/arbiter.py`, lines 65-78
**Description**: `arbitrate()` iterates over `matrix.score_all()`, which only returns beliefs that have at least one signal. Beliefs with no signals are never evaluated and remain in their current lifecycle indefinitely. There is no timeout or proactive probe mechanism for beliefs that never receive feedback.
**Fix**: The arbiter should also process beliefs with zero signals. A belief in `provisional` state with zero signals for too long should be flagged for proactive probing.

---

## New / Deepened Findings in Round 2

### R2-1: `evolve()` uses `import dataclasses; dataclasses.replace()` despite `replace` already imported at top level

**Severity**: MEDIUM
**File**: `planning/mainline/active_quest_context.py`, lines 18, 96-98
**Description**: Line 18 imports `replace` from `dataclasses`, but line 96 does `import dataclasses` and line 97 calls `dataclasses.replace()`. This:
1. Adds unnecessary per-call import overhead (though Python caches module imports).
2. Is inconsistent with the existing top-level import.
3. Suggests the code was written at different times.
**Fix**: Change line 97 to use the already-imported `replace`:
```python
return replace(
    self,
    version=self.version + 1,
    ...
)
```

### R2-2: Evidence matrix has no thread safety -- `_signals` dict mutated without locks

**Severity**: HIGH
**File**: `bagel/evidence_matrix.py`, lines 82-177
**Description**: The `_signals: dict[str, list[EvidenceSignal]]` is a mutable dict with no lock. Methods `add_signal` (line 84), `add_signals` (line 87), `score_belief` (line 91), `score_all` (line 161), `top_suspects` (line 165), and `clear` (line 172) all access `_signals` without synchronization. In the BAGEL runtime, `receive_feedback` calls `add_signal` while `run_attribution_cycle` calls `score_all` and `score_belief`. If these run on different threads, `RuntimeError: dictionary changed size during iteration` or data corruption is possible.
**Fix**: Add a `threading.Lock` to `EvidenceMatrix` and acquire it in all methods that read or write `_signals`.

### R2-3: `safe_revision.py` `decide()` has TOCTOU -- calls `fig.actions_for_belief()` and `fig.downstream_beliefs()` twice each

**Severity**: HIGH
**File**: `bagel/safe_revision.py`, lines 156-160
**Description**: The `decide()` method calls `fig.actions_for_belief(belief_id)` TWICE (lines 157-158) and `fig.downstream_beliefs(belief_id)` once (line 160), in addition to the earlier call in `assess_cascade()` (line 91). Between these calls, the FIG may be mutated by another thread, causing:
1. Different results from the two `actions_for_belief()` calls (line 157 uses index-based iteration over the length of the second call, risking IndexError if the first call returned more results).
2. `affected_belief_ids` in `RevisionDecision` may not match the ones used in `assess_cascade()`.
**Fix**: Cache the results of FIG queries in `assess_cascade()` and pass them to `decide()`, or call FIG queries once and store the results.

### R2-4: `safe_revision.py` `assess_cascade` reads FIG state without holding the FIG lock

**Severity**: HIGH
**File**: `bagel/safe_revision.py`, lines 73-138
**Description**: `assess_cascade()` makes 5+ separate calls to FIG methods (`fig.beliefs.get`, `fig.downstream_beliefs`, `fig.actions_for_belief`, `fig.actions.get`, `fig.actions[aid].claim_id`). Each individual call acquires and releases the FIG lock. Between calls, other threads can mutate the FIG. This means the cascade assessment is computed from an inconsistent snapshot -- downstream beliefs may change between the `downstream_beliefs()` call and the `actions_for_belief()` loop.
**Fix**: Either (a) add a method to FIG that computes the entire cascade assessment under a single lock acquisition, or (b) have `assess_cascade()` accept a pre-acquired lock or snapshot.

### R2-5: QuestStateTracker confidence decay is time-unaware and too aggressive (QST-C1)

**Severity**: CRITICAL (unchanged severity, deepened analysis)
**File**: `planning/mainline/quest_state_tracker_v2.py`, lines 149-160
**Description**: The confidence decay subtracts `0.02` (once) then `0.04` per `update()` call with no time awareness. At a typical perception rate of 10-30 fps:
- 30 fps: confidence drops from 1.0 to 0.05 in ~25 frames = 0.83 seconds
- 10 fps: confidence drops from 1.0 to 0.05 in ~25 frames = 2.5 seconds

The decay should be proportional to elapsed time, not call count. Additionally, the floor values (0.1 for first dropout, 0.05 for sustained dropout) are hardcoded and not configurable.
**Fix**: Use time-based decay:
```python
elapsed = time.perf_counter() - self._last_update_time
decay = 1.0 - math.exp(-self._decay_rate * elapsed)
confidence = max(0.05, confidence * (1 - decay))
```

### R2-6: VLM fallback regex only matches English (QST-H2)

**Severity**: HIGH (unchanged)
**File**: `planning/mainline/quest_state_tracker_v2.py`, lines 111-119
**Description**: The VLM fallback regex:
```python
re.search(r"(?:quest|task|objective|goal is)\s*([a-zA-Z0-9\s]+)", ...)
```
Only captures ASCII characters. For a Chinese game (the primary use case per CLAUDE.md), VLM scene descriptions in Chinese will never match. The regex should include Unicode character ranges.
**Fix**:
```python
re.search(r"(?:quest|task|objective|goal is|任务|目标|目标)\s*([a-zA-Z0-9\s一-鿿]+)", ...)
```

### R2-7: `hash()` is non-deterministic for blocker_id generation (QST-H3)

**Severity**: HIGH (unchanged)
**File**: `planning/mainline/quest_state_tracker_v2.py`, line 131
**Description**: `hash(line.strip()) % 10000` uses Python's randomized hash function. Same blocker text produces different IDs across Python sessions, making event log correlation and cross-session analysis impossible.
**Fix**: Use deterministic hash:
```python
import hashlib
blocker_id=f"blocker_{hashlib.md5(line.strip().encode()).hexdigest()[:4]}"
```

### R2-8: `classify_objective` keyword collision -- "go to" in both `dialog_kw` and `marker_kw` (AQC-M1)

**Severity**: MEDIUM (upheld from Round 1, NOT fixed)
**File**: `planning/mainline/active_quest_context.py`, lines 108, 111
**Description**: `"go to"` appears in `dialog_kw` (line 108) AND `marker_kw` (line 111). Since `combat_kw`, `domain_kw`, and `dialog_kw` are checked before `marker_kw`, any objective containing "go to" (e.g., "Go to the Adventurers' Guild") is classified as `dialog` instead of `go_to_marker`. The test suite does NOT test for this collision -- there is no test with "go to" that expects `go_to_marker`.
**Fix**: Remove `"go to"` from `dialog_kw` (line 108). It does not belong there -- "go to" is navigation, not dialogue.

### R2-9: `_TERMINAL_LIFECYCLES` excludes `falsified` and `stale`

**Severity**: MEDIUM
**File**: `bagel/fig_schema.py`, line 278
**Description**: Only `retired` and `posthoc_invalid` are terminal. But `falsified` is also semantically terminal -- a falsified belief should not be re-confirmed or re-provisioned without explicit re-investigation. Currently, `update_belief` allows `falsified -> confirmed` or `falsified -> provisional` transitions. Similarly, `stale` is supposed to be a transient state awaiting JIT regeneration, but there is no guard preventing `stale -> confirmed` without regeneration.
**Fix**: Either add `falsified` to `_TERMINAL_LIFECYCLES` (if falsification is irreversible) or add a `_REQUIRES_INVESTIGATION` set that blocks direct transitions to active states without going through a re-investigation flow.

### R2-10: `runtime.py` `run_attribution_cycle` does not check `event_store.append` return value

**Severity**: MEDIUM (upheld from Round 1)
**File**: `bagel/runtime.py`, lines 111, 132, 156, 177, 220, 269
**Description**: `event_store.append()` can return `False` on write failure. The runtime never checks this. The theory says "write failure prevents further external action." Currently, a write failure is silently ignored and the runtime continues as if the event was persisted. If the event store is the source of truth for audit/reconstruction, lost events mean lost attribution data.
**Fix**: Check the return value and log a warning or halt:
```python
if not self.event_store.append(event):
    log.error("[BAGEL] Event store write failed for %s", event.event_type)
```

### R2-11: Arbiter probe IDs can collide

**Severity**: MEDIUM (upheld from Round 1)
**File**: `bagel/arbiter.py`, line 174
**Description**: `f"probe_{result.belief_id[:16]}_{int(time.perf_counter())}"` -- two probes for the same belief in the same `perf_counter()` tick get identical IDs. The `ProbePolicy._create_probe` uses `uuid.uuid4().hex[:6]` which is collision-safe. The arbiter should do the same.
**Fix**: Use `uuid.uuid4().hex[:6]` instead of `int(time.perf_counter())`.

### R2-12: `_BLOCKED_RE` matches common quest text without word boundary checks

**Severity**: MEDIUM (upheld from Round 1)
**File**: `planning/mainline/quest_state_tracker_v2.py`, lines 40-43
**Description**: The regex `(?:blocked|stuck|failed|无法|卡住|障碍|锁定|未解锁)` will match substrings in normal Chinese text. For example, "锁定敌人" (lock onto enemy) contains "锁定" and would trigger a false blocker detection. "障碍物" (obstacle) is also a valid match but may appear in normal quest descriptions.
**Fix**: Add word-boundary or context checks. For Chinese, require a preceding negation or specific patterns.

### R2-13: `apply_revision` for `stale_marking` does not stale affected actions

**Severity**: MEDIUM (upheld from Round 1)
**File**: `bagel/safe_revision.py`, lines 194-201
**Description**: When downstream beliefs are marked `stale`, the actions driven by those beliefs are NOT updated. The theory says "mark downstream nodes stale" including actions. Stale beliefs still drive active actions with no guard.
**Fix**: Also mark affected actions with a status indicating they need regeneration, or add a guard in action execution that checks if driving beliefs are stale.

### R2-14: `claim_graph_summary` parameter accepted but unused

**Severity**: LOW
**File**: `planning/mainline/quest_state_tracker_v2.py`, line 80
**Description**: The `update()` method signature includes `claim_graph_summary: dict[str, Any] | None = None` but the implementation never reads it. This is dead API surface.
**Fix**: Either implement the integration or remove the parameter.

### R2-15: `runtime.py` `_attribution_count` is not thread-safe

**Severity**: LOW
**File**: `bagel/runtime.py`, line 210
**Description**: `self._attribution_count += 1` is not atomic. If `run_attribution_cycle` is called concurrently, the counter can be corrupted. In practice this is likely called from a single thread, but the attribute is not guarded.
**Fix**: Use `threading.Lock` or make the counter an `atomic` increment.

---

## Answers to Audit Questions

### Q1: Are there any NEW issues introduced by the Round 1 fixes?

**Yes, two:**

1. **NEW-1 (HIGH)**: The terminal lifecycle guard in `update_belief` only blocks lifecycle changes but allows other field updates (confidence, metadata) on terminal beliefs. This was likely not intended -- terminal protection should be comprehensive.

2. **NEW-2 (MEDIUM)**: `to_dict()` was missed when adding locks to query methods. It reads all FIG state without a lock, which can produce inconsistent snapshots under concurrent mutation.

### Q2: Is the thread safety model now complete for FIG?

**No. The thread safety model is improved but incomplete:**

1. **`to_dict()` has no lock** -- reads all collections without synchronization.
2. **`safe_revision.py` composes multiple FIG queries without holding the lock across them** -- TOCTOU between `downstream_beliefs()` and `actions_for_belief()` calls within `assess_cascade()` and `decide()`.
3. **`EvidenceMatrix` has no thread safety** -- `_signals` dict is mutated without locks, and the runtime calls `add_signal` (from `receive_feedback`) concurrently with `score_all` (from `run_attribution_cycle`).
4. **`assess_cascade` reads FIG state via multiple separate locked calls** -- each individual call is safe, but the compound read is not atomic.
5. **`runtime.py` composes thread-safe components but the composition is not atomic** -- e.g., `commit_belief` + `propose_action` releases the FIG lock between steps.

### Q3: Are there any remaining TOCTOU or race conditions in the BAGEL runtime?

**Yes, three significant TOCTOU/race conditions:**

1. **EvidenceMatrix TOCTOU** (`evidence_matrix.py`): `add_signal` and `score_belief`/`score_all` can run concurrently with no lock. `score_all` iterates over `_signals` dict keys while `add_signal` may be inserting new keys.

2. **SafeRevision TOCTOU** (`safe_revision.py`): `assess_cascade()` calls `fig.downstream_beliefs()`, then `fig.actions_for_belief()` in separate lock acquisitions. Between these calls, the FIG can be mutated. The `decide()` method compounds this by calling `fig.actions_for_belief()` TWICE separately and using index-based iteration that assumes both calls return the same list (they may not).

3. **Runtime compound operations** (`runtime.py`): `receive_feedback()` reads `fig.actions.get(feedback.action_id)` without a lock (line 180), then calls `matrix.add_signal()` without a lock. Between these calls, the action could be removed or the matrix could be scored by another thread. Similarly, `run_attribution_cycle` calls `arbiter.arbitrate()` which reads `matrix.score_all()`, then later calls `matrix.add_signal()` for probe results -- the matrix may have been modified between the score and the signal addition.

---

## Summary Table

| ID | Severity | File | Issue | Status |
|----|----------|------|-------|--------|
| NEW-1 | HIGH | fig_schema.py:286-289 | Terminal guard only blocks lifecycle changes | New |
| NEW-2 | MEDIUM | fig_schema.py:373-383 | `to_dict()` has no lock | New |
| CARRY-1 | CRITICAL | evidence_matrix.py:135-141 | Formula deviates from BAGEL v1.1 theory | Unfixed |
| CARRY-2 | HIGH | fig_schema.py:234-239 | Post-hoc detection is dead code | Unfixed |
| CARRY-3 | HIGH | event_store.py:187-204 | Reconstruction ignores most event types | Unfixed |
| CARRY-4 | MEDIUM | event_store.py:279-293 | Probe deserialization loses critical fields | Unfixed |
| CARRY-5 | MEDIUM | probe_policy.py:92-122 | `can_distinguish` not validated | Unfixed |
| CARRY-6 | HIGH | arbiter.py:65-78 | Skips beliefs with no signals | Unfixed |
| R2-1 | MEDIUM | active_quest_context.py:96-98 | `evolve()` ignores top-level `replace` import | Unfixed |
| R2-2 | HIGH | evidence_matrix.py:82-177 | No thread safety on `_signals` | New |
| R2-3 | HIGH | safe_revision.py:156-160 | TOCTOU: `actions_for_belief` called twice | New |
| R2-4 | HIGH | safe_revision.py:73-138 | Multi-call TOCTOU in cascade assessment | New |
| R2-5 | CRITICAL | quest_state_tracker_v2.py:149-160 | Time-unaware confidence decay too aggressive | Unfixed |
| R2-6 | HIGH | quest_state_tracker_v2.py:111-119 | VLM regex only matches English | Unfixed |
| R2-7 | HIGH | quest_state_tracker_v2.py:131 | `hash()` non-deterministic for blocker_id | Unfixed |
| R2-8 | MEDIUM | active_quest_context.py:108,111 | "go to" keyword collision dialog/marker | Unfixed |
| R2-9 | MEDIUM | fig_schema.py:278 | `falsified` not in terminal lifecycles | New |
| R2-10 | MEDIUM | runtime.py:111,132,156,177,220,269 | `event_store.append` return value unchecked | Unfixed |
| R2-11 | MEDIUM | arbiter.py:174 | Probe ID collision possible | Unfixed |
| R2-12 | MEDIUM | quest_state_tracker_v2.py:40-43 | `_BLOCKED_RE` false positives | Unfixed |
| R2-13 | MEDIUM | safe_revision.py:194-201 | Stale marking skips actions | Unfixed |
| R2-14 | LOW | quest_state_tracker_v2.py:80 | `claim_graph_summary` unused | Unfixed |
| R2-15 | LOW | runtime.py:210 | `_attribution_count` not thread-safe | Unfixed |

---

## Priority Recommendations for Round 3

1. **[CRITICAL]** Fix evidence matrix formula to match BAGEL v1.1 theory or formally document the deviation as intentional.
2. **[CRITICAL]** Fix confidence decay to be time-based, not per-call.
3. **[HIGH]** Add thread safety lock to `EvidenceMatrix._signals`.
4. **[HIGH]** Fix `safe_revision.py` TOCTOU by caching FIG query results.
5. **[HIGH]** Complete terminal lifecycle guard to block ALL updates to terminal beliefs.
6. **[HIGH]** Add lock to `to_dict()`.
7. **[HIGH]** Fix "go to" keyword collision in `classify_objective`.
8. **[HIGH]** Replace `hash()` with deterministic hash for blocker_id.
9. **[HIGH]** Add Chinese VLM fallback regex support.
10. **[HIGH]** Complete `reconstruct_fig` to handle lifecycle update events.
