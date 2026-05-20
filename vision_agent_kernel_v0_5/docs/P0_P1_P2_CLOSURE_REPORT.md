# P0/P1/P2 Closure Report

This report records the concrete fixes after the Stage 38 reality audit. The project is still not claimed as a production general-purpose embodied OS; the claim after this pass is narrower: the critical gaps now have deterministic, repeatable testbed-real acceptance paths instead of only synthetic unit tests.

## P0 Fixes

### Verifiers Are Frame-Grounded

Implemented `VerifierContext` in `execution/verifier_base.py`. Verifiers can now consume:

- runtime state
- `Observation`
- `TargetTrack`
- raw frame
- ROI frame map
- OCR text
- metadata

Updated verifiers:

- `execution/combat_verifier.py` reads HP from a red HUD bar in the actual frame and checks target disappearance.
- `execution/collection_verifier.py` detects green collectables in the frame and verifies disappearance/gain popup.
- `execution/visual_verifier.py` checks `TargetTrack`/`Observation`, not only a state dictionary.
- `execution/ui_verifier.py` checks OCR text and state.

### Realistic Testbed Suite

Added `testbed/realistic_scenarios.py` and `scripts/run_realistic_testbed_suite.py`.

Acceptance cases:

- `combat_task`: attack lowers HP, target disappears, combat verifier passes.
- `collection_task`: prompt appears, interact removes collectable, collection verifier passes.
- `mixed_task`: combat plus collection.
- `target_lost_recovery`: target disappears and is reacquired.
- `mission_resume`: MissionRunner checkpoints and resumes completed nodes.

Command:

```powershell
python scripts/run_realistic_testbed_suite.py
```

Expected output:

```text
combat_task: PASS
collection_task: PASS
mixed_task: PASS
target_lost_recovery: PASS
mission_resume: PASS
```

### Mission Execution No Longer Equals Binding

Updated `execution/mission_node_executor.py`:

- Binds a skill.
- Calls an actual `skill_runner` when provided.
- Verifies the post-execution `VerifierContext`.
- Supports verifier-only nodes without falsely requiring a skill.
- Calls cleanup runner on recover-or-skip failures.
- Captures snapshots for high-risk nodes.

Added `planning/mission_runner.py`:

- Runs MissionQueue nodes.
- Saves per-node checkpoints via HotResume.
- Skips completed nodes on resume.

### User Recording Loop

Added `scripts/run_real_skill_recording_suite.py`.

It exercises:

- authorized `test-window` recorder backend
- SkillDraft generation
- auto-segmentation
- SkillStore save and versioning
- SkillValidator
- dry-run runtime
- safe-window replay with explicit confirmation
- InputLease submission
- release_all on InputWorker stop

Command:

```powershell
python scripts/run_real_skill_recording_suite.py
```

Cases:

- `open_demo_menu_skill`
- `collect_visible_item_skill`
- `basic_combat_combo_skill`

## P1 Fixes

### Combat Multimodal Helper Cleaned Up

`combat/resource_manager.py` now implements an actual RGB-to-HSV-style red mask for HP bars and avoids divide-by-zero warnings.

`combat/checkpoint_runtime.py` now stores remaining combo steps and exposes a `resume_plan()`.

`combat/combat_fallback_policy.py` now follows the documented order:

1. action
2. combo
3. tactical
4. mission

### Collection Alignment Added

`collection/collect_runtime.py` now returns `ALIGN`/`align_interaction_prompt` when the collectable is visible but not centered enough for interaction.

### Learning Can Ingest Logs

Added `learning/telemetry_ingestor.py` and `scripts/run_learning_suite.py`.

Command:

```powershell
python scripts/run_learning_suite.py
```

Checks:

- JSONL failure ingestion
- privacy masking
- Skill patch suggestion from failure signature

### Agentic Safety Has Acceptance Script

Added `scripts/run_agentic_safety_suite.py`.

Command:

```powershell
python scripts/run_agentic_safety_suite.py
```

Checks:

- destructive UI blacklist
- safe high-confidence dry-run proposal
- low-confidence demonstration request

## P2 Fixes

### Open Beta Run Parsing

`open_beta/benchmark_suite.py` can now read real run folders with JSONL traces and summarize task completion, skill success, verifier records, target-lost count, recovery count, intervention count, and duration.

Added:

```powershell
python scripts/run_open_beta_suite.py
```

Checks:

- benchmark reads a run folder
- dangerous blueprint import is rejected
- feedback packages stay redacted and non-uploading by default

### Release Packaging

Added:

```powershell
python scripts/package_release.py --out dist/aurora_open_alpha.zip
```

The package excludes logs, run folders, caches, and private runtime artifacts.

### Open Alpha Templates

Added:

- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/safety_report.md`
- `.github/ISSUE_TEMPLATE/skill_blueprint.md`
- `CONTRIBUTING.md`

## Remaining Limitations

These are now explicit open-alpha product tasks, not hidden MVP claims:

- DangerDetector still accepts signal dictionaries for some demo paths; full pixel/projectile inference remains future work.
- GUI does not yet expose every new realistic suite as a one-click card.
- Knowledge editing is still file/import oriented.
- Real LLM providers remain guarded and optional; mock remains default.
- Release packaging is script/zip based rather than installer-grade.

## Commands Run In This Closure Pass

```powershell
python scripts/run_realistic_testbed_suite.py
python scripts/run_real_skill_recording_suite.py
python scripts/run_agentic_safety_suite.py
python scripts/run_learning_suite.py
python scripts/run_open_beta_suite.py
python scripts/package_release.py --out dist/aurora_open_alpha_test.zip
python -m pytest -q
```
