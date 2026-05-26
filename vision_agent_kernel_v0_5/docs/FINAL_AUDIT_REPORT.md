# Aurora GenesisAgent Closure Audit

> Date: 2026-05-27
> Scope: pre-real-world closure audit for the GenesisAgent launcher, reflex combat director, strategy reader, and claim-centered runtime integration.
> Auditor: Codex

## Verdict

The current repository passes the dry-run/testbed acceptance baseline after this closure pass. The result is acceptable as an engineering baseline for the next calibration and supervised real-world validation phase.

This is not evidence that Aurora can already complete a live Genshin or HSR end-to-end run unattended. The accepted boundary remains dry-run, testbed, authorized safe-window execution, and explicit profile calibration before any unattended flow.

## Issues Fixed In This Closure Pass

1. Launcher log bootstrap is now clean-checkout safe. `logs/` is created before `launcher.log`, `backend.log`, or `frontend.log` are opened.
2. Launcher diagnostics no longer install dependencies implicitly. Environment repair now requires `--repair`.
3. Launcher Node repair and frontend startup no longer use shell command strings. `npm install`, `npm run build`, `npm run dev`, and `npm run tauri dev` are invoked as argument lists.
4. `CombatDirector.update()` no longer blocks on `time.sleep()` in the high-frequency combat path. Delays are represented by `_next_step_ready_at`.
5. `ClaimGraphWorker.snapshot()` now goes through the single-writer command queue instead of reading `ClaimGraph` directly.
6. New regression tests cover launcher repair/startup safety, nonblocking combo execution, reflex preemption, deterministic strategy graph compilation, and single-writer snapshot behavior.

## Validation Results

Commands were run from `D:\Aurora\vision_agent_kernel_v0_5` unless noted.

```powershell
python -m pytest tests/test_genesis_agent_interfaces.py tests/test_claim_events.py -q
```

Result: passed.

```powershell
$env:TMP='D:\Aurora\vision_agent_kernel_v0_5\.tmp_pytest'
$env:TEMP='D:\Aurora\vision_agent_kernel_v0_5\.tmp_pytest'
python -m pytest -q
```

Result: `1021 passed`.

The workspace-local `TMP`/`TEMP` override was required because the default Windows temp pytest directory was not accessible in this environment.

```powershell
python -m compileall app_service reflex planning runtime tests -q
```

Result: passed.

```powershell
python .\scripts\check_core_boundaries.py --root .
```

Result: `core boundary scan passed`.

```powershell
python .\scripts\run_aurorabench.py --suite all --mode dry-run --output-dir .\benchmark_reports\codex_genesis_closure
```

Result: all suites passed.

## Remaining Boundaries

These are not test failures, but they remain product acceptance boundaries for the next phase:

1. Real Genshin/HSR completion is unproven until profile calibration, supervised runs, and real failure traces exist.
2. Direct VLM/zero-shot paths must remain proposal-only unless gated through claim verification, risk policy, and user confirmation.
3. StrategyReader currently provides deterministic local parsing and mockable retrieval. It is not a production web-search subsystem.
4. Boss combat is still a testbed-first subsystem. Real boss clear rate should be measured later through BossBench and supervised calibration, not inferred from unit tests.
5. Existing real-window input code must stay constrained to authorized safe-window/testbed use. Passing tests does not grant acceptance for bypasses, process injection, memory reading, or anti-cheat-adjacent behavior.

## Next Gate

The next phase should start with profile calibration and supervised testbed-to-real validation:

1. Run launcher in headless mode and GUI mode from a clean environment.
2. Calibrate HSR and Genshin UI anchors.
3. Run one HSR UI-first flow and one Genshin teleport/navigate/collect flow under supervision.
4. Capture ClaimGraph, EvidenceGraph, InputLease receipts, audit results, and failure records.
5. Promote only the flows that produce verified/audited terminal claims.
