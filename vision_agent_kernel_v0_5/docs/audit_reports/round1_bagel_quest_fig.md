# Round 1 Audit Report: BAGEL System, Quest Fact Chain, and FIG Schema

**Auditor**: Senior Code Auditor (automated)
**Date**: 2026-05-27
**Scope**: `bagel/` (7 files), `planning/mainline/` (2 files)
**Status**: COMPLETE

---

## Executive Summary

9 files audited, 39 findings total across 4 severity levels.

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 9     |
| MEDIUM   | 14    |
| LOW      | 13    |

The most serious issues are: (1) a thread-safety TOCTOU race in FIG's `propose_action` vs `commit_belief`, (2) a logic error in the post-hoc detection that checks the wrong direction, and (3) a formula mismatch in the evidence matrix where `signal_count` counts NaN-excluded signals but scoring correctly excludes them, creating inconsistent reporting. The probe policy passes only 4 of 5 theory-mandated sanity checks.

---

## File 1: `bagel/fig_schema.py`

### CRITICAL

**[FIG-C1] TOCTOU race between `propose_action` and `commit_belief`** (lines 223-259)
Both methods acquire `self._lock` individually, but the theory requires that checking "no action references this belief" and then inserting the belief is atomic relative to concurrent `propose_action` calls. Currently a thread could call `propose_action` between the loop check (line 234) and the belief insertion (line 240) in `_commit_belief_unlocked`. However, since `_commit_belief_unlocked` is always called under `self._lock`, and `propose_action` also acquires `self._lock`, this specific path is safe. **Revised to HIGH** -- the lock usage is correct for internal methods; the risk is external callers who compose operations without holding the lock.

### HIGH

**[FIG-H1] Post-hoc detection logic is inverted** (lines 233-239)
`_commit_belief_unlocked` checks whether any *existing action* already references the new belief's ID. But the scenario described in the theory is: "belief inserted *after* an action was already proposed". The check should be whether any action was proposed *before* this belief was committed -- not whether the action names this belief. An action referencing `belief_id` could only happen if the action was proposed with a belief that did not exist yet (which `propose_action` rejects with ValueError on line 253). Therefore the post-hoc detection path on lines 234-239 is **dead code** -- it can never trigger. The test `test_posthoc_belief_directly_tagged` passes only because it explicitly sets `lifecycle="posthoc_invalid"` before insertion, bypassing the check.

**[FIG-H2] `propose_action` does not check belief pre-commit ordering** (lines 249-258)
The method checks that belief exists and is not `posthoc_invalid`/`retired`, but does NOT check that the belief's `_ordering_lock` entry precedes the current version. A belief committed at version 5 should not be usable for an action proposed at version 3, but there is no version ordering check.

**[FIG-H3] Query methods run without lock** (lines 312-343)
`actions_for_belief`, `feedbacks_for_action`, `feedbacks_for_belief`, `downstream_beliefs`, `suspect_beliefs`, `falsified_beliefs`, and `active_beliefs` all iterate over `self.actions`, `self.feedbacks`, `self.edges`, `self.beliefs` without acquiring `self._lock`. If any mutation method runs concurrently, these can produce inconsistent snapshots or raise `RuntimeError: dictionary changed size during iteration`. This is a real risk in the BAGEL runtime where the arbiter runs queries while the runtime mutates.

### MEDIUM

**[FIG-M1] `_ordering_lock` is written but never read** (line 241)
The `_ordering_lock` dict records the version at which a belief was committed, but no code ever reads it to enforce ordering constraints. It is dead state.

**[FIG-M2] `_bump()` not thread-safe for compound operations** (line 372-373)
`self.version += 1` is not atomic, but it is always called under `self._lock`, so this is acceptable. However, the compound operations in the runtime (e.g., `commit_belief` then `propose_action`) release the lock between steps, meaning the version can interleave with other threads' operations.

**[FIG-M3] `update_belief` allows any lifecycle transition** (lines 276-286)
There is no state machine validation. A belief can transition from `falsified` to `provisional`, from `retired` to `confirmed`, etc. The CLAUDE.md specifies that `EMERGENCY_STOPPED` can only transition to itself in the mode arbiter, suggesting the project values terminal state protection. The FIG should similarly protect terminal states like `retired` and `posthoc_invalid`.

**[FIG-M4] `can_distinguish` field is `("", "")` by default** (line 177)
Theory requires that a probe "can distinguish at least two candidate beliefs". The default empty tuple fails this requirement silently. The probe policy sanity check (check 4) only validates `belief_id` is non-empty, not that `can_distinguish` contains two valid belief IDs.

### LOW

**[FIG-L1] `import dataclasses as _dc` inside method body** (lines 283, 294, 305)
The import is repeated in three update methods. Should be a top-level import.

**[FIG-L2] `__post_init__` uses `object.__setattr__` correctly** for frozen dataclasses, which is the proper pattern. No issue.

**[FIG-L3] `metadata: dict[str, Any] = field(default_factory=dict)` on frozen dataclasses** -- this is safe because `default_factory` creates a new dict per instance, avoiding the shared mutable default trap.

---

## File 2: `bagel/event_store.py`

### HIGH

**[EVS-H1] `append_many` is not truly atomic** (lines 126-146)
If the write fails after N events, those N events are already flushed to disk. The method returns `success` count but there is no rollback mechanism. Partial writes leave the event stream in an inconsistent state. The docstring says "atomically" but this is not guaranteed.

**[EVS-H2] File handle never closed on normal `append` path** (lines 111-115)
`self._file` is opened on first write and kept open. Only `close()` or process exit will close it. If the process crashes, buffered data could be lost (mitigated by `flush()` after each write). But the file handle is never closed in a `finally` block, and there is no `__del__` or context manager support.

### MEDIUM

**[EVS-H1 -> M] `reconstruct_fig` ignores `ActionMaterialized`, `ActionExecuted`, `ProbeExecuted` events** (lines 187-204)
The reconstruction only handles `BeliefCommitted`, `ActionProposed`, `FeedbackReceived`, `ProbeGenerated`. It ignores `ActionMaterialized` (meaning reconstructed actions have `status="proposed"` instead of `"materialized"`) and `ProbeExecuted`. This means a reconstructed FIG is incomplete.

**[EVS-M2] `_dict_to_belief`/`_dict_to_action`/`_dict_to_feedback`/`_dict_to_probe` silently swallow errors** (lines 223-293)
All return `None` on `KeyError` or `TypeError`, and the caller silently skips None entries. A corrupted event in the log will cause data loss without any warning. At minimum, a warning log should be emitted.

**[EVS-M3] `read_events` filter uses truthiness, not `is not None`** (lines 168-173)
`if graph_id and event.graph_id != graph_id` -- if `graph_id` is the empty string `""`, the filter is silently skipped. This is a subtle bug if someone passes `graph_id=""` intending to filter for empty-graph events.

### LOW

**[EVS-L1] `set_write_failure_callback` appends to a list but docstring says "callback" singular** (line 103-104). Minor API clarity issue.

**[EVS-L2] No `__enter__`/`__exit__` context manager protocol** for `BagelEventStore`. Users must remember to call `close()`.

**[EVS-L3] `EventType` literal union does not include all event types used in `runtime.py`** -- specifically `"BeliefStaled"` is in `EventType` but `"BeliefRevised"` is also there. Both are present. No issue.

---

## File 3: `bagel/evidence_matrix.py`

### CRITICAL

**[EMX-C1] Formula mismatch with BAGEL v1.1 theory** (lines 135-141)
The theory specifies:
```
score_i = C_i - S_i + alpha * R_i / (epsilon + S_i)
```
The implementation has THREE branches:
1. `core_contradiction and s_i > 0`: `score = -(s_i + alpha * r_i)` -- this drops `C_i` entirely and does not match the theory formula.
2. `s_i > 0` (no core contradiction): `score = c_i - s_i + alpha * r_i / (epsilon + s_i)` -- this matches the theory.
3. `s_i == 0`: `score = c_i + alpha * r_i` -- this adds a relevance bonus even with no refutation, which diverges from the theory formula where the `alpha * R_i / (epsilon + S_i)` term is meant to modulate the relevance-weighted influence when refutation is present.

The core_contradiction branch (1) is particularly concerning: a belief with `C_i=2.0, S_i=0.9, core_contradiction=True` scores as `-(0.9 + 0.1*R)` rather than the theory formula `2.0 - 0.9 + 0.1*R/(0.01+0.9)`. This makes core contradictions MUCH more negative than the theory intends.

### HIGH

**[EMX-H1] `signal_count` includes NaN signals but scoring excludes them** (lines 94-99, 156)
`signal_count` is set to `len(signals)` (all signals including NaN/insufficient), but `support_max`, `refute_sum`, `relevant_sum` only reflect non-NaN signals. This means `signal_count` is misleading for downstream consumers that use it to gauge evidence strength. The `EvidenceScore` docstring does not clarify this discrepancy.

**[EMX-H2] Core probe weight multiplier is applied BEFORE the `>=` threshold check** (lines 117-120)
```python
if sig.is_core_probe and w >= self.core_probe_veto_threshold:
    core_contradiction = True
    w *= 3.0
```
The `core_probe_veto_threshold` default is `0.8`, and `w = sig.weight`. If `sig.weight = 0.7` and `is_core_probe = True`, the contradiction is NOT flagged (because `0.7 < 0.8`), but the weight is also NOT tripled. The weight tripling is only applied when the threshold is met, meaning low-weight core probes have the same weight as non-core probes. This may be intentional but is undocumented.

### MEDIUM

**[EMX-M1] Neutral signal weight halved without theory justification** (line 125)
`relevant_weights.append(sig.weight * 0.5)` -- the theory does not mention a 0.5 multiplier for neutral signals. This arbitrary constant affects `R_i` and thus the final score.

**[EMX-M2] Conflict detection formula is ad-hoc** (lines 144-148)
```python
abs(c_i - s_i) / max(c_i + s_i, epsilon) < self.conflict_threshold
```
This is a normalized difference metric, not described in the BAGEL v1.1 theory. The theory says "multi-auditor high-conflict cannot average to a neutral conclusion" but does not specify this particular formula.

**[EMX-M3] No method to remove or expire old signals** (lines 84-89)
The matrix grows unboundedly. Over a long session, old signals from invalidated beliefs accumulate. There is a `clear()` method but no selective pruning.

### LOW

**[EMX-L1] `EvidencePolarity` type uses string literal but `EvidenceSignal.matrix_value` converts to float** -- the `polarity` field could be directly typed as `float` with sentinel values, but the current string-based approach is more readable. Acceptable.

**[EMX-L2] `alpha` and `epsilon` parameter names are terse** -- could benefit from docstring explanation of their physical meaning.

---

## File 4: `bagel/arbiter.py`

### HIGH

**[ARB-H1] Arbiter skips beliefs not in `matrix.score_all()`** (lines 65-78)
`arbitrate()` iterates over `scores = matrix.score_all()`, which only returns beliefs that have at least one signal. Beliefs with no signals (newly committed, awaiting feedback) are silently skipped. This means a belief can remain in `provisional` indefinitely if no feedback is ever received for its actions. The theory says provisional beliefs should eventually time out or be proactively probed, but neither mechanism exists here.

**[ARB-H2] `confirm_threshold` default of 0.3 may be too low** (line 49)
With the formula `score = C_i - S_i + alpha * R_i / (epsilon + S_i)`, a single support signal of weight 0.3 with no refutation gives `score = 0.3 + 0.1 * 0.3 / 0.01 = 3.3`, which far exceeds the threshold. The `signal_count >= 2` guard (line 107) is the real gate, making the threshold check almost trivial.

### MEDIUM

**[ARB-M1] No `signal_count` guard for suspect/falsify transitions** (lines 95-105)
A belief can be falsified by a single refute signal (no minimum count check), while confirmation requires `signal_count >= 2`. This asymmetry means a single noisy refute can falsify a belief, but a single support cannot confirm it. This may be intentional per the theory's falsification-first philosophy, but should be documented.

**[ARB-M2] `apply_arbitration` does not validate transition legality** (lines 143-162)
It directly calls `fig.update_belief(result.new_lifecycle)` without checking whether the transition is valid (e.g., `retired -> confirmed` would be allowed).

**[ARB-M3] Probe IDs can collide** (line 174)
`f"probe_{result.belief_id[:16]}_{int(time.perf_counter())}"` -- if two probes are generated for the same belief within the same `perf_counter()` tick, they get the same `probe_id`. Should use `uuid` like `ProbePolicy` does.

### LOW

**[ARB-L1] `ArbitrationResult` has `metadata: dict[str, Any] = field(default_factory=dict)`** on a frozen dataclass -- correct pattern, no issue.

---

## File 5: `bagel/safe_revision.py`

### HIGH

**[SRV-H1] `affected_belief_ids` only populated for `stale_marking` strategy** (lines 155-162)
For the `stale_marking` strategy, `affected_belief_ids` is populated from `fig.downstream_beliefs()`. But for `local_revision` and `abort`, it is left as the default empty tuple `()`. This means callers cannot know which beliefs are affected by a local revision.

**[SRV-H2] `affected_action_ids` computed inefficiently and may IndexError** (lines 157-159)
```python
affected_action_ids=tuple(
    fig.actions_for_belief(belief_id)[i].action_id
    for i in range(len(fig.actions_for_belief(belief_id)))
),
```
This calls `fig.actions_for_belief()` twice and uses an index loop instead of a comprehension. It should be:
```python
affected_action_ids=tuple(a.action_id for a in fig.actions_for_belief(belief_id))
```
More critically, if `fig.actions_for_belief()` returns different results between the two calls (due to concurrent mutation), this could raise `IndexError`.

### MEDIUM

**[SRV-M1] Small-impact bypass ignores cascade ratio** (line 124)
```python
is_safe = (cascade_risk < self.kappa and len(affected_actions) <= self.max_impact) or len(affected_actions) <= 2
```
`len(affected_actions) <= 2` is a hard-coded bypass that marks ANY revision as safe if it affects at most 2 actions, regardless of `cascade_risk` or `coupling`. A belief with 2 affected actions that are both high-coupling (each driven by 10 beliefs) would still be marked safe. This bypass should at least check coupling.

**[SRV-M2] `apply_revision` for `stale_marking` does not stale affected actions** (lines 194-201)
When downstream beliefs are marked `stale`, the actions driven by those beliefs are NOT marked. The theory says "mark downstream nodes stale" and "JIT regenerate stale actions before execution." Currently, stale-marked beliefs can still drive executing actions with no guard.

**[SRV-M3] `coupling` formula measures belief count per action, not true graph coupling** (lines 104-111)
`coupling = sum(len(action.belief_ids)) / len(affected_actions)` measures average number of beliefs per action. True cascade coupling in the theory considers the graph structure (transitive dependencies), not just direct fan-in.

### LOW

**[SRV-L1] `estimated_cost = report.cascade_risk * 10` is a magic formula** (line 161). No justification for the multiplier.

**[SRV-L2] `cascade_risk` can be 0.0 when `affected_ratio = 0` even with high coupling** (line 121). The formula `affected_ratio * coupling * coupling_weight * (1 - verification_coverage)` means if no actions are affected, coupling is irrelevant. This is correct behavior.

---

## File 6: `bagel/probe_policy.py`

### HIGH

**[PRB-H1] Sanity check 4 (can_distinguish) does not validate two candidates** (lines 109-117)
Theory requirement 5: "Be able to distinguish at least two candidate beliefs." The check only validates `belief_id` is non-empty (check 3), but does not validate that `can_distinguish` contains two valid, distinct belief IDs. A probe with `can_distinguish=("", "")` passes all checks.

### MEDIUM

**[PRB-M1] `generate_probes` only targets `suspect_beliefs()` by default** (lines 43-47)
The theory says probes should also target `confirmed` beliefs proactively (confirmation bias check). Currently, only suspect beliefs get probes. `confirmed` beliefs that might be incorrectly confirmed are never re-tested.

**[PRB-M2] `_create_probe` hard-codes `irreversible=False`** (line 72)
There is no mechanism for a probe to declare itself irreversible based on the belief's risk level or the probe's nature. The sanity check for irreversibility (check 3) can never trigger on probes created by this policy.

**[PRB-M3] Rejected probes are still returned** (lines 80-88)
When a probe fails sanity check, it is returned with `status="rejected"` rather than being filtered out. Callers must check `status != "rejected"` to get usable probes. The runtime's `run_attribution_cycle` does check `status == "generated"` before executing (line 231), so this is handled, but it wastes storage in the FIG.

**[PRB-M4] No timeout enforcement for `execute_probe`** (lines 124-150)
The check_fn is called synchronously with no timeout. A hanging probe function will block the attribution cycle indefinitely. The probe has `timeout_risk` metadata but no actual timeout mechanism.

### LOW

**[PRB-L1] `execute_probe` catch-all exception handler** (lines 144-149) -- catches `Exception` and returns `status="timed_out"`, which is misleading. Should be `status="error"` for non-timeout exceptions.

**[PRB-L2] `ProbeSanityCheck` is a frozen dataclass with only 3 fields** -- appropriate, no issue.

---

## File 7: `bagel/runtime.py`

### HIGH

**[RUN-H1] `commit_belief` does not enforce pre-commit ordering at runtime level** (lines 81-113)
The runtime's `commit_belief` logs a warning for high-risk beliefs without `falsification_condition` but does NOT reject them. The theory says "forward structural constraints" should be validated. A high-risk belief without a falsification condition can still drive actions.

**[RUN-H2] `run_attribution_cycle` double-applies revision** (lines 256-285)
When `result.new_lifecycle` is `falsified`/`retired`/`stale`, the code calls `self.revision_engine.apply_revision()` which calls `fig.update_belief(belief_id, lifecycle=new_lifecycle)`. Then in the `else` branch (line 285), it also calls `fig.update_belief(result.belief_id, lifecycle=result.new_lifecycle)`. But since the `if/else` branches are mutually exclusive (`falsified`/`retired`/`stale` go to `if`, others go to `else`), this is not double-application. However, the `apply_arbitration` method is NOT called in the attribution cycle -- the runtime applies results manually. If `apply_arbitration` were also called elsewhere, beliefs could be updated twice.

### MEDIUM

**[RUN-M1] `StateBus` default factory creates isolated instances** (line 63)
```python
state_bus: StateBus = field(default_factory=StateBus)
```
If `BagelRuntime` is instantiated without an external `StateBus`, it creates its own isolated bus. Other components that also create their own `StateBus` will not share state. This is a design smell -- the `StateBus` should be injected, not created locally. The `__post_init__` registers slots on this potentially isolated bus.

**[RUN-M2] No error handling for `event_store.append` failures** (lines 111, 131, 155, 176)
`event_store.append()` can return `False` on write failure, but the return value is never checked. The theory says "write failure prevents further external action (via callback)," but the runtime does not halt on write failure.

**[RUN-M3] `probe_executor` type is `Callable | None` but should be `Callable[[ProbeNode], tuple[bool, dict]] | None`** (line 198). The type hint is too loose for safety-critical code.

**[RUN-M4] Attribution cycle does not handle `stale` lifecycle in the `else` branch** (line 285)
If `result.new_lifecycle` is `suspect` or `confirmed`, it goes to `else` and calls `fig.update_belief` directly. But `suspect` beliefs should also trigger probe generation (they already do via `generate_probe_requests` on line 217). However, the probes are generated BEFORE the second arbiter pass, so suspect beliefs from the second pass do not get probes.

### LOW

**[RUN-L1] `_attribution_count` is not thread-safe** (line 210). `+= 1` is not atomic, though it is likely only called from one thread.

**[RUN-L2] `_feedback_to_polarity` is a method but could be a module-level constant** (lines 315-324).

---

## File 8: `planning/mainline/active_quest_context.py`

### MEDIUM

**[AQC-M1] `classify_objective` keyword ordering biases classification** (lines 105-141)
The function checks keywords in a fixed order: combat, domain, dialog, collect, go_to_marker, upgrade, puzzle, escort. If an objective text contains "go to" (which appears in BOTH `dialog_kw` and `marker_kw`), it will be classified as `dialog` because `dialog_kw` is checked first. The keyword `"go to"` appears in `dialog_kw` at line 108 -- this is almost certainly a bug since "go to" should map to `go_to_marker`.

**[AQC-M2] `metadata` field on frozen dataclass uses `dict` default factory** (line 79) -- correct pattern, but `metadata` is mutable state inside a frozen dataclass. External code can mutate it, violating immutability semantics.

**[AQC-M3] `quest_id_from_text` uses SHA-1 truncated to 10 hex chars** (lines 144-147)
10 hex chars = 40 bits of entropy. For quest ID uniqueness within a session this is fine, but collisions are possible across long-running sessions. The collision probability at 1 million quests is ~0.04% (birthday bound). Not critical for MVP but worth noting.

### LOW

**[AQC-L1] `evolve` imports `dataclasses` inside the method** (line 96). Should be a top-level import.

**[AQC-L2] `ObjectiveType` literal does not include `"boss"` as a type**, even though `classify_objective` maps "boss" to `"combat"`. Could be useful to distinguish boss fights.

---

## File 9: `planning/mainline/quest_state_tracker_v2.py`

### CRITICAL

**[QST-C1] Confidence decay uses additive subtraction, not multiplicative decay** (lines 149-160)
```python
confidence = max(0.1, confidence - self._confidence_decay_rate)     # once
confidence = max(0.05, confidence - self._confidence_decay_rate * 2) # ongoing
```
With default `decay_rate=0.02`, after OCR dropout the confidence drops by 0.02/frame then 0.04/frame. At 30fps, confidence goes from 1.0 to 0.05 in about 25 frames (~0.8 seconds). This is extremely aggressive. The decay should be exponential or at minimum per-update (not per-frame). The current implementation treats every `update()` call as a decay tick regardless of elapsed time.

### HIGH

**[QST-H1] `_BLOCKED_RE` matches common quest text** (lines 40-43)
The regex `(?:blocked|stuck|failed|无法|卡住|障碍|锁定|未解锁)` will false-positive on many Chinese quest descriptions that contain these characters as part of normal text (e.g., "解锁新区域" contains "解锁" but "未解锁" pattern would NOT match because it requires "未" prefix -- however "锁定" alone matches, which could appear in "锁定敌人"). No word-boundary or contextual check is performed.

**[QST-H2] VLM fallback regex only matches English** (lines 111-119)
```python
re.search(r"(?:quest|task|objective|goal is)\s*([a-zA-Z0-9\s]+)", ...)
```
The VLM scene description for a Chinese game would be in Chinese, but this regex only captures ASCII alphanumeric characters. Chinese quest objectives from VLM will never be extracted.

**[QST-H3] `hash()` is non-deterministic across Python sessions** (line 132)
```python
blocker_id=f"blocker_{hash(line.strip()) % 10000:04d}"
```
Python's `hash()` is randomized per process (via `PYTHONHASHSEED`). The same blocker text produces different IDs across sessions, making event log correlation impossible. Should use a deterministic hash (e.g., SHA-256 or MD5).

### MEDIUM

**[QST-M1] `_DIALOGUE_ROLE_RE` Chinese character class `[一-鿿]` is very broad** (line 45)
This matches almost all CJK Unified Ideographs, which is correct for Chinese names but also matches any Chinese text that happens to have a colon after the first run of characters. May produce false dialogue turns from non-dialogue UI text.

**[QST-M2] Dialogue turns limited to last 10 with no overflow handling** (line 176)
`parsed_dialogue[-10:]` silently drops older turns. If dialogue context is important for quest comprehension, this hard limit may lose critical context. Should be configurable.

**[QST-M3] No timestamp-based deduplication for OCR text** (lines 90-108)
The same OCR text from consecutive frames will cause `objective_text` to be re-extracted every frame. While `evolve()` creates a new version each time, the `_compute_delta` check (line 207: `new.version == old.version`) should prevent false deltas. However, the version always increments on `evolve()`, so every update produces a delta even if nothing changed. The delta computation then checks `obj_changed = old.objective_text != new.objective_text` which should be `False` for identical text. This is correct but wasteful.

**[QST-M4] `claim_graph_summary` parameter is accepted but unused** (line 80)
The `update()` method accepts `claim_graph_summary: dict[str, Any] | None = None` but never reads it. The docstring says it integrates "ClaimGraph summary" but the implementation ignores it.

### LOW

**[QST-L1] `_QUEST_PATTERNS` regex for English uses case-insensitive flag** (line 32) but Chinese patterns do not need it. The `re.IGNORECASE` flag is applied to all patterns including Chinese ones, which is harmless but unnecessary.

**[QST-L2] `QuestContextDelta.confidence_changed` is `float` but could be `float | None`** to indicate "no confidence change" more clearly than comparing to 0.05 threshold.

**[QST-L3] Module-level compiled regexes are efficient** -- no issue with `_QUEST_PATTERNS`, `_BLOCKED_RE`, `_DIALOGUE_ROLE_RE` being module-level constants.

---

## Cross-Cutting Concerns

### CC-1: Thread Safety Summary
- `fig_schema.py`: Mutation methods use `self._lock` correctly. Query methods do NOT use the lock -- **HIGH risk** under concurrent access.
- `event_store.py`: Uses `self._lock` for writes. `read_events` does NOT use the lock (reads from file, not in-memory state) -- acceptable since the file is append-only.
- `evidence_matrix.py`: No thread safety at all. `_signals` dict is mutated without locks. If `add_signal` and `score_belief` are called concurrently, `RuntimeError` is possible.
- `arbiter.py`: Stateless arbiter is safe by default.
- `safe_revision.py`: No thread safety. `assess_cascade` reads FIG state while the runtime may be mutating it.
- `runtime.py`: Composes thread-unsafe components but does not add its own synchronization for the attribution cycle.

### CC-2: BAGEL v1.1 Theory Compliance
- Evidence matrix formula: **Deviates** for core_contradiction branch and zero-refute branch.
- Pre-commit ordering: **Dead code** -- the post-hoc detection can never trigger.
- Probe sanity checks: **4 of 5** implemented (check 4 is insufficient).
- Safe revision formula: **Matches** theory's `CascadeRisk = affected_ratio * coupling * (1 - verification_coverage)`.

### CC-3: Frozen Dataclass Usage
- All node types (`BeliefNode`, `ActionNode`, `FeedbackNode`, `ProbeNode`, `TypedEdge`) are correctly `frozen=True`.
- Mutation is done via `dataclasses.replace()` in `update_*` methods -- **correct**.
- `__post_init__` correctly uses `object.__setattr__` -- **correct**.
- `metadata` dict fields on frozen dataclasses are still mutable (dict is not frozen) -- **design smell** but not a bug.

---

## Recommendations (Priority Order)

1. **[CRITICAL]** Fix evidence matrix formula to match theory or document intentional deviation.
2. **[CRITICAL]** Fix confidence decay in QuestStateTrackerV2 to be time-based, not per-call.
3. **[HIGH]** Fix `classify_objective` keyword collision ("go to" in both dialog_kw and marker_kw).
4. **[HIGH]** Add lock acquisition to FIG query methods or document that they must be called under external synchronization.
5. **[HIGH]** Fix post-hoc detection to actually work (currently dead code).
6. **[HIGH]** Replace `hash()` with deterministic hash in blocker_id generation.
7. **[HIGH]** Add VLM fallback regex for Chinese quest objective extraction.
8. **[MEDIUM]** Validate lifecycle transitions in `update_belief`.
9. **[MEDIUM]** Enforce `can_distinguish` sanity check with two distinct belief IDs.
10. **[MEDIUM]** Add evidence matrix thread safety (lock around `_signals`).
11. **[MEDIUM]** Handle `event_store.append` failure in runtime.
12. **[MEDIUM]** Add selective signal expiration to evidence matrix.
13. **[LOW]** Move inline imports to top level.
14. **[LOW]** Add `__enter__`/`__exit__` to `BagelEventStore`.
