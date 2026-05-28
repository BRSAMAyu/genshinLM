# Long-Horizon Skill Learning & Evolution Audit

**Scope**: Skill OS, Induction Pipeline, Evolution Engine, Decision Memory, Failure Analyzer
**Date**: 2026-05-28
**Auditor**: Automated audit of skill reliability decay, Wilson confidence gaming, motor tier isolation,
induction contamination, repair loops, BAGEL probe policy, and cross-session persistence.

---

## Finding: No Skill Demotion Pathway -- Promoted Skills Never Decay (SEVERITY: CRITICAL)

**What is wrong**: The promotion ladder in `skills/promotion.py` provides a one-way ratchet:
`raw_trace -> draft -> experimental -> candidate -> stable -> trusted`. There is no `demote_to()`,
no tier decrement, and no reliability decay mechanism anywhere in the codebase. The `can_promote_to()`
function (line 47) only checks `target_idx > current_idx` and explicitly rejects `target_idx <= current_idx`.

The `ThreeLayerReliabilityStore` in `reliability/reliability_store.py` has a `mark_version_drift()` method
that adds a skill to `_drift_demoted_skills` and halves its `skill_trust` via `execution_trust()` (line 489).
However, this is only a runtime penalty -- it never actually lowers the skill's `tier` field in the
`SkillRegistry`. The `DriftDetector` in `reliability/drift_detector.py` can detect environmental drift
and recommend `"invalidate_and_bootstrap"`, but nothing consumes this recommendation to trigger demotion.

**Why it matters for long sessions**: After a game patches and changes UI layout, a `trusted` skill
that relied on old anchor positions will fail every time. The skill remains `trusted` in the registry,
continues to be returned by `find_by_tier(min_tier="candidate")` and `find_applicable()`, and will be
repeatedly selected for execution despite 100% failure rate. The drift penalty (halving trust) is
insufficient because (a) it requires external code to call `mark_version_drift()`, and (b) the
`find_applicable()` method in `registry.py` does not check execution trust at all.

**Concrete scenario**: A Genshin Impact 5.x patch moves the "claim expedition rewards" button. Skill
`induced_claim_expedition_a3f2b1` was promoted to `stable` with 50/50 success/failure. After the patch,
it fails 100% of the time. The agent keeps selecting it because `tier == "stable"` passes the
`find_applicable` tier filter. No code path exists to demote it back to `experimental` or `raw_trace`.

**Suggested fix**:
1. Add a `demote_to(target_tier)` function in `skills/promotion.py` that creates a new `SkillDef`
   with lowered tier.
2. Wire `DriftDetector` output to an automatic demotion trigger: if a skill at `stable` or `trusted`
   accumulates N consecutive failures within a time window, demote it one tier.
3. Add a `consecutive_failures` counter in `SkillDef.metadata` that resets on success.
4. Make `find_applicable()` optionally filter by runtime execution trust, not just static tier.

---

## Finding: Wilson Confidence Can Be Permanently Locked by Historical Success (SEVERITY: CRITICAL)

**What is wrong**: The Wilson lower bound in `skills/promotion.py` (line 118) computes confidence over
cumulative `successes` and `failures`. However, the promotion gate at line 96 reads `success_count`
from `skill.metadata.get("execution_stats", {})`, and the caller in `InductionPipeline.process_session()`
at `pipeline.py` line 76-77 passes `successes=0, failures=0` as defaults to `try_promote()` for every
tier transition. This means:

1. For `candidate -> stable` promotion, the `meets_wilson_threshold()` check uses the caller-provided
   `successes/failures`, which default to 0/0. Wilson(0,0) returns 0.0, so the check fails -- but this
   is checked against `skill.metadata["execution_stats"]["success_count"]` on line 97, creating an
   inconsistency between where the data lives and how it is consumed.
2. More critically, even if execution stats are properly tracked, the Wilson interval has no recency
   weighting. A skill with 100 successes and 2 failures has `wilson_lower_bound(100, 2) = 0.926`.
   If the next 20 executions all fail, the score drops to `wilson_lower_bound(100, 22) = 0.764`,
   which still exceeds the 0.70 threshold. The skill remains above the gate even though it has been
   failing for 20 consecutive runs.

**Why it matters for long sessions**: Over multi-hour sessions with hundreds of executions, a skill's
early success history creates a massive confidence buffer that masks ongoing failure. A game meta shift
mid-session can render a skill useless, but it takes an impractical number of failures to bring the
Wilson score below threshold. The agent continues trusting and executing a broken skill.

**Concrete scenario**: A combat rotation skill "burst_dps_pyro" was used 200 times successfully in
session 1 (Wilson LB = 0.95). In session 2, the game nerfs the rotation and it fails 30 times in a
row. Wilson LB drops to `wilson_lower_bound(200, 30) = 0.828`. Still well above 0.70 threshold.
The agent keeps selecting this skill over alternatives that actually work.

**Suggested fix**:
1. Use a sliding window or exponentially weighted window for success/failure counts (e.g., last N
   executions, or EWMA decay with half-life of 50 executions).
2. Add a "consecutive failure circuit breaker": if N consecutive failures (e.g., N=5), immediately
   demote regardless of Wilson score.
3. In `InductionPipeline.process_session()`, propagate actual execution stats from the registry
   rather than defaulting to 0/0.

---

## Finding: EvolutionEngine Repair Loops Have No Bound (SEVERITY: HIGH)

**What is wrong**: The `EvolutionEngine` in `learning/evolution_engine.py` processes failures through
`handle_failure()` (line 104), which runs synchronously inside the `_drain_failures` worker thread
(line 96). There is no limit on how many repair sessions can be created for the same skill. The
`_repair_sessions` dict (line 61) grows unboundedly except for the `_compact()` method (line 302)
which only prunes sessions with empty `_events` lists and caps `_patch_drafts` at 50 and
`_approved_patches` at 100.

More critically, if a skill keeps failing, `handle_failure()` will be called repeatedly for the same
skill, creating a new `RepairSession` and `SkillPatchDraft` each time. There is no deduplication or
cooldown. The repair pipeline:
1. Builds a `FailureSignature`
2. Creates a `RepairSession`
3. Auto-seeds demonstration with `SkillPatchSuggester.suggest()` (which always returns
   `["add_timeout_recovery"]` as the default patch)
4. Validates in sandbox (which for `induced_*` skills always returns True -- see Finding #4)
5. Writes patch to disk

This means for every failure event, a new patch file is written to `data/skill_patches/`. If a motor
skill fails at 10 Hz (e.g., target lost during fast tracking), the engine generates 10 patch files
per second, each with a unique `RepairSession`, all for the same root cause.

**Why it matters for long sessions**: In a 30-minute play session, a consistently failing skill can
generate thousands of repair sessions and patch files. The `_failure_queue` (line 68) buffers all
incoming failures, so the worker thread will never catch up. Memory grows linearly with failures.
Disk I/O becomes a bottleneck.

**Concrete scenario**: A navigation skill fails every 3 seconds due to a map change. Over 30 minutes,
that is 600 failure events. Each generates a RepairSession, a SkillPatchDraft, a legacy patch dict,
disk writes, and potentially sandbox subprocess invocations. The `_failure_queue` grows, the repair
worker falls behind, and the system runs out of memory or disk space.

**Suggested fix**:
1. Add a per-skill cooldown: after handling a failure for skill X, ignore further failures for
   X for N seconds (e.g., 60s).
2. Cap `_repair_sessions` to a maximum size (e.g., 100) and reject new sessions when full.
3. Add a per-skill failure rate limiter: if skill X has generated more than M repair sessions
   in the last hour, mark it as "repair-exhausted" and stop attempting repairs.
4. Deduplicate: before creating a new repair session, check if an open one exists for the same
   skill + failure_code combination.

---

## Finding: Induced Skills Auto-Pass Sandbox Verification (SEVERITY: HIGH)

**What is wrong**: In `evolution_engine.py` line 337-338, the `_verify_in_sandbox()` method has
a special case:

```python
if skill_id.startswith("induced_"):
    patch["replay_result"] = {"passed": True, "skipped": "induced_skill_no_pytest"}
    return True
```

This means ANY skill whose ID starts with `induced_` automatically passes sandbox verification,
regardless of whether the patch is correct. Since `AnchorBinder.bind()` creates skills with IDs
like `induced_{goal[:20]}_{uuid}` (line 63 of `anchor_binder.py`), ALL induced skills bypass
the sandbox check.

The `SkillInductionGate` in `skill_induction_gate.py` line 133 also calls
`self._engine.verify_in_sandbox(patch_record)` and trusts the result. Since the patch record's
`skill_id` is the goal string (not starting with `induced_`), this particular call does not
auto-pass. However, the `RepairValidator` itself only checks structural properties of proposed
steps (that they have valid `action_type` strings), not semantic correctness.

**Why it matters for long sessions**: The sandbox bypass means the evolution engine's repair
pipeline has no real quality gate for induced skills. Bad patches that change step ordering,
introduce wrong anchors, or have incorrect wait conditions will be marked as `SANDBOX_VALIDATED`
and potentially `APPROVED`. Over time, the skill corpus accumulates low-quality or actively
harmful patches that have been "verified" by an empty check.

**Concrete scenario**: An induced skill `induced_open_character_menu_abc123` has a step that clicks
the wrong anchor. The evolution engine creates a patch that adds a `wait` step. The patch passes
sandbox verification automatically because the skill_id starts with `induced_`. The patch is approved
and the "improved" skill still fails in production, but now there is a validated patch record
claiming it works.

**Suggested fix**:
1. Remove the `induced_*` bypass entirely. If induced skills have no pytest markers, implement
   a structural validation (verify steps reference known anchors, wait conditions are bounded, etc.)
   rather than auto-passing.
2. Add an `AnchorBinder.validate()` step that checks induced skill steps against the current
   anchor registry before allowing promotion.
3. Make `RepairValidator.validate_dry_run()` actually execute steps in a simulation or mock
   environment rather than just checking field types.

---

## Finding: DecisionMemory Prunes by Age Only, Losing Rare but Critical Decisions (SEVERITY: HIGH)

**What is wrong**: `DecisionMemory.prune()` in `decision_memory.py` line 198-203 deletes all
records older than `max_age_days` (default 30). The only pruning key is `created_at` timestamp.
There is no consideration for:
- Whether the decision is the ONLY successful strategy for a given goal+screen_state combination
- The confidence score of the record
- Whether the strategy has been recently queried (access frequency)
- The rarity of the goal (some goals may only be achieved once per month)

The `best_strategy_for()` method (line 149) returns the highest-confidence successful strategy,
but if that strategy was pruned, it returns `None` with no indication that a previously-known
strategy was discarded.

**Why it matters for long sessions**: Rare but critical strategies (e.g., "how to navigate the
Abyss floor 12 chamber 3") may only be executed once every 2-3 weeks. After 30 days, the successful
strategy is pruned, and the agent must re-learn it from scratch. For episodic content that appears
infrequently, the agent never accumulates lasting knowledge.

**Concrete scenario**: The agent learns a successful strategy for "claim_daily_commission_reward"
which is a daily task. Over 30 days, it records 30 successful strategies. On day 31, the prune
removes day 1's record. This is fine. But consider "complete_spiral_abyss_floor_12" -- the agent
completes this once every two weeks. The first successful strategy is pruned before the second
attempt. The agent must re-explore and potentially fail multiple times before re-learning what
it already knew.

**Suggested fix**:
1. Add a "keep at least N per goal+capsule_id" rule: always retain the top-K (e.g., K=3) highest
   confidence strategies for each unique goal, regardless of age.
2. Track access frequency: if `best_strategy_for()` returns a strategy, update its "last_queried"
   timestamp. Prune least-recently-used strategies first.
3. Add an importance score based on goal rarity (inverse frequency of goal in the database).
4. Consider an archive table instead of deletion, so strategies can be recovered.

---

## Finding: AnchorBinder Produces Skills with No Timing Awareness (SEVERITY: HIGH)

**What is wrong**: `AnchorBinder.bind()` in `anchor_binder.py` creates `SkillStep` objects with
hardcoded `timeout_ms=5000` for every step (line 44). It discards all timing information from the
original `RecordedAction` objects. The `RecordedAction` dataclass has a `timestamp` field, but
`AnchorBinder` never uses it to compute inter-step delays, action durations, or timing patterns.

For motor-tier skills specifically, timing is critical. A combat rotation that requires "press E,
wait 200ms, press Q, wait 100ms, left-click" will be converted to steps that all have 5000ms
timeouts with no inter-step delays. When replayed, the steps execute as fast as possible, which
may trigger animation locks, input queuing issues, or miss timing windows.

Furthermore, the `SkillStep` schema has a `wait_until` field (a condition string to wait for
before proceeding), but `AnchorBinder` never populates it -- it is always set to `""` (line 47).

**Why it matters for long sessions**: Over extended play, motor skills that lack proper timing
will fail intermittently. The failure analyzer (`GenshinFailureAnalyzer`) will categorize these
as `SKILL_MISS` or `COMBAT_TIMEOUT`, but the repair pipeline cannot fix them because it does not
have access to the original timing information. Each "repair" creates a new patch with the same
timing deficiency, leading to an infinite repair loop for motor skills.

**Concrete scenario**: An induced motor skill for "dash-cancel normal attack" requires pressing
attack, waiting 180ms, pressing dash, waiting 50ms, pressing attack again. The induced skill has
three steps with no inter-step delays. On replay, all three inputs fire within 10ms. The game
queues them incorrectly, the dash does not cancel the attack animation, and the rotation fails.
The evolution engine creates a patch (adds `add_timeout_recovery`), but this does not fix the
timing issue.

**Suggested fix**:
1. Compute inter-step delays from `RecordedAction.timestamp` deltas and store them in
   `SkillStep.params["delay_ms"]`.
2. For motor-tier skills, require timing calibration: record the same action sequence multiple
   times and use the median timing, not a single observation.
3. Add a `wait_until` heuristic: if a screen state change follows a step, set `wait_until` to
   the expected state transition.
4. Differentiate motor-tier skill schemas from UI-tier: motor skills need sub-100ms timing
   precision, while UI skills can use 5000ms timeouts.

---

## Finding: Concurrent Induction and Execution with No Isolation (SEVERITY: HIGH)

**What is wrong**: The `SkillRegistry` in `skills/registry.py` uses a `threading.Lock()` for
thread safety on individual operations (`register`, `get`, `find_applicable`, etc.). However,
the `InductionPipeline.process_session()` at `pipeline.py` lines 76-84 performs a read-modify-write
sequence across multiple lock acquisitions:

```python
promo = self.gate.try_promote(current, next_tier)   # acquires lock inside
promoted = self.registry.get(current.skill_id)        # acquires lock again
current = promoted if promoted is not None else current
```

Between `try_promote()` writing the promoted skill and `registry.get()` reading it back, another
thread could call `registry.register()` with a different version of the same skill (e.g., from a
concurrent induction or an evolution engine patch). The promotion pipeline would then operate on
a stale skill definition.

Similarly, the `EvolutionEngine._drain_failures()` worker thread calls `handle_failure()` which
modifies `_repair_sessions`, `_skill_patch_drafts`, `_patch_drafts`, and writes to disk -- all
under `self._lock`. But the `approve_patch()` method also modifies these same collections under
`self._lock`. If the failure worker is processing a failure for skill X while the main thread
approves a patch for skill X, the collections can become inconsistent.

**Why it matters for long sessions**: In production, the induction pipeline and evolution engine
run concurrently with skill execution. Over long sessions, the probability of a race condition
increases. A skill could be promoted to `stable` while simultaneously being patched by the
evolution engine, resulting in a `stable` skill with unverified patches.

**Concrete scenario**: Thread A (induction) promotes skill X from `experimental` to `candidate`.
Thread B (evolution) simultaneously creates a patch for skill X based on the `experimental` version.
The patch is approved and written as a new version, but the registry still holds the `candidate`
version. The next execution picks the `candidate` version (no patch applied) and fails for the
same reason the evolution engine already identified.

**Suggested fix**:
1. Use a single transaction-like pattern for promotion: acquire the registry lock once, read the
   current skill, check promotion conditions, write the promoted skill, and release.
2. Add optimistic concurrency: include a `version` field in `SkillDef` and reject promotions if
   the version has changed since reading.
3. Serialize induction and evolution through a single-threaded executor rather than allowing
   concurrent modification.

---

## Finding: BAGEL Probe Policy is Decorative -- Never Consumed (SEVERITY: MEDIUM)

**What is wrong**: The `SkillBagelProbePolicy` dataclass in `skills/schema.py` (lines 97-100)
defines `probe_family`, `max_non_decidable`, and `tie_breaker_required` fields. These are
serialized and deserialized in `to_dict()`/`from_dict()`. However, no code in the entire codebase
reads these fields to make any decision. The probe policy is defined, stored, and never used.

A search of the codebase for `bagel_probe_policy`, `max_non_decidable`, or `tie_breaker_required`
shows they only appear in `schema.py` (definition, serialization, deserialization) and in tests
that verify the schema round-trips correctly. No executor, no reliability gate, no applicability
matcher reads the probe policy.

**Why it matters for long sessions**: The BAGEL probe policy was designed to prevent skills from
being promoted based on non-decidable probe results (where the BAGEL verifier cannot confirm or
deny the skill's effect). Without enforcement, skills can accumulate "verified" status from
non-decidable probes, inflating their reliability scores. Over time, the Wilson lower bound
becomes meaningless because it incorporates these non-informative confirmations.

**Concrete scenario**: A skill for "scroll down in character menu" produces a
`SkillProducedClaim` with `verifier_recipe="screen_state_stable.default"`. The BAGEL probe
runs this recipe, which checks if the screen state is stable. After scrolling, the screen is
stable (because scrolling completed), so the probe says "verified" -- but it did not verify
that the correct content is now visible. The probe is non-decidable for the skill's actual
intent. Without `max_non_decidable` enforcement, this skill accumulates verified counts and
gets promoted to `stable` despite never being truly validated.

**Suggested fix**:
1. Implement the BAGEL probe consumption in `SkillReliabilityGate` or `PromotionGate`:
   when evaluating a skill for promotion, check how many of its verified counts came from
   non-decidable probes. If `non_decidable_count > max_non_decidable`, block promotion.
2. Add a `probe_result` field to execution stats: `{"decidable": N, "non_decidable": M}`.
3. Require at least one decidable probe verification before promotion past `experimental`.

---

## Finding: GenshinFailureAnalyzer Clears All Patterns on Every New Failure (SEVERITY: MEDIUM)

**What is wrong**: In `genshin_failure_analyzer.py` line 76, `record_failure()` calls
`self._patterns.clear()` after appending every single failure:

```python
def record_failure(self, signature: GameFailureSignature) -> None:
    self._failures.append(signature)
    if len(self._failures) > self._MAX_FAILURES:
        self._failures = self._failures[-self._MAX_FAILURES:]
    self._patterns.clear()
```

This means `analyze_patterns()` (line 79) re-computes all patterns from scratch every time
any new failure is recorded. The pattern cache is defeated by design. While the comment suggests
this ensures freshness, it creates an O(N * K) cost where N is failure count and K is the number
of pattern detection methods called.

More importantly, the `_MAX_FAILURES = 1000` cap (line 60) with slice retention `self._failures =
self._failures[-1000:]` means old failures are silently dropped. This can erase the only evidence
of a rare failure pattern just because the buffer filled up with common failures.

**Why it matters for long sessions**: In a 2-hour combat session, the agent may generate hundreds
of failures. After 1000 failures, the oldest ones (which might include rare but informative
failure signatures like a specific boss mechanic) are dropped. The pattern detector loses the
ability to detect patterns that span the full session duration. Additionally, the re-computation
cost grows linearly, creating latency spikes during intense gameplay.

**Concrete scenario**: The agent fights 50 different enemies and records 1000 failures. The first
30 failures are against a rare boss with a specific element mismatch pattern. After the buffer
fills with common `TARGET_LOST` failures from regular enemies, the boss failures are evicted.
The `ELEMENT_MISMATCH` pattern for that boss is lost and never surfaces as a suggestion.

**Suggested fix**:
1. Use an incremental pattern update instead of clearing on every failure. Track pattern
   counts and update them incrementally.
2. Implement a stratified failure buffer: keep at least N failures per category, preventing
   common categories from evicting rare ones.
3. Raise `_MAX_FAILURES` for long sessions or make it configurable based on session duration.
4. Add a persistence mechanism so failure patterns survive across sessions.

---

## Finding: SkillDef Schema Version Has No Migration Path (SEVERITY: MEDIUM)

**What is wrong**: `SkillDef` in `skills/schema.py` has a `version` field (line 109, default 1),
but `from_dict()` (line 192) does not check the version at all. It silently applies current-schema
defaults to any input. If a future version adds new required fields or changes field semantics,
old serialized skills will be loaded with incorrect defaults.

The `SkillStore` in `app_service/skill_manager.py` maintains its own separate `SkillDefinition`
class (not `skills.schema.SkillDef`) with a different schema. There are now two parallel skill
schemas in the codebase: `skills.schema.SkillDef` and `app_service.skill_manager.SkillDefinition`.
Neither has a migration utility, and they are not interchangeable.

**Why it matters for long sessions**: Skills persisted to disk in session N may be loaded in
session N+K with a different code version. If the schema changed (e.g., a new field was added
to `SkillApplicability`, or `StepAction` gained new values), old skills load with silent
defaults that may be semantically wrong. Over multiple sessions, the skill corpus accumulates
skills that were valid when created but are now subtly broken.

**Concrete scenario**: Session 1 saves a skill with `SkillStep(action="press_key", target="E",
wait_until="skill_ready")`. In a later code update, the `wait_until` field semantics change from
"a visual trigger name" to "a state claim ID". The old skill loads with `wait_until="skill_ready"`,
which is now interpreted as a claim ID that does not exist. The skill always times out at this step,
but the timeout error is opaque because the mismatch is in the schema interpretation layer.

**Suggested fix**:
1. Add version validation in `from_dict()`: if `data["version"]` is not the current schema version,
   apply explicit migration functions before constructing the dataclass.
2. Maintain a `_MIGRATORS: dict[int, Callable]` registry that upgrades old versions to current.
3. Unify `SkillDef` and `SkillDefinition` into a single schema, or create an explicit adapter
   between them.
4. Add a schema version constant (`CURRENT_SCHEMA_VERSION = 2`) and reject loading skills with
   versions higher than what the current code supports (forward compatibility guard).

---

## Finding: RepairValidator Only Checks Structural Properties, Not Semantic Correctness (SEVERITY: MEDIUM)

**What is wrong**: `RepairValidator` in `repair/repair_validator.py` has two methods:

1. `validate_dry_run()` (line 11): Checks that each step has an `action_type` string and that
   `params` is a dict. That is the entire validation.
2. `validate_verifier_replay()` (line 30): Checks that the patch has proposed steps and that
   required action types (if specified in the contract) are present. No actual replay execution.

Neither method executes the proposed steps against any real or simulated environment. The
"validation" is purely syntactic. The `RepairBenchmarkRunner` in `repair_benchmark_runner.py`
is equally synthetic: `run_before()` always returns `pass_rate=0.0` and `run_after()` returns
`pass_rate=1.0` if the patch status is `SANDBOX_VALIDATED` (line 49), creating a tautological
benchmark.

**Why it matters for long sessions**: The evolution engine's repair-approve-deploy cycle has no
real quality gate. Patches that pass "validation" may introduce regressions. The benchmark delta
always shows improvement because it is derived from the patch status, not from actual execution.
Over time, the skill corpus accumulates patches that "improved" on paper but degraded in practice.

**Concrete scenario**: A repair patch for skill `induced_open_inventory` changes step 2 from
`click_anchor("sort_button")` to `click_anchor("filter_button")`. Both have valid `action_type`
strings, so `validate_dry_run()` passes. The verifier contract has no `required_actions` constraint,
so `validate_verifier_replay()` passes. The benchmark shows +100% improvement (from 0.0 to 1.0)
because the patch is `SANDBOX_VALIDATED`. The skill is deployed and now clicks the wrong button.

**Suggested fix**:
1. Implement actual dry-run execution: replay proposed steps against a mock or recorded environment.
2. Add semantic validation: verify that anchor IDs in proposed steps exist in the current anchor
   registry.
3. Make `RepairBenchmarkRunner` replay actual recorded scenarios before and after patching,
   rather than using synthetic metrics.
4. Add a "regression test" step: before approving a patch, verify that the patched skill still
   passes scenarios that the original skill passed.

---

## Finding: Induction Pipeline Registers Coordinate-Only Skills as raw_trace But Never Cleans Them Up (SEVERITY: MEDIUM)

**What is wrong**: In `pipeline.py` line 66-67, coordinate-only skills are registered into the
registry as `raw_trace`:

```python
if result.coordinate_only:
    coordinate_only += 1
    self.registry.register(result.skill)
    continue
```

These skills are stored permanently in the registry with no cleanup mechanism. The registry has
an `unregister()` method, but nothing calls it for stale `raw_trace` skills. Over many induction
sessions, the registry accumulates coordinate-only skills that can never be promoted.

While `find_applicable()` filters by `min_tier` (default `candidate`), so these skills are not
returned for execution, they still consume memory and slow down `all_skills()` and `find_by_*()`
scans. More importantly, if a user or test calls `find_by_screen_state()` (line 41) without
specifying `min_tier`, raw_trace skills ARE returned, including coordinate-only ones.

**Why it matters for long sessions**: Over dozens of induction sessions, each producing 5-20
episodes, the registry can accumulate hundreds of useless `raw_trace` skills. If induction runs
every few minutes during autonomous play, this grows to thousands within an hour. Registry
operations that scan all skills slow down proportionally.

**Concrete scenario**: An autonomous session runs for 2 hours with induction triggered every 5
minutes. Each session produces 10 episodes, of which 7 are coordinate-only. After 2 hours: 24
sessions * 7 = 168 coordinate-only skills in the registry. `find_by_screen_state("combat_main")`
scans all 168 useless entries plus the real ones. If the agent is also running combat at high
frequency, this registry scan becomes a measurable latency contributor.

**Suggested fix**:
1. Do not register coordinate-only skills in the registry at all. Store them in a separate
   "trace archive" for offline analysis.
2. If they must be registered, add a periodic cleanup: delete `raw_trace` skills older than N hours
   that have no anchor bindings.
3. Make `find_by_screen_state()` accept an optional `min_tier` parameter, consistent with
   `find_applicable()`.

---

## Finding: EpisodeSegmenter Does Not Validate Episode Coherence (SEVERITY: MEDIUM)

**What is wrong**: `EpisodeSegmenter.segment()` in `episode_segmenter.py` splits trace sessions
at screen state transitions. It does not validate:
- Episode duration (a "micro-episode" of 1 action at 50ms is treated the same as a 30-second episode)
- Episode goal coherence (the goal string is copied from the session to every episode verbatim)
- Minimum action count (single-action episodes are valid)
- Whether the screen state transition is meaningful or noise (a transient state flash creates
  a split)

If the screen state detector produces noisy results (e.g., brief `unknown` states during transitions),
the segmenter will create micro-episodes that get bound into skills. These micro-skills are typically
not useful but pass all validation checks because they have anchors and steps.

**Why it matters for long sessions**: Noisy screen state detection during fast gameplay (combat,
quick menu navigation) produces many spurious state transitions. Each becomes a micro-episode,
each gets bound by AnchorBinder, and each produces a skill in the registry. The induction pipeline
generates junk skills that dilute the skill corpus.

**Concrete scenario**: During combat, the screen state detector flickers between `combat_main` and
`unknown` every 200ms due to explosion effects. The segmenter creates 10 micro-episodes in 2 seconds.
Each becomes a skill with 1-2 steps, registered as `raw_trace` or `draft`. Over a 10-minute combat
session, hundreds of junk skills accumulate.

**Suggested fix**:
1. Add a minimum episode duration threshold (e.g., discard episodes shorter than 500ms).
2. Add a minimum action count (e.g., at least 2 actions per episode).
3. Implement a state transition debounce: ignore `unknown` or transient states shorter than a
   threshold before splitting.
4. Validate episode goal coherence: if an episode has a single action and the goal is complex
  (e.g., "complete_daily_commissions"), flag it as low-quality.

---

## Finding: ThreeLayerReliabilityStore Snapshot Deserialization Mutates Frozen Dataclasses (SEVERITY: MEDIUM)

**What is wrong**: In `reliability_store.py` lines 576-594, `_load_snapshot()` attempts to
modify fields of `VerifierReliabilityEntry`, `RecipeReliabilityEntry`, and
`SkillClaimReliabilityEntry` using `setattr()`. However, all three dataclasses are declared with
`frozen=True` (lines 85, 184, 290). Calling `setattr()` on a frozen dataclass raises
`dataclasses.FrozenInstanceError` at runtime.

This means snapshot loading silently fails (the `except (OSError, json.JSONDecodeError)` block
in `_load_snapshot()` does not catch `FrozenInstanceError`). After a restart, the reliability
store loses all accumulated history and starts from scratch.

The `SkillClaimReliabilityEntry` deserialization at line 594 tries to access `entry.outcome_counts`,
but the dataclass does not have an `outcome_counts` field. This would raise `AttributeError`.

**Why it matters for long sessions**: If the agent restarts (crash, user close, update), all
reliability data is lost. Skills that were reliability-tested over hours of play start with zero
history. The Wilson lower bounds reset to 0.0, causing all skills to fail the promotion threshold
and effectively demoting them to untrusted status. The agent must re-earn all reliability
certifications from scratch.

**Concrete scenario**: The agent runs for 4 hours, building reliability history for 20 skills.
A crash occurs. On restart, `_load_snapshot()` fails with `FrozenInstanceError`. All reliability
entries are empty. Skills that were `trusted` or `stable` now have Wilson LB = 0.0. The agent
behaves as if it has never played before, selecting suboptimal strategies and re-inducing skills
that already exist.

**Suggested fix**:
1. Use `dataclasses.replace()` instead of `setattr()` to create new frozen instances with updated
   fields.
2. Fix the `SkillClaimReliabilityEntry` deserialization: the serialized format uses `outcome_counts`
   but the dataclass has individual fields (`claim_verified`, `claim_rejected`, etc.). Add a
   proper mapping.
3. Add error handling for `FrozenInstanceError` and `AttributeError` in `_load_snapshot()`.
4. Add a round-trip test: serialize, deserialize, verify equality.

---

## Finding: GenshinFailureAnalyzer Generates Static Adjustments Regardless of Context (SEVERITY: LOW)

**What is wrong**: The `generate_improved_playbook()` method in `genshin_failure_analyzer.py`
returns hardcoded adjustment values regardless of the actual failure context. For example,
for `TARGET_LOST`, it always suggests `increase_coasting_window_ms: 2000` and
`add_re_acquire_step_after_lost: True` (lines 120-126). For `HP_DEPLETED`, it always suggests
`lower_hp_threshold: 0.4` (line 133).

These values do not adapt based on:
- Current coasting window (what if it is already 2000ms?)
- Current HP threshold (what if it is already 0.3?)
- The specific enemy or region causing the failure
- The number of times this adjustment has already been applied

**Why it matters for long sessions**: Applying the same adjustment repeatedly creates no additional
benefit. After the first `TARGET_LOST` adjustment, subsequent failures of the same type generate
identical suggestions. The evolution engine applies them, creating new patch versions that are
functionally identical to the previous one. This wastes repair cycles and pollutes the patch history.

**Concrete scenario**: The agent fails with `TARGET_LOST` 10 times against the same enemy. Each
time, the analyzer suggests `increase_coasting_window_ms: 2000`. The evolution engine creates 10
patches, all with the same adjustment. After approval, the coasting window is set to 2000ms 10 times
(it was already 2000ms after the first patch). The remaining 9 failures go unrepaired because the
root cause (wrong tracking target) is never addressed.

**Suggested fix**:
1. Track applied adjustments and avoid re-suggesting the same values.
2. Make adjustment values adaptive: if `TARGET_LOST` persists after increasing coasting window to
   2000ms, try 3000ms, then add re-acquisition, then suggest human review.
3. Use the failure pattern context (enemy ID, region) to produce more specific suggestions.
4. Add a feedback loop: after applying an adjustment, track whether the failure rate decreased.

---

## Finding: SkillStore and SkillRegistry Are Separate, Unconnected Stores (SEVERITY: LOW)

**What is wrong**: The codebase has two independent skill storage systems:
1. `SkillRegistry` in `skills/registry.py` -- in-memory, thread-safe dict, used by the induction
   pipeline and promotion gate.
2. `SkillStore` in `app_service/skill_manager.py` -- file-backed JSON store with versioning,
   rollback, and archival, used by the skill manager and product API.

Skills registered in `SkillRegistry` via induction are never persisted to `SkillStore`. Skills
saved in `SkillStore` via the product API are never loaded into `SkillRegistry`. The two systems
operate on completely different schemas (`SkillDef` vs `SkillDefinition`) and have no
synchronization mechanism.

**Why it matters for long sessions**: Skills learned during autonomous play (registered in
`SkillRegistry`) are lost when the process exits. Skills created via the product UI (saved in
`SkillStore`) are invisible to the induction pipeline and execution engine. This creates a
fragmented experience where the agent "forgets" everything it learned between sessions, and
manually-created skills cannot be used by the autonomous execution layer.

**Concrete scenario**: The agent runs for 3 hours, inducing 15 skills via the induction pipeline,
all registered in `SkillRegistry`. The process exits. Next session, `SkillRegistry` is empty.
The agent must re-induce all 15 skills. Meanwhile, a user created 5 skills via the product UI,
stored in `SkillStore`. These skills are never seen by the execution engine because it queries
`SkillRegistry`, not `SkillStore`.

**Suggested fix**:
1. Unify the two storage systems, or create a synchronization bridge that copies skills between
   them.
2. Make `SkillRegistry` persist its contents to disk (JSON or SQLite) and reload on startup.
3. Make the induction pipeline register skills in both stores.
4. Add a startup reconciliation step that loads `SkillStore` skills into `SkillRegistry`.

---

## Summary Table

| # | Finding | Severity | Subsystem |
|---|---------|----------|-----------|
| 1 | No skill demotion pathway | CRITICAL | promotion.py, registry.py |
| 2 | Wilson confidence locked by historical success | CRITICAL | promotion.py, pipeline.py |
| 3 | Repair loops have no bound | HIGH | evolution_engine.py |
| 4 | Induced skills auto-pass sandbox | HIGH | evolution_engine.py |
| 5 | DecisionMemory prunes critical rare decisions | HIGH | decision_memory.py |
| 6 | AnchorBinder loses timing information | HIGH | anchor_binder.py |
| 7 | Concurrent induction/execution race conditions | HIGH | pipeline.py, registry.py |
| 8 | BAGEL probe policy never consumed | MEDIUM | schema.py |
| 9 | FailureAnalyzer clears patterns on every failure | MEDIUM | genshin_failure_analyzer.py |
| 10 | SkillDef schema has no migration path | MEDIUM | schema.py |
| 11 | RepairValidator is purely structural | MEDIUM | repair_validator.py |
| 12 | Coordinate-only skills accumulate in registry | MEDIUM | pipeline.py, registry.py |
| 13 | EpisodeSegmenter creates micro-episodes from noise | MEDIUM | episode_segmenter.py |
| 14 | ReliabilityStore snapshot breaks on frozen dataclasses | MEDIUM | reliability_store.py |
| 15 | FailureAnalyzer generates static adjustments | LOW | genshin_failure_analyzer.py |
| 16 | SkillStore and SkillRegistry are disconnected | LOW | skill_manager.py, registry.py |

**CRITICAL findings (2)**: Must fix before any long-session autonomous deployment. Skills will
silently degrade with no recovery mechanism.

**HIGH findings (5)**: Must fix for reliable multi-hour sessions. Will cause visible failures,
data corruption, or resource exhaustion within 1-2 hours of autonomous play.

**MEDIUM findings (7)**: Should fix for production quality. Will cause gradual degradation over
multiple sessions or edge-case failures.

**LOW findings (2)**: Quality improvements. Reduce maintenance burden and user confusion.
