# Agent A: End-to-End Data Flow Audit Report

Auditor: Agent A (Data Flow)
Date: 2026-05-30
Scope: Trace every data path from screen capture to physical game input and back.

---

## Executive Summary

Of 6 data paths audited, 2 are VERIFIED, 3 are BROKEN, and 1 has a SIGNIFICANT ISSUE. The two core infrastructure paths (pipeline->StateBus, controller->input) are functionally complete but have a registration-order dependency. The Genshin agent paths have critical gaps: duplicate capture, no StateBus integration, a VLM prompt that produces unmatched state strings, and an incomplete action map.

---

## Path 1: dxcam capture -> PerceptionPipeline -> StateBus.publish_observation()

**Verdict: VERIFIED**

Trace:
1. `DxcamCapturer.get_latest_frame()` (`perception/dxcam_capture.py:52-69`) calls `self._camera.get_latest_frame()` from dxcam, wraps result in `FramePacket(frame_id, timestamp, image, source_size, color_format)`. Returns real numpy array from screen capture.

2. `PerceptionPipeline._run_loop()` (`perception/pipeline.py:86-106`) calls `self._capturer.get_latest_frame()`, gets a `FramePacket | None`. If not None, calls `self._publish_packet(packet)`.

3. `_publish_packet()` (`perception/pipeline.py:108-150`) constructs an `Observation` dataclass with real data: frame_id, t_capture, t_processed, latency_ms, viewport_size from viewport transformer. Runs post_processors which can mutate the observation (e.g., populate `target_track`, `ui_state`). Finally calls `self._state_bus.publish_observation(observation)` at line 142.

4. `StateBus.publish_observation()` (`core/state_bus.py:176-179`) puts into `latest_observation` slot and appends to `observation_ring`. Both are populated with real data.

Verified: frame_id increments, image data flows through, observation is published with real capture timestamp and computed latency.

---

## Path 2: StateBus latest_observation -> ControllerLoop -> CameraServo -> CameraIntent -> StateBus slot -> IntentBridge -> InputLease -> InputWorker -> SafeWindowInputBackend.mouse_move()

**Verdict: VERIFIED (with caveat: slot registration order dependency)**

Full trace:

1. **ControllerLoop._run_loop()** (`control/controller_loop.py:49-67`): Polls `state_bus.latest_observation_snapshot()`. If new version, extracts observation, calls `_execute_decision()`.

2. **_execute_decision()** (`control/controller_loop.py:69-91`): If `self._camera_servo` and `observation.target_track` are not None and `self._camera_model` is not None:
   - Calls `self._camera_servo.compute_error(observation.target_track, self._camera_model)` -- returns `CameraControlError`.
   - Calls `self._camera_servo.step(error, dt=self._tick_seconds)` -- returns `CameraIntent`.
   - Puts CameraIntent into `self._state_bus.get_slot("camera_intent")`.

3. **CameraServo.step()** (`control/camera_servo.py:63-115`): Returns `CameraIntent(yaw_delta, pitch_delta, duration_ms, confidence, reason)`. All fields populated with computed values.

4. **IntentBridge._drain_camera_intent()** (`execution/intent_bridge.py:89-112`): Polls `self._camera_slot.snapshot()`. If new version, creates `InputLease(lease_id, owner, priority=30, key_states={}, mouse_delta=(yaw_delta, pitch_delta), created_at, expires_at, reason)`. Calls `self._input_worker.submit_lease(lease)`.

5. **InputWorker._apply_lease()** (`execution/input_worker.py:143-167`): Validates lease. Calls `self._backend.mouse_move(dx, dy, reason)` at line 163, where dx=yaw_delta, dy=pitch_delta.

6. **SafeWindowInputBackend.mouse_move()** (`execution/safe_window_backend.py:125-151`):
   - Calls `self._ensure_target_focused()`.
   - Converts: `pixel_dx = int(round(dx * self.pixels_per_degree))`, `pixel_dy = int(round(dy * self.pixels_per_degree))`.
   - Constructs `INPUT` struct with `type=INPUT_MOUSE`, `MOUSEINPUT(dx=pixel_dx, dy=pixel_dy, dwFlags=MOUSEEVENTF_MOVE)`.
   - Calls `SendInput(1, ...)` -- this is a real Win32 relative mouse move.

7. **Type chain verified**: TargetTrack.smoothed_center_px -> (float,float) -> pixel_to_yaw_pitch_error_deg() -> (float,float) degrees -> CameraServo.step() -> CameraIntent(yaw_delta:float, pitch_delta:float) -> InputLease.mouse_delta:(float,float) -> SafeWindowInputBackend.mouse_move(dx:float, dy:float) -> pixel conversion -> SendInput.

**Caveat**: `ControllerLoop` calls `get_slot("camera_intent")` without registering it itself. `IntentBridge.__init__()` registers it at line 54. If `ControllerLoop` starts before `IntentBridge` is created, `get_slot()` returns `None` and intents are silently dropped. In `run_kernel.py`, IntentBridge is constructed at line 171 before ControllerLoop at line 188, so registration order is correct in the main pipeline. But this is fragile.

---

## Path 3: AutonomousTaskBrain -> GenshinPerceptionProvider.capture_frame()

**Verdict: BROKEN -- Duplicate dxcam, no StateBus integration**

Trace:
1. `GenshinPerceptionProvider.__init__()` (`agent/genshin_game_agent.py:62-82`) creates its **own** `DxcamCapturer(CaptureConfig(target_fps=15.0))` at line 73.

2. `capture_frame()` (`agent/genshin_game_agent.py:90-95`) calls `self._capturer.get_latest_frame()`, returns `packet.image`.

3. **Problem 1**: `GenshinPerceptionProvider` creates its own dxcam instance. If the main `PerceptionPipeline` also uses dxcam, two dxcam cameras compete for the same screen. dxcam's `create()` typically creates one camera per output. Two cameras on the same output causes frame corruption or crashes.

4. **Problem 2**: `create_genshin_agent()` (`agent/genshin_game_agent.py:368-417`) creates `AutonomousTaskBrain` at line 411 with `perception=perception, executor=executor, config=config` but **no state_bus parameter**. Therefore `AutonomousTaskBrain.__init__()` gets `state_bus=None` (line 143 of `autonomous_task_brain.py`), meaning:
   - `self._state_bus` is `None`
   - `_publish_task_state()` does nothing (line 636: early return if `self._state_bus is None`)
   - No task state snapshot is published to StateBus
   - No integration with the main PerceptionPipeline observation stream
   - The brain operates entirely on its own capture cycle, duplicating screen capture work

5. **No frame sharing**: The main PerceptionPipeline could publish frames via observation_ring, but GenshinPerceptionProvider never reads from StateBus. It always captures fresh.

**Files**:
- `agent/genshin_game_agent.py:73` -- duplicate dxcam
- `agent/genshin_game_agent.py:411` -- no state_bus passed to AutonomousTaskBrain

---

## Path 4: GenshinActionExecutor.execute_semantic() -> SafeWindowInputBackend

**Verdict: PARTIALLY VERIFIED -- 21 of 26 actions produce real input, 5 are stubs/no-ops**

`_ACTION_MAP` (`agent/genshin_game_agent.py:337-365`) maps 26 action strings to handler methods.

### Actions that produce real input (21):

| Action | Handler | What it does |
|--------|---------|-------------|
| `move` | `_handle_move` | key_down/keys for 1.5s, key_up |
| `open_menu` | `_handle_open_menu` | press ESC 0.3s |
| `close_menu` | `_handle_close_menu` | press ESC 0.3s |
| `advance_dialog` | `_handle_advance_dialog` | press SPACE 0.3s |
| `select_option` | `_handle_select_option` | press number key 0.3s |
| `click_button` | `_handle_advance_dialog` | press SPACE 0.3s |
| `use_skill` | `_handle_use_skill` | press E/Q/1-4 0.3s |
| `basic_attack` | `_handle_basic_attack` | left_click() |
| `go_back` | `_handle_go_back` | press ESC 0.3s |
| `confirm` | `_handle_confirm` | press ENTER 0.3s |
| `interact` | `_handle_interact` | press F 0.3s |
| `jump` | `_handle_jump` | press SPACE 0.15s |
| `dash` | `_handle_dash` | press SHIFT 0.2s |
| `sprint` | `_handle_sprint` | hold SHIFT 2s |
| `swim` | `_handle_swim` | hold SHIFT 0.3s |
| `select_quest` | `_handle_advance_dialog` | press SPACE 0.3s |
| `claim_reward` | `_handle_confirm` | press ENTER 0.3s |
| `select_item` | `_handle_select_option` | press number key 0.3s |
| `buy_item` | `_handle_confirm` | press ENTER 0.3s |
| `use_item` | `_handle_confirm` | press ENTER 0.3s |
| `teleport` | `_handle_confirm` | press ENTER 0.3s |

### Stubs / No-ops (5):

| Action | Handler | Problem |
|--------|---------|---------|
| `navigate_to` | `_handle_navigate_to` | Opens map (M key) but then logs WARNING and returns `False`. Navigation not implemented. (`genshin_game_agent.py:251-256`) |
| `observe` | `_handle_observe` | Just `time.sleep(2.0)`, no input. Acceptable for "wait" semantics. |
| `wait` | `_handle_observe` | Same as observe. |
| `look` | `_handle_observe` | **STUB** -- "look" implies camera movement but just sleeps. No mouse_move called. (`genshin_game_agent.py:349`) |
| `toggle_auto` | `_handle_unknown` | Sleeps 1s and returns True. No actual toggle. (`genshin_game_agent.py:364`) |
| `track_quest` | `_handle_advance_dialog` | Maps to SPACE -- probably wrong for quest tracking in Genshin. |

### Additional issues:

1. **`_handle_move` blocks the thread** (`genshin_game_agent.py:246-248`): Uses `time.sleep(1.5)` which blocks the entire task brain loop. This prevents shutdown detection during movement. Should use interruptible wait or lease-based approach.

2. **All `_press_key` calls block** (`genshin_game_agent.py:332-335`): Each key press sleeps for `hold_sec`, blocking the thread.

---

## Path 5: GenshinPerceptionProvider.analyze_vlm() -> VLMOutput -> ScreenStateClaimBuilder

**Verdict: BROKEN -- VLM prompt produces state strings that don't match valid ScreenStateKind values**

Trace:
1. `analyze_vlm()` (`agent/genshin_game_agent.py:97-163`) sends a prompt to GLM-4V asking for JSON with:
   ```
   "screen_state": "loading_screen|dialog|world_hud|full_menu|paimon_menu|no_hud|combat"
   ```

2. The VLM response is parsed into `VLMOutput(screen_state=..., ...)` at lines 153-161. Whatever string the VLM returns is stored directly.

3. `VLMOutput` flows to `ScreenStateClaimBuilder.build()` (`planning/screen_state_claim_builder.py:49-82`).

4. `_resolve_screen_state()` (`screen_state_claim_builder.py:85-103`) checks `valid_states`:
   ```python
   valid_states = {
       "overworld", "combat", "turn_based_combat", "dialog", "menu",
       "map", "loading", "inventory", "shop", "quest_log",
       "reward_screen", "boss_fight", "cutscene", "unknown",
   }
   ```

5. **Mismatch**: The VLM prompt asks for `loading_screen`, `world_hud`, `full_menu`, `paimon_menu`, `no_hud` but the valid states in `_resolve_screen_state()` are `loading`, `overworld`, `menu`, `unknown`. The only overlaps are `dialog` and `combat`.

   | VLM prompt string | Matches valid state? |
   |---|---|
   | `loading_screen` | NO -- should be `loading` |
   | `dialog` | YES |
   | `world_hud` | NO -- should be `overworld` |
   | `full_menu` | NO -- should be `menu` |
   | `paimon_menu` | NO -- should be `menu` |
   | `no_hud` | NO -- falls through to `unknown` |
   | `combat` | YES |

6. The normalization at line 100-102 (`candidates[0].lower().replace(" ", "_")`) won't help because the strings already have underscores and don't match.

7. **Result**: For 5 of 7 VLM states, the claim builder falls through to return `"unknown"`. This means the HierarchicalPlanner and AffordanceDeriver receive `screen_state="unknown"` most of the time, degrading planning quality to near-zero.

**Files**:
- `agent/genshin_game_agent.py:109` -- VLM prompt with wrong state names
- `planning/screen_state_claim_builder.py:91-95` -- valid_states set that doesn't match

**Fix**: Either update the VLM prompt to use the canonical state names from `ScreenStateKind`, or add an alias mapping in `_resolve_screen_state()`.

---

## Path 6: SafeWindowInputBackend.left_click() -- MOUSEINPUT structure

**Verdict: VERIFIED (with minor note)**

Analysis of `left_click()` (`execution/safe_window_backend.py:153-176`):

1. **Structure correctness**: `MOUSEINPUT` fields are correctly defined:
   - `dx=0, dy=0` -- no position change during click
   - `mouseData=0` -- no scroll wheel
   - `dwFlags=MOUSEEVENTF_LEFTDOWN` (0x0002) for down, `MOUSEEVENTF_LEFTUP` (0x0004) for up
   - These flags are correct for relative-mode mouse click events

2. **No MOUSEEVENTF_ABSOLUTE flag**: Without this flag (0x8000), dx/dy are treated as relative movement in pixels. Since dx=0 and dy=0, the click happens at the current cursor position. This is correct behavior for clicking where the mouse already is.

3. **No SetCursorPos needed for left_click()**: The click fires at the current cursor position. For camera-servo-driven clicks (via `mouse_move` then `left_click`), the cursor is already at the right spot from the relative move. For targeted clicks at specific screen coordinates, `click_at()` (`safe_window_backend.py:178-183`) correctly calls `SetCursorPos()` first, then `left_click()`.

4. **50ms down-up delay** (`_time.sleep(0.05)` at line 169): This is a reasonable delay to ensure the game registers the click as distinct down+up events rather than a single impulse. Some games require minimum 20-50ms.

5. **Potential issue**: `_ensure_target_focused()` is called before each click. If focus is lost mid-combat, the backend attempts `_force_foreground()` which uses `AttachThreadInput` trick. If that fails, it calls `release_all()` and raises `SafeWindowInputError`. This is safe behavior.

**Minor note**: The `click_at()` method (line 178-183) calls `SetCursorPos` then `left_click`. `SetCursorPos` moves the OS cursor in absolute screen coordinates. This works, but for games with raw input enabled (rare for Genshin), the game may not register the cursor position change. For Genshin specifically, `SetCursorPos` works because Genshin uses normal Windows cursor events in menus.

---

## Summary Table

| Path | Description | Verdict | Key File(s) |
|------|-------------|---------|-------------|
| 1 | dxcam -> Pipeline -> StateBus observation | **VERIFIED** | `perception/pipeline.py`, `core/state_bus.py` |
| 2 | StateBus -> ControllerLoop -> CameraServo -> IntentBridge -> InputWorker -> SafeWindowBackend | **VERIFIED** (fragile slot registration order) | `control/controller_loop.py`, `execution/intent_bridge.py`, `execution/safe_window_backend.py` |
| 3 | AutonomousTaskBrain -> GenshinPerceptionProvider capture | **BROKEN** (duplicate dxcam, no StateBus) | `agent/genshin_game_agent.py:73,411` |
| 4 | GenshinActionExecutor -> SafeWindowBackend | **PARTIALLY VERIFIED** (21/26 actions work, 5 stubs) | `agent/genshin_game_agent.py:337-365` |
| 5 | VLM -> VLMOutput -> ScreenStateClaimBuilder | **BROKEN** (5/7 VLM state strings don't match valid ScreenStateKind) | `agent/genshin_game_agent.py:109`, `planning/screen_state_claim_builder.py:91-95` |
| 6 | SafeWindowInputBackend.left_click() MOUSEINPUT | **VERIFIED** | `execution/safe_window_backend.py:153-176` |

---

## Critical Issues Requiring Fix

### CRITICAL-1: Genshin agent has no StateBus integration
- **File**: `agent/genshin_game_agent.py:411`
- **Impact**: AutonomousTaskBrain operates entirely disconnected from the kernel's main observation stream. No task state is published. No heartbeat. Cannot be monitored or interrupted via StateBus.
- **Fix**: Pass `state_bus` to `AutonomousTaskBrain.__init__()`. Consider also using the pipeline's observation stream instead of creating a second dxcam instance.

### CRITICAL-2: Duplicate dxcam capture
- **File**: `agent/genshin_game_agent.py:73`
- **Impact**: Two dxcam instances on the same output can cause frame corruption, crashes, or doubled GPU load.
- **Fix**: Either share the existing PerceptionPipeline's capture (read from StateBus observation ring), or ensure only one capture path is active at a time.

### CRITICAL-3: VLM prompt state strings don't match ScreenStateKind
- **File**: `agent/genshin_game_agent.py:109`, `planning/screen_state_claim_builder.py:91-95`
- **Impact**: 5 of 7 VLM-returned screen states map to `"unknown"`, making the planning system effectively blind to actual game state.
- **Fix**: Align VLM prompt enum values with `ScreenStateKind` definition, or add an alias mapping in `_resolve_screen_state()`:
  - `loading_screen` -> `loading`
  - `world_hud` -> `overworld`
  - `full_menu` / `paimon_menu` -> `menu`
  - `no_hud` -> `overworld` or `unknown`

### HIGH-1: `look` action is a stub
- **File**: `agent/genshin_game_agent.py:349`
- **Impact**: Planner can issue `look` actions expecting camera movement but gets a no-op sleep instead.
- **Fix**: Implement using `SafeWindowInputBackend.mouse_move()` with angular deltas.

### HIGH-2: `_handle_move` blocks task brain thread
- **File**: `agent/genshin_game_agent.py:246-248`
- **Impact**: `time.sleep(1.5)` blocks the entire AutonomousTaskBrain loop, preventing shutdown detection, progress monitoring, or interrupt handling during movement.
- **Fix**: Use the kernel's InputLease/IntentBridge mechanism instead of direct blocking calls.
