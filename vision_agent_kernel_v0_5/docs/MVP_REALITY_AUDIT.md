# MVP Reality Audit

Date: 2026-05-20

This audit is intentionally stricter than `pytest passed`. It asks whether each subsystem works in a real product chain, not whether its API shape exists.

## Reality Scale

- **R0 - Stub:** interface exists, behavior is placeholder.
- **R1 - Synthetic:** works with direct dictionaries, mock events, or in-memory arrays.
- **R2 - Local Component:** real local persistence/service/UI behavior, but not integrated into live perception/action.
- **R3 - Testbed Loop:** works against `pseudo3d_scene` or another controlled visual testbed.
- **R4 - Safe-Window Loop:** can act on an authorized window through safe-window protections.
- **R5 - Product Ready:** robust for non-developer users with recovery, reports, and realistic failure handling.

## Summary Table

| Area | Reality Level | Verdict |
| --- | ---: | --- |
| Knowledge | R1 | Demo knowledge pack with spatial graph. Not a real editable domain KB yet. |
| Planning | R2 | Can generate a valid `MissionQueue` from simple goals. Not yet semantically rich. |
| SkillBinder | R1 | Matches by skill id/type metadata. Does not prove the Skill works in the current scene. |
| Verifier | R1 | Verifiers inspect passed state dictionaries. They do not yet observe live frames. |
| Combat | R2 | Danger/playbook/reflex logic is real code, but danger inputs are synthetic or scripted. |
| Collection | R1 | Green-mask detector and collect flow exist in memory. No testbed collection loop yet. |
| Agentic | R1 | Proposes actions from OCR-like items and blocks destructive labels. No OCR/live UI loop yet. |
| Learning | R1 | Builds signatures and patch suggestions from supplied failure data. No log-ingestion loop yet. |
| Persistence | R2 | SQLite checkpoint/hot-resume storage works. Not integrated into Orchestrator resume. |
| GUI | R2 | GUI can control service, diagnostics, reports, planner demos, showcase. Not a full no-command-line install/launch experience. |

## Module Audit

### Knowledge

**What exists**

- `knowledge/resource_db.py`, `source_resolver.py`, `route_selector.py`, and `world_graph.py`.
- Default `material_x` demo resource with one source and waypoint route.
- Route ranking uses waypoint traversal cost rather than LLM-invented routes.

**Reality**

- **R1 Synthetic.**
- Data is default demo data unless a pack is loaded manually.
- There is no GUI editor/import validation for a real world knowledge pack.
- There is no observed map/world-position calibration from the testbed.

**Answer to prompt**

Knowledge is mostly demo data plus a real route-cost algorithm.

### Planning

**What exists**

- `planning/intent_parser.py` parses simple material goals.
- `TaskSpecBuilder` creates a `MissionQueue` with enter/acquire/combat/verify nodes.
- `PlanValidator` rejects forbidden raw-input node types and reports missing skills.
- Service endpoint: `POST /mission/plan`.

**Reality**

- **R2 Local Component.**
- It can generate a real `MissionQueue`, but only for narrow demo intents.
- It does not yet use real LLM output for mission graph generation.
- It does not yet query a large knowledge base or choose between several realistic strategies.

**Answer to prompt**

Planning can really generate a MissionQueue, but only for the demo material/resource shape.

### SkillBinder

**What exists**

- `execution/skill_binder.py` binds by exact `skill_id`, then by `type`.
- `MissionNodeExecutor` captures a state snapshot before high-risk nodes.
- Failure can report a cleanup skill under `recover_or_skip`.

**Reality**

- **R1 Synthetic.**
- Matching is metadata-based, not behavior-based.
- It does not inspect Skill preconditions deeply enough to prove compatibility.
- It does not execute the bound Skill against a live scene during binding.

**Answer to prompt**

SkillBinder can match a listed Skill, but it does not yet prove that Skill is executable or successful in the current environment.

### Verifier

**What exists**

- UI, visual, combat, and collection verifier classes.
- Combat verifier checks state like `target_hp_ratio` and `target_defeated`.
- Collection verifier checks state like `item_disappeared`, `gain_popup`, or `count_delta`.

**Reality**

- **R1 Synthetic.**
- Verifiers currently consume already-prepared state dictionaries.
- They are not yet connected to the perception pipeline to inspect live frames, OCR, HP bars, prompts, or reward popups.
- VisualActionBlock has trigger-driven waiting in earlier stages, but the general MissionNode verifier layer is not yet live-frame grounded.

**Answer to prompt**

Verifier does not yet truly observe the screen to decide success. It is a verifier contract with synthetic state inputs.

### Combat

**What exists**

- `DangerDetector`, `DodgePolicy`, `ReflexEvasion`, `CombatPlaybookRuntime`.
- Combat 2.0 helpers: cooldown OCR parsing, template readiness, HP bar ratio helper, interruption detector, checkpoint runtime.
- `pseudo3d_scene.py --combat-demo` displays warning arcs, projectile, danger zone, HP, dodge feedback.
- `run_showcase_demo.py` generates a combat showcase report.

**Reality**

- **R2 Local Component.**
- The playbook/reflex/cooldown logic is real local code.
- Danger events in demos are still passed as synthetic signal dictionaries.
- The detector does not yet infer `generic_warning_area`, projectile, HP drop, or enemy-facing state from pixels.

**Answer to prompt**

Combat is more than a pure mock, but still not a real visual combat detector. It is scripted/signal-driven.

### Collection

**What exists**

- `CollectableDetector` uses a green mask on a provided image.
- `InteractionPromptDetector` checks OCR-like text.
- `CollectRuntime` progresses through search/approach/interact/success states.

**Reality**

- **R1 Synthetic.**
- There is no dedicated collectable testbed scenario.
- There is no closed-loop movement toward a collectable.
- There is no real prompt OCR or safe-window interaction path for collection.

**Answer to prompt**

Collection cannot yet complete a real testbed collection task. It only works against in-memory frame arrays and synthetic state.

### Agentic

**What exists**

- `VisualGrounding` accepts OCR-like items.
- `ActionProposer` proposes dry-run click candidates.
- `ConfidenceGate` blocks destructive semantics such as delete/discard/dismantle/consume.
- Destructive actions require human override.

**Reality**

- **R1 Synthetic.**
- There is no OCR pipeline feeding live UI elements.
- It does not yet execute safe dry-run action candidates through a verifier.
- It correctly blocks dangerous labels, but only after receiving OCR text.

**Answer to prompt**

Agentic can propose actions from supplied OCR items. It cannot yet autonomously ground and test actions from a live UI.

### Learning

**What exists**

- `FailureSignatureBuilder`, `FailureClusterer`, `SkillPatchSuggester`, `ProfilePatchSuggester`, `LearningReport`.
- `PrivacyMask` can black out all pixels outside an allowed ROI and redact sensitive ROIs.

**Reality**

- **R1 Synthetic.**
- It does not yet ingest real telemetry/failure logs automatically.
- It does not yet connect generated patches to Skill Library review.
- It does not provide a visual review UI before export/upload.

**Answer to prompt**

Learning can generate a patch suggestion from supplied failure data. It does not yet learn from real run logs end-to-end.

### Persistence

**What exists**

- `SQLiteStore`, `MissionCheckpoint`, `HotResume`.
- Can save latest mission checkpoint and detect profile mismatch.

**Reality**

- **R2 Local Component.**
- SQLite persistence works.
- Orchestrator does not yet write checkpoints during every node.
- GUI does not yet offer a real hot-resume prompt.

**Answer to prompt**

Persistence can store and read checkpoints, but task execution is not yet resumable after interruption.

### GUI

**What exists**

- Dashboard can start/pause/resume/stop/emergency stop through FastAPI.
- Dashboard can run diagnostics.
- Combat page can trigger danger and run Showcase.
- Reports page can read kernel/product/showcase reports.
- Calibration/Skill/Planner pages exist.

**Reality**

- **R2 Local Component.**
- GUI can operate meaningful parts of the system without typing the corresponding Python commands after the service is running.
- There is no packaged one-click desktop launcher that starts service and GUI without a shell.
- Several GUI flows still surface JSON/debug output instead of polished product interactions.

**Answer to prompt**

GUI can complete demo monitoring and report viewing, but not yet the full no-command-line user journey.

## Real Chain Verdict

Current MVP is a **broad local agent framework with several working synthetic/testbed demos**, not yet a fully grounded embodied-agent operating system.

The strongest real pieces are:

- Input lease/deadman/release-all safety.
- Local FastAPI + GUI control plane.
- Visual servo/testbed demos from earlier stages.
- Product E2E dry-run.
- Combat playbook/reflex logic as a dry-run showcase.
- Diagnostics and report loading.

The weakest true-grounding gaps are:

- MissionNode Verifiers do not yet read live observations.
- Collection has no real testbed loop.
- SkillBinder is metadata matching rather than observed capability matching.
- Agentic exploration has no live OCR/visual UI loop.
- Learning is not fed by real failure logs.
- Hot resume is not integrated into orchestration.

## Commands Used During Audit

```powershell
python -m compileall combat collection knowledge planning execution agentic learning persistence open_beta app_service scripts testbed tests
python -m pytest -q
python scripts/doctor.py
python scripts/validate_mvp.py
python scripts/run_product_demo.py --mode dry-run --seconds 10
python scripts/run_product_e2e.py --mode dry-run --seconds 20 --use-mock-llm
python scripts/run_showcase_demo.py --mode dry-run --seconds 30
npm run build
```

These passing commands are useful smoke evidence, but they do not prove full real-world grounding.
