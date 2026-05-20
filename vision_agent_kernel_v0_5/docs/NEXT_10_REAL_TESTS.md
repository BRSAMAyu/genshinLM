# Next 10 Real Tests

These tests were introduced by the Stage 38 audit. Items 1-9 now have automated acceptance commands. Item 10 remains a manual/product QA pass because it requires launching the GUI.

## 1. Realistic Combat Task

Command:

```powershell
python scripts/run_realistic_testbed_suite.py --case combat_task
```

Expected:

```text
combat_task: PASS
```

Scenario:

- monster target appears.
- agent locks target.
- action block triggers attack intent.
- testbed HP decreases.
- target disappears at zero HP.
- combat verifier reads target disappearance or HP zero from frames.

## 2. Realistic Collection Task

Command:

```powershell
python scripts/run_realistic_testbed_suite.py --case collection_task
```

Expected:

```text
collection_task: PASS
```

Scenario:

- collectable appears.
- agent approaches/alignment reaches range.
- interaction prompt appears.
- interact action fires.
- item disappears or gain popup appears.
- collection verifier confirms success from frames.

## 3. Mixed Combat + Collection Mission

Command:

```powershell
python scripts/run_realistic_testbed_suite.py --case mixed_task
```

Expected:

```text
mixed_task: PASS
```

Scenario:

- MissionQueue: enter region -> combat -> verify reward -> collect item -> final verify.
- Each node must have SkillBindingResult and VerifierResult.
- No node may mark complete without verifier success.

## 4. Target Lost Recovery

Command:

```powershell
python scripts/run_realistic_testbed_suite.py --case target_lost_recovery
```

Expected:

```text
target_lost_recovery: PASS
```

Scenario:

- target disappears or is occluded.
- tracker enters COASTING then LOST.
- MissionNode failure policy triggers reacquire/recover.
- task returns to acquire target and continues.

## 5. Mission Resume

Command:

```powershell
python scripts/run_realistic_testbed_suite.py --case mission_resume
```

Expected:

```text
mission_resume: PASS
```

Scenario:

- MissionQueue reaches node 2.
- process stops.
- checkpoint is persisted.
- restart prompts resume.
- completed nodes are not repeated.
- resume continues from last safe node.

## 6. User-Recorded Combat Skill Loop

Command:

```powershell
python scripts/run_real_skill_recording_suite.py --case basic_combat_combo_skill
```

Expected:

```text
basic_combat_combo_skill: PASS
```

Scenario:

- user/test harness records a combat combo in testbed.
- SkillDraft contains checkpoint and fallback.
- validate passes.
- dry-run replay passes.
- safe-window replay passes under focus check.
- MissionPlanner binds the Skill.
- combat verifier confirms target defeated.

## 7. User-Recorded Collection Skill Loop

Command:

```powershell
python scripts/run_real_skill_recording_suite.py --case collect_visible_item_skill
```

Expected:

```text
collect_visible_item_skill: PASS
```

Scenario:

- record approach + interact.
- SkillDraft captures prompt checkpoint.
- replay uses InputLease.
- collection verifier confirms item disappearance.

## 8. Destructive UI Human Override

Command:

```powershell
python scripts/run_agentic_safety_suite.py --case destructive_ui
```

Expected:

```text
destructive_ui: PASS
```

Current command:

```powershell
python scripts/run_agentic_safety_suite.py
```

Current output:

```text
destructive_ui_blacklist: PASS
safe_high_confidence_proposal: PASS
low_confidence_requires_confirmation: PASS
```

Scenario:

- testbed displays an unknown button labeled delete/discard/dismantle/consume.
- OCR detects label.
- ConfidenceGate returns `HUMAN_OVERRIDE_REQUIRED`.
- no dry-run or real action is attempted.
- Companion warns the user.

## 9. Failure Learning From Real Trace

Command:

```powershell
python scripts/run_learning_suite.py --case failed_combat_trace
```

Expected:

```text
failed_combat_trace: PASS
```

Current command:

```powershell
python scripts/run_learning_suite.py
```

Current output:

```text
failure_log_ingest: PASS
privacy_mask_redacts: PASS
skill_patch_suggested: PASS
```

Scenario:

- force combat verifier failure.
- telemetry parser creates FailureSignature.
- screenshots pass PrivacyMask.
- clusterer groups similar failure.
- Skill patch suggestion is shown but not applied without user confirmation.

## 10. GUI No-Command Product Flow

Manual or Playwright-backed test:

```text
start service
open GUI
run diagnostics
select testbed window
load profile
load/record skill
generate MissionQueue
confirm dry-run
run task
open report
```

Expected:

```text
gui_product_flow: PASS
```

Acceptance:

- no direct Python command required after service/GUI launch.
- all unsafe actions remain disabled by default.
- report includes verifier results, failures, and release_all status.

## Required Suite Output

Implemented:

```powershell
python scripts/run_realistic_testbed_suite.py
```

And print:

```text
combat_task: PASS
collection_task: PASS
mixed_task: PASS
target_lost_recovery: PASS
mission_resume: PASS
```
