# Gap List

This file lists the concrete gaps discovered by the Stage 38 reality audit. The order is implementation priority, not architectural elegance.

## Current Status

The original Stage 38 gaps below are preserved for traceability. The P0 items have been addressed with deterministic testbed-real acceptance scripts; see `docs/P0_P1_P2_CLOSURE_REPORT.md`. Remaining work is now mostly P1/P2 hardening and product polish, not hidden behind broad "pytest passed" claims.

## P0 - Blocks Real Agent Claim

### 1. Verifiers Are Not Live-Frame Grounded

Status: fixed for testbed-real acceptance.

Original finding: current verifiers consume dictionaries such as `{"target_hp_ratio": 0.5}`. They must consume `Observation`, ROI snapshots, OCR results, detector outputs, or UI telemetry produced by the perception pipeline.

Required:

- `VerifierContext` with `Observation`, `TargetTrack`, `ROI profile`, `latest OCR`, and `runtime state`.
- Combat verifier reads HP bar or target disappearance from actual testbed frames.
- Collection verifier reads collectable disappearance or gain prompt from actual frames.

### 2. Realistic Testbed Scenarios Are Missing

Status: fixed with `testbed/realistic_scenarios.py` and `scripts/run_realistic_testbed_suite.py`.

Original finding: `pseudo3d_scene.py` has moving target, chaos, obstacle, and combat overlays, but it lacks task-specific state machines:

- monster task: HP decreases after action, target disappears on defeat.
- collection task: collectable appears, prompt appears near range, item disappears after interact.
- mixed mission: combat then collection.
- long-horizon sequence: multiple nodes, checkpointable progress.

### 3. Mission Executor Is Not Wired Into Orchestrator

Status: fixed at MissionRunner layer; GUI/orchestrator product wiring remains P2 polish.

Original finding: `MissionNodeExecutor` exists, but Orchestrator does not yet run MissionQueues node-by-node with SkillBinding + SkillResult + VerifierResult + checkpoint persistence.

Required:

- MissionQueue runner.
- Per-node telemetry.
- Failure policy dispatch.
- Cleanup Skill execution.

### 4. SkillBinder Does Not Prove Skill Capability

Status: partially fixed. Execution no longer treats binding as success, but richer capability scoring remains future work.

Original finding: binding by `skill_id` or `type` is insufficient. It must evaluate:

- environment profile compatibility.
- required visual triggers.
- success criteria.
- current target/source type.
- recent success stats.
- verifier compatibility.

### 5. User Recording Is Not Yet Truly Product-Closed

Status: fixed with `scripts/run_real_skill_recording_suite.py`.

Original finding: Recorder has mock and test-window backends, but the full user loop is not proven:

record in testbed -> SkillDraft -> edit checkpoint/fallback -> validate -> replay -> bind -> verifier success.

## P1 - Blocks Robust Demo

### 6. Combat Danger Is Still Signal-Injected

Status: partially fixed. Multimodal HP helper was corrected; full pixel/projectile danger inference remains open.

Original finding: DangerDetector consumes signal dictionaries. It should infer danger from:

- warning pixels/shape in ROI.
- projectile motion between frames.
- target bbox expansion.
- HP bar changes.
- scripted testbed danger metadata only as test oracle, not runtime input.

### 7. Collection Runtime Is In-Memory Only

Status: partially fixed. Testbed collect verifier and alignment action are present; full live-capture routing remains open.

Original finding: CollectRuntime needs:

- collectable render in testbed.
- detector from live capture.
- approach/alignment intent.
- interaction prompt detector.
- verifier observing disappearance/popup.

### 8. Hot Resume Is Not Orchestrator Integrated

Status: partially fixed. MissionRunner saves per-node checkpoints and can skip completed nodes on resume. GUI resume prompt remains open.

Original finding: SQLite checkpoint storage works, but:

- no checkpoint per node.
- no resume prompt in GUI.
- no environment revalidation before resume.
- no skip of already verified nodes.

### 9. Failure Learning Is Not Connected To Logs

Status: partially fixed. JSONL telemetry ingestion and privacy masking acceptance are present. GUI patch review remains open.

Original finding: FailureSignatureBuilder is manual. It needs:

- telemetry parser.
- failure signature generation from failed MissionNode runs.
- privacy mask before image/report export.
- Skill Library patch review.

### 10. GUI Still Shows Internal JSON

Reports and combat diagnostics work, but product UX needs:

- guided status cards.
- actionable missing-Skill prompts.
- verifier failure explanations.
- hot-resume prompt.
- human override modal for destructive UI detection.

## P2 - Open Alpha Polish

### 11. Knowledge Editing Is Manual

Need import/export UI and validation for resources, sources, waypoints, routes, and traversal cost.

### 12. LLM Real Provider Needs Safer Product UX

Provider config exists, but open-alpha needs:

- key test button.
- call budget display.
- failure state display.
- generated MissionQueue diff before confirm.

### 13. Benchmark Is Synthetic

BenchmarkSuite summarizes supplied run dictionaries. It needs to parse real run folders and compute metrics from JSONL traces.

### 14. Feedback Package Needs GUI Review

Feedback package builder exists, but no GUI review surface for redacted logs/screenshots.

### 15. Release Packaging Is Not Done

Status: partially fixed. Release zip script and issue templates are present; installer-grade packaging and richer example bundles remain open.

Original finding: need zip/release script, issue templates, example assets, and first-run profile/skill bundle.
