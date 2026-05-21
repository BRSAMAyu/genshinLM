# Claim-Centric Runtime Design

**Status**: MVP implemented for dry-run/testbed pre-realworld closure. The runtime now has ClaimGraph, ClaimGraphWorker, ClaimAdjudicator, declarative verifier execution, delayed audit scheduling, reliability tracking, and StateBus claim events.
**Scope**: Aurora's transition from action-centric to claim-centric execution for long-horizon task reliability.

---

## 1. Core Philosophy

Aurora does not optimize for "an action ran". It optimizes for "the world state changed as claimed, with enough evidence to keep planning safely".

Every meaningful Skill result is a `StateDeltaClaim` — not a boolean success/fail, but a structured declaration of state change backed by evidence, confidence, and auditability.

```text
Action produces Claim
Claim forms ClaimGraph
Verifier supports or refutes Claim
DelayedAudit calibrates Claim
ReliabilityStore learns Claim/Skill/Verifier real reliability
Planner selects next step based on reliability
LLM participates only in low-confidence or strategic divergence
```

The fundamental shift:

```text
"动作不是重点，状态变化才是重点。
 即时成功不是重点，延迟审计后的真实成功才是重点。
 日志不是重点，可复用的决策记忆才是重点。
 规划不是重点，可验证、可恢复、知道自己不确定的规划才是重点。"
```

---

## 2. Hard Rules

These rules are non-negotiable constraints on the entire system:

1. **Claims are the unit of truth.** Skills do not return plain success for terminal facts.
2. **Claim dependencies must be explicit.** Inferred dependencies are temporary patches and produce `DEPENDENCY_DECLARATION_GAP`.
3. **Cascade invalidation is cluster-scoped.** A demoted claim only blocks decisions that depend on its affected cluster.
4. **Uncertainty must exit.** It may resample, use an alternate verifier, safe-probe, local-recover, ask the user, or abort safely.
5. **Confidence is system-computed from measured factors.** LLMs can consume confidence but cannot estimate it.
6. **Delayed audits must carry execution snapshots.** Contaminated audits do not update reliability.
7. **Reliability is conditional.** Planner decisions use context backoff instead of one flat skill score.
8. **Risk level controls thresholds.** Critical tasks are never fully automatic.
9. **False negatives are detected via downstream chain tracing.** When downstream succeeds but upstream was demoted, upstream is revalidated to tentative.
10. **Stabilization windows auto-adjust** based on historical failure rates after each claim family.
11. **Environment version drift is detected** and demotes affected skills to bootstrap mode.

---

## 3. Five Control Planes

The Claim-Centric Runtime is organized into five interdependent control planes:

```text
Control Plane 1: Claim Graph
  StateDeltaClaim, depends_on, cascade invalidation, stabilization_window

Control Plane 2: Uncertainty Engine
  uncertain exit policy, confidence thresholds, max replan cycle, plan quality checklist

Control Plane 3: Audit Engine
  delayed audit, execution snapshot, contaminated audit handling, delta mismatch tracking

Control Plane 4: Reliability Engine
  Wilson lower bound, conditional reliability pyramid (3 layers), context backoff, version drift demotion

Control Plane 5: Decision Memory
  RunJournal raw facts, EpisodeAnalyzer, reusable decision summary, LLM-facing strategy packet
```

---

## 4. Control Plane 1: Claim Graph

### 4.1 StateDeltaClaim

```text
claim_id: str
mission_id: str
node_id: str
skill_id: str
claim_type: str                    # inventory_delta, screen_state_transition, combat_target_killed, etc.
claimed_delta: dict                # what changed, e.g. {item: "qingxin", delta: +1}
status: ClaimStatus                # proposed → tentative → verified → locked → audited
risk_level: RiskLevel              # LOW / MEDIUM / HIGH / CRITICAL
confidence: float                  # system-computed only
confidence_factors: ConfidenceFactors
evidence_refs: list[str]           # observation_claim_ids
signals: list[SignalEvidence]
input_claims: list[str]            # author-declared upstream dependencies
depends_on: list[str]              # explicit dependency chain
inferred_depends_on: list[str]     # system-detected dependencies
time_windows: TimeWindows          # before/action/observe/confirm/expiry
stabilization_window_ms: int       # auto-adjusted per claim family
metadata: dict
```

### 4.2 Claim Status State Machine

```text
proposed → tentative → verified → locked → audited
              ↓           ↓          ↓
           uncertain   suspect    suspect
              ↓           ↓          ↓
           rejected    demoted    demoted
                                      ↓
                                   reverified

Any status → expired (time window exceeded)
```

Status meanings:

```text
proposed:    Skill plans to produce this claim, not yet executed
tentative:   Initial evidence exists but insufficient for strong dependency
verified:    ClaimAdjudicator considers current evidence sufficient
locked:      Claim has been checkpointed or referenced by downstream critical nodes
             Cannot be silently modified
audited:     Delayed audit completed, entered long-term reliability statistics

uncertain:   Evidence insufficient or conflicting, needs uncertainty policy exit
suspect:     Upstream claim demoted, or downstream counter-evidence appeared
demoted:     Previously verified claim downgraded, no longer usable as reliable premise
reverified:  Re-validated after suspect/demoted status

rejected:    Determined to be false
expired:     Exceeded validity window, cannot be used as current fact
```

### 4.3 Three Node Types in ClaimGraph

```text
StateDeltaClaim:
  World state or task state change.
  e.g. inventory.qingxin +1, screen_state → combat, boss_phase → phase_2
  Only produced by Skill/Controller/Planner execution results.

ObservationClaim:
  Observation facts.
  e.g. toast visible, anchor disappeared, OCR matched "+1 清心"
  Produced by ObservationBuilder / Verifier.
  Verifiers NEVER produce business conclusions directly.

AdjudicationEvent:
  Adjudication records.
  e.g. verified, rejected, uncertain, demoted, disputed
  Produced by ClaimAdjudicator only.
```

### 4.4 ClaimGraph Lifecycle

**Creation**: Each Mission creates one active `MissionClaimGraph`. No global shared graph.

**Three-layer storage**:

```text
MissionClaimGraph:
  Current mission's active claim graph. Short-term fact ledger.

SessionClaimIndex:
  Lightweight index of recent mission claim summaries within a session.

ReliabilityStore / DecisionMemory / EvidenceStore:
  Cross-mission long-term statistics, experience, and evidence archive.
```

**Size limits**:

```text
max_active_claims_per_mission: 500
max_observation_claims_per_state_claim: 20
max_evidence_refs_per_claim: 10
max_raw_frame_refs_hot: 3
```

**Compaction**: When limits are exceeded:

```text
old ObservationClaims → summarize into EvidenceSummary
old resolved subgraphs → collapse into CheckpointClaim
raw frame refs → move to EvidenceStore cold storage
```

**Post-mission processing**:

```text
1. Archive: Full ClaimGraph written to EvidenceStore / run archive
2. Distill: EpisodeAnalyzer extracts DecisionMemory:
   - Which paths succeeded?
   - Which claims frequently suspect?
   - Which verifiers have high false negative rates?
   - Which contexts are skills reliable in?
3. Update: DelayedAudit / ReliabilityStore update long-term statistics
4. Prune: Active graph cleared, retain only:
   - mission summary
   - audited claims
   - failed/suspect clusters
   - skill reliability updates
   - decision memory packet
   - benchmark regression seed
```

### 4.5 Time Windows

Each claim has explicit time window semantics:

```text
TimeWindows:
  before_window:    Frames before action (establish baseline)
  action_window:    Frame(s) during action execution
  observation_window: Frames after action (look for effects)
  confirmation_window: Extended window for secondary verification
  expiry:           Time after which the claim can no longer serve as current fact
```

Example (collection):

```text
before:    frame 100-110 — no toast present
action:    frame 111 — execute interaction
observe:   frame 112-150 — look for toast
confirm:   frame 151-240 — inventory change
expiry:    10 seconds — if not confirmed, claim downgrades to tentative
```

### 4.6 Default Stabilization Windows

```text
ui_screen_transition:   800ms
dialogue_advance:       500ms
inventory_delta:        1200ms
collection_pickup:      900ms
teleport_loaded:        1500ms
navigation_arrival:     700ms
combat_target_killed:   1200ms
boss_phase_changed:     1800ms
danger_cleared:         3 consecutive safe frames + 200ms
generic_unknown:        1000ms
```

Auto-adjustment rule:

```text
if next_action failure rate > 20% after a claim family:
  increase stabilization window by 30%
if next_action failure rate < 5%:
  slowly decrease (never below family default)
```

---

## 5. Control Plane 2: Uncertainty Engine

### 5.1 Uncertainty Exit Policy

Uncertainty is not a stable end state. It must have a fixed exit strategy:

```text
UNCERTAIN
→ resample_observation (wait and re-capture)
→ alternate_verifier (use different verification method)
→ safe_probe (try a minimal action to gather more signal)
→ local_recovery (attempt recovery without replanning)
→ human_confirm (ask user)
→ abort_safe (clean shutdown)
```

Different action types use different exit strategies:

```text
Collection:
  toast seen but inventory not verified
  → wait 1.5s resample
  → open inventory for secondary verification
  → still uncertain → record delayed_audit
  → mark as tentative_success, not fully verified

Combat:
  screen_state=combat but enemy not stable
  → wait for N consecutive frames of stable target/danger/resource signals
  → timeout → target_acquire_failed

UI Click:
  click produced no screen_state change
  → retry once
  → OCR rescan
  → fallback anchor
  → still failed → ANCHOR_CLICK_NO_EFFECT
```

### 5.2 Risk-Stratified Thresholds

Risk level is declared at Mission design time, not guessed at runtime.

```text
LOW:      min_auto_execution = 0.60, min_auto_replan = 0.50, human_confirm = false
MEDIUM:   min_auto_execution = 0.70, min_auto_replan = 0.60, human_confirm = when_uncertain_or_replan_loop
HIGH:     min_auto_execution = 0.80, min_auto_replan = 0.70, human_confirm = required_for_low_reliability_skill
CRITICAL: auto_execution = false, human_confirm = always
```

### 5.3 Max Replan Cycles

```text
MAX_REPLAN_CYCLE_PER_NODE = 3
```

Beyond this limit: safe abort with evidence snapshot.

### 5.4 Plan Quality Checklist

Every LLM replan must pass structural pre-check before execution:

```text
- At least one usable Skill exists for the proposed action
- Skill reliability exceeds risk-specific threshold
- Verifier exists for the claim type
- No circular dependencies in the plan
- Does not repeat a path that just failed
- Does not violate safety/risk policy
```

### 5.5 Low-Confidence Hard Stop

If ALL candidate actions are below threshold:

```text
stop → show evidence snapshot → ask user
```

LLM may explain and rank options, but CANNOT break through the reliability gate.

---

## 6. Control Plane 3: Audit Engine

### 6.1 Delayed Audit

Immediate verification is not enough to measure false accept rate. Delayed audits compare a claim against a captured execution snapshot.

```text
AuditSnapshot:
  claim_id: str
  claimed_delta: dict
  execution_snapshot:
    inventory_before
    position_before
    screen_state_before
    team_state_before
    active_task_before
    timestamp
  audit_target:
    expected_delta
    allowed_external_mutation
  audit_result: AuditResult
```

The snapshot captures the **global state at execution time**, not just "current inventory". This prevents the "user consumed items mid-task" contamination problem.

### 6.2 Audit Results

```text
matched:       Claim confirmed by post-hoc verification
mismatch:      Claim contradicted by post-hoc verification (false accept detected)
contaminated:  External activity made audit data unreliable
unverifiable:  No viable verification method available at audit time
```

### 6.3 Contaminated Audit Handling

`contaminated` is not success and not failure. It means "this Skill currently cannot be reliably measured."

```text
contaminated_rate = contaminated_audits / total_audits

if contaminated_rate > 0.5:
  → switch to low_activity_window_audit
  → only audit during 30+ second idle periods

low_activity_window_audit consecutive failures >= 3:
  → mark skill as audit_difficult

audit_difficult skill:
  - Does NOT enter normal reliability pyramid
  - Cannot be automatic main path for high-risk missions
  - Can only participate in low-risk missions with tentative reliability
  - UI explicitly shows: "This Skill is difficult to auto-audit"
```

### 6.4 False Negative Detection via Downstream Tracing

When a downstream claim is verified but its upstream was previously demoted:

```text
downstream claim verified
→ check all upstream dependencies
→ if upstream is demoted/suspect:
   → structural evidence suggests upstream was likely correct (false negative)
   → revalidate upstream to "tentative"
   → record FalseNegativeReport
   → update verifier's false_negative_estimate
```

This prevents the system from treating a correct action as failed just because a single verifier missed the signal.

---

## 7. Control Plane 4: Reliability Engine

### 7.1 Three-Layer Statistical Model

Reliability is tracked at three granularities, answering different questions:

**Layer 1: VerifierReliability**

```text
Question: Is this witness (verifier/signal family) trustworthy?

Key:     verifier_id + source_family + context_key

Metrics:
  support_correct: int
  support_wrong: int
  refute_correct: int
  refute_wrong: int
  false_positive_estimate: float
  false_negative_estimate: float
  contaminated_rate: float
  latency_p95: float
  sample_count: int
  wilson_lower_bound: float

Usage:
  - ClaimAdjudicator weights EvidenceVotes
  - Detect if a verifier's failure reports might be false negatives
  - Decide whether to use alternate verifier
```

**Layer 2: RecipeReliability**

```text
Question: Is this ClaimRecipe's overall adjudication reliable?

Key:     claim_type + recipe_id + capsule_id + context_key

Metrics:
  adjudicated_verified: int
  adjudicated_rejected: int
  delayed_audit_matched: int
  delayed_audit_mismatch: int
  disputed_rate: float
  uncertain_rate: float
  audit_difficult_rate: float
  wilson_lower_bound: float

Usage:
  - Determine if a recipe can serve as terminal claim basis
  - Determine if custom_mapping can graduate from bootstrap to trusted
  - Detect if Core recipe degrades under a specific Capsule
```

**Layer 3: SkillClaimReliability**

```text
Question: Is this Skill's claim reliable in this context?

Key:     skill_id + claim_type + recipe_id + context_key

Metrics:
  claim_verified: int
  claim_rejected: int
  claim_demoted: int
  delayed_audit_matched: int
  delayed_audit_mismatch: int
  cascade_invalidated_count: int
  recovery_success_rate: float
  mean_time_to_recover: float
  wilson_lower_bound: float

Usage:
  - Planner selects Skills
  - Capability Reliability Gate determines auto-execution permission
  - Detect Skill reliability varies by context
```

### 7.2 How the Three Layers Compose

```text
ClaimAdjudicator uses:
  EvidenceVote.weight = signal_quality × VerifierReliability × context_match × freshness × drift_penalty
  recipe_trust = RecipeReliability × custom_mapping_penalty × audit_difficulty_penalty

Planner/Gate uses:
  skill_claim_trust = SkillClaimReliability with context backoff

Final auto-execution gate:
  execution_trust = min(recipe_trust, skill_claim_trust, dependency_health)
```

**Why `min` instead of average or multiplication?**

Because this is a safety gate. Any single短板 — unreliable recipe, unreliable skill, unhealthy dependency — should block auto-execution. Average masks weaknesses.

### 7.3 Reliability Pyramid (Context Backoff)

Context is not tracked at a single granularity. The system uses a pyramid:

```text
L0: global + skill
L1: capsule + skill
L2: capsule + skill + screen_state + mission_phase
L3: L2 + target_class
L4: L3 + profile_bucket
L5: L4 + game-specific dimension (boss_id, team_archetype, route_id, etc.)
```

Default query levels differ per entity:

```text
VerifierReliability:  default L2 (verifiers mainly affected by screen_state/profile)
RecipeReliability:    default L2/L3 (recipes affected by claim_type and scene)
SkillClaimReliability: default L3/L4 (skills strongly depend on target, path, team, boss)
```

When samples are insufficient at the target level, back off to coarser level with `sample_sufficiency_penalty`.

### 7.4 Confidence Computation

Confidence is always system-computed. LLM never produces these values.

```text
confidence =
  signal_quality          # spatial, OCR, detector, frame consistency, temporal pattern, cross-signal agreement
  × verifier_historical_reliability  # Wilson lower bound from VerifierReliability
  × context_match_score   # how similar current context is to verified contexts
  × sample_sufficiency    # penalty for insufficient historical samples
  × drift_penalty         # penalty for detected environment version drift
```

### 7.5 Drift Detection

```text
DriftDetector checks:
  layout_shift_score
  ocr_anchor_shift_score
  template_match_drop
  detector_confidence_drop
```

When drift is detected:

```text
Affected VerifierReliability entries get drift_penalty = 0.5
Affected RecipeReliability entries marked as degraded
Affected SkillClaimReliability entries demoted to bootstrap mode
Historical data preserved but excluded from current decisions
System requests recalibration
```

Skills are NOT deleted — they return to bootstrap mode until new evidence is collected.

---

## 8. Control Plane 5: Decision Memory

### 8.1 Distillation Pipeline

Raw RunJournal is not LLM context. It is distilled through multiple stages:

```text
RunJournal (raw event stream)
  → EpisodeAnalyzer (pattern extraction)
    → DecisionMemoryPacket (actionable conclusions)
      → LLM Context (structured strategy packet)
```

### 8.2 LLM Receives

The LLM does NOT read hundreds of raw decisions. It receives:

```text
current_goal: str
last_successful_approach: str
current_obstacle: str
recovery_options: list[RecoveryOption]
confidence_this_works: float     # system-computed, not LLM-estimated
do_not_repeat: list[str]        # paths that failed recently
evidence_refs: list[str]        # link to archived evidence
reliable_known_facts: list[str]
suspect_claims: list[str]
required_user_confirmation_points: list[str]
```

### 8.3 LLM Role Boundaries

LLM CAN:
- Understand user goals
- Explain failures
- Select strategies from presented options
- Generate candidate replan proposals
- Communicate with user

LLM CANNOT:
- Judge whether an action succeeded
- Judge whether a verifier is trustworthy
- Estimate real confidence
- Make millisecond-level recovery decisions
- Act as final fact judge
- Produce confidence, reliability, false_accept_rate, or success_probability values

---

## 9. Verifier System

### 9.1 Design Principle: Claim-Driven, Not Verifier-Driven

Developers do NOT choose verifiers. They declare what claim they want to prove. The system automatically recommends and compiles a verifier bundle.

```text
Developer writes:
  produced_claim:
    type: inventory_delta
    target: qingxin
    delta: +1
    risk_level: low

System generates:
  verifier_bundle with primary/secondary/delayed_audit signals
```

### 9.2 Three-Layer Verifier Architecture

**Layer 1: Declarative Verifiers (covers ~80% of scenarios)**

System provides a set of verification primitives. Developers write YAML, not Python.

Available types:

```text
screen_state_match / transition / stable
element_appearance / disappearance
text_match / regex_match
anchor_exists / anchor_not_exists
color_region_change
numeric_delta
progress_threshold
danger_score_below
temporal_pattern_match
composite: all_of / any_of / vote
```

Example declarations:

```yaml
# Screen state transition
verifier:
  type: screen_state_transition
  from: overworld
  to: combat
  timeout_ms: 3000

# Text match
verifier:
  type: text_match
  roi: dialog_area
  contains: "+1 清心"
  timeout_ms: 1500

# Composite
verifier:
  type: composite
  all_of:
    - type: screen_state_stable
      state: overworld
      frames: 5
    - type: element_disappeared
      roi: loading_area
      anchor: loading_spinner
```

**Layer 2: VLM Verifiers (supplementary signal only)**

For scenarios that cannot be expressed declaratively. Hard constraints:

```text
VLM confidence ceiling <= 0.70
VLM-only claim CANNOT be terminal success in strict/high risk mode
VLM output must pass VisionOutputGuard
VLM result must enter cross-signal agreement, NOT directly determine success
```

Suitable for:
- Unknown UI state interpretation
- Boss phase coarse classification
- Dialog/popup semantic understanding
- Failure reason explanation

NOT suitable for:
- Whether inventory incremented
- Whether target was killed
- Whether reward was claimed
- Whether it's safe to continue auto-operation

**Layer 3: Custom Python Verifiers (rare exceptions)**

Only for Capsule-specific business logic. Must register as Capsule provider. Must have tests and schema.

Suitable for:
- HSR SP/turn/auto-battle state tracking
- Genshin elemental reaction chains
- Complex temporal patterns
- Capsule-specific domain logic

### 9.3 VerifierBundle

A VerifierBundle is the complete verification configuration for a claim type:

```yaml
verifier_bundle:
  claim_type: inventory_delta
  primary:
    - type: text_match
      roi: toast_area
      contains_any: ["清心", "+1"]
  secondary:
    - type: element_disappeared
      anchor: collect_prompt
    - type: screen_state_stable
      state: overworld
      frames: 5
  delayed_audit:
    - type: inventory_count_delta
      item: qingxin
      expected_delta: 1
  uncertainty_policy:
    on_low_confidence: resample_then_inventory_audit
```

### 9.4 ClaimRecipe

ClaimRecipe defines the evidence structure required for a claim type:

```yaml
claim_type: inventory_delta
required_families:
  - inventory_delta
optional_families:
  - toast
  - prompt_disappeared
  - screen_stable
negative_families:
  - inventory_full
min_independent_support_families: 2
terminal_requires:
  - delayed_audit_or_inventory_delta
vlm_allowed: supplement_only
family_correlations:
  - families: [toast, prompt_disappeared]
    correlation: 0.6   # reserved for MVP+; prevents noisy-or over-estimation
```

### 9.5 VerifierCompiler

```text
Developer declares claim
→ VerifierCompiler looks up ClaimRecipe
→ Auto-generates VerifierBundle
→ Developer confirms or adjusts ROI/anchor/text/thresholds
→ System dry-run validates
→ Failure samples feed into delayed audit and reliability store
```

**Mapping rules**:

```text
Core Verifier Recipes:
  Universal claim_type → verifier_bundle templates
  Quality controlled, tested, versioned

Capsule Verifier Recipes:
  Game-specific claim_types, or parameterized extensions of core recipes
  Can shadow core recipe with custom_mapping = true
  Shadow triggers strict reliability audit

Override Policy:
  Capsule can shadow core recipe
  But must be marked custom_mapping
  bootstrap_reliability = low
  requires_audit = true
  cannot_use_for_high_risk_until_samples_sufficient = true
```

### 9.6 VerifierRouter (Runtime)

At runtime, VerifierRouter dynamically selects verification paths based on:

```text
Verification Budget:
  verify_budget_ms: int       # time budget for this claim's verification
  max_compute_cost: float     # GPU/compute budget
  allow_vlm: bool             # whether VLM verification is permitted
  allow_resample: bool        # whether resampling is permitted
  deadline_ms: int            # hard deadline
  risk_level: RiskLevel       # controls budget allocation
  action_window_sensitivity: float  # how time-critical the next action is
```

Default budgets:

```text
LOW:      verify_budget_ms = 500, declarative only, no VLM
MEDIUM:   verify_budget_ms = 1500, declarative + one resample
HIGH:     verify_budget_ms = 3000, declarative + resample + optional VLM supplement
CRITICAL: no auto finalization, human confirm required
```

Cost dimensions:

```text
latency_cost:        VLM = 500ms-2s, template match = 5ms
compute_cost:        GPU load impact on game + YOLO + VLM
opportunity_cost:    Time spent verifying may miss next action window
reliability_risk:    Low-reliability verifier as final judge = high risk
```

Router solves:

```text
maximize expected_confidence_gain
subject to:
  time_cost <= verify_budget_ms
  compute_cost <= current_budget
  opportunity_cost <= allowed_window_loss
  risk_policy satisfied
```

### 9.7 False Negative Handling

When verifier reports failure but alternative signals suggest success:

```text
Case 1: Visual signal missed (frame gap)
  → Wait 1-2s, recapture, re-verify

Case 2: Proxy correct but game state wrong (game bug)
  → Detect via downstream claim verification

Case 3: Proxy signal itself unstable
  → Multi-signal cross-validation
```

VerifierResult extended fields:

```text
alternative_signals: list[SignalCorroboration]
downstream_effects_verified: list[str]
false_negative_likelihood: float
re_verify_recommended: bool
```

---

## 10. ClaimAdjudicator

### 10.1 Algorithm: Rule Engine + Statistical Correction

The adjudicator uses ClaimRecipe-driven structural gates combined with statistical confidence:

```text
1. Load ClaimRecipe
2. Collect ObservationClaims
3. Normalize into EvidenceVotes
4. Check dependency health
5. Check time windows / stabilization
6. Apply structural gates (evidence structure sufficient?)
7. Compute confidence (statistical)
8. Resolve conflicts (conservative)
9. Emit adjudication status + next_action
```

### 10.2 EvidenceVote Structure

Verifier output is NOT `ok/fail`. It is an evidence vote:

```text
EvidenceVote:
  claim_id: str
  source_family: str               # e.g. "toast", "inventory", "anchor"
  polarity: support | refute | neutral
  signal_quality: float
  verifier_reliability: float
  context_match: float
  temporal_fit: float
  freshness: float
  independence_group: str          # votes in same group cannot be simply summed

vote_weight = signal_quality × verifier_reliability × context_match × temporal_fit × freshness
```

Votes in the same `independence_group` cannot be simply summed. They are aggregated conservatively:

```text
toast_ocr:     0.82
toast_template: 0.78
toast_vlm:     0.65
→ toast family aggregate ≈ 0.82 (not 2.25)
```

### 10.3 Structural Gates (Before Confidence)

Structure is checked BEFORE confidence is computed:

```text
inventory_delta example:

Only toast support:
  → tentative / uncertain, NOT verified

Toast + prompt disappeared:
  → tentative_success + delayed_audit

Toast + inventory_count_delta:
  → verified

inventory_full refute:
  → rejected or disputed
```

This prevents "high-confidence OCR single signal" from directly judging a terminal claim as success.

### 10.4 Conflict Resolution

When support and refute are both strong:

```text
support_score = 0.82, refute_score = 0.79
→ CANNOT pick the higher one
→ Output: disputed
→ next_action: alternate_verify / delayed_audit / human_confirm
```

Rules:

```text
strong_support AND strong_refute → disputed
support enough BUT required family missing → tentative or uncertain
refute blocker present AND reliable → rejected
evidence weak BUT recoverable → uncertain
evidence strong AND structure complete → verified
```

### 10.5 Output States

```text
verified:    Evidence sufficient, confidence above threshold
tentative:   Support exists, needs delayed audit
uncertain:   Evidence insufficient
disputed:    High-quality evidence conflicts
rejected:    Determined false
suspect:     Upstream dependency or drift affected
expired:     Evidence stale, cannot be referenced
```

### 10.6 Independent Family Aggregation

Uses noisy-or for independent families, with correlation discount:

```text
P(support) = 1 - Π(1 - correlated_family_weight)

where correlated_family_weight = family_weight × (1 - correlation × other_family_weight)
```

`family_correlations` declared in ClaimRecipe schema (reserved for MVP+):

```yaml
family_correlations:
  - families: [toast, prompt_disappeared]
    correlation: 0.6
```

### 10.7 Final Confidence Formula

```text
support_confidence = independent_family_aggregate(support_votes)
refute_confidence  = independent_family_aggregate(refute_votes)

confidence =
  support_confidence
  × dependency_health
  × recipe_completeness
  × sample_sufficiency
  × drift_penalty
  × (1 - refute_confidence × conflict_penalty)
```

---

## 11. MissionGraph (DAG)

### 11.1 MissionGraph is a DAG, Not a List

```text
MissionGraph: records action dependencies (what to do in what order)
ClaimGraph:   records fact dependencies (what is true and why)

Planner rerouting must consult both:
  MissionGraph: which alternative paths exist?
  ClaimGraph:   which paths depend on now-untrusted facts?
```

### 11.2 Alternative Paths

MissionGraph nodes declare alternative branches:

```text
Node A → [B, C] → D

If B is blocked (dependency claim unverifiable):
  → Try path through C instead
  → If no alternative exists → abort
```

### 11.3 Unverifiable Claim Policy

Claims are categorized by their role in the mission:

```text
informational_claim:
  Only affects explanation, not subsequent decisions
  → Can continue as tentative

local_claim:
  Only affects current node
  → low risk: tentative continue + delayed audit
  → medium: alternate verifier or safe_probe
  → high/critical: block

dependency_claim:
  Subsequent nodes depend on it
  → Cannot silently continue
  → Must reverify / alternate verifier / skip dependent branch / human confirm

terminal_claim:
  Determines mission completion
  → Unverifiable cannot declare mission success
```

**Unverifiable Budget** per mission:

```text
mission_unverifiable_budget:
  max_count: int              # max unverifiable claims allowed
  max_weight: float           # max cumulative risk weight
  allowed_claim_types: list   # which types can be unverifiable
  allowed_risk_levels: list   # which risk levels can be unverifiable
  terminal_claim_requires_verification: true
```

**Unattended mode policies**:

```text
unattended_mode = conservative:
  dependency/terminal unverifiable → safe pause

unattended_mode = opportunistic:
  low-risk local unverifiable → tentative continue
  budget exceeded → safe pause

unattended_mode = supervised:
  prompt human confirm

Defaults:
  Low-risk daily:      opportunistic
  Medium-risk task:    conservative
  High-risk/boss:      supervised or conservative
  Critical:            supervised
```

---

## 12. Graph Implementation

### 12.1 Custom Python, Not LangGraph

LangGraph solves "LLM workflow orchestration" (multi-step dialog, tool calling). Aurora's graphs are domain-specific fact ledgers and action DAGs. No framework handles:

```text
Claim lifecycle state machines
Evidence aggregation
Cascade invalidation with cluster isolation
Budget-constrained verification
Risk-stratified adjudication
```

### 12.2 Implementation

```text
Underlying structure: Python native dict + set (no third-party graph library)
Domain models: Custom dataclasses (StateDeltaClaim, ObservationClaim, AdjudicationEvent)
Graph operations: Custom (DAG traversal, path finding, cluster detection, cascade demotion)
Persistence: JSON/pickle + EvidenceStore file archive
```

Core data structures:

```python
class ClaimGraph:
    _claims: dict[str, StateDeltaClaim]
    _observations: dict[str, ObservationClaim]
    _adjudications: dict[str, AdjudicationEvent]
    _depends_on: dict[str, set[str]]      # claim_id → upstream claim_ids
    _dependents: dict[str, set[str]]      # claim_id → downstream claim_ids (reverse index)
    _evidence: dict[str, list[str]]       # claim_id → observation_ids

    def add_claim(claim, depends_on): ...
    def add_observation(obs, supports): ...
    def adjudicate(claim_id, event): ...
    def get_dependent_cluster(claim_id) -> set[str]: ...     # cascade invalidation
    def demote_cascade(claim_id, reason) -> list[str]: ...
    def get_verified_claims() -> list[StateDeltaClaim]: ...
    def get_suspect_claims() -> list[StateDeltaClaim]: ...
    def is_dependency_satisfied(claim_id) -> bool: ...
    def compact_old_claims(before_time) -> int: ...
```

MissionGraph:

```python
class MissionGraph:
    _nodes: dict[str, MissionNode]
    _edges: dict[str, set[str]]            # node_id → downstream node_ids
    _alternatives: dict[str, set[str]]     # node_id → alternative node_ids

    def find_path_to(target, avoid) -> list[str] | None: ...
    def find_alternative_path(blocked_node) -> list[str] | None: ...
    def mark_node_blocked(node_id, reason): ...
```

---

## 13. Integration Points with Existing Aurora

### 13.1 Modified Classes

```text
SkillResult:
  + claim_id: str | None          # Links execution to claim tracking
  + claim_status: ClaimStatus     # Current claim status

VerifierResult:
  + alternative_signals: list[SignalCorroboration]
  + downstream_effects_verified: list[str]
  + false_negative_likelihood: float
  + re_verify_recommended: bool

MissionNode:
  + risk_level: RiskLevel         # Declared at Mission design time
  + unverifiable_budget: UnverifiableBudget

RunCheckpoint:
  + claim_refs: list[str]         # Checkpoint carries claim references for resume validation
```

### 13.2 New Classes

```text
StateDeltaClaim, ObservationClaim, AdjudicationEvent
ClaimGraph, MissionGraph
ClaimRecipe, VerifierBundle, EvidenceVote
ClaimAdjudicator
VerifierCompiler, VerifierRouter
ReliabilityStore (3 layers: VerifierReliability, RecipeReliability, SkillClaimReliability)
DelayedAuditor
DriftDetector
EpisodeAnalyzer, DecisionMemoryPacket
UncertaintyPolicy
PlanQualityChecklist
ClaimProducingExecutor (integrates all 5 control planes)
```

### 13.3 StateBus Extensions

```text
New dynamic slots:
  claim_graph_state     # current claim graph summary
  reliability_summary   # current reliability stats
  drift_status          # drift detection status
```

---

## 14. Claim-Producing Executor Pipeline

The `ClaimProducingExecutor` bridges skill execution and the Claim-Centric Runtime:

```text
1. Pre-flight:
   - Reliability gate check (is this Skill reliable enough for this context?)
   - UncertaintyPolicy decision (should we proceed?)

2. Execute:
   - Skill runs with InputLease
   - Capture AuditSnapshot (world state before execution)

3. Produce:
   - Create StateDeltaClaim from signals
   - Claim enters ClaimGraph as "tentative"

4. Verify:
   - VerifierRouter selects verification path within budget
   - Verifiers produce ObservationClaims
   - ClaimAdjudicator emits AdjudicationEvent
   - Claim status updated (verified/uncertain/rejected)

5. Audit:
   - Create DelayedAuditRecord with execution snapshot
   - Schedule for post-task or 5-10 minute verification

6. Record:
   - Update ReliabilityStore (all 3 layers)
   - Update StabilizationTracker
   - Run DriftDetector

7. Distill:
   - EpisodeAnalyzer processes events into DecisionMemoryPacket
   - Available for next LLM replan context
```

---

## 15. MVP Acceptance Criteria

The MVP is complete when tests demonstrate:

1. **Claim confidence is system-computed** — LLM never produces confidence values
2. **Inferred dependencies produce declaration-gap warnings** — DEPENDENCY_DECLARATION_GAP events
3. **Cascade invalidation is cluster-scoped** — not global abort, not unbounded propagation
4. **False negatives detected via downstream chain tracing** — demoted claims revalidated when downstream succeeds
5. **Low-confidence options trigger user confirmation or safe abort** — not LLM picking least-bad option
6. **Contaminated audits do not update reliability** — and can mark a Skill as audit_difficult
7. **Reliability uses context backoff and risk-stratified thresholds** — no single flat score
8. **Stabilization windows auto-adjust** based on failure rate history
9. **Drift detection identifies environment version changes** — demotes to bootstrap mode
10. **DecisionMemory summarizes reusable conclusions** — not exposing raw logs
11. **PlanQualityChecklist validates replan proposals** — rejects low-reliability, circular, repeated-failure plans
12. **ClaimProducingExecutor integrates all 5 control planes end-to-end**

### MVP Validation Tasks

```text
HSR:
  Menu → Quest/Rewards → Auto-battle/Claim → Delayed audit reward changes

Genshin:
  Teleport → Navigate → Collect → Verify toast → Delayed audit inventory changes
```

Each task must produce a complete pipeline output:

```text
claim → evidence → uncertain exit (if applicable) → audit result
→ reliability update → planner gate decision
```

---

## 16. MVP Implementation Decisions

### 16.1 MVP Scope

**Included in MVP:**

```text
1. StateDeltaClaim + ClaimGraph (with per-mission lifecycle)
2. Simplified ClaimAdjudicator (ClaimRecipe gates + source-family dedup + reliability weighting)
3. VerifierReliability (Layer 1 reliability tracking)
4. SkillClaimReliability (Layer 3 reliability tracking)
5. DelayedAudit queue (persistent, three trigger types)
6. UncertaintyPolicy (6-level exit)
7. Claim YAML schema (for Skill declarations)
8. Legacy VerifierResult / SkillResult compatibility bridge
```

**Excluded from MVP (schema reserved, logic deferred):**

```text
RecipeReliability: schema exists, does not participate in main decisions
family_correlations: schema reserved in ClaimRecipe, MVP only does source-family dedup
Complex EpisodeAnalyzer: fixed template output, no LLM summarization
Smart VerifierCompiler: lookup table only, no auto-reasoning
Full MissionGraph rerouting: DAG data structure + simple alternative path only
```

### 16.2 DelayedAudit Scheduling

Three trigger types:

```text
post_node_audit:
  Triggered after MissionNode completion, short delay
  Suitable for: UI changes, reward claims, pickups

mission_terminal_audit:
  Triggered after Mission reaches terminal node
  Suitable for: inventory deltas, total rewards, mission completion

low_activity_audit:
  Triggered when 30+ seconds of low activity detected
  Suitable for: skills prone to contamination
```

AuditScheduler manages a persistent queue:

```text
AuditRecord:
  audit_id: str
  claim_id: str
  due_at: float
  deadline_at: float
  audit_type: post_node | mission_terminal | low_activity
  snapshot_ref: str        # reference to AuditSnapshot in EvidenceStore
  status: pending | completed | contaminated | unverifiable | expired
  retry_count: int
  result: AuditResult | None
```

**Persistence**: All pending audits are serialized to `pending_audits.jsonl` (transaction log) at capture time. On Aurora restart, the log is automatically loaded and pending audits are resumed.

**Scheduling**:

```text
Dual-track scheduling:
  Track A (Node-completion trigger):
    MissionNode completes → wait stabilization_window_ms → immediate audit attempt
    If high-frequency interaction detected → defer to Track B

  Track B (Idle monitor):
    Background timer (every 60s) scans pending queue
    Executes audits during CPU/GPU low-load windows
    Suitable for contaminated-prone skills
```

Edge cases:

```text
User closes game before audit:
  before deadline → persists in pending_audits.jsonl, resumes on next session
  after deadline → marked expired
  external state contamination → marked contaminated
  restart within 5 min of snapshot → attempt re-audit
  restart after 5 min of snapshot → mark unverifiable + emit DECLARATION_GAP warning

Audit result writeback:
  matched/mismatch → immediately updates in-memory ReliabilityStore + async flush to JSON/SQLite
  contaminated/unverifiable → does NOT update success rates, only audit_difficulty stats
```

### 16.3 Zero-Sample Skill Bootstrap Policy

New Skills with Wilson lower bound = 0.0 are handled per risk level:

```text
LOW risk:
  Allow exploratory auto-run
  Delayed audit required
  Results marked "exploratory", do not enter trusted reliability

MEDIUM risk:
  Human confirm once
  After reaching sample threshold → can auto-run

HIGH risk:
  Not allowed as automatic main path
  Testbed / supervised only

CRITICAL risk:
  Always human confirm
```

Initial prior from same-Capsule average:
- Can be used for ranking/ordering suggestions only
- CANNOT be used for safety gate decisions
- Must not disguise new Skills as reliable assets

**Design decision (Codex vs Gemini divergence)**:

```text
Option A (Codex): Safety gate always sees Wilson = 0.0 for zero-sample Skills.
  No prior enters safety computation. Period.
  Prior only used for Planner path recommendation ordering.

Option B (Gemini): bootstrap_prior = 0.75 from Capsule average
  with extreme sample_sufficiency penalty making effective score very low.
  Mathematically elegant but risks "prior misleading" if penalty is miscalculated.

Chosen: Option A.
Rationale: Safety gates must never see a non-zero confidence for untested Skills.
           The risk of sample_sufficiency miscalculation is not worth the Bayesian elegance.
           Prior can inform Planner ordering but NEVER gate decisions.
```

### 16.4 DecisionMemory MVP Format

MVP uses deterministic EpisodeAnalyzer (no LLM summarization).

Input:

```text
MissionClaimGraph summary
RunJournal entries
Audit results
Failure clusters
Reliability deltas
```

Output (fixed JSON):

```json
{
  "mission_id": "...",
  "goal": "collect_qingxin",
  "successful_approaches": ["route_northeast"],
  "failed_approaches": ["route_west"],
  "do_not_repeat": ["route_west_failed_3_times"],
  "reliable_skills": ["genshin_collect_qingxin"],
  "suspect_claims": ["claim_42_inventory_delta_tentative"],
  "recommended_next_options": [
    {"skill": "genshin_collect_qingxin", "route": "northeast", "estimated_reliability": 0.72}
  ],
  "evidence_refs": ["mission_42_archive"]
}
```

Frequency:

```text
Mission end → always run
Major failure / cascade invalidation → incremental run
Session end → summary run
```

LLM may later produce user-readable summaries, but CANNOT write to fact fields or reliability fields.

### 16.5 Skill YAML Declaration Format

Concrete example for MVP:

```yaml
skill_id: genshin_collect_qingxin
capsule_id: genshin
version: 1
risk_level: low

capabilities_provided:
  - collect_material

input_claims:
  - type: navigation_arrival
    target: qingxin_node
    required_status: verified

required_world_facts:
  - screen_state: overworld
  - profile_ready: true

produced_claims:
  - claim_type: inventory_delta
    target: qingxin
    delta: 1
    claim_role: terminal            # informational | local | dependency | terminal
    stabilization_window_ms: 900
    verifier_recipe: inventory_delta.default
    delayed_audit:
      type: inventory_count_delta
      item: qingxin
      expected_delta: 1

semantic_actions:
  - type: interact
    target: collect_prompt

failure_modes:
  - code: CLAIM_UNCERTAIN
    policy: resample_then_delayed_audit
  - code: AUDIT_MISMATCH
    policy: mark_skill_suspect
```

Developers declare Claims. They do NOT hand-write verifier classes.

**HSR example (reward claim):**

```yaml
skill_id: hsr_claim_rewards
display_name: "Honkai: Star Rail Daily Reward Claimer"
kind: menu_interaction_skill
risk_level: low

capabilities_provided:
  - hsr_reward_claim

resources:
  - hsr_screen_regions
  - hsr_keymap

produced_claims:
  - claim_type: inventory_delta
    target: stellar_jade
    delta: +60
    claim_role: terminal
    stabilization_window_ms: 1200
    verifier_bundle:
      primary:
        - type: text_match
          roi: toast_area
          contains: "+60"
          timeout_ms: 1500
      secondary:
        - type: element_disappeared
          anchor: active_claim_button
          timeout_ms: 2000
      delayed_audit:
        - type: currency_check
          currency: stellar_jade
          expected_delta: 60
      uncertainty_policy:
        on_low_confidence: resample_then_inventory_audit
        max_retries: 2

input_claims:
  - type: screen_state_match
    target: hsr.screen_state
    expected: reward_menu
    required_status: verified
  - type: screen_state_match
    target: hsr.cooldown_state
    expected: ready
    required_status: verified

required_world_facts:
  - hsr_active_session: true
```

### 16.6 Migration Strategy (Gradual, Not Big Bang)

**SkillResult evolution:**

```text
Existing fields preserved:
  skill_name, status, failure_code, started_at, finished_at, payload, verifier_result

New fields added:
  + claims: list[StateDeltaClaim]
  + claim_graph_refs: list[str]

Old tests continue using status/payload.
New Claim path activated through adapter bridge.
```

**VerifierResult evolution:**

```text
Existing fields preserved:
  ok, verifier_id, confidence, reason, evidence, frame_id, roi_ids, detection_confidence

New fields added:
  + observation_claims: list[ObservationClaim]
  + evidence_votes: list[EvidenceVote]
  + source_family: str
  + alternative_signals: list[SignalCorroboration]
  + downstream_effects_verified: list[str]
  + false_negative_likelihood: float
  + re_verify_recommended: bool
```

**Adapter bridge for existing verifiers:**

```text
Existing Python verifiers wrapped in DeclarativeVerifierAdapter:
  ObservationGraphUIVerifier → adapter → produces ObservationClaims
  NavigationProgressVerifier → adapter → produces ObservationClaims
  CombatDangerClearedVerifier → adapter → produces ObservationClaims
```

Old verifiers continue to work. Adapter translates their VerifierResult into the new Claim pipeline.
Once ClaimRuntime is stable, gradually convert them to YAML recipe declarations.

### 16.7 ClaimProducingExecutor Placement

ClaimProducingExecutor is NOT a sixth plane. It does NOT replace the Execution plane.

It is a **fact-commitment layer between Execution and Orchestration**:

```text
[ Orchestration Plane (MissionGraph) ]
              |  Sends MissionNode
              v
=== [ ClaimProducingExecutor (The Bridge) ] ====================
  - Pre-flight: Check SkillClaimReliability Gate
  - Execute: Calls execution plane (with InputLease)
  - Verify: Calls perception plane (ObservationGraph) → ClaimAdjudicator
  - Audit: Registers DelayedAudit
================================================================
              |  Returns ClaimAdjudicationResult
              v
[ Orchestration Plane ]
  Decides to proceed / recover / replan based on verified/uncertain/rejected

[ Execution Plane (InputLease / InputWorker) ]
  Dispatches motor commands, produces InputReceipts
```

It spans two planes but does not replace either. It bridges the semantic gap between "action completed" and "world state changed as claimed."

Code organization:

```text
runtime/claim_runtime.py          # ClaimGraph + ClaimProducingExecutor
runtime/claim_adjudicator.py      # Adjudication engine
runtime/audit_scheduler.py        # DelayedAudit scheduling + pending_audits.jsonl persistence
execution/claim_adapter.py        # Bridge from legacy VerifierResult to new pipeline
reliability/reliability_store.py  # Three-layer reliability tracking
reliability/drift_detector.py     # Environment version drift detection
```

### 16.8 Implementation Phases

```text
Phase 1: Foundation
  - SkillResult / VerifierResult compatibility extensions
  - Claim YAML schema definition
  - ClaimProducingAdapter (legacy bridge)

Phase 2: Core Adjudication
  - ClaimAdjudicator MVP (rule engine + source-family dedup + reliability weighting)
  - VerifierReliability tracking
  - SkillClaimReliability tracking

Phase 3: Audit Loop
  - DelayedAuditScheduler with persistent queue
  - AuditSnapshot capture
  - Reliability writeback on match/mismatch

Phase 4: Verifier Infrastructure
  - Declarative VerifierRecipe lookup table
  - VerifierCompiler MVP (claim_type → bundle mapping)
  - Core recipes for common claim types

Phase 5: Mission Graph
  - MissionGraph DAG with alternative paths
  - UnverifiablePolicy + budget
  - Cluster-scoped cascade invalidation

Phase 6: Validation
  - HSR: Menu → Quest/Rewards → Auto-battle/Claim → Delayed audit
  - Genshin: Teleport → Navigate → Collect → Verify toast → Delayed audit
  - Each task produces full pipeline: claim → evidence → audit → reliability → gate decision
```

**Core principle: MVP builds the Claim data loop and reliability accumulation first. Smart compilation and full graph search come later.**

---

## 17. Engineering Decisions: 17 Critical Implementation Points

### 17.1 Concurrency Model (Q1)

**Decision: Single-writer event loop with immutable snapshots.**

```text
Execution thread / Verification thread / Audit thread
  → submit ClaimEvent to queue
  → ClaimGraphWorker single-threaded sequential apply
  → Readers access immutable snapshots
```

No multi-threaded writes to ClaimGraph. This prevents cascade, state machine, and audit writeback race conditions.

Readers (Orchestration, UI, Planner) always get consistent snapshots — never partial state.

**Alternative considered**: RLock (Gemini). Rejected because ClaimGraph operations (cascade invalidation, cluster computation) are multi-step and need atomicity beyond simple locking.

### 17.2 Claim Verification Pipeline (Q2)

**Decision: Dependency-gated optimistic pipeline.**

```text
B depends on A's verified/locked claim:
  MUST wait for A adjudication

B does NOT depend on A, or only depends on tentative-allowed claim:
  CAN proceed in parallel

A later rejected:
  Cascade marks B/C as suspect, rolls back or re-validates as needed
```

Default is conservative: dependency claims must be verified before downstream branches proceed.

### 17.3 P0 Interrupt During Claim Verification (Q3)

```text
Lease not yet executed:
  action claim → interrupted / expired

Lease executed but not yet verified:
  claim → uncertain_interrupted
  Cannot auto-count as success
  Must reobserve / reverify before resume

Post-P0 behavior:
  safe pause + release_all + checkpoint uncertain state
  No normal cascade propagation during emergency
```

### 17.4 ObservationGraph → ObservationClaim Bridge (Q4)

**ObservationGraph is the single source of truth. ObservationClaim is a "testimony slice" extracted by Verifiers.**

```text
ObservationGraphNode: raw structured observation (perception plane output)
ObservationClaim:     a Verifier's testimony about a specific claim
                      includes graph_id, frame_id, roi_id, node_refs, source_family, polarity
```

No parallel perception stream. All ObservationClaims reference ObservationGraph nodes.

### 17.5 DeclarativeVerifierEngine Implementation (Q5)

**Interpreter pattern: YAML config dispatched to Python handlers.**

```text
type: text_match       → TextMatchHandler
type: anchor_exists    → AnchorExistsHandler
type: screen_stable    → ScreenStableHandler
type: color_change     → ColorChangeHandler
type: numeric_delta    → NumericDeltaHandler
type: composite        → CompositeHandler (all_of / any_of / vote)
```

Handlers consume ObservationGraph nodes. They do NOT re-capture frames directly.
If fresh data is needed, handlers request Perception plane to re-sample.

### 17.6 Legacy Verifier Adapter Bridge (Q6)

**Universal wrapper with explicit metadata requirement.**

Old verifiers wrapped in `DeclarativeVerifierAdapter`. The adapter maps:

```text
VerifierResult.ok == True       → polarity: support
VerifierResult.ok == False      → polarity: refute
VerifierResult.confidence       → signal_quality (capped)
VerifierResult.verifier_id      → source_family
```

If old VerifierResult lacks required metadata:

```text
source_family: legacy_unknown
confidence_cap: 0.5
requires_migration_warning: true
```

The adapter does NOT guess business semantics. Unknown verifiers get low trust.

### 17.7 ReliabilityStore Persistence (Q7)

**JSONL event log + compacted JSON snapshot.**

```text
reliability_events.jsonl     Append-only, crash-safe (each line is a complete event)
reliability_snapshot.json    Periodic compaction of accumulated events
```

Write strategy: temp file + atomic `os.replace` rename. No SQLite in MVP.

### 17.8 Context Key Construction (Q8)

**ContextKeyBuilder assembles context tuples from defined sources.**

```text
Source mapping:
  capsule_id:     active capsule from CapsuleRegistry
  skill_id:       currently executing skill
  screen_state:   ObservationGraph / StateBus slot
  mission_phase:  MissionNode.type
  target_class:   TargetTrack / claim target / mission target
  profile_bucket: calibration profile hash
  game_specific:  Capsule provider optional dimension
```

All Reliability queries MUST go through ContextKeyBuilder. No ad-hoc tuple construction.

### 17.9 MissionGraph YAML Format (Q9)

```yaml
mission_id: genshin_collect_qingxin
risk_level: low
unattended_mode: opportunistic

unverifiable_budget:
  max_count: 3
  allowed_risk_levels: [low]
  terminal_claim_requires_verification: true

nodes:
  teleport:
    type: ui_interact
    skill: genshin_teleport
    produces: [location_loaded]

  collect_route_a:
    type: navigate
    skill: genshin_route_a
    depends_on: [teleport]

  collect_route_b:
    type: navigate
    skill: genshin_route_b
    depends_on: [teleport]
    alternative_for: collect_route_a

  collect:
    type: collect
    skill: genshin_collect_qingxin
    depends_on: [collect_route_a]

edges:
  - [teleport, collect_route_a]
  - [teleport, collect_route_b]
  - [collect_route_a, collect]
  - [collect_route_b, collect]
```

### 17.10 MissionGraph Authoring (Q10)

**Dual-track: YAML templates for daily tasks, Planner-generated DAG for complex/ad-hoc tasks.**

Both use the same schema. Planner output must pass `MissionGraphValidator` before execution.

### 17.11 Dry-Run/Testbed DelayedAudit Behavior (Q11)

```text
dry-run mode:
  Validates pipeline integrity only
  Uses synthetic snapshots + synthetic observed deltas
  Audit results marked "synthetic"
  Does NOT enter real ReliabilityStore
  Only enters test reliability namespace

testbed mode:
  Uses testbed state model (simulated inventory/location/HP)
  Can verify state transitions against simulated game state

real authorized window:
  Only mode that performs real profile audit
  Not a dependency for MVP
```

### 17.12 MVP Validation Task Execution (Q12)

```text
HSR UI flow (testbed):
  Testbed UI state machine + synthetic inventory/reward state

Genshin collect flow (testbed):
  Testbed pseudo-3D + synthetic route/progress/inventory state

Real-device phase (post-MVP):
  Calibration/profile binding + real-world measurement only
```

### 17.13 EpisodeAnalyzer Extraction Rules (Q13)

```text
successful_approaches:
  Claim chains with audited=matched OR verified with no later demotion

failed_approaches:
  Claim chains with rejected / demoted / audit mismatch

do_not_repeat:
  Same context + failure count >= 2 OR cascade_invalidated >= 1

reliable_skills:
  SkillClaimReliability >= risk threshold AND sample_count >= min_samples

suspect_claims:
  Status in: suspect / demoted / disputed / expired

recommended_next_options:
  Alternative paths with highest reliability AND not in do_not_repeat
```

Output is fixed JSON. No natural language as fact source.

### 17.14 Claim Event Propagation (Q14)

**Through StateBus publish/subscribe. No separate callback channels.**

```text
Event types published to StateBus:
  "claim_created"         — new claim entered graph
  "claim_adjudicated"     — status changed by adjudicator
  "claim_cascade"         — cascade invalidation triggered
  "audit_scheduled"       — delayed audit registered
  "audit_completed"       — audit result available
  "reliability_updated"   — ReliabilityStore entry changed
```

Orchestration, UI, AuditScheduler all subscribe to these events.

### 17.15 claim_graph_state Slot Content (Q15)

```text
claim_graph_state:
  mission_id: str
  graph_id: str
  active_claim_count: int
  latest_claim_id: str
  latest_status: ClaimStatus
  blocked_nodes: list[str]
  suspect_clusters: list[set[str]]
  unresolved_uncertain_count: int
  updated_at: float
```

Published on every claim status change. Full graph details via ClaimGraphStore query, not in slot.

### 17.16 ClaimAdjudicator Failure Handling (Q16)

```text
ClaimAdjudicator throws exception:
  → claim status = adjudication_error
  → next_action = safe_pause
  → emit claim_adjudication_error event
  → do NOT update ReliabilityStore
  → downstream treats as high-risk uncertain
  → does NOT auto-continue
```

### 17.17 ReliabilityStore Corruption Recovery (Q17)

```text
Snapshot corrupted:
  → Rebuild from JSONL event log

JSONL tail corrupted:
  → Truncate to last valid record

Fully corrupted:
  → ReliabilityStore reset
  → All Skills enter bootstrap mode
  → High-risk auto-run disabled until new samples collected

Write safety:
  → temp file + atomic os.replace rename
  → Integrity check on startup
```

---

## 18. Open Questions (Post-MVP)

1. **Conditional reliability granularity**: L3/L4 may be too fine-grained for rare contexts. Need empirical calibration after initial data collection.

2. **DecisionMemory distillation algorithm**: EpisodeAnalyzer's pattern extraction is not yet specified. Needs research on what patterns are most useful for LLM replanning.

3. **Temporal pattern matching language**: The `temporal_pattern_match` verifier type needs a concrete DSL for declaring temporal expectations (e.g., "glow intensity monotonically increases for 30 frames").

4. **Cross-mission reliability transfer**: When a new mission starts, how much of the previous mission's reliability data transfers? Full context or just coarse statistics?

5. **Calibration Wizard integration**: How does the initial user calibration interact with ClaimRecipe validation? Can calibration produce baseline reliability for common claim types?

---

All implementation remains scoped to dry-run/testbed/authorized safe-window abstractions. No real client automation, no memory reading, no anti-cheat bypass.
