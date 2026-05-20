# Showcase Demo

The showcase is a dry-run-first product acceptance path for authorized sandbox work. It demonstrates persona selection, combat playbook validation, danger scoring, reflex dodge cooldown, checkpoint recovery, and report generation.

## Run

```powershell
python scripts/run_showcase_demo.py --mode dry-run --seconds 30
```

Optional testbed visualization:

```powershell
python testbed/pseudo3d_scene.py --combat-demo
```

Safe-window mode is restricted to the authorized `pseudo3d_scene` window title. If the target title does not match the sandbox, the script refuses to run.

## Output

Each run creates:

- `logs/runs/<run_id>/showcase_trace.jsonl`
- `logs/runs/<run_id>/showcase_report.md`

The report includes:

- playbook nodes executed
- skill dry-run success rate
- danger events
- dodge count
- dodge success/failure
- target lost count
- recovery count
- final outcome
- companion summary
- suggested skill patch

## Safety

The showcase does not call raw mouse or keyboard APIs. Combat modules emit validated playbooks, interrupts, and short lease-style dodge intents. Physical execution remains behind safe-window confirmation and the normal `release_all` shutdown path.
