# Long-Range Autonomy Closure Plan

**Branch:** codex/pre-realworld-closure
**Date:** 2026-05-28
**Goal:** After execution, 30+ minute autonomous sessions have zero known vulnerabilities.
**Scope:** BAGEL, Skill OS, Vision Pipeline, Mainline Loop, minor cleanups.

## Phase 1: BAGEL Session Boundary & Lifecycle Management

### 1.1 FIG Eviction — `bagel/fig_schema.py`

Add `evict_terminated(max_age_sec=300.0) -> int`:
- Under lock, find beliefs with lifecycle in `("retired", "falsified", "posthoc_invalid", "stale")` where `updated_at < now - max_age_sec`.
- Remove them from `beliefs`, also remove associated actions (where all belief_ids are evicted), feedbacks, probes, edges referencing evicted IDs.
- Clean `_ordering_lock` for evicted belief IDs.
- Return count evicted.

### 1.2 EvidenceMatrix Temporal Decay — `bagel/evidence_matrix.py`

Add `timestamp: float = 0.0` field to `EvidenceSignal`, defaulting to `time.perf_counter()` in `__post_init__`.
Add `signal_horizon_sec: float = 600.0` (10 min) to `EvidenceMatrix`.
In `score_belief()`, skip signals where `now - sig.timestamp > signal_horizon_sec`.
Add `evict_signals_before(cutoff: float) -> int` and `clear_for_beliefs(belief_ids: list[str]) -> int`.
Replace `clear()` body with delegation to `clear_for_beliefs(list(self._signals.keys()))`.

### 1.3 Quest Transition Protocol — `bagel/runtime.py`

Add `quest_transition(new_mission_id: str, carry_forward_beliefs: list[str] | None = None, trace_id: str = "") -> dict[str, Any]`:
1. Run final attribution cycle for current quest.
2. Archive current FIG state via event store (write `QuestArchived` event with full FIG snapshot).
3. Call `fig.evict_terminated(max_age_sec=0.0)` to remove all terminal beliefs.
4. Call `matrix.evict_signals_before(now)` to clear stale signals.
5. If `carry_forward_beliefs`, keep those; evict the rest of non-terminal beliefs.
6. Set `fig.mission_id = new_mission_id`, bump version.
7. Reset probe_policy taboo (`reset_taboo()` on ProbePolicy).
8. Write `QuestTransition` event.
9. Return summary dict.

### 1.4 Probe Starvation Prevention — `bagel/probe_policy.py`

Add `_taboo_timestamps: dict[str, float] = field(default_factory=dict)` alongside `_taboo_probe_families`.
In `degrade_non_decidable()`, also record timestamp.
Add `reset_taboo()` and `expire_taboos(max_age_sec=600.0)`.
In `generate_probes()`, check if belief already has a probe with status in `("generated", "sanity_checked", "approved", "executing")`. If yes, skip (max 1 pending probe per belief).

### 1.5 Belief Oscillation Dampening — `bagel/arbiter.py`

Track oscillation in `ArbitrationResult.metadata["oscillation_count"]`:
- If old_lifecycle == new_lifecycle of a previous result for same belief, increment count.
- Arbiter keeps `_oscillation_counts: dict[str, int]` (non-frozen, internal state).
- After 3 oscillations, instead of flipping again, keep current lifecycle and set `reason="oscillation_dampened"`.

### 1.6 EventStore Compaction & Lifecycle — `bagel/event_store.py`

Add `__enter__`/`__exit__` for context manager.
Add `atexit.register(self.close)` in `__init__`.
Add `snapshot_fig(graph_id: str) -> dict[str, Any]` that calls `reconstruct_fig` and caches result.
Add `compact(graph_id: str) -> None`: reconstruct FIG, write snapshot as single `FigSnapshot` event, truncate file to start from that event.
In `BagelRuntime`, add `shutdown()` that calls `event_store.close()`.

### 1.7 BFS Performance Fix — `bagel/fig_schema.py`, `bagel/safe_revision.py`

Replace `queue = [belief_id]` / `queue.pop(0)` with `from collections import deque; queue = deque([belief_id])` / `queue.popleft()`.

### 1.8 Arbiter Age Awareness — `bagel/arbiter.py`

In `_evaluate()`:
- If belief is `provisional` and `belief.updated_at < now - 120.0` (2 min stale), transition to `"retired"` with reason `"provisional_expired"`.
- If `belief.valid_while_structured` is non-empty, check conditions (currently unimplemented — add a placeholder that checks if target_object still exists in FIG beliefs; if not, mark stale).

### 1.9 Attribution Phase Reset — `bagel/runtime.py`

Add `reset_phase()` that calls `fig.set_phase("execution")` and clears `_frozen_snapshot`.
In `run_attribution_cycle()`, guard against double-freeze: if `fig.phase == "attribution_frozen"` when entering, call `reset_phase()` first.

### 1.10 Omitted Belief Lifecycle Fix — `bagel/omitted_belief.py`

In `ConstrainedVerbalizer.verbalize()`:
- Add `skip_existing: dict[str, Any] | None = None` parameter.
- If `skip_existing` is provided and belief_id already in it, skip (return empty list).
- Change lifecycle from `"challenged"` to `"provisional"` so omitted beliefs enter the normal probe pipeline.

### 1.11 Feedback Shift Guard — `bagel/runtime.py`

In `compute_feedback_shift()`:
- Before calling `fig.update_belief()`, check if belief lifecycle is in `("falsified", "retired")`. If so, skip update, just return the result without modifying FIG.
- Add staleness check: if `belief.updated_at > bridge_created_at + 300.0`, skip (bridge too old).

### 1.12 CausalBridge Temporal Validity — `bagel/runtime.py`

In `score_delayed_feedback()`, replace binary freshness with exponential decay:
`freshness = exp(-0.01 * (now - belief.updated_at))` instead of 0.0/1.0.

### 1.13 Condensed Node Revalidation — `bagel/fig_schema.py`

Add `invalidate_condensed_for_belief(belief_id: str) -> list[str]`: find all condensed nodes whose `source_node_ids` include `belief_id`, remove them, return their IDs.
Call this from `update_belief()` when lifecycle transitions to a terminal state.

### 1.14 Probe Taboo Expiry — `bagel/probe_policy.py`

Change `_taboo_probe_families: set[str]` to `_taboo_probe_families: dict[str, float]` (family -> timestamp).
In `generate_probes()`, skip taboo only if `now - timestamp < taboo_ttl_sec` (default 600s).
Add `taboo_ttl_sec: float = 600.0` to `ProbePolicy`.

### 1.15 _ordering_lock Cleanup — `bagel/fig_schema.py`

In `evict_terminated()`, also clean `_ordering_lock` entries for evicted belief IDs.
In `update_belief()` when lifecycle transitions to terminal, also remove from `_ordering_lock`.

## Phase 2: Skill OS Adaptive Tier Management

### 2.1 Skill Demotion — `skills/promotion.py`

Add `can_demote_to(skill: SkillDef, target: PromotionTier, consecutive_failures: int = 0) -> tuple[bool, str]`:
- target_idx must be < current_idx.
- consecutive_failures >= 3 triggers mandatory demotion.
- Otherwise, require explicit reason.

Add `demote_skill(skill: SkillDef, target: PromotionTier) -> SkillDef`:
- Returns new SkillDef with lowered tier, reset promotion counters in metadata.

### 2.2 Wilson Recency Window — `skills/promotion.py`

Add `windowed_wilson(successes: int, failures: int, total_successes: int, total_failures: int, window_weight: float = 0.7) -> float`:
- Blend windowed (recent) stats with total: `effective_s = window_weight * successes + (1 - window_weight) * max(0, total_successes - successes)`, similarly for failures.
- Compute Wilson on effective counts.

Add consecutive failure circuit breaker to `can_promote_to()`: if `failures >= 5` in the last window, reject promotion.

### 2.3 EvolutionEngine Repair Bounds — `learning/evolution_engine.py`

Add `_repair_cooldowns: dict[str, float] = field(default_factory=dict)` (skill_id -> last repair timestamp).
In `_drain_failures()` / `handle_failure()`:
- Check cooldown: skip if `now - last_repair_time < 60.0`.
- Cap `_repair_sessions` at 100 total; reject new when full.

### 2.4 Induced Skill Sandbox Validation — `learning/evolution_engine.py`

Remove the `if skill_id.startswith("induced_"): return True` bypass in `_verify_in_sandbox()`.
Replace with structural validation: check that all step actions reference known anchor IDs, that wait conditions are bounded, that timeouts are > 0.

### 2.5 DecisionMemory Smart Pruning — `learning/decision_memory.py`

In `prune()`:
- Before deleting, group by goal+capsule_id.
- For each group, always keep top-3 by confidence regardless of age.
- Delete only entries that are not in top-3 AND older than max_age.

### 2.6 AnchorBinder Timing — `learning/skill_induction/anchor_binder.py`

In `bind()`:
- Compute inter-step delays from `RecordedAction.timestamp` deltas.
- Store in `SkillStep.params["delay_ms"]`.
- For motor-tier skills, use median of multiple observations if available.

### 2.7 BAGEL Probe Policy Enforcement — `skills/promotion.py`

In `can_promote_to()` for stable/trusted tiers:
- Check `skill.metadata.get("non_decidable_count", 0)` against `skill.bagel_probe_policy.max_non_decidable`.
- If exceeded, reject: "too many non-decidable probe results".

### 2.8 SkillDef Version Migration — `skills/schema.py`

Add `CURRENT_SCHEMA_VERSION = 2` constant.
In `from_dict()`: if `data.get("version", 1) < CURRENT_SCHEMA_VERSION`, apply migration functions.
Add `_migrate_v1_to_v2(data)`: ensure `jit_regeneration_policy` and `bagel_probe_policy` exist.

## Phase 3: Vision Pipeline Resilience

### 3.1 Vision Failover — `llm/gemma_vision_provider.py`

Add `FallbackVisionBackend`:
- Holds `primary: VisionBackend` and `fallback: VisionBackend`.
- `extract_facts()`: try primary; on `ProviderRequestError`/`ProviderUnavailable`, log warning, call fallback.
- Fallback returns `VisionFactBundle` with `uncertainty=1.0`, `screen_state="unknown"`.

Add `DeterministicFallbackBackend` (minimal):
- Always returns "unknown" screen state, empty facts, uncertainty 1.0.

### 3.2 Output Guard All Fact Types — `llm/gemma_vision_provider.py`

In `_parse_fact_bundle()`, apply `guard.validate_fact_schema(fact)` for ALL fact types, not just `ui_grounding`.
Move confidence check after guard validation.

### 3.3 Fact Bundle Consistency — `llm/vision_provider.py`

Add `validate_bundle(bundle: VisionFactBundle) -> VisionFactBundle`:
- If any `VisionFact.fact_type == "screen_state"` disagrees with `bundle.screen_state`, set `bundle.screen_state = "unknown"`, `uncertainty = max(bundle.uncertainty, 0.5)`.
- Cap `facts` to max 20 entries.
- Return corrected bundle.

### 3.4 Focus Detection Resilience — `execution/safe_window_backend.py`

Add PID-based fallback:
- Store `_target_pid: int | None = None` after first successful window find.
- In `_find_target_window()`, if title match fails and `_target_pid` is set, enumerate windows by PID using `GetWindowThreadProcessId`.
- Add `_focus_grace_count: int = 0` (max 3 consecutive failures before triggering release).
- Replace `time.sleep(0.1)` with chunked 10ms x 10 loop checking stop event.

### 3.5 Profile Switch Safety — `execution/safe_window_backend.py`

Add `_profile_version: int = 0`.
In `is_target_focused()`, check profile version before each action.
If version changed, reload window title from profile, reset `_target_pid`, log warning.

## Phase 4: Minor Cleanups

### 4.1 Worker Crash StateBus Interrupt — `execution/input_worker.py`

In `_run_loop()` exception handler: if `self._state_bus` available, publish P0 interrupt `WORKER_CRASHED`.

### 4.2 LLMRequestGuard Monotonic Clock — `llm/vision_output_guard.py` or wherever it is

Replace `time.time()` with `time.perf_counter()` in any rate-limiting code.

### 4.3 ReliabilityStore Frozen Dataclass Fix — `reliability/reliability_store.py`

Replace `setattr()` calls in `_load_snapshot()` with `dataclasses.replace()`.

### 4.4 EpisodeSegmenter Min Duration — `learning/skill_induction/episode_segmenter.py`

Add `min_episode_duration_ms: float = 500.0` and `min_actions: int = 2`.
Discard episodes shorter than either threshold.

### 4.5 FailureAnalyzer Incremental Patterns — `learning/genshin_failure_analyzer.py`

Don't call `_patterns.clear()` on every `record_failure()`.
Instead, incrementally update pattern counts.
Only recompute on explicit `analyze_patterns()` call.

### 4.6 ConsoleBackend Deque — `execution/console_backend.py`

Replace `_events: list` with `collections.deque(maxlen=self._max_events)`.

## Verification

After all phases:
1. `python -m pytest tests/ -q` — all tests pass
2. `python -m compileall bagel/ skills/ llm/ execution/ learning/ planning/ -q` — zero errors
3. Grep audit: verify each finding is addressed
4. Run existing tests + new tests for each phase
