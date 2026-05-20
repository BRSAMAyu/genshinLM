# Developer Guide

## Architecture Direction

Stages 28-37 evolve the project into a local embodied-agent OS:

- Knowledge Layer resolves resources, sources, spatial topology, and route traversal cost.
- Mission Planner converts user goals into validated MissionQueues.
- SkillBinder binds nodes to existing Skills; Verifiers prevent false completion.
- Runtime modules handle combat, collection, recovery, and bounded autonomous exploration.
- Learning and persistence make failures reviewable and resumable.

## Validation

```powershell
python -m compileall combat collection knowledge planning execution agentic learning persistence open_beta app_service scripts tests
python -m pytest -q
python scripts/validate_mvp.py
```

## Rules

- Do not add raw input paths for LLMs.
- Keep all physical input behind safe-window confirmation.
- Every MissionNode needs a verifier and failure policy.
- Failure screenshots must pass privacy masking before export or LLM review.

