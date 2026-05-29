# Agent D: Safety, Robustness & Integration Audit Report

**Scope**: Genshin agent pipeline crash paths, race conditions, resource leaks, safety violations.
**Date**: 2026-05-30
**Auditor**: Agent D (Safety & Robustness)
**Files reviewed**:
- `agent/genshin_game_agent.py`
- `execution/safe_window_backend.py`
- `execution/intent_bridge.py`
- `agent/autonomous_task_brain.py`
- `perception/dxcam_capture.py`
- `execution/input_worker.py`
- `core/state_bus.py`
- `execution/input_lease.py`
- `scripts/run_genshin_agent.py`
- `agent/exploration_agent.py`
- `perception/genshin_screen_classifier.py`
- `core/local_secret_store.py`

---

## CRITICAL Issues (crash / data corruption)

### C1. VLM call can block the brain loop for 30+ seconds with no retry/backoff
**File**: `agent/genshin_game_agent.py:141`
**Severity**: CRITICAL

`urllib.request.urlopen(request, timeout=30)` has a 30-second timeout, but the broader `except Exception` at line 162 swallows ALL errors and returns `None`. If the VLM server is down for an extended period, the brain will call `analyze_vlm()` every `state_sample_interval_sec` (default 3s), each call blocking for up to 30 seconds. This effectively freezes the agent main loop. There is no:
- Circuit breaker or exponential backoff
- Fast-fail after N consecutive failures
- Distinction between auth errors (wrong API key) vs transient network errors

The 30-second timeout itself is dangerous -- `_resample_current_state_after_action()` (line 478-496 in autonomous_task_brain.py) calls `analyze_vlm` synchronously AFTER executing an action, meaning the agent sits frozen for 30s holding whatever game state it left, with no interrupt check.

### C2. `SafeWindowInputBackend` `_force_foreground` deadlocks with `_ensure_target_focused`
**File**: `execution/safe_window_backend.py:322-338`
**Severity**: CRITICAL

`_force_foreground` calls `AttachThreadInput(cur_tid, fg_tid, True)` followed by `SetForegroundWindow`. If the foreground window's thread has hung or is in a similar wait state, `AttachThreadInput` can block indefinitely (it synchronizes thread input queues). This is called inside `_ensure_target_focused`, which is called before EVERY input operation (`key_down`, `key_up`, `mouse_move`, `left_click`, `click_at`). A hung foreground application will freeze all input operations with no timeout.

There is no timeout on `AttachThreadInput`, and the `finally` block that calls `AttachThreadInput(cur_tid, fg_tid, False)` may never be reached if the thread is blocked.

### C3. `_handle_move` holds keys with blocking sleep, no interrupt path
**File**: `agent/genshin_game_agent.py:244-249`
**Severity**: CRITICAL

```python
for key in keys:
    self._backend.key_down(key, reason=f"move_{key}")
time.sleep(1.5)
for key in keys:
    self._backend.key_up(key, reason=f"move_{key}_done")
```

If a shutdown/interrupt occurs during the 1.5-second sleep, the keys remain held down until the sleep completes. There is no mechanism to interrupt this sleep. If the brain's `_shutdown` event is set, `_handle_move` does not check it. Similarly, `_handle_sprint` (line 316-318) holds shift for 2 seconds, `_handle_observe` (line 289) sleeps for 2 seconds, and `_press_key` (line 332) sleeps for `hold_sec`.

### C4. `release_all` calls `_resolve_vk` outside the lock, sends key_up events without lock
**File**: `execution/safe_window_backend.py:247-271`
**Severity**: CRITICAL

`release_all` snapshots `_down_keys` under `_lock`, clears it, then iterates outside the lock calling `SendInput`. If another thread calls `key_down` adding the same key between the snapshot and `SendInput(key_up)`, the key will be released by `release_all` but tracked as held in `_down_keys` by the `key_down` caller. The physical key state (released) and the tracked state (held) diverge, meaning the key will never be released again.

### C5. `_drain_movement_intent` releases keys outside the lock, TOCTOU race
**File**: `execution/intent_bridge.py:151-166`
**Severity**: CRITICAL

```python
with self._movement_lock:
    to_release = self._active_movement_keys - desired_keys
    self._active_movement_keys = desired_keys
# Lock released here
for key in to_release:
    release_lease = InputLease(...)
    self._input_worker.submit_lease(release_lease)
```

Between computing `to_release` and submitting the release leases, `_release_movement_keys` (called from the `finally` block in `_run_loop`) could clear `_active_movement_keys` and submit its own release leases for the same keys. This causes duplicate key_up events and a race between the drain loop and the shutdown cleanup.

---

## HIGH Issues (can freeze or hang agent)

### H1. `capture_frame()` raises exception if dxcam not started, brain does not handle it
**File**: `perception/dxcam_capture.py:54-55`, `agent/autonomous_task_brain.py:231-234`
**Severity**: HIGH

`DxcamCapturer.get_latest_frame()` raises `DxcamCaptureError("capturer is not started")` if called before `start()`. In `autonomous_task_brain.py:231`, `capture_frame()` is called directly without checking if the capturer is running. The outer `try/except Exception` at line 355 catches this as a "Transient error" and logs it, but the agent will loop indefinitely calling `capture_frame()` and hitting this exception every iteration until `max_iterations` is exhausted.

The brain should either: (a) detect DxcamCaptureError and abort, or (b) have the perception provider return None instead of raising.

### H2. `_resample_current_state_after_action` calls VLM synchronously in the execution path
**File**: `agent/autonomous_task_brain.py:478-496`
**Severity**: HIGH

After every action (when `post_action_resample=True`, which is the default), the brain calls `analyze_vlm()` synchronously. This blocks the main brain loop for up to 30 seconds per action. During this time:
- No shutdown check occurs
- No interrupt from StateBus is processed
- The game state is not observed

If VLM is slow or down, the agent enters a cycle of: act -> block 30s on VLM -> act -> block 30s on VLM, effectively running at ~2 actions per minute with no awareness.

### H3. No upper bound on VLM network retries -- agent burns API quota on persistent failures
**File**: `agent/genshin_game_agent.py:162-164`
**Severity**: HIGH

The broad `except Exception` at line 162 catches everything (HTTP 401, 403, 429, 500, DNS failures, SSL errors, timeouts) and returns None. There is no tracking of consecutive failures, no backoff, and no differentiation between permanent errors (wrong API key -> HTTP 401) and transient errors (HTTP 429 rate limit). A wrong API key will cause a useless VLM call every 3 seconds for the entire agent lifetime, burning network resources and producing log spam.

### H4. Brain `_execute_node` returns False forever when affordances don't match, no escape
**File**: `agent/autonomous_task_brain.py:376-458`
**Severity**: HIGH

When `_execute_node` is called with a node whose `semantic_action` has no matching affordance AND no applicability gate scores, AND the action is one of ("observe", "wait", "move", "look"), the method falls through to line 459 without entering any code path. It then proceeds to `_requires_human_confirmation` and `execute_semantic`. But if `execute_semantic` returns False (e.g. focus lost), the node never gets `status = "failed"` because `attempts` is only incremented at line 314, but the failure path at line 343 only fires if `attempts >= max_attempts`. The node gets re-attempted forever until `max_iterations` is exhausted.

More critically: when the exploration slow path (line 399-458) returns False from `_verify_node_claim`, the node's `attempts` counter is incremented but `status` is not set to "failed". The brain will re-plan but get the same node back if the plan doesn't change. The `_replan_count` mitigation only triggers after 3 replans but does not abort -- it just waits and replans again.

### H5. `_ensure_target_focused` sleeps 100ms synchronously on every focus miss
**File**: `execution/safe_window_backend.py:314-315`
**Severity**: HIGH

```python
time.sleep(0.1)
```

This blocking sleep is called every time the target window is not focused. If the window keeps losing focus (e.g. another app stealing focus repeatedly), every input operation incurs a 100ms+ penalty. Combined with the `_force_foreground` call, a single `key_down` could take 200+ ms. At 30Hz control rate, this makes input delivery impossible.

### H6. `left_click` has a 50ms blocking sleep between down/up
**File**: `execution/safe_window_backend.py:168-169`
**Severity**: HIGH

```python
import time as _time
_time.sleep(0.05)
```

During this 50ms sleep, the thread cannot respond to shutdown or interrupt signals. This violates the "no blocking waits" rule from CLAUDE.md. The `_press_key` method (genshin_game_agent.py:332) has a similar issue with configurable `hold_sec` sleep.

### H7. `DxcamCapturer.get_latest_frame` returns None indefinitely if dxcam camera has no frames
**File**: `perception/dxcam_capture.py:57-58`
**Severity**: HIGH

If dxcam returns None for 100+ consecutive frames (e.g. game is minimized, display is in sleep mode, or dxcam's internal buffer is corrupted), the brain enters the `frame is None` path at line 232-234 and waits 1 second each time. With `max_iterations=100`, the agent will waste 100 seconds doing nothing and then report failure. There is no:
- Counter for consecutive None frames with escalation
- Diagnostic logging of frame_id or capture state
- Attempt to restart dxcam after N consecutive failures

### H8. `find_target_window` fails silently if game window title changes mid-session
**File**: `execution/safe_window_backend.py:340-349`
**Severity**: HIGH

Genshin Impact's window title changes based on game state (loading, cutscene, etc.). The title is hardcoded once at construction and never updated. If the window title changes, `_find_target_window` raises `SafeWindowInputError`, which propagates through `_ensure_target_focused` and causes every input to fail. The agent will execute actions that all return False (because `_ensure_target_focused` calls `release_all` then raises, which is caught by the broad except in `execute_semantic`).

The `alt_window_titles` mechanism exists but requires manual pre-configuration of all possible titles.

---

## MEDIUM Issues (degraded behavior)

### M1. `_encode_frame_jpeg` PIL fallback has a bug: resize never applied
**File**: `agent/genshin_game_agent.py:44-48`
**Severity**: MEDIUM

In the PIL fallback path, when `max(h, w) > max_long_side`, the code computes `scale` and copies the frame, but the actual resize is only applied to the PIL Image later (line 52-53). However, the `frame` variable is reassigned to `frame.copy()` at line 48 but the copy is never resized. The subsequent `rgb = frame[:, :, ::-1]` creates the PIL Image from the un-resized copy. The `img.resize()` at line 53 does resize correctly, but the comment at line 48 "Simple resize via slicing" is misleading -- the resize is not done via slicing. Functionally the code works but the dead copy at line 48 is wasted memory.

### M2. `GenshinPerceptionProvider` never calls `dxcam.stop()` on error paths
**File**: `agent/genshin_game_agent.py:83-88`
**Severity**: MEDIUM

The `stop()` method exists and calls `self._capturer.stop()`, but if `start()` succeeds and then an exception occurs before `stop()` is called (e.g. in `brain.run()`), the dxcam camera continues capturing in the background. The `scripts/run_genshin_agent.py:72-88` has a try/finally that calls `perception.stop()`, but if the process is killed (SIGKILL, task manager, OOM), dxcam's internal thread may leak. The camera thread is not a daemon thread in dxcam's implementation.

### M3. IntentBridge `_release_movement_keys` runs in `finally` of `_run_loop`, may submit to a stopped InputWorker
**File**: `execution/intent_bridge.py:86-87`, `183-199`
**Severity**: MEDIUM

When `_run_loop` exits (via `_stop_event`), the `finally` block calls `_release_movement_keys()` which submits release leases to `self._input_worker`. If `InputWorker.stop()` was called first (which is the typical shutdown order), the worker's command queue may be full or the worker thread may already be dead, causing `submit_lease` to return False silently. Keys may remain physically held.

### M4. `_history` list in AutonomousTaskBrain grows unbounded
**File**: `agent/autonomous_task_brain.py:163`
**Severity**: MEDIUM

`self._history: list[dict[str, Any]] = []` appends a dict on every iteration (both success and failure). With `max_iterations=100`, this is fine, but `TaskBrainResult` returns `history=list(self._history)`, which copies the full list. If `max_iterations` is set to a large value, memory usage grows linearly. No bounding or cap is applied.

### M5. `SafeWindowInputBackend` `_configure_win32` does not set `GetForegroundWindow` restype to HWND
**File**: `execution/safe_window_backend.py:354-355`
**Severity**: MEDIUM

`GetForegroundWindow` argtypes is set to empty list but `restype` is not set. Without an explicit `restype`, ctypes defaults to `c_int` (32-bit), but `HWND` is a pointer type on 64-bit Windows. On 64-bit Python, this truncates the window handle to 32 bits, causing `GetForegroundWindow` to return wrong values for windows with handles above `0x7FFFFFFF`. This makes `is_target_focused()` always return False on such windows, triggering unnecessary `_force_foreground` calls on every input.

### M6. `_exploration_trace` slicing creates a new list every time it exceeds the cap
**File**: `agent/autonomous_task_brain.py:444-445`
**Severity**: MEDIUM

```python
if len(self._exploration_trace) > self._MAX_EXPLORATION_TRACE:
    self._exploration_trace = self._exploration_trace[-self._MAX_EXPLORATION_TRACE:]
```

This creates a new list copy every time the cap is exceeded. For a list of 50 elements this is negligible, but it's a pattern that could become a perf issue if `_MAX_EXPLORATION_TRACE` is increased. A `deque(maxlen=50)` would be more appropriate.

### M7. `_NullStateBus.subscribe` and `_NullStateBus.get_slot` return None instead of proper types
**File**: `agent/autonomous_task_brain.py:60-64`
**Severity**: MEDIUM

`subscribe` returns `None` but callers may expect a subscription ID string. `get_slot` returns `None` which could cause `NoneType` errors if callers try to call `.put()` on it. The `register_slot` returns `_NullSlot()` which is correct.

### M8. `classify_screen` does not handle cv2 import failure or corrupted frame
**File**: `perception/genshin_screen_classifier.py:28-61`
**Severity**: MEDIUM

The classifier uses `cv2.cvtColor`, `cv2.HoughCircles`, etc. If cv2 is not installed or the frame is corrupt (e.g. wrong number of channels, zero-size ROI), the methods will raise and the exception propagates through `classify_screen` in `genshin_game_agent.py:167-172`, which has no try/except. This gets caught by the brain's outer exception handler but produces a "Transient error" on every iteration until the frame changes.

### M9. `_encode_frame_jpeg` imports cv2 and PIL inline on every call
**File**: `agent/genshin_game_agent.py:33, 43`
**Severity**: MEDIUM

`import cv2` and `from PIL import Image` are done inside the function body on every VLM call. While Python caches module imports, the try/except and import machinery still executes on each call. For a function called every 3 seconds, this adds unnecessary overhead.

### M10. `GenshinActionExecutor.execute_semantic` catches all exceptions, swallows SafeWindowInputError
**File**: `agent/genshin_game_agent.py:217-219`
**Severity**: MEDIUM

```python
except Exception as exc:
    log.warning("[GenshinExecutor] Action %s failed: %s", action, exc)
    return False
```

`SafeWindowInputError` from focus loss is caught and logged as a warning, then the method returns False. The brain treats this as a normal failure and may retry the same action. There is no distinction between "focus lost" (which should trigger a pause/wait for refocus) and "action failed" (which should trigger a replan). This can cause rapid cycling of focus-lost failures.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|-----------|
| CRITICAL | 5 | Blocking VLM with no backoff, AttachThreadInput deadlock risk, uninterruptible key holds, release_all lock gap, movement key TOCTOU race |
| HIGH | 8 | Unhandled dxcam errors, VLM blocking execution path, no failure escalation, focus loss feedback loop, dxcam None frame starvation |
| MEDIUM | 10 | Resource cleanup gaps, unbounded history, HWND truncation, exception swallowing, import overhead |

**Top 3 most dangerous issues**:
1. **C1/C2/C3 combined**: The agent can be rendered completely unresponsive for 30+ seconds by a slow VLM call, while holding keys down with no interrupt capability, and potentially deadlocking on `AttachThreadInput`.
2. **C4/C5 combined**: Thread safety issues in key release paths mean keys can get stuck in a "physically released but logically tracked as held" state, or vice versa, causing phantom inputs.
3. **H4**: The brain has no effective escape from a state where all nodes fail verification -- it will replan and retry until `max_iterations` is exhausted, potentially holding keys or leaving the game in an inconsistent state.
