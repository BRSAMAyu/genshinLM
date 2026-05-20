# Persona Layer

The persona layer translates low-level kernel events into user-facing companion feedback.

## Profiles

Profiles live in `configs/personas.json` and are generated on first service start.

Each profile contains:

- `persona_id`
- `name`
- `style`
- `tone`
- `avatar_asset`
- `voice_config`
- `event_templates`
- `safety_style`
- `technical_detail_level`

The default personas are original placeholders: `default_companion`, `cheerful_guide`, `calm_operator`, `healing_partner`, and `developer_mode`.

## Boundaries

The MVP does not use unauthorized character art, voices, official lines, or branded IP. Voice output is text-only unless a future authorized voice pack is configured.

## Events

Supported translations include `TARGET_LOST`, `NO_TASK_PROGRESS`, `RECOVERY_STARTED`, `SKILL_TIMEOUT`, `TASK_COMPLETE`, `FOCUS_LOST`, `EMERGENCY_STOP`, and `DODGE_REFLEX`.
