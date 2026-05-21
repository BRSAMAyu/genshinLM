# Claim-Centric Runtime Design

## Goal

Aurora should not optimize for "an action ran". It should optimize for "the world state changed as claimed, with enough evidence to keep planning safely".

The runtime therefore treats every meaningful Skill result as a `StateDeltaClaim`.

```text
Action -> StateDeltaClaim -> ClaimGraph -> Verifier/Audit -> Reliability -> Planner Gate
```

LLMs may explain, compare strategies, and propose plans. They do not produce factual confidence scores and they do not act as final judges of success.

## Hard Rules

1. Claims are the unit of truth. Skills do not return plain success for terminal facts.
2. Claim dependencies must be explicit. Inferred dependencies are temporary patches and produce `DEPENDENCY_DECLARATION_GAP`.
3. Cascade invalidation is cluster scoped. A demoted claim only blocks decisions that depend on its affected cluster.
4. Uncertainty must exit. It may resample, use an alternate verifier, safe-probe, local-recover, ask the user, or abort safely.
5. Confidence is system computed from measured factors. LLMs can consume confidence but cannot estimate it.
6. Delayed audits must carry execution snapshots. Contaminated audits do not update reliability.
7. Reliability is conditional. Planner decisions use context backoff instead of one flat skill score.
8. Risk level controls thresholds. Critical tasks are never fully automatic.
9. False negatives are detected via downstream chain tracing. When downstream succeeds but upstream was demoted, upstream is revalidated to tentative.
10. Stabilization windows auto-adjust based on historical failure rates after each claim family.
11. Environment version drift is detected and demotes affected skills to bootstrap mode.

## StateDeltaClaim

```text
claim_id
mission_id
node_id
skill_id
claim_type
claimed_delta
status
risk_level
confidence
confidence_factors
evidence_refs
signals
input_claims
depends_on
inferred_depends_on
time_windows
stabilization_window_ms
metadata
```

`input_claims` and `depends_on` are author-declared. `inferred_depends_on` is produced by comparing verifier observation windows with declared dependencies.

Default stabilization windows are claim-family based:

```text
ui_screen_transition: 800ms
dialogue_advance: 500ms
inventory_delta: 1200ms
collection_pickup: 900ms
teleport_loaded: 1500ms
navigation_arrival: 700ms
combat_target_killed: 1200ms
boss_phase_changed: 1800ms
danger_cleared: 3 safe frames + 200ms
generic_unknown: 1000ms
```

## Confidence

Confidence is computed by the runtime:

```text
confidence =
  signal_quality
  * verifier_historical_reliability
  * context_match_score
  * sample_sufficiency
  * drift_penalty
```

`signal_quality` includes spatial quality, OCR quality, detector confidence, frame consistency, temporal pattern match, and cross-signal agreement.

Historical reliability uses conservative estimates such as Wilson lower bound. Small samples are penalized.

LLMs never produce these values. They only consume them and explain why the system considers them low or high.

## Uncertainty Policy

Uncertainty is not a stable end state:

```text
UNCERTAIN
-> resample_observation
-> alternate_verifier
-> safe_probe
-> local_recovery
-> human_confirm
-> abort_safe
```

If all replan options are below the risk-specific replan threshold, the system must not ask the LLM to pick the least bad option. It asks the user or aborts safely.

Default thresholds:

```text
LOW:      auto >= 0.60, replan >= 0.50
MEDIUM:   auto >= 0.70, replan >= 0.60
HIGH:     auto >= 0.80, replan >= 0.70
CRITICAL: no automatic execution
```

Maximum replan cycles per node: 3. Beyond that, safe abort.

## Cascade Invalidation

When a claim is demoted:

```text
demoted claim
-> downstream claims become suspect
-> affected dependency cluster is computed
-> current or next decision is checked against the cluster
```

Responses:

```text
no dependency on cluster: continue_with_warning
low risk dependency: revalidate_cluster
medium/high risk dependency: pause_replan
critical risk dependency: safe_abort_user_confirm
```

This keeps blast radius local while preventing execution on a known-bad premise.

## False Negative Detection

When a downstream claim is verified but its upstream was previously demoted:

```text
downstream claim verified
-> check all upstream dependencies
-> if upstream is demoted/suspect:
   -> structural evidence suggests upstream was likely correct (false negative)
   -> revalidate upstream to "tentative"
   -> record FalseNegativeReport
```

This prevents the system from treating a correct action as failed just because a single verifier missed the signal.

## Delayed Audit

Immediate verification is not enough to measure false accept. Delayed audits compare a claim against a captured execution snapshot.

```text
AuditSnapshot:
  inventory_before
  position_before
  screen_state_before
  team_state_before
  active_task_before
  timestamp
```

Audit outcomes:

```text
matched
mismatch
contaminated
unverifiable
```

`contaminated` means external activity made the audit invalid. It is not success or failure and does not update normal reliability.

If contamination exceeds 50%, the runtime switches to low-activity-window audits. If low-activity retries still fail repeatedly, the Skill is marked `audit_difficult` and cannot be a high-risk automatic main path.

## Stabilization Windows

Each claim family has a default stabilization window. The system auto-adjusts:

```text
if next_action failure rate > 20% after a claim family:
  increase stabilization window by 30%
if next_action failure rate < 5%:
  slowly decrease (never below family default)
```

This prevents "correct claim but next action hits visual residue" problems (e.g., boss death animation blocking the next UI click).

## Drift Detection

Environment version changes (game patches, UI layout changes) invalidate historical reliability.

```text
DriftDetector checks:
  layout_shift_score
  ocr_anchor_shift_score
  template_match_drop
  detector_confidence_drop
```

When drift is detected:

```text
affected skills are demoted to bootstrap mode
historical reliability is preserved but drift_penalty=0.5 applied
system requests recalibration
```

Skills are not deleted — they return to bootstrap mode until new evidence is collected.

## Reliability Pyramid

Reliability is not a single global skill score.

```text
L0: global + skill
L1: capsule + skill
L2: capsule + skill + screen_state + mission_phase
L3: L2 + target_class
L4: L3 + profile_bucket
L5: L4 + game-specific dimension
```

The gate prefers Level 2/3 when enough samples exist. If samples are sparse, it backs off to coarser levels and applies sample sufficiency penalties.

Version drift demotes affected skills/verifiers instead of deleting them. They return to bootstrap mode until new evidence is collected.

## Decision Memory

Raw `RunJournal` is not LLM context. It is distilled:

```text
RunJournal -> EpisodeAnalyzer -> DecisionMemoryPacket -> LLM
```

The LLM receives:

```text
current_goal
last_successful_approach
current_obstacle
recovery_options
confidence_this_works
do_not_repeat
evidence_refs
```

The LLM does not read hundreds of raw decisions and does not reconstruct reliability from prose.

## Claim-Producing Executor

The `ClaimProducingExecutor` bridges skill execution and the Claim-Centric Runtime:

```text
1. Pre-flight: Gate check + UncertaintyPolicy decision
2. Produce: Create StateDeltaClaim from signals + reliability
3. Verify: Update claim status based on verifier result
4. Audit: Create DelayedAuditRecord with execution snapshot
5. Record: Update ReliabilityStore and StabilizationTracker
6. Distill: Summarize journal for LLM consumption
```

## Verifier Enhancements

`VerifierResult` includes multi-signal verification fields:

```text
alternative_signals: list[SignalCorroboration]
downstream_effects_verified: list[str]
false_negative_likelihood: float
re_verify_recommended: bool
```

When the primary signal says fail but alternative signals support success, the system calculates a false negative likelihood. This feeds into the false negative detection mechanism.

## Integration Points

- `SkillResult.claim_id`: Links skill execution to claim tracking
- `MissionNode.risk_level`: Declared at Mission design time, controls all threshold gating
- `RunCheckpoint.claim_refs`: Checkpoints carry claim references for resume validation
- `RunSummary.claim_status`: Context compactor includes claim status for LLM replan

## MVP Acceptance

The MVP is complete when tests demonstrate:

- Claim confidence is system computed (55 tests)
- Inferred dependencies produce declaration-gap warnings
- Cascade invalidation is cluster scoped
- False negatives detected via downstream chain tracing
- Low-confidence options trigger user confirmation or safe abort
- Contaminated audits do not update reliability and can mark a Skill as audit difficult
- Reliability uses context backoff and risk-stratified thresholds
- Stabilization windows auto-adjust based on failure rate history
- Drift detection identifies environment version changes
- DecisionMemory summarizes reusable conclusions instead of exposing raw logs
- PlanQualityChecklist rejects low-reliability skills, cycles, and repeated failed paths
- ClaimProducingExecutor integrates all 5 control planes end-to-end

All implementation remains scoped to dry-run/testbed/authorized safe-window abstractions.
