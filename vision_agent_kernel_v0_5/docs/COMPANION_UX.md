# Companion UX

The companion layer provides a user-friendly overlay for kernel events, task status and failure explanations.

## Personas

Available personas:

- `default_companion`
- `cheerful_guide`
- `calm_operator`
- `healing_partner`
- `developer_mode`

Profiles live in `configs/personas.json`. They are original placeholder personas and do not use unauthorized official characters, voices or lines.

## Emotions

Supported emotions:

- `normal`
- `thinking`
- `nervous`
- `happy`
- `warning`

Events such as `TARGET_LOST`, `RECOVERY_STARTED`, `DODGE_REFLEX`, `SKILL_TIMEOUT`, `TASK_COMPLETE` and `FOCUS_LOST` map to an overlay state and emotion.

## Overlay Controls

The GUI companion page supports:

- persona selection
- mock event trigger
- latest bubble display
- emotion display
- current task summary through planner output
- failure explanation through `/planner/explain_failure`
- visible pause/emergency stop controls

All suggested patches require user confirmation before changing configuration.
