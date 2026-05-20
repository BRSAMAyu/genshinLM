# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

**Sparkle Project** — 端侧视觉交互 Agent 内核 (Vision Agent Kernel v0.5)。面向 ACG 玩家的桌面端赛博伴游与具身智能控制中枢的内核 MVP。仅限授权 3D 沙盒 / 自建 ARPG 测试环境 / QA 单机研究环境。

完整产品愿景与架构哲学见 `PROJECT_ALIGNMENT.md`，该文件是本项目的"宪法"，所有代码决策必须符合其原则。

## Commands

```bash
# Install
pip install -e ".[dev]"          # core + dev tools
pip install -e ".[testbed]"      # + pygame testbed

# Test
pytest                           # all tests
pytest tests/test_state_bus.py   # single file
pytest -x                        # stop on first failure

# Lint / Type
ruff check .
mypy core/ perception/ control/ execution/ orchestration/

# Run demos (all default to dry-run / console backend)
python scripts/run_kernel.py
python scripts/run_final_demo.py
python scripts/run_testbed.py
```

## Architecture: The 5-Plane Model

All cross-plane communication goes exclusively through **StateBus** (thread-safe) or event queues. Direct cross-plane calls are forbidden.

```
Perception (high-freq)  →  Observation  →  StateBus
Control (mid-freq)      ←  TargetTrack/Progress/Frustration  →  Interrupts
Execution (strict seq)  ←  InputLease/DeadmanSwitch  →  InputWorker
Orchestration (event)   ←  SkillResult/TaskGraph  →  ModeTransitions
Telemetry (async)       ←  JSONL + video recording (bounded queue)
```

**StateBus** (`core/state_bus.py`): Central hub with `LatestSlot[T]`, `RingBuffer[T]`, `PriorityEventQueue[T]`. Holds `latest_observation`, `observation_ring` (300 frames), `event_queue` (priority interrupts), `mode_request_queue`, `heartbeat_table`, `shutdown_flag`.

**Interrupt priorities** (lower = higher urgency):
- P0 (0): Emergency stop, focus loss — requires input release
- P1 (10): Watchdog timeout
- P2 (20): Human override
- P3 (30): Action block exclusive
- P4 (40): Recovery
- P5 (50): Tracking
- P6 (100): Idle

**Mode state machine** (`core/mode_arbiter.py`): Priority-based preemption with terminal mode protection. `EMERGENCY_STOPPED` can only transition to itself.

## Key Design Rules

1. **No blocking waits** — Use chunked waits (~50ms loops) checking StateBus interrupts. Never `time.sleep()` for long durations.
2. **No single-frame decisions** — Progress/frustration uses EWMA + time-window slopes, never `current_frame vs previous_frame`.
3. **Monotonic clock only** — `time.perf_counter()` everywhere. `time.time()` is banned for logic.
4. **LLM stays strategic** — LLM decides *which skill to use*, never *how many pixels to move*.
5. **Every action has a fallback** — Default assumption is failure. Drive state forward via visual feedback (Visual Checkpoint), not timers.

## Safety Model

- Default mode is **dry-run** (`ConsoleInputBackend` — prints actions, never touches OS input).
- `SafeWindowInputBackend` must be explicitly selected; verifies target window focus before input.
- All physical input flows through `InputLease` → `InputWorker`. Controllers never call OS input APIs directly.
- **Deadman switch**: lease expiry, thread death, or focus loss triggers immediate `release_all`.
- Emergency stops: F9 key, Ctrl+C/SIGTERM, watchdog timeout — all call `release_all`.

## Core Data Flow

```
ScreenCapture (DXcam/MSS)
  → FramePacket → YOLO Detector → TargetCandidate[]
  → BoT-SORT Tracker → TargetTrack
  → VisualTriggerDetector → trigger dict
  → Observation (published to StateBus)
```

```
TargetTrack → CameraServo (FOV-aware pixel→yaw/pitch) → CameraIntent
            → ProgressSupervisor → ProgressState (frustration, slope, oscillation)
            → RecoveryPolicy / ObstaclePolicy → MovementIntent or Interrupt
```

## Config

YAML configs in `configs/`: `default.yaml`, `control.yaml`, `perception.yaml`, `input.yaml`, `telemetry.yaml`, `testbed.yaml`, `model.yaml`. Action block definitions in `action_blocks/`. Task specs loaded from YAML via `orchestration/task_spec.py`.

## Type System

- All core types use `@dataclass(slots=True)` in `core/types.py` — `Observation`, `TargetTrack`, `TargetCandidate`, `ObstacleField`, `CameraIntent`, `MovementIntent`, `InputLease`, `ProgressState`, `SkillResult`.
- Events: `Interrupt(priority, code, source, ...)` and `ModeRequest` in `core/events.py`.
- Protocols (not ABCs) for pluggable components: `Detector`, `Tracker`, `ScreenCapturer`, `ObstacleEstimator` in their respective `*_base.py` files.

## Python Style

- Python 3.11+, `from __future__ import annotations` in all files.
- `slots=True` on all dataclasses.
- Ruff: line-length 100, target py311, rules E/F/I/B/UP/ANN (ignore ANN101/ANN102).
- MyPy: strict mode, `disallow_untyped_defs = true`.
- Pytest: `testpaths = ["tests"]`, `pythonpath = ["."]`.
