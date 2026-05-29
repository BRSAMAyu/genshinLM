# Pipeline Integration Worklog

## Goal: Aurora kernel autonomous Genshin main storyline completion

---

## Round 1: Pipeline Connection Audit & Critical Fixes

**Date**: 2026-05-30

### Problem Identified
The project had 5 well-designed planes (Perception, Control, Execution, Orchestration, Telemetry) but they were **not connected** to each other. Each component worked in isolation but the end-to-end data flow was broken.

### Critical Broken Connections Found

| Connection | Status | Impact |
|---|---|---|
| ControllerLoop → InputWorker | BROKEN | CameraIntent/MovementIntent published to StateBus slots but nothing reads them. No input reaches game. |
| YOLO/Tracker → PerceptionPipeline | NOT WIRED | Detection and tracking exist but aren't added as post-processors. observation.target_track is always None. |
| DualChamberScheduler → Kernel | NOT INTEGRATED | Dual-chamber architecture designed but never added to run_kernel.py. |
| CameraModel → ControllerLoop | NOT WIRED | CameraServo needs CameraModel to compute error, but it was never set. |
| run_kernel.py real input | NO OPTION | Only ConsoleInputBackend, no way to use SafeWindowInputBackend for real games. |

### Fixes Applied

1. **Created `execution/intent_bridge.py`** — NEW file
   - Bridges StateBus "camera_intent"/"movement_intent" slots → InputWorker InputLease
   - Converts CameraIntent (yaw/pitch degrees) → mouse_delta (pixels) using pixels_per_degree
   - Converts MovementIntent (forward/right/jump/dash) → key_states ("w"/"a"/"s"/"d"/"space"/"shift")
   - Tracks active movement keys and releases stale ones on direction change
   - Releases all movement keys on shutdown
   - Background thread polling at ~100Hz

2. **Created `perception/detector_post_processor.py`** — NEW file
   - Implements FramePostProcessor protocol
   - Wraps UltralyticsTracker for detection+tracking in one call
   - Lazy initialization (only loads model on first frame)
   - Graceful fallback: if ultralytics not installed, target_track stays None (no crash)
   - Populates observation.target_track with best-confidence tracked target

3. **Rewrote `scripts/run_kernel.py`** — Complete rewrite
   - Added `--model-path` for YOLO model path
   - Added `--real-input` flag for SafeWindowInputBackend
   - Added `--window-title` and `--alt-window-titles` for game window targeting
   - Added `--game` selector (genshin/hsr/general) for servo config
   - Added `--pixels-per-degree` for mouse sensitivity
   - Added `--capture-fps` for screen capture rate
   - Wires YOLO post-processor into PerceptionPipeline
   - Creates IntentBridge between StateBus and InputWorker
   - Wires CameraModel to ControllerLoop for servo error computation
   - Uses game-specific CameraServo config (genshin has tuned PID params)

4. **Created `tests/test_intent_bridge.py`** — NEW file
   - 11 tests covering camera, movement, diagonal, direction change, lifecycle
   - Tests pixel conversion, key release, dash, backward movement

### Test Results
- **1383 passed, 1 skipped** (0 failures)
- 11 new IntentBridge tests all pass

### Remaining Pipeline Gaps (Next Round)

1. **DualChamberScheduler not wired** — needs reflex_fn and cognitive_fn callbacks connected to actual detection and VLM providers
2. **No VLM post-processor in run_kernel.py** — VLMPostProcessor exists but not added to pipeline
3. **No OCR post-processor** — OcrPostProcessor exists but not wired
4. **Orchestrator has no task** — it starts in INIT state with no task loaded, runs NoopSkill forever
5. **No task specification mechanism** — no way to tell the kernel "complete quest X"
6. **Visual trigger detection not wired** — PerceptionPipeline uses static_visual_triggers, no real trigger detection
7. **ProgressSupervisor needs tuning** — default parameters may not work for Genshin exploration

### Full Pipeline Flow After Round 1

```
ScreenCapture (dxcam, 30Hz)
  → ViewportTransformer.normalize()
  → DetectionTrackingPostProcessor (YOLO+BoT-SORT)
  → observation.target_track populated
  → StateBus.publish_observation()

ControllerLoop (30Hz)
  ← StateBus.latest_observation_snapshot()
  → ProgressSupervisor.update() → ProgressState
  → RecoveryPolicy.decide() → RecoveryDecision
  → CameraServo.compute_error() + step() → CameraIntent
  → StateBus["camera_intent"].put(CameraIntent)
  → StateBus["movement_intent"].put(MovementIntent)

IntentBridge (100Hz)
  ← StateBus["camera_intent"].snapshot()
  ← StateBus["movement_intent"].snapshot()
  → InputLease(mouse_delta / key_states)
  → InputWorker.submit_lease()

InputWorker (100Hz)
  → SafeWindowInputBackend.key_down/key_up/mouse_move()
  → Physical game input (SendInput)

Orchestrator (variable Hz)
  ← StateBus.next_interrupt()
  → Skill.run() → SkillResult
  → StateBus.publish("skill_result")
  → OrchestrationGraph → next state
```

---

## Round 2: [PENDING]

TODO: Wire DualChamberScheduler, VLM post-processor, task specification, visual triggers
