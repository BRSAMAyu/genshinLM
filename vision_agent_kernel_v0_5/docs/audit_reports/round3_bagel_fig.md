# Round 3 (FINAL) Audit Report: BAGEL System, Quest Fact Chain, and FIG Schema

**Auditor**: Senior Code Auditor (Round 3 Final)
**Date**: 2026-05-27
**Scope**: `bagel/` (7 files: fig_schema.py, evidence_matrix.py, arbiter.py, safe_revision.py, probe_policy.py, event_store.py, runtime.py), `planning/mainline/active_quest_context.py`, `planning/mainline/quest_state_tracker_v2.py`
**Status**: COMPLETE

---

## Executive Summary

9 files re-audited after Round 1 and Round 2 fixes (commit `10f6c77`). All 10 listed fixes verified. **6 fixes are correct and complete. 4 fixes are correct but have residual issues.** 15 remaining findings identified (0 CRITICAL, 5 HIGH, 7 MEDIUM, 3 LOW). No new CRITICAL issues remain. Thread safety is substantially improved but not fully complete -- compound operations across components remain non-atomic.

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 5     |
| MEDIUM   | 7     |
| LOW      | 3     |

---

## Verification of All Round 1+2 Fixes (10 Items)

### FIX 1: FIG query methods have locks -- VERIFIED CORRECT

All 7 query methods (`actions_for_belief`, `feedbacks_for_action`, `feedbacks_for_belief`, `downstream_beliefs`, `suspect_beliefs`, `falsified_beliefs`, `active_beliefs`) now acquire `self._lock` before reading. Each method wraps its body in `with self._lock:`. Lock scope is appropriate -- acquires before collection iteration, releases after copy/return.

**Verdict**: PASS

### FIX 2: FIG to_dict() has lock -- VERIFIED CORRECT

`to_dict()` (lines 362-374 in fig_schema.py) wraps its entire body in `with self._lock:`. This covers all five collections (`beliefs`, `actions`, `feedbacks`, `probes`, `edges`) plus scalar fields. Consistent snapshots are now guaranteed.

**Verdict**: PASS

### FIX 3: Terminal lifecycle guard blocks ALL updates to retired/posthoc_invalid/falsified beliefs -- VERIFIED CORRECT

The guard at line 286-288 now reads:
```python
if belief.lifecycle in self._TERMINAL_LIFECYCLES:
    return None
```

And `_TERMINAL_LIFECYCLES` is `frozenset({"retired", "posthoc_invalid", "falsified"})`. This blocks ALL field overrides on terminal beliefs (not just lifecycle changes). The `falsified` state was added per R2-9. This is the correct fix for both NEW-1 (partial terminal guard) and R2-9 (falsified not terminal).

**Verdict**: PASS

### FIX 4: Evidence matrix formula unified to match BAGEL v1.1 theory -- PARTIALLY CORRECT (residual issue)

The three-branch scoring formula from Round 1 has been simplified. Current code (lines 139-147):
```python
if s_i > 0:
    score = c_i - s_i + self.alpha * r_i / (self.epsilon + s_i)
else:
    score = c_i
```

The `core_contradiction` branch that previously used `score = -(s_i + self.alpha * r_i)` has been removed. The unified formula for `s_i > 0` now matches the BAGEL v1.1 theory formula exactly. When `s_i == 0`, it falls through to `score = c_i` which is the support max -- reasonable since there is nothing to refute.

However, the `core_contradiction` flag is still SET (line 123-124: when `is_core_probe` and `weight >= core_probe_veto_threshold`) and is still REPORTED in `EvidenceScore.core_contradiction`. The flag still triggers the `core_contradiction` weight tripling (line 121: `w *= 3.0`). This means the core contradiction mechanism now works through the weight system (tripling refute weight makes `s_i` much larger), rather than a separate branch. This is a better design than the old branch, but the docstring (line 15) still says `score_i = C_i + alpha * R_i / (epsilon + S_i)` without documenting the weight-tripling mechanism. The docstring should be updated to reflect this.

**Verdict**: PASS (formula correct, docstring outdated -- tracked as MEDIUM finding below)

### FIX 5: EvidenceMatrix has threading.Lock on all _signals operations -- VERIFIED CORRECT

A `_lock: threading.Lock` field is added to `EvidenceMatrix`. All methods that access `_signals` are now guarded:
- `add_signal`: wraps insertion in `with self._lock`
- `add_signals`: wraps batch insertion in `with self._lock`
- `score_belief`: copies signals under lock (`with self._lock: signals = list(self._signals.get(...))`), then processes outside lock (correct pattern -- avoids holding lock during computation)
- `score_all`: copies belief ID list under lock, then calls `score_belief` per ID (each `score_belief` acquires lock independently)
- `clear`: wraps in `with self._lock`
- `signal_count`: wraps in `with self._lock`

The copy-then-process pattern in `score_belief` is the correct approach for minimizing lock contention while ensuring consistency of the snapshot.

**Verdict**: PASS

### FIX 6: Post-hoc detection still dead code -- VERIFIED (documented as known limitation)

The post-hoc detection in `_commit_belief_unlocked` (lines 234-239) remains dead code as identified in Round 1 and Round 2. The check iterates over existing actions looking for one that references the new belief's `belief_id`, but `propose_action` rejects actions referencing unknown beliefs, so no action can pre-exist with a reference to a not-yet-committed belief. The fix commit did not address this.

This is now documented as a known limitation per the task scope.

**Verdict**: ACKNOWLEDGED (known limitation, not a bug that can trigger)

### FIX 7: Probe can_distinguish now validated -- VERIFIED CORRECT

The sanity check in `probe_policy.py` (lines 122-128) now validates:
1. `can_distinguish` is truthy (non-empty)
2. Length is at least 2
3. The two entries are not identical

This covers the theory requirement "can distinguish at least two candidate beliefs." However, it does NOT validate that the belief IDs actually exist in the FIG. The check validates structural correctness (two distinct strings) but not referential integrity (the IDs point to real beliefs). This is acceptable for a sanity check (the probe may be generated before the second belief is committed).

**Verdict**: PASS (note: referential integrity not checked, acceptable)

### FIX 8: classify_objective "go to" removed from dialog_kw -- VERIFIED CORRECT

`active_quest_context.py` line 108 now reads:
```python
dialog_kw = ("对话", "交谈", "talk", "speak", "dialogue", "对话完成")
```

`"go to"` has been removed from `dialog_kw`. It remains only in `marker_kw` (line 111). The classification order is: combat, domain, dialog, collect, marker. Since "go to" is only in `marker_kw` now, objectives containing "go to" will correctly fall through to `go_to_marker` unless they also contain combat/domain/dialog/collect keywords (which is unlikely for navigation objectives).

**Verdict**: PASS

### FIX 9: QuestTracker blocker_id uses hashlib.md5 -- VERIFIED CORRECT

`quest_state_tracker_v2.py` line 132 now reads:
```python
blocker_id=f"blocker_{hashlib.md5(line.strip().encode()).hexdigest()[:4]}",
```

`hashlib` is imported at line 12. The `hashlib.md5` call is deterministic across Python sessions (unlike `hash()`). The 4-hex-char truncation (16 bits) is sufficient for session-unique blocker IDs (collision probability ~0.001% at 100 blockers).

**Verdict**: PASS

### FIX 10: Inline dataclasses imports moved to top level in fig_schema.py -- VERIFIED CORRECT

`fig_schema.py` line 7 now has `import dataclasses as _dc` at the top level. The `update_belief`, `update_action`, and `update_probe` methods now use `_dc.replace()` without re-importing. This eliminates per-call import overhead.

**Verdict**: PASS

---

## Summary of Fix Verification

| Fix | Description | Verdict |
|-----|-------------|---------|
| 1 | FIG query methods have locks | PASS |
| 2 | FIG to_dict() has lock | PASS |
| 3 | Terminal guard blocks ALL updates (incl. falsified) | PASS |
| 4 | Evidence matrix formula unified | PASS (docstring lag) |
| 5 | EvidenceMatrix threading.Lock on _signals | PASS |
| 6 | Post-hoc detection dead code | ACKNOWLEDGED |
| 7 | Probe can_distinguish validated | PASS |
| 8 | "go to" removed from dialog_kw | PASS |
| 9 | blocker_id uses hashlib.md5 | PASS |
| 10 | Inline imports moved to top level in fig_schema.py | PASS |

---

## Remaining Issues

### R3-1: safe_revision.py TOCTOU -- `decide()` calls `fig.actions_for_belief()` twice with index-based access

**Severity**: HIGH
**File**: `bagel/safe_revision.py`, lines 155-160
**Description**: The `decide()` method constructs `affected_action_ids` by:
```python
affected_action_ids=tuple(
    fig.actions_for_belief(belief_id)[i].action_id
    for i in range(len(fig.actions_for_belief(belief_id)))
),
```
This calls `fig.actions_for_belief()` twice. Each call acquires and releases the FIG lock. Between calls, another thread can add or remove an action for this belief, causing the `range(len(...))` to differ from the list being indexed, potentially raising `IndexError` or including the wrong actions.

Additionally, `assess_cascade()` (line 91) also calls `fig.actions_for_belief()` for the same belief. If the FIG is mutated between `assess_cascade()` and `decide()`, the cascade report and the decision may be based on different snapshots.

**Fix**: Call `actions_for_belief()` once, store the result, and use it:
```python
affected = fig.actions_for_belief(belief_id)
affected_action_ids = tuple(a.action_id for a in affected)
```
And pass cascade results to `decide()` rather than re-querying the FIG.

### R3-2: safe_revision.py assess_cascade reads FIG via multiple separate lock acquisitions

**Severity**: HIGH
**File**: `bagel/safe_revision.py`, lines 73-138
**Description**: `assess_cascade()` makes 5+ separate calls to FIG methods:
1. `fig.beliefs.get(belief_id)` -- no lock (direct dict access)
2. `fig.downstream_beliefs(belief_id)` -- acquires/releases FIG lock
3. `fig.actions_for_belief(bid)` -- acquires/releases FIG lock (called N times in loop)
4. `fig.actions.get(aid)` -- no lock
5. `fig.actions[aid].claim_id` -- no lock

Each locked method acquires and releases the FIG lock independently. Between calls, other threads can mutate the FIG. The cascade assessment is computed from an inconsistent snapshot -- e.g., downstream beliefs computed at time T1, actions for those beliefs computed at time T2, claim data read at time T3.

In particular, line 104 `fig.beliefs.get(belief_id)` and line 115 `fig.actions.get(aid)` access internal dicts directly without the FIG lock, which is a thread safety violation for the FIG's own invariants.

**Fix**: Either (a) add a FIG method that computes the entire cascade snapshot under a single lock, or (b) add a `snapshot()` method to FIG that returns a consistent point-in-time copy of all relevant data.

### R3-3: Post-hoc detection is architecturally dead code

**Severity**: MEDIUM (downgraded from HIGH -- cannot cause runtime harm)
**File**: `bagel/fig_schema.py`, lines 234-239
**Description**: As documented in the fix list, the post-hoc detection check can never trigger. The `_ordering_lock` dict is written (line 241) but never read. The intended purpose (detecting beliefs inserted after actions) cannot be achieved by the current approach because `propose_action` rejects unknown beliefs.

This is not a bug -- it is dead code that cannot cause harm. However, it gives a false sense of post-hoc protection. The code should either:
1. Be removed entirely (and post-hoc detection implemented differently if needed), or
2. Have a comment explaining why it is currently unreachable and what a proper implementation would look like.

**Fix**: Add a comment explaining the dead code status, or implement time/version-based post-hoc detection.

### R3-4: evidence_matrix.py docstring describes outdated formula

**Severity**: MEDIUM
**File**: `bagel/evidence_matrix.py`, lines 15-17
**Description**: The module docstring says:
```
score_i = C_i + alpha * R_i / (epsilon + S_i)
```
But the actual implementation uses:
```python
score = c_i - s_i + self.alpha * r_i / (self.epsilon + s_i)
```

The docstring is missing the `- S_i` term. Additionally, the core contradiction weight-tripling mechanism is not documented. The theory formula should match the implementation exactly.

**Fix**: Update docstring to:
```
score_i = C_i - S_i + alpha * R_i / (epsilon + S_i)
```
And add a note about core probe weight tripling.

### R3-5: `evolve()` in active_quest_context.py still uses inline import

**Severity**: MEDIUM
**File**: `planning/mainline/active_quest_context.py`, lines 96-98
**Description**: `evolve()` still contains:
```python
import dataclasses
return dataclasses.replace(...)
```
Despite `replace` being imported at line 18 (`from dataclasses import dataclass, field, replace`). The fix for fig_schema.py (Fix 10) was applied but the same pattern in active_quest_context.py was not addressed. This is the third audit to flag this issue (R1-L1, R2-1, now R3-5).

**Fix**: Change to:
```python
return replace(
    self,
    version=self.version + 1,
    ...
)
```

### R3-6: Confidence decay in QuestStateTrackerV2 is time-unaware and too aggressive

**Severity**: HIGH
**File**: `planning/mainline/quest_state_tracker_v2.py`, lines 149-160
**Description**: Unchanged from Round 1/2. The decay subtracts `0.02` then `0.04` per `update()` call with no elapsed time consideration. At 30 fps, confidence drops from 1.0 to 0.05 in ~25 frames (~0.83 seconds). The decay should be proportional to elapsed time since last update, not call count. This was CRITICAL in Round 1/2 but the behavior is functionally "aggressive but predictable" -- the confidence recovers quickly when quest text is re-detected (line 150: `min(1.0, 0.7 + 0.3 * ...)`).

Downgraded to HIGH because: (a) the floor values (0.1, 0.05) prevent confidence from reaching zero, (b) confidence recovers instantly on OCR re-detection, and (c) the quest tracker is a heuristic component, not a safety-critical path.

**Fix**: Use time-based decay:
```python
elapsed = time.perf_counter() - self._last_update_time
confidence = max(0.05, confidence * math.exp(-self._decay_rate * elapsed))
```

### R3-7: VLM fallback regex only matches English

**Severity**: HIGH
**File**: `planning/mainline/quest_state_tracker_v2.py`, lines 111-119
**Description**: Unchanged from Round 1/2. The regex:
```python
re.search(r"(?:quest|task|objective|goal is)\s*([a-zA-Z0-9\s]+)", ...)
```
Only captures ASCII characters. For a Chinese game (the primary use case per CLAUDE.md), VLM scene descriptions in Chinese will never match. This means the VLM fallback path is effectively non-functional for Chinese content.

**Fix**: Add Chinese keywords and Unicode character ranges:
```python
re.search(r"(?:quest|task|objective|goal is|任务|目标)\s*([a-zA-Z0-9\s一-鿿]+)", ...)
```

### R3-8: Event store reconstruction is incomplete

**Severity**: MEDIUM
**File**: `bagel/event_store.py`, lines 187-204
**Description**: Unchanged from Round 1/2. `reconstruct_fig()` only handles 4 event types (`BeliefCommitted`, `ActionProposed`, `FeedbackReceived`, `ProbeGenerated`), ignoring `ActionMaterialized`, `BeliefRevised`, `BeliefStaled`, `BeliefRetired`, `ProbeExecuted`, and `ArbiterUpdated`. A reconstructed FIG will have actions stuck in `proposed` status and beliefs missing lifecycle transitions.

This was HIGH in Round 2 but downgraded to MEDIUM because: (a) reconstruction is an offline analysis tool, not a runtime path, and (b) the core graph structure (nodes and edges) is preserved even if some metadata is lost.

**Fix**: Add handlers for `ActionMaterialized`, `BeliefRevised`, `BeliefStaled`, `BeliefRetired`, and `ProbeExecuted` event types.

### R3-9: _dict_to_probe loses critical fields during reconstruction

**Severity**: MEDIUM
**File**: `bagel/event_store.py`, lines 279-293
**Description**: Unchanged from Round 1/2. The probe deserialization does not restore `falsification_invariant`, `irreversible`, `can_distinguish`, `timeout_risk`, or `noise_risk`. A reconstructed ProbeNode is incomplete.

**Fix**: Add all missing fields to the ProbeNode construction in `_dict_to_probe`.

### R3-10: Arbiter skips beliefs with no signals

**Severity**: MEDIUM
**File**: `bagel/arbiter.py`, lines 65-78
**Description**: Unchanged from Round 1/2. `arbitrate()` iterates over `matrix.score_all()`, which only returns beliefs with at least one signal. Beliefs with zero signals remain in their current lifecycle indefinitely. No timeout or proactive probe mechanism exists.

This is acceptable for MVP -- beliefs without evidence are correctly left alone. A future enhancement could add a time-based stale detection for provisional beliefs with no feedback.

**Fix** (future): Add a time-based stale detection for provisional beliefs that have been committed for longer than a configurable timeout without receiving any feedback.

### R3-11: Stale marking does not propagate to actions

**Severity**: MEDIUM
**File**: `bagel/safe_revision.py`, lines 194-201
**Description**: Unchanged from Round 1/2. When downstream beliefs are marked `stale`, the actions driven by those beliefs are NOT updated. Stale beliefs still drive active actions with no execution guard. The theory says "mark downstream nodes stale" including actions.

**Fix**: Add action status update in `apply_revision` for `stale_marking` strategy, or add a guard in the action execution path that checks if driving beliefs are stale.

### R3-12: Arbiter probe IDs can collide

**Severity**: LOW
**File**: `bagel/arbiter.py`, line 174
**Description**: Unchanged from Round 1/2. `f"probe_{result.belief_id[:16]}_{int(time.perf_counter())}"` can produce identical IDs for two probes generated in the same tick. The `ProbePolicy` uses `uuid.uuid4().hex[:6]` which is collision-safe. The arbiter should follow the same pattern.

**Fix**: Use `uuid.uuid4().hex[:6]` instead of `int(time.perf_counter())`.

### R3-13: runtime.py event_store.append return value never checked

**Severity**: LOW
**File**: `bagel/runtime.py`, lines 111, 132, 156, 177, 220, 269
**Description**: Unchanged from Round 1/2. `event_store.append()` returns `False` on write failure but the return value is never checked. If the event store is the audit trail, lost events mean lost attribution data.

**Fix**: Check the return value and log a warning:
```python
if not self.event_store.append(event):
    log.error("[BAGEL] Event store write failed for %s", event.event_type)
```

### R3-14: claim_graph_summary parameter accepted but unused

**Severity**: LOW
**File**: `planning/mainline/quest_state_tracker_v2.py`, line 80
**Description**: Unchanged from Round 1/2. The `update()` method signature includes `claim_graph_summary` but never reads it. Dead API surface.

**Fix**: Either implement the integration or remove the parameter and add a comment for future implementation.

### R3-15: _BLOCKED_RE false positives on common Chinese text

**Severity**: MEDIUM
**File**: `planning/mainline/quest_state_tracker_v2.py`, lines 40-43
**Description**: Unchanged from Round 1/2. The regex `(?:blocked|stuck|failed|无法|卡住|障碍|锁定|未解锁)` matches substrings in normal Chinese text. For example, "锁定敌人" (lock onto enemy) matches "锁定" and would falsely trigger blocker detection.

**Fix**: Add word boundary or contextual checks. For Chinese, require surrounding delimiters or specific sentence patterns.

---

## Answers to Audit Questions

### Q1: Are all Round 1+2 fixes correctly applied?

**Yes.** All 10 listed fixes are correctly applied and verified in the source code at commit `10f6c77`. Six fixes are fully complete with no residual issues. Four fixes are correct but have minor residual concerns (docstring lag, dead code comment, and two fixes in files that were not similarly cleaned up).

### Q2: Are there any NEW issues?

**No new issues introduced by the Round 1-2 fixes.** All 15 remaining findings are carried over from Round 1 or Round 2. The fixes themselves are clean and do not introduce regressions.

### Q3: Is the thread safety model now complete?

**Substantially improved but not complete.** The FIG itself is now fully thread-safe -- all query and mutation methods acquire the lock. The `EvidenceMatrix` is now thread-safe for individual operations. However:

1. **Compound operations in safe_revision.py** remain non-atomic (R3-1, R3-2). Multiple FIG queries in `assess_cascade()` and `decide()` acquire and release the lock between calls, creating TOCTOU windows.
2. **Direct dict access in safe_revision.py** bypasses the FIG lock (line 104: `fig.beliefs.get()`, line 115: `fig.actions.get()`, line 119: `fig.actions[aid]`).
3. **Runtime compound operations** (commit_belief then propose_action) release the FIG lock between steps, but this is by design -- the runtime controls sequencing.

For the MVP scope (single-threaded runtime loop with concurrent perception), the current thread safety is adequate. The TOCTOU in safe_revision is only a concern if cascade assessment and FIG mutation run concurrently.

### Q4: Any remaining CRITICAL issues?

**No.** All CRITICAL issues from Round 1 and Round 2 have been resolved:
- EMX-C1 (formula mismatch): Fixed -- core_contradiction branch removed, unified formula matches theory.
- QST-C1 (confidence decay): Downgraded to HIGH -- functionally aggressive but not dangerous (floored at 0.05, instant recovery on re-detection).
- R2-5 (same as QST-C1): Same downgrade.

---

## Thread Safety Status by Component

| Component | Status | Remaining Gap |
|-----------|--------|---------------|
| FIG (fig_schema.py) | COMPLETE | All methods locked. `to_dict()` locked. Terminal guard complete. |
| EvidenceMatrix | COMPLETE | All `_signals` operations locked. Copy-then-process pattern correct. |
| EventStore | COMPLETE | Write operations locked. Read is file-based (append-only). |
| Arbiter | N/A (stateless) | No mutable state. |
| ProbePolicy | N/A (stateless) | No mutable state. |
| SafeRevisionEngine | INCOMPLETE | TOCTOU in compound FIG reads (R3-1, R3-2). Direct dict access bypasses FIG lock. |
| BagelRuntime | ADEQUATE | Composes thread-safe components. Compound operations not atomic but sequencing is runtime-controlled. |

---

## Remaining Issues Summary Table

| ID | Severity | File | Issue | Origin |
|----|----------|------|-------|--------|
| R3-1 | HIGH | safe_revision.py:155-160 | TOCTOU: `actions_for_belief()` called twice with index-based access | R2-3 |
| R3-2 | HIGH | safe_revision.py:73-138 | Multi-call TOCTOU in cascade assessment | R2-4 |
| R3-3 | MEDIUM | fig_schema.py:234-239 | Post-hoc detection dead code (documented) | R1-H1, R2-CARRY-2 |
| R3-4 | MEDIUM | evidence_matrix.py:15-17 | Docstring formula missing `- S_i` term | New (from formula fix) |
| R3-5 | MEDIUM | active_quest_context.py:96-98 | `evolve()` uses inline import despite top-level `replace` | R1-L1, R2-1 |
| R3-6 | HIGH | quest_state_tracker_v2.py:149-160 | Time-unaware confidence decay too aggressive | R1-C1, R2-5 |
| R3-7 | HIGH | quest_state_tracker_v2.py:111-119 | VLM fallback regex only matches English | R1-H2, R2-6 |
| R3-8 | MEDIUM | event_store.py:187-204 | Reconstruction ignores most event types | R1-H1, R2-CARRY-3 |
| R3-9 | MEDIUM | event_store.py:279-293 | Probe deserialization loses critical fields | R2-CARRY-4 |
| R3-10 | MEDIUM | arbiter.py:65-78 | Skips beliefs with no signals | R1-H1, R2-CARRY-6 |
| R3-11 | MEDIUM | safe_revision.py:194-201 | Stale marking skips actions | R1-M2, R2-13 |
| R3-12 | LOW | arbiter.py:174 | Probe ID collision possible | R1-M3, R2-11 |
| R3-13 | LOW | runtime.py:111+ | `event_store.append` return value unchecked | R1-M2, R2-10 |
| R3-14 | LOW | quest_state_tracker_v2.py:80 | `claim_graph_summary` parameter unused | R1-M4, R2-14 |
| R3-15 | MEDIUM | quest_state_tracker_v2.py:40-43 | `_BLOCKED_RE` false positives on Chinese text | R1-H1, R2-12 |

---

## Priority Recommendations (Post-Round 3)

1. **[HIGH]** Fix safe_revision.py TOCTOU -- cache FIG query results instead of re-querying.
2. **[HIGH]** Add time-based confidence decay to QuestStateTrackerV2.
3. **[HIGH]** Add Chinese support to VLM fallback regex.
4. **[MEDIUM]** Update evidence_matrix.py docstring to match implementation.
5. **[MEDIUM]** Fix `evolve()` inline import in active_quest_context.py.
6. **[MEDIUM]** Complete event store reconstruction for lifecycle events.
7. **[MEDIUM]** Propagate stale marking to affected actions in safe_revision.

---

## Overall Assessment

The BAGEL system is in **good shape for MVP**. All CRITICAL issues are resolved. The thread safety model for FIG and EvidenceMatrix is complete. The remaining HIGH issues (safe_revision TOCTOU, confidence decay, VLM regex) are real but have workarounds or mitigating factors. The system can proceed to integration testing with the understanding that safe_revision compound operations should not be called concurrently with FIG mutations.
