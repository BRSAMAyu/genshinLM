# Contributing

Aurora is a visual interaction agent kernel for authorized sandbox, QA, and research environments. Contributions must preserve the safety boundary: no online game automation, no anti-cheat bypass, no memory reading, and no driver or hardware input injection.

## Before Opening A PR

Run:

```powershell
python -m compileall app_service persona llm combat collection agentic learning persistence execution perception control orchestration planning knowledge scripts testbed tests
python -m pytest -q
python scripts/validate_mvp.py
python scripts/run_realistic_testbed_suite.py
python scripts/run_real_skill_recording_suite.py
python scripts/run_agentic_safety_suite.py
python scripts/run_learning_suite.py
python scripts/run_open_beta_suite.py
```

## Safety Rules

- Default execution must remain dry-run.
- Safe-window execution must check the authorized target window.
- P0/P1 interrupts must release input leases.
- LLM providers may only call whitelisted planning and explanation tools.
- Destructive UI semantics must require human override.
- Feedback packages must be redacted by default.

## Code Style

- Keep state flowing through `StateBus` or explicit context objects.
- Do not make controllers depend on vendor detector internals.
- Verifiers should consume post-execution observations, not pre-action assumptions.
- Prefer small deterministic testbed acceptance scripts for new behavior.
