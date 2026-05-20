# Aurora Stage 44-47 Execution Blueprint

Date: 2026-05-21

Audience: implementation Code Agent that will work for a long uninterrupted run.

Purpose: turn the Aurora hardcore moat strategy into executable architecture, module boundaries, contracts, tests, and acceptance gates. This is not a brainstorming memo. Treat it as the build plan for the next core milestone.

## North Star

Aurora must become a proof-carrying visual control runtime.

Do not optimize for more demos, more app-specific data, or more UI panels before the core runtime can prove every critical action:

```text
frame -> observation -> precondition evidence -> proof-carrying action
-> input lease -> actuation result -> verifier result
-> mission node result -> failure or benchmark delta
```

The product moat is not "can automate." The moat is:

- every meaningful action has evidence
- every physical action has a bounded lease
- every terminal success has verifier proof
- every failure has a recovery or learning path
- every repair can show benchmark improvement

## Current Baseline To Respect

The current codebase has recently added:

- `StateBus` dynamic slots and publish/subscribe.
- `PerceptionPipeline` post-processors and `POST_PROCESSOR_ERROR`.
- `AgentController` app-aware startup and `FrameSourceFactory`.
- `GenshinApp` install hooks, skill/transition registration, failure/persona bridge subscriptions.
- `VerifierResult.frame_id`, `roi_ids`, `detection_confidence`.
- `InputWorker._run_focus_check`.
- `EvolutionEngine` prototype.

Do not revert those changes. Refactor only when necessary to make the contracts below real.

## Non-Negotiable Constraints

1. No Genshin/domain-specific concepts in `core/`.
2. Strict mode must fail closed. If evidence is required and missing, the node/action fails.
3. Legacy dry-run tests may use permissive mode only where explicitly marked.
4. Real/safe-window physical input must go through `InputLease`.
5. No broad UI polish until Stage 44 and Stage 45 acceptance pass.
6. No marketplace/sharing work until Skill + Verifier + Benchmark metadata is trustworthy.
7. Do not claim R4 unless a safe-window path uses real frame source and real key/mouse actuation with focus-loss release evidence.

## Stage Overview

| Stage | Name | Goal | Exit Gate |
| --- | --- | --- | --- |
| 44 | Proof-Carrying Runtime Core | Make evidence and proof-carrying actions runtime contracts. | MissionNode success without verifier evidence is rejected in strict mode; trace query reconstructs action chain. |
| 45 | Verified Reflex Resume Gauntlet | Prove local reflex can preempt, dodge, verify, and resume. | Reflex benchmark reports latency, danger-clear verifier, checkpoint resume, final mission success. |
| 46 | Failure-To-Skill Repair Flywheel | Convert failure into reviewed, replayed, versioned skill patch with benchmark delta. | Forced failure becomes patch draft; patch-specific replay passes; before/after benchmark improves. |
| 47 | AuroraBench v1 + AppCapsule Boundary | Productize four crown-jewel benchmarks and capsule boundary. | All four suites generate evidence-backed reports; capsules do not modify `core/`. |

Stage 44 is the foundation. Do not skip it.

---

# Stage 44: Proof-Carrying Runtime Core

## Target

Create first-class runtime support for:

- `ProofCarryingAction`
- `TemporalEvidenceGraph`
- `EvidenceStrictMode`
- trace reconstruction
- strict terminal success gate

## New Modules

Create:

```text
core/proof_carrying_action.py
evidence/__init__.py
evidence/evidence_nodes.py
evidence/evidence_graph.py
evidence/evidence_store.py
evidence/strict_mode.py
evidence/trace_query.py
tests/test_evidence_graph.py
tests/test_proof_carrying_action.py
tests/test_strict_evidence_mode.py
tests/test_evidence_trace_query.py
```

Keep `core/proof_carrying_action.py` app-agnostic. It may reference ids and generic concepts, but it must not import domain capsules.

## Core Data Contracts

### ProofCarryingAction

Implement in `core/proof_carrying_action.py`.

Use dataclasses and string literals or enums. Keep fields JSON serializable.

Required shape:

```python
@dataclass(slots=True)
class ActionIntent:
    intent_id: str
    kind: str
    params: dict[str, object]
    reason: str


@dataclass(slots=True)
class ExpectedStateDelta:
    delta_id: str
    description: str
    success_triggers: list[str]
    forbidden_regressions: list[str]
    timeout_ms: int


@dataclass(slots=True)
class VerifierContract:
    contract_id: str
    verifier_id: str
    required_evidence_types: list[str]
    min_confidence: float
    roi_ids: list[str]
    timeout_ms: int


@dataclass(slots=True)
class RecoveryPolicyRef:
    policy_id: str
    strategy: str
    max_retries: int


@dataclass(slots=True)
class ProofCarryingAction:
    action_id: str
    mission_id: str | None
    node_id: str | None
    skill_id: str | None
    precondition_evidence_ids: list[str]
    action_intent: ActionIntent
    input_lease_id: str | None
    expected_state_delta: ExpectedStateDelta
    verifier_contract: VerifierContract
    recovery_policy: RecoveryPolicyRef
    telemetry_trace_id: str
    learning_hook_id: str | None
    status: str
    created_at: float
    finished_at: float | None = None
    verifier_result_id: str | None = None
```

Allowed statuses:

```text
PROPOSED
AUTHORIZED
LEASED
EXECUTED
VERIFIED_SUCCESS
VERIFIED_FAILED
RECOVERED
ABORTED
```

### Evidence Nodes

Implement in `evidence/evidence_nodes.py`.

Minimum node types:

```text
FrameNode
ObservationNode
TargetTrackNode
ROIEvidenceNode
PreconditionNode
ActionIntentNode
InputLeaseNode
ActuationResultNode
VerifierContractNode
VerifierResultNode
InterruptNode
RecoveryNode
SkillResultNode
MissionNodeResultNode
FailureSignatureNode
PatchProposalNode
BenchmarkResultNode
```

Each node must include:

```python
node_id: str
node_type: str
created_at: float
payload: dict[str, object]
```

Use generic dataclass wrappers; do not overfit to Genshin.

### Evidence Edges

Required edges:

```text
frame -> observation
observation -> target_track
observation -> roi_evidence
roi_evidence -> precondition
precondition -> action_intent
action_intent -> input_lease
input_lease -> actuation_result
actuation_result -> verifier_result
verifier_contract -> verifier_result
verifier_result -> mission_node_result
skill_result -> mission_node_result
interrupt -> recovery
failure_signature -> patch_proposal
patch_proposal -> skill_version
skill_version -> benchmark_result
```

Edges should be typed strings:

```text
DERIVED_FROM
SATISFIES
AUTHORIZES
LEASED_AS
RESULTED_IN
VERIFIED_BY
FAILED_WITH
RECOVERED_BY
PATCHED_BY
BENCHMARKED_BY
```

## Evidence Store

Implement `evidence/evidence_store.py`.

Requirements:

- in-memory graph for tests
- optional JSONL persistence under `logs/runs/<run_id>/evidence_graph.jsonl`
- append-only writes
- JSON serializable nodes/edges
- no full raw screenshots by default
- frame evidence stores frame id, timestamp, dimensions, source, optional hash, optional redacted artifact path

Do not require SQLite in Stage 44. JSONL is enough.

## Trace Query

Implement `evidence/trace_query.py`.

Minimum API:

```python
class TraceQuery:
    def action_chain(self, action_id: str) -> dict[str, object]: ...
    def verifier_chain(self, verifier_result_id: str) -> dict[str, object]: ...
    def mission_node_chain(self, node_result_id: str) -> dict[str, object]: ...
    def failures_for_skill(self, skill_id: str) -> list[dict[str, object]]: ...
```

Acceptance:

- Given a mission node result id, reconstruct:
  `frame -> observation -> action -> lease -> verifier -> mission result`.
- Return missing-link diagnostics instead of throwing unclear errors.

## Strict Mode

Implement `evidence/strict_mode.py`.

Minimum API:

```python
@dataclass(slots=True)
class StrictModeConfig:
    enabled: bool = True
    require_terminal_verifier: bool = True
    require_visual_evidence: bool = True
    require_lease_for_physical_action: bool = True
    require_patch_benchmark_delta: bool = True


class StrictModeValidator:
    def validate_action(self, action: ProofCarryingAction, graph: EvidenceGraph) -> list[str]: ...
    def validate_verifier_result(self, verifier_result: object, graph: EvidenceGraph) -> list[str]: ...
    def validate_mission_terminal_success(self, mission_result: object, graph: EvidenceGraph) -> list[str]: ...
```

Strict invariants:

1. Terminal mission success requires `VerifierResult`.
2. Visual `VerifierResult` requires at least one evidence node.
3. Visual `VerifierResult` must link `FrameNode` or `ObservationNode`.
4. Physical action requires `InputLeaseNode` with `expires_at`.
5. Recovery requires a linked failure or interrupt.
6. Patch approval requires before/after benchmark evidence.

## Integration Points

### PerceptionPipeline

When publishing an observation:

- create `FrameNode`
- create `ObservationNode`
- link frame -> observation
- if target track exists, create `TargetTrackNode`
- if post-processor emits ROI evidence, create `ROIEvidenceNode`

Avoid storing raw full frames unless explicitly configured for testbed.

### Verifiers

Extend `VerifierResult` with optional:

```python
evidence_ids: list[str] = field(default_factory=list)
contract_id: str | None = None
action_id: str | None = None
```

Existing `frame_id`, `roi_ids`, `detection_confidence`, and `evidence` remain.

All core verifiers must fill `evidence_ids` when an evidence graph is available.

### InputLease

Add optional fields without breaking existing calls:

```python
action_id: str | None = None
evidence_id: str | None = None
```

When `InputWorker` applies a lease, record `InputLeaseNode`.

When it calls backend actions, record `ActuationResultNode`.

### Orchestrator And MissionNodeExecutor

Do not allow these two concepts to collapse:

```text
SkillResult != MissionNodeResult
MissionNodeResult success requires verifier proof in strict mode.
```

Add or refactor toward:

```text
orchestration/mission_result.py
```

Suggested fields:

```python
mission_id
node_id
status
skill_result_id
proof_action_ids
verifier_result_id
evidence_errors
started_at
finished_at
```

In strict mode:

- if a node reaches success without verifier evidence, mark failed with `EVIDENCE_MISSING`
- publish strict-mode error to telemetry/evidence graph
- do not silently continue

## Stage 44 Tests

Add tests that prove:

1. Evidence graph can add nodes/edges and query action chain.
2. `ProofCarryingAction` serializes cleanly.
3. Strict mode rejects terminal success without verifier.
4. Strict mode accepts terminal success with frame/observation/verifier evidence.
5. `InputLease` can link to action id and evidence id.
6. Existing core tests still pass.

Commands:

```powershell
python -m pytest tests/test_evidence_graph.py tests/test_proof_carrying_action.py tests/test_strict_evidence_mode.py tests/test_evidence_trace_query.py -q
python -m pytest tests/test_verifier_driven_e2e.py tests/test_heart_bypass_e2e.py -q
python -m pytest -q
```

---

# Stage 45: Verified Reflex Resume Gauntlet

## Target

Prove Aurora's real-time moat:

```text
danger appears while skill is executing
-> reflex preempts current action
-> bounded dodge lease executes
-> danger-clear verifier rejects until danger is gone
-> target reacquires
-> original skill resumes from checkpoint
```

## New Modules

Create:

```text
reflex/__init__.py
reflex/reflex_scheduler.py
reflex/preemption_token.py
reflex/resume_contract.py
reflex/danger_clear_verifier.py
benchmarks/__init__.py
benchmarks/reflex_gauntlet/__init__.py
benchmarks/reflex_gauntlet/scenario.py
benchmarks/reflex_gauntlet/runner.py
benchmarks/reflex_gauntlet/evaluator.py
tests/test_reflex_scheduler.py
tests/test_verified_reflex_resume_gauntlet.py
```

## Contracts

### PreemptionToken

```python
@dataclass(slots=True)
class PreemptionToken:
    token_id: str
    interrupted_action_id: str | None
    interrupted_skill_id: str | None
    checkpoint_id: str | None
    reason: str
    interrupt_id: str
    created_at: float
    expires_at: float
```

### ResumeContract

```python
@dataclass(slots=True)
class ResumeContract:
    contract_id: str
    preemption_token_id: str
    checkpoint_id: str
    required_evidence_ids: list[str]
    reacquire_required: bool
    max_resume_delay_ms: int
```

### DangerClearVerifier

Must return `VerifierResult` with:

- `ok=False` while danger is still present
- `ok=True` only after danger score is below threshold
- `frame_id`
- `evidence_ids`
- `detection_confidence`

## Integration

ReflexScheduler responsibilities:

- subscribe to danger observations or registered danger slot
- emit interrupt only when threshold crossed and cooldown permits
- create `PreemptionToken`
- request bounded dodge input via `InputLease`
- invoke/coordinate `DangerClearVerifier`
- produce `ResumeContract`

VisualActionBlockExecutor responsibilities:

- expose checkpoint id before executing interruptible steps
- pause on preemption token
- resume from checkpoint after resume contract is satisfied

Do not put LLM calls in the reflex path.

## Benchmark: Reflex Gauntlet

Scenario variants:

1. ground danger appears
2. projectile danger appears
3. HP drop danger appears
4. target occlusion during danger
5. repeated danger with cooldown
6. danger false positive

Metrics:

```text
frame_to_observation_ms
observation_to_interrupt_ms
interrupt_to_lease_ms
danger_clear_time_ms
danger_false_clear_rate
resume_success_rate
max_consecutive_dodges_observed
final_task_success
```

Acceptance:

- verifier rejects while danger remains
- verifier accepts after clear
- no infinite dodge loop
- checkpoint resume happens
- evidence graph links danger frame, interrupt, lease, verifier, resume

---

# Stage 46: Failure-To-Skill Repair Flywheel

## Target

Make repair real, not just a patch suggestion.

Required chain:

```text
failed run
-> FailureSignature
-> user repair session
-> demonstration segments
-> SkillPatch draft
-> temporary patched skill
-> verifier-backed replay
-> human approval
-> versioned skill patch
-> before/after benchmark delta
```

## New Modules

Create:

```text
repair/__init__.py
repair/repair_session.py
repair/demo_segmenter.py
repair/skill_patch_builder.py
repair/repair_validator.py
repair/repair_benchmark_runner.py
tests/test_repair_session.py
tests/test_skill_patch_builder.py
tests/test_failure_to_skill_repair_flywheel.py
```

Keep `learning/evolution_engine.py`, but refactor it to orchestrate these modules instead of doing everything itself.

## Data Artifacts

Use:

```text
data/skill_patches/
  <skill_id>/
    patch_<timestamp>_<short_id>.json
```

Patch draft schema:

```json
{
  "patch_id": "...",
  "skill_id": "...",
  "source_failure_signature_id": "...",
  "source_run_id": "...",
  "demonstration_segment_ids": [],
  "proposed_steps": [],
  "verifier_contract": {},
  "safety": {
    "requires_user_approval": true,
    "dry_run_required": true,
    "safe_window_required": false
  },
  "validation": {
    "dry_run_passed": false,
    "verifier_replay_passed": false,
    "benchmark_before": null,
    "benchmark_after": null
  },
  "status": "DRAFT"
}
```

Allowed statuses:

```text
DRAFT
SANDBOX_VALIDATED
REJECTED
APPROVED
APPLIED
ROLLED_BACK
```

## Repair Session UX Contract

Even if GUI work is later, backend APIs must support this language:

```text
"The task failed because the interaction prompt was not verified.
Show me one correct example. I will convert it into a guarded skill patch."
```

Repair session must record:

- failure evidence ids
- user demonstration event ids
- proposed new checkpoints
- proposed verifier contract
- replay result
- benchmark delta

## EvolutionEngine Requirements

Refactor `EvolutionEngine` so it:

- does not verify a patch by running unrelated fixed pytest only
- creates a patch draft file
- applies patch to a temporary skill store or temporary skill copy
- runs patch-specific dry-run replay
- runs at least one verifier-backed replay
- records before/after benchmark result
- requires explicit approval before applying to canonical skill

No silent auto-merge.

## Stage 46 Tests

Add tests that prove:

1. Forced `TARGET_LOST` failure creates `FailureSignature`.
2. Repair session records demonstration events.
3. Skill patch draft is written under `data/skill_patches/` in a temp root during tests.
4. Patch-specific replay runs against the patched skill, not unrelated pytest.
5. Patch cannot be applied without approval.
6. Approved patch creates a new skill version or patch artifact.
7. Before/after benchmark delta is present.

---

# Stage 47: AuroraBench v1 + AppCapsule Boundary

## Target

Convert the four crown-jewel scenarios into product-level benchmarks.

## New Modules

Create:

```text
benchmarks/benchmark_types.py
benchmarks/benchmark_runner.py
benchmarks/report_builder.py
benchmarks/reflex_gauntlet/
benchmarks/long_horizon_route_fight_collect_resume/
benchmarks/failure_to_skill_repair/
benchmarks/high_res_ui_safety_grounding/
scripts/run_aurorabench.py
tests/test_aurorabench_v1.py
```

Optional capsule structure:

```text
capsules/
  demo_arpg/
    capsule.yaml
    frame_processors/
    skills/
    verifiers/
    transitions/
    benchmarks/
  desktop_ui/
    capsule.yaml
    skills/
    verifiers/
    benchmarks/
```

Do not move existing Genshin code wholesale unless it is low-risk. It is acceptable in Stage 47 to create `demo_arpg` and `desktop_ui` capsules first, then migrate Genshin later.

## Benchmark Result Contract

```python
@dataclass(slots=True)
class BenchmarkResult:
    benchmark_id: str
    run_id: str
    task_completion_rate: float
    verifier_false_accept_rate: float
    verifier_false_reject_rate: float
    recovery_success_rate: float
    resume_success_rate: float
    user_intervention_count: int
    mean_time_to_complete_ms: float
    release_all_reliability: float
    evidence_coverage_rate: float
    before_after_delta: dict[str, float]
    report_path: str
```

Every benchmark report must include:

- evidence coverage
- success/failure table
- verifier results
- interrupt/recovery summary
- safety summary
- benchmark-specific metrics

## AuroraBench v1 Suites

### A. Reflex Dodge And Resume Gauntlet

Stage 45 benchmark promoted into official suite.

### B. Long-Horizon Route, Fight, Collect, Resume

Required chain:

```text
knowledge resolve -> route choose -> enter region -> combat
-> danger reflex -> collect -> forced stop -> hot resume -> final verifier
```

Acceptance:

- every terminal node has verifier evidence
- resume skips verified nodes
- report shows route nodes and recovery transitions

### C. Failure-To-Skill Repair

Stage 46 benchmark promoted into official suite.

Acceptance:

- failure evidence shown
- patch created
- patch replayed
- benchmark delta shown

### D. High-Resolution UI Safety And Grounding

Use a deterministic dense UI testbed first.

Required chain:

```text
screen -> ROI cascade -> grounded element -> confidence gate
-> block destructive action or require confirmation
-> safe action -> post-action verifier
```

Acceptance:

- destructive labels are blocked
- low confidence requires confirmation
- safe high-confidence action executes in dry-run
- verifier evidence links frame/ROI/element

## AppCapsule Boundary

AppCapsule must include:

```text
frame_processors
slots
skills
transitions
verifiers
failure_bridge
persona_bridge
benchmark_tasks
```

Capsule invariants:

1. Installing a capsule must not edit `core/`.
2. Activation/deactivation must not leak active hooks.
3. Capsule benchmark can run independently.
4. Capsule failure does not crash the kernel; it emits evidence and diagnostics.
5. Capsule uninstall/unregister must clean or disable subscriptions. If `StateBus.unsubscribe` is missing, add it.

## Stage 47 Tests

Add tests that prove:

- `scripts/run_aurorabench.py --suite all --mode dry-run` completes.
- each suite produces a JSON report and markdown report.
- evidence coverage rate is computed.
- capsule install/activate/deactivate/unregister cleans hooks.
- no `genshin` references appear under `core/`.

---

# Priority Fixes From Latest Review

These are small but important and should be fixed before or during Stage 44:

1. `FOCUS_LOST` priority must follow queue semantics.
   Current queue returns smaller priority first. Do not label `priority=100` as highest. Either use `priority=0` for safety or invert/rename priority semantics consistently.

2. Avoid repeated focus-loss interrupt spam.
   `InputWorker._run_focus_check` should publish once per focus-loss episode and reset when focus returns.

3. `SafeWindowInputBackend.key_down/key_up` cannot remain ignored for R4.
   Either implement real Win32 keyboard input or explicitly mark safe-window keyboard actuation unsupported and prevent R4 claims.

4. Post-processor bridge internals should not silently swallow errors.
   Domain bridges may downgrade errors, but they must emit diagnostics or evidence events when internal classifier/extractor fails.

5. `StateBus.subscribe` needs unsubscribe or subscription token.
   AppCapsule deactivate/unregister cannot be clean without it.

6. `FrameSourceFactory` must be selected by config/API.
   `_run_real_loop` should not hardcode `"demo"` except as default dry-run mode.

7. `EvolutionEngine` must validate the patch itself.
   Running a fixed pytest that does not apply the patch is not sufficient.

## Suggested Immediate PR Order

1. Stage 44 data contracts and tests only.
2. Stage 44 evidence store + trace query.
3. Stage 44 integration with perception, input lease, verifier, mission terminal gate.
4. Priority fixes 1-6.
5. Stage 45 reflex scheduler and benchmark.
6. Stage 46 repair flywheel.
7. Stage 47 AuroraBench and capsule cleanup.

Each PR must keep `python -m pytest -q` green.

## Final Acceptance For This Program

The whole Stage 44-47 program is complete only when this demo runs:

```text
Aurora starts a long-horizon task.
It resolves a route, enters a target area, fights, detects danger,
preempts into dodge, verifies danger cleared, resumes from checkpoint,
collects a resource, hits a forced failure, explains the failure from evidence,
records a user repair, creates and approves a skill patch,
reruns AuroraBench, and reports before/after improvement.
```

This final report must include:

- evidence graph coverage
- action chain reconstruction
- verifier false accept/false reject summary
- focus/lease/release_all safety summary
- reflex latency metrics
- resume success metric
- repair before/after delta
- capsule boundary check

If that report is real and reproducible, Aurora has crossed from impressive prototype to defensible visual-agent runtime.

