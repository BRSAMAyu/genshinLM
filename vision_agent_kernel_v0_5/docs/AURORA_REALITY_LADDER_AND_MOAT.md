# Aurora Reality Ladder And Technical Moat

Date: 2026-05-20

This document is the working architecture audit for the next Aurora planning cycle. It translates the current codebase, tests, and product docs into a stricter capability map: what is real now, what is still only testbed-real, which task chains must be punched through next, and where Aurora can build a defensible technical moat.

## Executive Verdict

Aurora is currently an open-alpha visual-agent kernel with unusually strong safety, dry-run, replay, and testbed acceptance scaffolding. It should not be positioned as a mature general-purpose embodied OS yet.

The strongest current asset is not a single feature. It is the contract:

```text
observe -> decide -> execute through lease -> verify from observation -> log -> learn -> version
```

The most important product claim should therefore become:

> Aurora is a verifier-first visual agent system: no task is complete until observed state proves it.

This is a better moat than "we can automate X." Most agent frameworks emphasize LLM orchestration, handoffs, memory, and tracing. Aurora should win on embodied reliability: visual grounding, interruptible execution, input safety, replayable traces, and failure-to-skill improvement.

## External System Lessons

The external agent landscape points to five requirements for serious systems:

- Explicit, stateful workflows. LangGraph describes itself as infrastructure for long-running, stateful workflows and emphasizes observability/evaluation for reliable agents: <https://docs.langchain.com/oss/python/langgraph/overview>
- Durable checkpoints and replay. LangGraph persistence writes graph state to checkpoints and supports state history/update patterns: <https://docs.langchain.com/oss/python/langgraph/persistence>
- Owned orchestration, tools, approvals, and state. The OpenAI Agents SDK docs frame agent applications as systems that plan, call tools, collaborate, and keep state, with the application owning orchestration and approvals: <https://developers.openai.com/api/docs/guides/agents>
- Guardrails around tool calls, not only prompts. The OpenAI Agents SDK guardrails docs separate input/output/tool guardrails and note that tool guardrails run around custom tool invocations: <https://openai.github.io/openai-agents-python/guardrails/>
- Execution-based evaluation for computer-use agents. OSWorld stresses real desktop environments, task setup, execution-based evaluation scripts, and shows GUI grounding and operational knowledge as major failure modes: <https://arxiv.org/abs/2404.07972>

Aurora already has local answers for several of these, but they are not yet deep enough: MissionRunner is not yet the central product execution surface, verifier grounding is still simple, and GUI/product QA is not yet one-click end-user complete.

## Reality Ladder

Use this ladder for every subsystem and every public claim.

| Level | Meaning | Evidence Required |
| --- | --- | --- |
| R0 | Stub | Interface exists, no credible behavior. |
| R1 | Synthetic | Works on dictionaries, mocks, or tiny in-memory arrays. |
| R2 | Local component | Real local code/persistence/service/UI behavior, but not a closed agent loop. |
| R3 | Deterministic testbed loop | Works in repeatable pseudo3d/realistic testbed scenarios with verifier results. |
| R4 | Authorized safe-window loop | Works against an explicit authorized target window with focus gate, input lease, release_all, and live perception. |
| R5 | Product-ready user loop | Non-developer can install, calibrate, run, diagnose, repair, and compare results through GUI without command-line fallback. |

## Current Module Map

| Module | Current Reality | Evidence | Main Gap | Next Gate |
| --- | ---: | --- | --- | --- |
| Core StateBus/time/interrupt | R3 | `core/`, priority interrupts, monotonic time, 13 related test files | Runtime policy is present but not exposed as a formal invariant suite | Add invariant tests that replay traces and prove P0/P1 behavior under load |
| Perception | R2 | capture pipeline, YOLO wrapper, OCR wrapper, profile/ROI data | `PerceptionPipeline` publishes observations but does not continuously wire detector/OCR/danger outputs into one live observation graph | Build unified `ObservationBuilder`: frame -> detector -> tracker -> OCR -> danger -> verifier context |
| Control / camera servo | R3 | FOV-aware servo, Genshin compensation, visual servo scripts | Mostly proven in testbed; not calibrated with live authorized scenario metrics | Add calibration table, tracking error curves, and safe-window servo acceptance |
| Execution / Input safety | R3/R4 partial | `InputLease`, `InputWorker`, deadman, safe-window gate, release_all tests | `SafeWindowInputBackend` mouse path is real, key path is currently logged/ignored; R4 claim must be scoped | Complete authorized testbed key/mouse path with focus-loss and release_all evidence |
| Visual Action Blocks | R3 | chunked waits, interrupts, visual trigger tests | Trigger set is narrow and not connected to real detector confidence | Add trigger registry with verifier-compatible evidence |
| Orchestration / MissionRunner | R3 | node execution, SkillBinder, verifier, checkpoint/resume acceptance | Product GUI still does not make MissionRunner the main user journey | Make MissionRunner the only route for task execution in GUI and service |
| Planning / LLM | R2 | mock/GLM/MiniMax providers, sandbox validation, request guards | Narrow intent parsing; real providers optional and mostly not in acceptance path | Add plan diff, budget display, provider health, and real-provider replay tests |
| Knowledge | R2 | route cost algorithm, resource/monster/world graph data | Data is file/import oriented; no user-editable knowledge lifecycle | Add Knowledge Workshop: import, validate, route preview, simulation |
| Combat | R2/R3 | playbook runtime, danger scoring, reflex evasion, testbed combat success | Danger still relies on signal dictionaries or simple HSV; no robust pixel/projectile benchmark | Build pixel-grounded danger dataset and danger verifier suite |
| Collection | R3 testbed, R2 real | collect runtime, green detector, interaction prompt, testbed verifier | Testbed works; real capture routing and prompt OCR are not product-closed | Build live capture collection chain with prompt OCR and disappearance verifier |
| Agentic UI exploration | R1/R2 | OCR-like grounding, destructive blacklist, human override | No live OCR/UI loop; action proposals are not verified through GUI task completion | Build safe UI sandbox: OCR -> proposal -> confirmation -> dry-run click -> verifier |
| Learning | R2/R3 partial | JSONL ingestor, privacy mask, failure signature, patch suggestion | Patch suggestion is not a closed regression/versioning loop | Implement failure flywheel: cluster -> patch -> sandbox replay -> human approve -> skill version |
| Persistence / hot resume | R3 backend, R1 GUI | SQLite, HotResume, MissionRunner resume | GUI resume prompt and environment revalidation are missing | Add resume modal with profile/window/skill compatibility checks |
| Product shell / Desktop | R2/R3 | FastAPI, React/Vite/Tauri shell, product E2E dry-run | Many flows still surface JSON; GUI no-command product flow is manual | Make GUI Product Flow Test pass with Browser/Playwright |
| Open beta / benchmark | R2 | run folder parser, feedback package, skill workshop | Metrics are basic and not yet a canonical benchmark suite | Define AuroraBench with fixed tasks, traces, videos, and success scripts |

## Task Chains To Punch Through

These are the chains that turn Aurora from a broad prototype into a system with compounding reliability.

### Chain 1: Live Observation To Verifier

Goal: every verifier receives evidence produced by the actual perception path, not manually assembled state.

```text
FrameSource -> ObservationBuilder -> ROI/OCR/Detector/Tracker/Danger -> VerifierContext -> VerifierResult -> Telemetry
```

Acceptance:

- One combat task and one collection task run without injected state dictionaries.
- Verifier evidence includes frame id, ROI id, detector class/confidence, OCR text when relevant, and reason.
- Failure report can show why the verifier rejected the task.

Why it matters: this is the difference between "script says done" and "screen proves done."

### Chain 2: Authorized Safe-Window Execution

Goal: prove a real local target window can be controlled safely end to end.

```text
Select authorized window -> focus gate -> capture -> plan -> InputLease -> deadman -> release_all -> report
```

Acceptance:

- Mouse and key events both pass through `InputLease`.
- Focus loss forces `release_all`.
- Safe-window run refuses non-authorized windows.
- Trace includes all leases, expirations, interrupts, and final release status.

Why it matters: Aurora's safety moat is only real if physical input is never outside the lease discipline.

### Chain 3: Skill Flywheel

Goal: user demonstrations become versioned, verifiable, shareable skills.

```text
Record -> Segment -> Draft -> Validate -> Dry-run replay -> Safe-window replay -> Bind -> Verify -> Version
```

Acceptance:

- Generated skill has preconditions, visual checkpoints, success criteria, fallback, cleanup, safety metadata.
- SkillBinder rejects incompatible profile/trigger/verifier combinations.
- Skill success stats feed future binding decisions.

Why it matters: a famous agent system needs an extensible skill economy, not one-off scripts.

### Chain 4: Failure Learning Flywheel

Goal: failures become regression assets and reviewed improvements.

```text
Failed run -> Trace ingest -> FailureSignature -> Cluster -> Patch candidates -> Sandbox replay -> Human review -> Skill/Profile version -> Benchmark delta
```

Acceptance:

- Every failed MissionNode emits a normalized failure record.
- Patch suggestions include evidence and expected metric improvement.
- No patch is applied without human approval.
- Benchmark compares before/after success rate, verifier pass rate, interventions, and time.

Why it matters: this is the strongest long-term compounding moat.

### Chain 5: GUI No-Command Product Flow

Goal: prove a non-developer path exists.

```text
Launch service/GUI -> diagnostics -> select window -> calibrate -> load/record skill -> generate mission -> run dry-run -> inspect report -> resume/repair
```

Acceptance:

- No direct Python command after launch.
- Internal JSON is replaced by status cards, evidence panels, and action prompts.
- User sees "what happened, why, what to do next."

Why it matters: product trust is built in the repair loop, not just the success demo.

### Chain 6: AuroraBench

Goal: convert local runs into a benchmark that can guide engineering and external credibility.

```text
Task pack -> initial state -> run -> execution-based evaluator -> trace/video/report -> leaderboard metrics
```

Minimum task pack:

- visual target lock and servo
- collect visible object
- combat with danger and recovery
- UI destructive-action override
- target lost and reacquire
- mission resume after stop
- skill recording and replay
- failure learning patch suggestion
- GUI product journey
- long-run endurance with chaos

Metrics:

- task completion rate
- verifier true-pass / false-pass rate
- recovery success rate
- human interventions
- mean time to complete
- input safety violations
- release_all reliability
- perception latency and stale-frame rate

## Core Technical Moats

### 1. Verifier-First Embodied Agent Contract

Aurora should make verifier results first-class. A MissionNode is complete only when a verifier accepts observation-derived evidence.

Research angle: action completion as observation-grounded proof, not agent self-report.

### 2. Lease-Based Physical Input Safety

Every physical action is bounded by owner, priority, expiry, focus, and cleanup. This is stronger than a generic "tool guardrail" because it governs the dangerous actuator layer itself.

Research angle: time-bounded actuation contracts for GUI/desktop agents.

### 3. Dual-Speed Brain/Reflex Control

LLM/planner makes strategic choices; local reflex handles high-frequency hazards and interrupts. The product should formalize this as a scheduler, not just combat code.

Research angle: hybrid deliberative/reactive architecture for screen-grounded agents.

### 4. Failure-To-Skill Compounding Loop

Failures should automatically become signatures, clusters, patches, tests, and version history. This is how Aurora becomes better with use.

Research angle: trace-grounded skill evolution with human approval and regression proof.

### 5. Local-First Privacy-Preserving Telemetry

Observation evidence, screenshots, and logs stay local by default and are masked before export.

Research angle: privacy-preserving evaluation datasets for desktop/visual agents.

### 6. Skill/Profile/Playbook Asset Economy

Aurora's reusable artifacts should be validated, versioned, benchmarked, and shareable.

Product angle: the community does not share "prompts"; it shares verified skills with known success rates and safety metadata.

## Innovation Backlog

### Near-Term Engineering Innovations

- `ObservationBuilder`: one typed builder for frame, ROI, OCR, detector, tracker, danger, and metadata.
- `VerifierEvidence`: structured evidence object with frame references, ROI references, confidence, and rejection reason.
- `CapabilityScoredSkillBinder`: score by profile compatibility, visual triggers, verifier compatibility, and recent success stats.
- `MissionRunnerService`: make MissionRunner the central service path for GUI task execution.
- `TraceReplayHarness`: replay JSONL and frames to reproduce verifier and learning decisions.

### Product Innovations

- Evidence panel: show what the agent saw and why the verifier accepted/rejected.
- Repair console: turn a failure into "record missing step", "adjust ROI", "retry with patch", or "mark as unsafe."
- Skill workshop: visual editor for checkpoints, fallbacks, and success criteria.
- Hot-resume prompt: resume only after target window/profile/skill compatibility checks.
- AuroraBench dashboard: per-version success and safety deltas.

### Research/Whitepaper Topics

- Verifier-first visual agent execution.
- Time-bounded input leases for safe desktop actuation.
- Human-reviewed trace-to-skill learning loop.
- Dual-speed control for real-time visual tasks.
- Local-first privacy-preserving telemetry for embodied agents.

## Next 30-Day Execution Plan

### Week 1: Observation And Verifier Grounding

- Implement `ObservationBuilder`.
- Refactor combat and collection verifiers to consume typed evidence.
- Add one acceptance case with no injected success state.

Exit gate: Chain 1 passes for combat and collection.

### Week 2: MissionRunner Becomes Product Path

- Add service endpoint to run a MissionQueue through `MissionRunner`.
- Wire GUI Product Demo to MissionRunner, not only product E2E dry-run helpers.
- Add trace/report output per node.

Exit gate: GUI can run a full dry-run mission and show per-node verifier results.

### Week 3: Failure Learning Flywheel

- Normalize failure telemetry for every failed MissionNode.
- Add cluster and patch review object.
- Add sandbox regression for candidate patches.

Exit gate: one failed run becomes a reviewed patch candidate and a before/after benchmark comparison.

### Week 4: AuroraBench And Product QA

- Define fixed task pack and evaluator schema.
- Add GUI no-command test with Browser/Playwright.
- Package one open-alpha example bundle.

Exit gate: AuroraBench v0 produces a report with task completion, verifier accuracy, safety, intervention, and latency metrics.

## Positioning

Do not position Aurora as "another Agent framework." That space is crowded and general-purpose.

Position Aurora as:

> a local-first, verifier-first visual agent kernel for safe, replayable, self-improving desktop and 3D sandbox workflows.

The moat is not model size. The moat is reliable embodied execution under uncertainty: explicit state, safe actuation, observation-grounded verification, replayable telemetry, and human-approved improvement.
