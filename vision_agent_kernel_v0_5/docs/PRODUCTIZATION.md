# Productization Architecture

Stage 19 turns the kernel into a local desktop product shell. Stage 20 adds onboarding, calibration, and model management so users do not have to edit YAML by hand.
Stage 21 adds Skill recording/editing/versioning. Stage 22 adds companion persona feedback and safe mock LLM planning. Stage 23 adds combat playbook and reflex evasion dry-run demos.

## Layers

- **Kernel:** perception, control, execution, orchestration, telemetry.
- **Local Service:** `app_service/` exposes REST and WebSocket endpoints through FastAPI.
- **AgentController:** thread-safe facade over lifecycle commands. API handlers never access kernel worker threads directly.
- **Desktop Shell:** `desktop/` React/Vite UI with Tauri structure for packaging.
- **Calibration Store:** `configs/profiles/` contains active and versioned window/ROI calibration profiles.
- **Model Manager:** service facade for detector backend, model path, tracker config, and lightweight benchmark checks.
- **Skill System:** `data/skills/` stores versioned reusable skills with schema validation and dry-run replay.
- **Persona Layer:** `persona/` translates kernel events into original companion messages.
- **LLM Planner:** `llm/` exposes safe tool schemas, mock/GLM/MiniMax providers, and sandbox validation.
- **Combat Intelligence:** `combat/` validates playbooks and emits reflex dodge intents from danger signals.

## API

- `GET /health`
- `GET /state`
- `POST /agent/start`
- `POST /agent/pause`
- `POST /agent/resume`
- `POST /agent/stop`
- `POST /agent/emergency_stop`
- `GET /runs/latest`
- `GET /config/current`
- `GET /windows`
- `POST /window/select`
- `GET /capture/snapshot`
- `POST /calibration/profile`
- `GET /calibration/profiles`
- `GET /calibration/profiles/{id}`
- `POST /calibration/test`
- `GET /models/status`
- `POST /models/load`
- `POST /models/benchmark`
- `POST /skills/record/start`
- `POST /skills/record/stop`
- `GET /skills`
- `POST /skills`
- `POST /skills/{id}/validate`
- `POST /skills/{id}/dry_run`
- `POST /persona/event`
- `POST /planner/task`
- `POST /combat/playbook`
- `POST /combat/danger`
- `GET /product/checklist`
- `POST /product/run_e2e`
- `GET /product/latest_report`

## WebSocket

`/ws/state` pushes `AgentStateSummary` at 5Hz. Dashboard and Run Monitor subscribe to this stream.

## Safety Model

The product shell defaults to `console` dry-run input. Emergency stop is routed through `AgentController.emergency_stop()`, which submits a P0 interrupt and calls `release_all` through the worker/backend path.

## Desktop UX

The current shell includes Dashboard, Run Monitor, Reports, Settings, Calibration, and placeholders for Skill Library and Task Planner. It is designed as a lightweight local control surface rather than an administrative table UI.

## Calibration Workflow

The Calibration page is a six-step wizard:

1. Select a safety-first operating mode.
2. Select a visible target window and preview a screenshot.
3. Draw ROIs directly on the screenshot.
4. Save each ROI as either relative ratios or anchor-based pixel offsets.
5. Check detector/model/tracker availability and run a lightweight benchmark.
6. Confirm dry-run safety defaults and save the active profile.

Profiles are saved in `configs/profiles/`. Re-saving the same profile creates a previous-version copy under `configs/profiles/versions/`, and `profiles/index.json` tracks the active profile.

## LLM And Companion

The planner supports `mock`, `glm`, and `minimax`. Real providers read keys from `GLM_API_KEY` and `MINIMAX_API_KEY`, use request guards for rate/cost limits, and fail over to mock if unavailable. Companion UX supports persona selection, event bubbles, emotion states, and failure explanations.

## Product E2E

`scripts/run_product_e2e.py` and `/product/run_e2e` execute the product acceptance chain:

1. Check service health and active calibration profile.
2. Validate the selected Skill.
3. Generate a mock LLM TaskSpec and run sandbox validation.
4. Confirm safe input backend and emergency-stop policy.
5. Dry-run the Skill.
6. Write `product_e2e_trace.jsonl` and `product_e2e_report.md`.
7. Stop the worker and verify `release_all_called`.

Safe-window mode is gated. It requires a selected target window whose title matches the authorized testbed markers, and it returns `confirm_required` until the user explicitly confirms execution.

## Skill Recording And Replay

Stage 25 adds recorder backend layering:

- `MockRecorderBackend`: default safe path for GUI and tests.
- `TestWindowRecorderBackend`: records only focused authorized pseudo3d/testbed/QA windows.
- `GlobalHookBackend`: interface stub only; disabled by default with a safety error.

Recording events include key down/up, mouse move/click, waits, active-window state, visual snapshot summaries, timestamps and markers. Events are enriched with target state, focus state, active ROI profile, observation frame id and detected visual triggers.

SkillDraft slicing uses pause gaps, visual state changes, user markers, target lost/reacquired transitions and action-burst grouping. Replay defaults to dry-run. Safe-window replay requires explicit confirmation and focused target window before any action is converted into `InputLease`.

## Tauri Notes

The `desktop/src-tauri/` folder is present. If Rust/Tauri tooling is unavailable, run the Vite web UI directly and keep the same service API.
