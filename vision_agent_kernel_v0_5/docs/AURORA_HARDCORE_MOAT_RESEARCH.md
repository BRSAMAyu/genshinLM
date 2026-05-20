# Aurora Hardcore Moat Research

Date: 2026-05-20

This document is not a feature backlog. It is a research memo for the hardest parts of Aurora: the task scenarios, core chains, metrics, and technical inventions that can make the system genuinely hard to surpass.

The central thesis:

> Aurora should not compete as "another GUI agent" or "another LLM planner." Aurora should become the best proof-carrying visual control runtime: every meaningful action carries visual evidence, a time-bounded actuation contract, a verifier, a recovery path, and a learning trace.

## What The Outside World Teaches Us

Current agent benchmarks expose the same pattern repeatedly:

- Real computer-use agents fail because GUI grounding and operational knowledge are hard. OSWorld uses real OS environments, execution-based evaluation, and 369 tasks; reported human success is over 72.36%, while the best evaluated model in the paper reaches 12.24%, mainly struggling with GUI grounding and operational knowledge. Source: <https://proceedings.neurips.cc/paper_files/paper/2024/hash/5d413e48f84dc61244b6be550f1cd8f5-Abstract-Datasets_and_Benchmarks_Track.html>
- Web agents need functional correctness, not just plausible actions. WebArena reports a GPT-4-based best baseline at 14.41% end-to-end success versus 78.24% human performance on realistic, long-horizon web tasks. Source: <https://arxiv.org/abs/2307.13854>
- Enterprise workflows remain far from fully automated. WorkArena focuses on ServiceNow knowledge-work tasks and finds a considerable gap toward full task automation. Source: <https://arxiv.org/abs/2403.07718>
- Cross-platform robustness is weak. AndroidWorld reports 30.6% best-agent task completion and shows task variations can significantly change measured performance. Source: <https://arxiv.org/abs/2405.14573>
- GUI perception is still a bottleneck. UI-Vision highlights limitations in professional software understanding, spatial reasoning, and drag/drop action prediction across desktop apps. Source: <https://arxiv.org/abs/2503.15661>
- High-resolution professional GUI grounding is especially hard. ScreenSpot-Pro reports poor performance from existing GUI grounding models, with the best model at 18.9%, and shows that planner-guided cascaded search improves grounding. Source: <https://arxiv.org/abs/2504.07981>
- Embodied agents compound through skill libraries and self-verification. Voyager's core ingredients are automatic curriculum, an expanding skill library, and iterative improvement with environment feedback and self-verification. Source: <https://arxiv.org/abs/2305.16291>
- Generalist embodied systems need environment, knowledge, and scalable architecture together. MineDojo argues for that trinity explicitly. Source: <https://papers.nips.cc/paper_files/paper/2022/hash/74a67268c5cc5910f64938cac4526a90-Abstract-Datasets_and_Benchmarks.html>
- Native keyboard/mouse action from video is a hard but valuable signal. OpenAI's VPT work emphasizes that unlabeled videos lack action labels, then uses inverse dynamics to infer keyboard/mouse actions and learn through the native human interface. Source: <https://openai.com/index/vpt/>

Aurora's opportunity is to combine these lessons in a narrower but deeper domain: real-time visual tasks, desktop/sandbox interaction, verifier-driven execution, and user-repairable skills.

## The Crown Jewel: Proof-Carrying Visual Action

The core invention should be a first-class action object:

```text
ProofCarryingAction =
  precondition_evidence
  + action_intent
  + input_lease
  + expected_state_delta
  + verifier_contract
  + rollback_or_recovery
  + telemetry_trace
  + learning_hook
```

This is the difference between an agent that "clicks because it thinks it should" and an agent that can prove:

- what it saw before acting
- why the action was allowed
- what physical input was leased
- what state change was expected
- which verifier accepted or rejected the result
- how the system recovered
- what should be improved next time

This should become Aurora's central abstraction, above any single game or app.

## The Five Hardest Moats

### 1. Temporal Evidence Graph

Most agents keep logs. Aurora should keep a temporal evidence graph.

Each frame, observation, action, interrupt, skill result, verifier result, failure signature, and patch proposal should be linked by ids:

```text
frame_id -> observation_id -> action_id -> lease_id -> verifier_result_id -> failure_or_success -> patch_id
```

Why it is hard to copy:

- It requires discipline across perception, control, execution, orchestration, telemetry, and learning.
- It makes false success visible instead of letting it hide in logs.
- It becomes training/evaluation data over time.

Hard metric:

- 100% of MissionNode terminal states have a linked verifier result.
- 100% of verifier results link to frame/ROI/action evidence when visual evidence is applicable.
- 0 accepted task completions with missing evidence in strict mode.

### 2. Reflex With Verified Resume

Aurora's real-time advantage should be:

```text
detect danger -> preempt skill -> bounded input lease -> verify danger cleared -> resume checkpoint
```

The novelty is not "dodge." The novelty is verified preemption and verified resume.

Hard metric:

- p95 frame-to-interrupt latency under 150 ms in deterministic testbed.
- p95 frame-to-dodge-intent latency under 250 ms in authorized safe-window mode.
- danger false-clear rate below 1% in the danger gauntlet.
- resume success above 95% after reflex interruption.

This is where Aurora can outperform generic LLM agents: no LLM should be in the millisecond reflex path.

### 3. User-Repairable Skill Flywheel

The product moat is not that Aurora has many built-in skills. The moat is that users can repair the system and every repair becomes structured capability.

```text
failure -> explanation -> user demonstration -> segmented skill draft -> verifier contract -> replay -> approval -> versioned skill -> benchmark delta
```

Hard metric:

- A new user can repair a failed visible task in under 3 minutes.
- The repaired skill must pass dry-run replay and one verifier-backed testbed replay.
- The system must show before/after benchmark delta.

This is the user-experience reason for innovation: the user does not need to understand the kernel, but they can teach it.

### 4. App Capsules With Zero Core Pollution

Genshin should be treated as proof of a reusable App Capsule pattern, not as the kernel's identity.

```text
AppCapsule =
  frame processors
  + slots
  + skills
  + transitions
  + verifiers
  + failure bridge
  + persona bridge
  + benchmark tasks
```

Hard metric:

- A new App Capsule can add domain perception, skills, and transitions without editing `core/`.
- App unregistration removes all runtime hooks or marks them inactive.
- Capsule tests include install, activate, run, deactivate, unregister, and trace cleanup.

This prevents Aurora from becoming a single-use automation tree.

### 5. Benchmark-As-Product

AuroraBench should not be a script afterthought. It should become the product's reality meter.

Every release should answer:

- What tasks did it solve?
- Which evidence proved completion?
- How often did it recover?
- How often did the user intervene?
- What got worse?
- What new failure clusters appeared?

Hard metric:

- Every user-facing demo maps to one benchmark task.
- Every critical bug creates one regression task.
- Every skill patch must show before/after metrics.

This makes progress defensible instead of anecdotal.

## The Four Crown-Jewel Task Scenarios

These are the tasks worth making excellent. They are difficult enough to matter and focused enough to finish.

### Scenario A: Reflex Dodge And Resume Gauntlet

Task:

- Agent is executing a combat sequence.
- Dynamic danger appears in multiple forms: ground warning, projectile motion, HP drop, boss windup, target occlusion.
- Agent must interrupt current skill, dodge safely, verify danger cleared, reacquire target, and resume from checkpoint.

Why this is core:

- It tests perception latency, reflex preemption, input lease safety, verifier evidence, checkpoint resume, and persona explanation in one loop.
- Generic LLM agents are structurally weak here.

Required proof:

- trace with frame ids and danger scores
- interrupt record
- input lease record
- verifier rejection while danger remains
- verifier acceptance after danger clears
- resume checkpoint id
- final mission outcome

### Scenario B: Long-Horizon Route, Fight, Collect, Resume

Task:

- Start from a calibrated profile.
- Plan route to a resource.
- Navigate to target area.
- Fight blocking enemy.
- Collect resource.
- Handle target lost, obstacle blocking, and interruption.
- Stop mid-run and resume from the last verified node.

Why this is core:

- It tests whether Aurora is a real agent runtime rather than a demo loop.
- It joins knowledge, planning, navigation, combat, collection, verifier, checkpoint, and learning.

Required proof:

- every MissionNode has verifier evidence
- route decisions reference knowledge graph nodes
- recovery transitions are explicit
- resume skips already verified nodes
- final report contains success/failure explanation

### Scenario C: Failure-To-Skill Repair

Task:

- Force a task failure.
- System clusters the failure.
- GUI explains why it failed using visual evidence.
- User records a repair step.
- System converts it into a skill patch.
- Patch is sandbox-replayed, approved, versioned, and benchmarked.

Why this is core:

- It turns users into a data flywheel.
- It is a better moat than static automation.

Required proof:

- failure signature id
- cluster id
- patch proposal
- approval state
- skill version diff
- before/after AuroraBench result

### Scenario D: High-Resolution UI Safety And Grounding

Task:

- Agent operates a dense desktop UI or in-game menu at high resolution.
- It must identify a safe action, reject destructive actions, and ask for human confirmation when confidence is low.

Why this is core:

- GUI grounding remains a hard unsolved problem in external benchmarks.
- Aurora's evidence and safety model can make this more trustworthy than a raw coordinate predictor.

Required proof:

- ROI cascade or planner-guided search trace
- grounded element evidence
- confidence gate decision
- human override record for destructive actions
- verifier result after action

## Research Concepts Worth Naming

### Proof-Carrying Visual Control

Every control decision must carry enough evidence for replay, rejection, recovery, and learning.

### Verified Reflex Scheduling

Local reflexes may preempt planners, but only through bounded leases and verified resume.

### Evidence-Strict Orchestration

State transitions are not allowed to advance on skill completion alone. They require verifier evidence in strict mode.

### Human-Repairable Skill Distillation

Human demonstrations are not saved as raw macros. They are distilled into skills with preconditions, visual checkpoints, verifier contracts, failure policies, and benchmark metrics.

### App Capsule Architecture

Domain-specific intelligence lives in capsules. The kernel owns timing, leases, evidence, safety, telemetry, and learning contracts.

## What Not To Optimize First

- Do not chase broad app support before the four crown-jewel scenarios are excellent.
- Do not optimize model size before the evidence graph and verifier contracts are strict.
- Do not count unit tests as product capability unless they correspond to benchmark tasks.
- Do not let Genshin-specific code leak into kernel contracts.
- Do not build a skill marketplace before skill success metrics and safety metadata are trustworthy.
- Do not let persona become decorative; persona should explain evidence, risk, failure, recovery, and next action.

## Metrics That Matter

### Reliability

- task completion rate
- verifier false accept rate
- verifier false reject rate
- recovery success rate
- resume success rate

### Real-Time Control

- frame-to-observation latency
- frame-to-interrupt latency
- frame-to-input-lease latency
- stale-frame rate
- control oscillation score

### Safety

- input lease expiry reliability
- release_all reliability
- focus-loss release latency
- unauthorized-window rejection rate
- destructive-action block rate

### Learning

- failures clustered per run
- patch proposal acceptance rate
- patch replay pass rate
- before/after benchmark improvement
- repeated failure recurrence rate

### Product UX

- time to diagnose failure
- time for user to repair skill
- number of command-line steps after GUI launch
- user interventions per mission
- clarity of evidence report

## Recommended Deep Work For The Lead Track

The engineering agents can implement many modules in parallel. The lead architecture track should protect these invariants:

1. Define `ProofCarryingAction` and require every critical skill to emit one.
2. Define `TemporalEvidenceGraph` ids and make telemetry write them.
3. Make strict mode reject terminal MissionNode states without verifier evidence.
4. Make reflex interruption resumable by contract, not by convention.
5. Make failure repair produce benchmark deltas, not just patch suggestions.
6. Make every App Capsule bring its own benchmark tasks.

## 30-Day Hard-Core Target

The next 30 days should culminate in one demo that is hard to fake:

```text
Aurora starts a long-horizon task.
It navigates, fights, detects danger, dodges, verifies safety, resumes,
collects a resource, fails once, explains the failure from evidence,
records a user repair, versions the repaired skill,
reruns the benchmark, and shows the before/after improvement.
```

If Aurora can do that cleanly in an authorized testbed, it has a real technical story:

- not just planning
- not just automation
- not just UI
- not just tests

It becomes a verifiable, safe, self-improving visual agent runtime.

