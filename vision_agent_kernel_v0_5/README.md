# Vision Agent Kernel v0.5

Vision Agent Kernel v0.5 is a local, dry-run-first visual interaction kernel for authorized 3D sandboxes, QA testbeds, self-built environments, AI coaching, and analysis workflows.

It provides screen capture, target tracking, FOV-aware camera servo, visual action blocks, obstacle recovery, task orchestration, runtime health telemetry, a desktop product shell, guided onboarding/calibration, Skill recording/editing, companion persona feedback, mock LLM planning, and combat reflex dry-run demos.

## Safety Boundary

- Default mode is `dry-run` with `ConsoleInputBackend`.
- Real input must be explicitly enabled through `safe-window`.
- Physical input is restricted to an authorized target window.
- F9 emergency stop, Ctrl+C handling, and `release_all` are preserved.
- The project does not implement online game automation, boosting, anti-cheat bypass, memory reading, process injection, driver-level input, or any unauthorized control path.

## Quick Start

```powershell
python -m pytest -q
python scripts/validate_mvp.py
python scripts/run_final_demo.py --mode dry-run --seconds 60 --chaos mild
python scripts/generate_demo_report.py --latest
python scripts/run_product_e2e.py --mode dry-run --seconds 20 --use-mock-llm
python scripts/run_product_demo.py --mode dry-run --seconds 30
python scripts/run_showcase_demo.py --mode dry-run --seconds 30
python scripts/doctor.py
```

## Local Service

Install service dependencies if needed:

```powershell
python -m pip install -r requirements.txt
```

Start the FastAPI service:

```powershell
uvicorn app_service.main:app --host 127.0.0.1 --port 8765
```

Smoke checks:

```powershell
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/state
curl http://127.0.0.1:8765/windows
curl http://127.0.0.1:8765/models/status
```

## Desktop GUI

The desktop shell lives in `desktop/`. It can run as a Vite web UI first, with Tauri structure preserved.

```powershell
cd desktop
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

Use the `Calibration` page for first-run setup:

1. Choose a dry-run oriented operating mode.
2. Select the authorized target window and preview its screenshot.
3. Draw ROIs on the screenshot and save them as relative or anchor-based regions.
4. Check model/tracker availability and run a lightweight benchmark.
5. Confirm dry-run input, F9 emergency stop, focus protection, and `release_all`.
6. Save the active profile under `configs/profiles/`.

Use the `Skill Library` page to start/stop recording, capture test-window events, add markers, inspect generated segments, save a reusable SkillDraft, validate it, and dry-run replay it. Use `Task Planner` for mock LLM TaskSpec generation and sandbox validation. Use `Companion` and `Combat` for persona event bubbles, playbook graph display, DangerScore, dodge cooldown, and reflex evasion history.

Use the `Product Demo` page to view the end-to-end acceptance checklist and trigger a dry-run product demo. The service endpoints are `GET /product/checklist`, `POST /product/run_e2e`, and `GET /product/latest_report`.

Use the Dashboard launcher for diagnostics and quick navigation. Use the Combat page's `Run Showcase Demo` button to execute the dry-run showcase and the Reports page's `Showcase` button to read `showcase_report.md` directly.

If the Tauri toolchain is installed:

```powershell
cd desktop
npm run tauri dev
```

## Stage Verification

```powershell
python scripts/run_visual_servo_test.py --mode dry-run --seconds 10
python scripts/run_visual_action_block_test.py --seconds 30 --mode dry-run
python scripts/run_chaos_recovery_test.py --scenario disappear --seconds 20
python scripts/run_endurance_test.py --seconds 180 --mode dry-run --chaos mild --save-report
python scripts/run_yolo_tracking_test.py --help
python scripts/run_fov_servo_test.py --fov 90 --seconds 20 --mode dry-run
python scripts/run_obstacle_recovery_test.py --scenario blocked --seconds 30
python scripts/run_task_demo.py --task configs/demo_task.yaml --seconds 60 --mode dry-run
python scripts/validate_mvp.py
python scripts/run_product_e2e.py --mode dry-run --seconds 20 --use-mock-llm
python scripts/run_product_demo.py --mode dry-run --seconds 10
python scripts/run_showcase_demo.py --mode dry-run --seconds 30
```

Skill recorder replay smoke:

```powershell
python -m pytest tests/test_skill_recording_replay.py -q
```

## Configuration

- `configs/model.yaml`: YOLO/Ultralytics backend, model path, tracker YAML, thresholds, device.
- `configs/profiles/index.json`: active calibration profile registry.
- `configs/profiles/default_1920x1080.json`: sample relative and anchor-based ROI profile.
- `configs/personas.json`: generated original persona profiles.
- `data/skills/index.json`: generated reusable Skill registry.
- `data/combat_profiles/*.yaml`: abstract non-IP combat profiles.
- `configs/demo_task.yaml`: final demo task spec.
- `action_blocks/demo_visual_action_block.yaml`: visual trigger action block.

## FAQ

- **FastAPI not installed:** run `python -m pip install -r requirements.txt`.
- **No Ultralytics model:** use the lightweight detector fallback for sandbox tests.
- **Safe-window exits early:** keep focus on the pseudo3d testbed window.
- **No screenshot preview:** choose a visible target window first and install Pillow if the service reports it missing.
- **No report:** run `python scripts/run_final_demo.py --mode dry-run --seconds 60`, then `python scripts/generate_demo_report.py --latest`.
