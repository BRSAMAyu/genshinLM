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

## Round 1b: Opus Audit Fixes

**Date**: 2026-05-30

### Opus Agent Audit Findings (3 CRITICAL, 4 HIGH, 7 MEDIUM)

Fixed issues that would completely prevent real-game operation:

| Issue | Severity | Fix |
|---|---|---|
| Missing `import os` in run_kernel.py | CRITICAL | Added `import os` |
| Double pixel conversion (IntentBridge AND SafeWindowInputBackend both ×ppd) | CRITICAL | Removed conversion from IntentBridge, pass raw degree deltas |
| No version check on intent slots → same intent applied ~3x | HIGH | Added `_last_camera_version`/`_last_movement_version` tracking |
| CameraModel attached via private attr hack | HIGH | Added proper `camera_model` parameter to ControllerLoop.__init__ |

### Test Results
- **1395 passed, 1 skipped** (0 failures)
- 12 IntentBridge tests (added version-tracking test)

---

## Round 2: Genshin Game Agent + Screen Classifier

**Date**: 2026-05-30

### What Was Done

1. **Created `agent/genshin_game_agent.py`** — NEW file
   - `GenshinPerceptionProvider`: Implements PerceptionProvider protocol
     - dxcam for capture, Zhipu GLM-4V for VLM analysis, GenshinScreenClassifier for classify
     - JPEG encoding with 1280px resize for VLM API
     - JSON extraction from VLM responses
   - `GenshinActionExecutor`: Implements ActionExecutor protocol
     - Translates 20+ semantic actions to concrete key/mouse inputs
     - Action map: move, navigate_to, open_menu, close_menu, advance_dialog, use_skill, etc.
     - Uses SafeWindowInputBackend for all physical input
   - `create_genshin_agent()`: Factory that wires everything together

2. **Created `scripts/run_genshin_agent.py`** — NEW file
   - CLI entry point with --goal, --window-title, --max-iterations
   - Countdown before starting, log file output
   - Sets AURORA_ENABLE_AUTHORIZED_SAFE_WINDOW

3. **Created `perception/screen_classifier_post_processor.py`** — NEW file
   - FramePostProcessor adapter for GenshinScreenClassifier
   - Populates observation.ui_state with screen state and indicators

### Architecture: How It Connects

```
GenshinGameAgent (main thread)
  ↓ creates
GenshinPerceptionProvider (dxcam + GLM-4V + GenshinClassifier)
  ↓ + GenshinActionExecutor (SafeWindowInputBackend)
  ↓ creates
AutonomousTaskBrain (the strategic brain)
  ↓ run(goal)
  loop:
    1. perception.capture_frame() → np.ndarray
    2. perception.classify_screen(frame) → ClassifierOutput
    3. perception.analyze_vlm(frame, "genshin") → VLMOutput
    4. ScreenStateClaimBuilder.build(vlm, classifier, ocr) → ScreenStateClaim
    5. AffordanceDeriver.derive(claim) → ActionAffordance[]
    6. HierarchicalPlanner.plan(goal, claim, actions) → MissionGraph
    7. executor.execute_semantic(action, target, ctx) → bool
    8. Update MissionGraph, record to DecisionMemory
```

### Test Results
- **1395 passed, 1 skipped** (0 failures)

### Remaining Work (Round 3)

1. **GenshinActionExecutor needs mouse click support** — currently only keyboard, no left-click for basic attack or UI interaction
2. **No waypoint/map navigation** — navigate_to is a stub
3. **No OCR integration** — OCR could provide quest text, NPC names, item names
4. **No combat system wired** — combat/ directory has full combat planner but not connected
5. **No minimap flow tracking** — minimap_flow_tracker.py exists but not wired
6. **Action mapping is incomplete** — many Genshin-specific actions (swim, climb, glide) missing
7. **No visual verification after actions** — actions fire and forget, no confirmation

---

## Round 2b: Opus 4-Agent Deep Audit

**Date**: 2026-05-30

### Method: 4 Opus agents, each auditing a specific domain, writing independent reports in `docs/audit_reports/round1/`.

| Agent | Domain | Report |
|---|---|---|
| A | End-to-end data flow | `agent_a_data_flow.md` |
| B | Action completeness | `agent_b_action_completeness.md` |
| C | Perception & decision | `agent_c_perception_decision.md` |
| D | Safety & robustness | `agent_d_safety_robustness.md` |

### Critical Findings (24 total: 13 CRITICAL, 11 HIGH)

**Data Flow (Agent A)**:
- C1: Genshin agent has no StateBus integration (brain gets state_bus=None)
- C2: Duplicate dxcam capture (GenshinPerceptionProvider creates its own)
- C3: VLM prompt state strings don't match ScreenStateKind (5/7 → "unknown")

**Action Completeness (Agent B)**:
- 10 orphan actions in affordance system with no executor handler
- "attack" vs "basic_attack" naming mismatch
- "look" action is a no-op sleep
- No mouse-click-at-coordinates for UI interaction
- No climb/glide actions for traversal

**Perception & Decision (Agent C)**:
- Classifier outputs (world_hud, loading_screen, full_menu) don't match valid_states (overworld, loading, menu)
- "monster" vs "enemy" in VLM output vs affordance check
- VLM blocks main loop 2-30s with no async/caching

**Safety & Robustness (Agent D)**:
- 5 CRITICAL: VLM blocking, AttachThreadInput deadlock, uninterruptible key holds, release_all lock gap, movement key race
- 8 HIGH: Unhandled dxcam errors, VLM in execution path, no failure escalation, focus loss loop

---

## Round 3: Fix All Critical Issues from Opus Audit

**Date**: 2026-05-30

### Fixes Applied

| # | Issue | File(s) | Fix |
|---|---|---|---|
| F1 | Classifier state names don't match ScreenStateKind | `planning/screen_state_claim_builder.py` | Added `_STATE_ALIASES` mapping (world_hud→overworld, loading_screen→loading, full_menu→menu, etc.) + `_normalize_state()` method |
| F2 | VLM checked after classifier → combat always overridden by "overworld" | `planning/screen_state_claim_builder.py` | Swapped candidate priority: VLM first (semantic understanding), classifier second (structural detection) |
| F3 | VLM prompt uses wrong state names | `agent/genshin_game_agent.py` | Updated prompt to canonical ScreenStateKind values (overworld, combat, dialog, menu, loading, map, etc.) + changed "monster" to "enemy" in type field |
| F4 | "monster" vs "enemy" type mismatch | `planning/action_affordance.py` | Changed `o.get("type") == "enemy"` to accept both "enemy" and "monster" |
| F5 | 13 orphan actions in executor | `agent/genshin_game_agent.py` | Added handlers: attack, use_burst, use_ultimate, switch_char, select_dialog_option, move_forward, open_map, close_map, select_waypoint, dodge, heal, skip, claim_all, sort |
| F6 | "look" action is no-op sleep | `agent/genshin_game_agent.py` | Implemented `_handle_look()` using `mouse_move()` with angular deltas for left/right/up/down |
| F7 | No StateBus passed to brain | `agent/genshin_game_agent.py` | Added `state_bus` parameter to `create_genshin_agent()`, passes to AutonomousTaskBrain |
| F8 | Planner _ALLOWED_SEMANTIC_ACTIONS missing new actions | `planning/hierarchical_planner.py` | Added all new action names to allowlist + decomposition prompt |

### Test Results
- **1395 passed, 1 skipped** (0 failures)

### Full Action Map After Fix

```
move, move_forward, navigate_to, open_menu, close_menu,
advance_dialog, select_option, select_dialog_option,
click_button, use_skill, use_burst, use_ultimate,
basic_attack, attack, observe, wait, look, go_back,
confirm, interact, jump, dash, dodge, sprint, swim,
select_quest, claim_reward, claim_all, select_item,
buy_item, use_item, teleport, track_quest, toggle_auto,
open_map, close_map, select_waypoint, skip, switch_char,
heal, sort
```

42 total actions → all have handlers in executor, all in _ALLOWED_SEMANTIC_ACTIONS.

### State Resolution Chain After Fix

```
Classifier: world_hud → _normalize_state → "overworld" ✓
Classifier: loading_screen → _normalize_state → "loading" ✓
Classifier: full_menu → _normalize_state → "menu" ✓
Classifier: paimon_menu → _normalize_state → "menu" ✓
Classifier: dialog → already canonical → "dialog" ✓
VLM: combat → already canonical → "combat" ✓ (checked FIRST)
VLM: overworld → already canonical → "overworld" ✓
VLM: menu → already canonical → "menu" ✓
```

### Remaining Known Issues (not fixed this round)

1. Duplicate dxcam — GenshinPerceptionProvider still creates its own capturer (should share kernel's)
2. VLM blocking — synchronous urllib calls block brain loop up to 30s
3. Blocking time.sleep in action handlers — no interrupt capability during movement
4. No combat detection in classifier — relies entirely on VLM
5. AttachThreadInput deadlock risk in SafeWindowInputBackend
6. No climb/glide actions for Genshin traversal
7. release_all TOCTOU race conditions
