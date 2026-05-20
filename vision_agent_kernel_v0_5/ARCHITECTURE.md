# Architecture

## Five Planes

- **Perception:** screen/video capture, YOLO or lightweight detection, tracking, visual trigger detection, obstacle estimation.
- **Control:** FOV-aware camera servo, progress supervision, obstacle policy, recovery policy.
- **Execution:** input lease, background InputWorker, dry-run/safe-window backends, visual action blocks.
- **Orchestration:** task graph, skills, failure policy, retry/recovery transitions.
- **Telemetry:** bounded JSONL logging, runtime health sampling, reports.
- **Product Shell:** FastAPI service, React/Tauri UI, calibration wizard, Skill editor, companion overlay and combat demo panels.

## StateBus

`StateBus` is the only shared state path. It provides latest observation slots, bounded ring buffers, priority interrupt queues, mode queues and heartbeats. Full image history is not retained; runners publish observation summaries and bounded references only.

## Interrupts

Interrupts are priority ordered. P0 emergency and focus loss require input release. P1/P2 recovery events such as `TARGET_LOST`, `NO_TASK_PROGRESS`, `WATCHDOG_TIMEOUT`, `STALE_OBSERVATION` are routed through StateBus and orchestrator transitions.

## Input Lease

Controller produces intents. InputWorker owns backend calls, lease expiry and Deadman release. Stop paths and P0 interrupts call `release_all`.

## Camera Servo

Camera servo converts pixel center error into angular yaw/pitch error using CameraModel FOV. Gain, dead zone, smoothing and invert flags are configuration-level controls.

## Visual Action Block

Visual action blocks wait on visual triggers in small chunks, check P0/P1 interrupts between chunks, pause on `TARGET_LOST`, emit combo step telemetry and return `SkillResult`.

## Skill System

Skills are versioned JSON definitions stored in `data/skills/`. The recorder produces raw events, automatic segments, suggested preconditions, visual checkpoints, success criteria and fallbacks. Validation rejects permanent `key_down`, missing focus/interrupt safety, missing duration, unsafe tools and missing profiles.

## Persona And Planner

The persona layer translates kernel events into original companion messages. LLM providers are high-level planners only; mock, GLM and MiniMax providers create TaskSpec proposals that must pass sandbox validation and user confirmation before running.

## Combat Intelligence

Combat playbooks are schema-validated graphs. Reflex evasion computes `DangerScore`, emits P1 `DODGE_REFLEX`, applies dodge cooldown and resumes through reacquire/checkpoint logic.

## Telemetry

Telemetry uses a bounded priority queue. Low priority observation summaries may be dropped under pressure; interrupts, transitions and skill results are preserved. Reports are generated from JSONL and health summaries.
