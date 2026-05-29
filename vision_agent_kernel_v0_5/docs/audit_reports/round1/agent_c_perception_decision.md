# Agent C: Perception & Decision Pipeline Audit

**Date**: 2026-05-30
**Scope**: Verify that the perception-to-decision pipeline produces correct, usable information for game control.
**Files audited**: 8 core files across perception, planning, agent layers.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH | 7 |
| MEDIUM | 5 |

---

## 1. GenshinScreenClassifier ROI Scaling (`perception/genshin_screen_classifier.py`)

### 1.1 [MEDIUM] `_scale_roi` does not clamp coordinates to frame bounds

**File**: `perception/genshin_screen_classifier.py:128-133`

The `_scale_roi` method simply multiplies reference coordinates by scale factors without clamping:

```python
@staticmethod
def _scale_roi(roi, sx, sy):
    x1, y1, x2, y2 = roi
    return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
```

For a 3840x2160 frame, `sx=2.0, sy=2.0`, the `_hp_bar_roi = (610, 970, 1310, 1010)` becomes `(1220, 1940, 2620, 2020)` -- valid. For 2560x1440, `sx=1.33, sy=1.33`, it becomes `(811, 1290, 1742, 1343)` -- valid.

However, for non-16:9 resolutions (e.g., 1920x1200 = 16:10, `sx=1.0, sy=1.11`), the `_dialog_roi = (0, 756, 1920, 1080)` becomes `(0, 839, 1920, 1199)` -- which is just barely inside the frame. For 1920x1000 (unlikely but possible windowed), `sy=0.926`, so `_hp_bar_roi` Y values become `(898, 936)` -- very thin strip at bottom. The ROI coordinates are tuned for 1080p and will degrade at other aspect ratios.

Each detector checks `roi.size == 0` which protects against empty ROIs, but there is no protection against very thin ROIs (1-2 pixels tall) that produce misleading results. No hard crash risk, but classification accuracy silently degrades for non-16:9.

**Verdict**: Works correctly for 1920x1080, 2560x1440, 3840x2160. Non-16:9 aspect ratios will silently produce degraded (but not crashing) results.

### 1.2 [HIGH] `_detect_minimap` HoughCircles parameters are fragile

**File**: `perception/genshin_screen_classifier.py:63-80`

The minimap detection uses `cv2.HoughCircles` with:
- `dp=1.2`, `param1=50`, `param2=30`, `minRadius=20`, `maxRadius=int(min(x2-x1, y2-y1)/2)`

The Genshin minimap is a circular element in the top-left corner with a distinct border. However:
- `param2=30` is a fairly low accumulator threshold. In practice, the minimap is a *filled* circle with internal structure (compass rose, character arrow, terrain texture). HoughCircles detects circles from edge patterns, and a filled circle with internal features will NOT produce clean circular edges.
- The ROI `(0, 0, 220, 220)` at 1080p captures more than just the minimap -- the Genshin minimap radius is roughly 80-90 pixels at 1080p, centered around (110, 110). The ROI is padded enough, but `maxRadius=110` (half of 220) means it could detect larger artifacts.
- No preprocessing to isolate the minimap border. The grayscale + Gaussian blur approach will struggle with the minimap's internal terrain textures generating false edges.

**Verdict**: This detector is unlikely to reliably detect the Genshin minimap on real screenshots. The minimap should be detected by its circular border (ring detection) rather than HoughCircles on the full ROI. A more reliable approach would be template matching on the minimap frame/border, or detecting the circular border via edge detection + contour analysis.

### 1.3 [MEDIUM] `_detect_hp_bar` threshold uses absolute pixel counts

**File**: `perception/genshin_screen_classifier.py:82-94`

```python
threshold = roi.shape[0] * roi.shape[1] * 0.15
return total > threshold
```

This scales correctly with ROI size (percentage-based), which is good. However, `total` sums boolean mask values (0 or 255 per pixel from `cv2.inRange`), while `threshold` uses `shape[0] * shape[1] * 0.15` (a count of 15% of pixels). The masks produce values of 255 for matching pixels, so `total` is actually `matching_pixel_count * 255`. This means the actual threshold is effectively `0.15 / 255 = 0.059%` of pixels needing to match, not 15%. The detector is far more sensitive than the 15% threshold comment implies. This may cause false positives on any screen with a slight green/red/yellow tint in that region.

**Verdict**: The threshold math is wrong. `cv2.inRange` returns 0 or 255, not 0 or 1. Either the masks should be divided by 255 or the threshold should be multiplied by 255.

### 1.4 [MEDIUM] `_detect_dialog_box` edge density magic number

**File**: `perception/genshin_screen_classifier.py:113-122`

The dialog detection uses `mean_val` range `(30, 160)` and `edge_density > 5.0`. The Canny edge sum per pixel is 0 or 255, so `edge_density` is in the range 0-255. A value of 5.0 means roughly 2% of pixels being edges is sufficient. This is quite low and could false-positive on many game scenes with text overlays, quest markers, or skill cooldown numbers in the dialog ROI region.

---

## 2. DxcamCapture (`perception/dxcam_capture.py`)

### 2.1 [HIGH] No support for windowed-mode or region capture -- always captures full screen

**File**: `perception/dxcam_capture.py:36-44`

`dxcam.create()` creates a full-screen Desktop Duplication capture. The `region` parameter in `CaptureConfig` can be passed to `self._camera.start(region=...)`, but `GenshinPerceptionProvider.__init__` at `agent/genshin_game_agent.py:72-73` creates a `DxcamCapturer` with default `CaptureConfig(target_fps=15.0)` and no region specified:

```python
self._capturer = DxcamCapturer(CaptureConfig(target_fps=15.0), timebase=self._timebase)
```

This means:
- **Fullscreen**: Works correctly. dxcam captures the entire screen.
- **Windowed mode**: Captures the entire desktop, not just the game window. The classifier will see other windows, taskbar, desktop icons, etc. producing wrong classifications.
- **Obscured window**: dxcam uses Desktop Duplication API which captures what's rendered on the display. If the game window is partially obscured by another window, dxcam captures the obscuring window's content instead.

**Verdict**: For windowed mode, the `region` parameter should be set to the game window's bounds. The `GenshinPerceptionProvider` does not do this. Windowed mode gameplay will produce corrupted perception.

### 2.2 [MEDIUM] `get_latest_frame` raises exception instead of returning None when not started

**File**: `perception/dxcam_capture.py:52-55`

```python
if not self._started or self._camera is None:
    raise DxcamCaptureError("capturer is not started")
```

The `ScreenCapturer` protocol in `capture_base.py` has `get_latest_frame() -> FramePacket | None`. Raising an exception violates the protocol contract. The caller in `autonomous_task_brain.py:231` expects `None` on failure:

```python
frame = self._perception.capture_frame()
if frame is None:
    ...
```

But `capture_frame` in `genshin_game_agent.py:90-95` calls `self._capturer.get_latest_frame()` which will raise instead of returning `None` if the capturer hasn't been started or has been stopped. The exception is caught by the per-iteration `except Exception` in the main loop, so it won't crash the brain, but it's still a protocol violation.

---

## 3. VLM Response Parsing (`agent/genshin_game_agent.py`)

### 3.1 [CRITICAL] `_extract_json` fails on truncated JSON responses

**File**: `agent/genshin_game_agent.py:179-198`

The `_extract_json` method:
1. Strips markdown fences (```...```)
2. Tries `json.loads(cleaned)` on the whole text
3. Falls back to finding the outermost `{` and `}` and parsing that substring

The critical flaw: when the VLM response is truncated (which is common with `max_tokens=800`), the JSON will be incomplete. For example:

```json
{"screen_state": "world_hud", "player_status": {"hp": "high"}, "visible_objects": [{"type": "monster", "descri
```

Step 3 finds `{` at position 0 and `}` -- there is no closing brace. `cleaned.rfind("}")` returns -1, so `end = -1 + 1 = 0`. The condition `start >= 0 and end > start` becomes `0 >= 0 and 0 > 0` which is `False`. So it correctly returns `None`.

However, consider a response where there's a stray `}` somewhere:
```json
{"screen_state": "world_hud", "player_status": {"hp": "high"...
Some trailing text with } brace
```

Then `rfind("}")` finds the stray brace, and `json.loads` will fail on the invalid JSON between `{` and the stray `}`. This correctly returns `None`.

The real issue is more subtle: if the JSON is valid but the markdown fence stripping is broken. The fence stripping logic at line 183-185 removes lines starting with ```` ``` ``, but if the response is:
```
```json
{"screen_state": "world_hud"}
```
Some analysis text...
```

It produces `{"screen_state": "world_hud"}\nSome analysis text...` which `json.loads` fails on, but the fallback `{`...`}` extraction will correctly parse the JSON. This path works.

But if the response is:
```
Here is the analysis:
```json
{"screen_state": "world_hud"}
```
```

The fence stripping removes the ``` lines, producing `Here is the analysis:\n{"screen_state": "world_hud"}\n` which `json.loads` fails on, but the fallback correctly extracts the JSON. This works too.

**Verdict**: The `_extract_json` is actually reasonably robust for the common cases. The markdown fence stripping handles the main case. The `{`...`}` fallback handles embedded JSON. The main risk is with **truncated JSON with nested braces** where `rfind("}")` might find an inner closing brace and produce a partial parse of only the outer structure. This is mitigated by the VLM response typically being a flat JSON object.

Revised assessment: **MEDIUM** rather than CRITICAL. The handling is adequate for common cases. The edge case of truncated responses with nested braces could produce partial/wrong data, but the downstream code uses `.get()` with defaults which limits damage.

### 3.2 [HIGH] `_extract_json` markdown fence stripping breaks with language annotation

**File**: `agent/genshin_game_agent.py:182-185`

```python
if cleaned.startswith("```"):
    lines = cleaned.split("\n")
    lines = [l for l in lines if not l.strip().startswith("```")]
    cleaned = "\n".join(lines)
```

When the response starts with `` ```json ``, the filter removes the entire line (because it starts with `` ``` ``). This is correct. However, if the response contains inline code with triple backticks in the JSON value itself (extremely unlikely for VLM game analysis, but possible), those lines would also be stripped. Not a practical concern for this use case.

The more significant issue is that this stripping only handles the case where the text starts with ```. If the VLM wraps the JSON in fences but has preamble text before the fences, the `startswith("```")` check fails and the fences are not stripped. Example:

```
Based on the screenshot, here is the analysis:
```json
{"screen_state": "world_hud"}
```
```

The `cleaned.startswith("```")` is `False`, so the fence stripping is skipped. Then `json.loads(cleaned)` fails. The fallback finds `{` at position ~44 and `}` near the end, and successfully extracts the JSON. So this case works, but relies on the fallback.

**Verdict**: The parsing works but is fragile. It relies on the `{...}` fallback for the common case of VLM responses with preamble text. This is adequate but not robust.

---

## 4. VLMOutput to ScreenStateClaim Conversion (`planning/screen_state_claim_builder.py`)

### 4.1 [HIGH] `visible_objects` type mismatch between VLMOutput and affordance system

**File**: `planning/screen_state_claim_builder.py:62` and `planning/action_affordance.py:185`

`VLMOutput.visible_objects` is `list[dict[str, str]]` and is passed through directly to `ScreenStateClaim.visible_objects` as `tuple[dict[str, str], ...]`.

The affordance deriver at `action_affordance.py:185` checks:
```python
return any(o.get("type") == "enemy" for o in claim.visible_objects)
```

This works IF the VLM returns objects with `"type"` key. The VLM prompt at `genshin_game_agent.py:111` specifies:
```
"visible_objects": [{"type":"monster|npc|item|chest|waypoint","description":"...","position":"center/left/right"}]
```

The VLM returns `"monster"` but the affordance check looks for `"enemy"`. These don't match. The precondition `"enemy visible in range"` will NEVER be satisfied because the VLM uses `"monster"` not `"enemy"`.

**Verdict**: The affordance precondition for attack actions can never be met via VLM detection because of the `"monster"` vs `"enemy"` mismatch. This means the affordance deriver will never derive attack affordances for combat even when enemies are visible.

### 4.2 [HIGH] `_resolve_screen_state` type coercion is unsafe

**File**: `planning/screen_state_claim_builder.py:85-103`

The `_resolve_screen_state` method returns a `ScreenStateKind` (which is a `Literal[...]` type), but the actual return is a `str` that is type-ignored:

```python
for c in candidates:
    if c in valid_states:
        return c  # type: ignore[return-value]
```

This is technically fine at runtime since `c` is verified to be in `valid_states`. However, the VLM prompt asks for states like `"world_hud"`, `"full_menu"`, `"paimon_menu"`, `"no_hud"` -- none of which are in the `valid_states` set! The valid states are `"overworld"`, `"combat"`, `"menu"`, etc. The classifier returns `"world_hud"`, `"dialog"`, `"loading_screen"`, etc. -- only `"dialog"` matches.

So for most classifier outputs (`"world_hud"`, `"full_menu"`, `"paimon_menu"`, `"no_hud"`, `"loading_screen"`), the normalization path is hit. `"world_hud"` normalizes to `"world_hud"` which is NOT in valid_states. `"loading_screen"` normalizes to `"loading_screen"` which is NOT in valid_states (the set has `"loading"` not `"loading_screen"`). `"full_menu"` is not in the set. `"paimon_menu"` is not in the set.

Every classifier result except `"dialog"` falls through to `return "unknown"`. This means the classifier is effectively useless -- it always produces `"unknown"` screen state after going through the builder.

**Verdict**: The classifier states and the claim builder's valid states are misaligned. The classifier uses `world_hud`, `full_menu`, `paimon_menu`, `no_hud`, `loading_screen` while the builder expects `overworld`, `menu`, `loading`, etc. A mapping layer is needed.

### 4.3 [MEDIUM] VLM `suggested_action` field is ignored by the pipeline

**File**: `planning/screen_state_claim_builder.py:20-28`

`VLMOutput` has a `suggested_action` field. The `ScreenStateClaimBuilder.build()` method does NOT propagate this field into the `ScreenStateClaim`. The `ScreenStateClaim` dataclass has no `suggested_action` field. This means the VLM's suggested action is discarded entirely.

The brain relies on the planner to decide actions, so this is by design -- the VLM suggestion is not used for action selection. However, it could be valuable as a hint for the planner or as a cross-check. Currently it's pure dead data.

---

## 5. HierarchicalPlanner to GenshinActionExecutor Semantic Action Mapping (`planning/hierarchical_planner.py` + `agent/genshin_game_agent.py`)

### 5.1 [CRITICAL] Massive gap between planner's allowed actions and executor's action map

**File**: `planning/hierarchical_planner.py:210-216` vs `agent/genshin_game_agent.py:337-365`

The planner's `_ALLOWED_SEMANTIC_ACTIONS` set:
```
navigate_to, click_button, select_quest, claim_reward, claim_all,
open_menu, close_menu, advance_dialog, select_option, teleport,
track_quest, toggle_auto, use_skill, basic_attack, observe,
go_back, select_item, buy_item, use_item, confirm, interact,
move_forward, open_map, select_waypoint
```

The executor's `_ACTION_MAP`:
```
move, navigate_to, open_menu, close_menu, advance_dialog, select_option,
click_button, use_skill, basic_attack, observe, wait, look,
go_back, confirm, interact, jump, dash, sprint, swim,
select_quest, claim_reward, select_item, buy_item, use_item,
teleport, track_quest, toggle_auto
```

**Actions the planner can produce that the executor CANNOT handle:**
- `claim_all` -- not in executor map, falls to `_handle_unknown` (logs warning, sleeps 1s)
- `move_forward` -- not in executor map, falls to `_handle_unknown`
- `open_map` -- not in executor map, falls to `_handle_unknown`
- `select_waypoint` -- not in executor map, falls to `_handle_unknown`
- `interact` -- IS in executor map, OK

**Actions the affordance deriver produces that neither planner nor executor handle:**
- `move_forward` (from affordance deriver for overworld)
- `attack` (from affordance deriver for combat/boss_fight)
- `use_burst` (from affordance deriver for combat/boss_fight)
- `dodge` (from affordance deriver for combat/boss_fight)
- `switch_char` (from affordance deriver for combat)
- `use_ultimate` (from affordance deriver for turn_based_combat)
- `skip` (from affordance deriver for cutscene)
- `sort` (from affordance deriver for inventory)
- `close_map` (from affordance deriver for map)
- `heal` (from affordance deriver for boss_fight)
- `sprint` (from affordance deriver for overworld) -- IS in executor but NOT in planner
- `navigate_to` -- IS in both but executor's `_handle_navigate_to` returns `False` (not implemented)
- `click_button` -- maps to `_handle_advance_dialog` (space key) which is wrong for button clicks

**Verdict**: There is a severe three-way mismatch between (a) what affordance deriver produces, (b) what planner allows, and (c) what executor handles. Any plan containing `claim_all`, `move_forward`, `open_map`, or `select_waypoint` will silently degrade to `_handle_unknown` (1s sleep, no action). Combat affordances (`attack`, `use_burst`, `dodge`) can never be planned because the planner doesn't allow them. This makes combat automation impossible through the normal pipeline.

### 5.2 [HIGH] `_handle_navigate_to` always returns False

**File**: `agent/genshin_game_agent.py:251-256`

```python
def _handle_navigate_to(self, target, context):
    self._press_key("m", "open_map", 0.5)
    time.sleep(1.0)
    log.warning("[GenshinExecutor] navigate_to is not yet fully implemented for target=%s", target)
    return False
```

This action opens the map but always fails. Since `navigate_to` is one of the most common planner outputs, this means many plans will stall at the navigation step. The brain's retry logic will attempt the node up to `max_attempts` (default 3) times, each time opening and closing the map, then mark the node as failed and trigger replanning.

---

## 6. AutonomousTaskBrain Main Loop (`agent/autonomous_task_brain.py` lines 200-370)

### 6.1 [CRITICAL] VLM call blocks main loop for up to 30 seconds per state sample

**File**: `agent/autonomous_task_brain.py:238-249` + `agent/genshin_game_agent.py:141`

The main loop calls `self._perception.analyze_vlm(frame, ...)` synchronously. This makes a blocking HTTP request with `timeout=30` seconds. During this time, the main loop is completely blocked -- no interrupt checking, no state updates, no action execution.

The `_interruptible_wait` method correctly uses chunked waits, but the VLM call itself is not interruptible. If the VLM API hangs, the brain is unresponsive for 30 seconds. With the default `state_sample_interval_sec=2.0` and `plan_interval_sec=10.0`, a 30s VLM timeout means the brain misses 15 state samples and 3 plan intervals.

Furthermore, after every successful action, `_resample_current_state_after_action` (line 478-496) calls VLM again, adding another 2-30 second blocking wait. With `action_interval_sec=1.5`, the actual iteration time is dominated by VLM latency.

**Verdict**: The brain's effective cycle time is 2-30 seconds per iteration (dominated by VLM), not the configured 1.5s action interval. For real-time game control, this is unacceptable. The VLM call should be async/cached, or the classifier alone should drive fast iterations with VLM on a slower cadence.

### 6.2 [HIGH] Infinite replan loop when plan produces only unexecutable nodes

**File**: `agent/autonomous_task_brain.py:268-310`

The replan loop detection (lines 299-308) counts consecutive replans and waits `plan_interval_sec` after 3 replans. But the `replan_count` is only reset on successful action execution (line 318). If the plan consistently produces nodes that fail immediately (e.g., all nodes return `False` from the executor), the brain enters this cycle:

1. Plan (creates graph with failing nodes)
2. Execute node -> fails
3. Node hits `max_attempts` -> marked failed
4. `next_pending()` returns `None` (all nodes failed)
5. Replan (creates new graph with same failing nodes)
6. Repeat

The `replan_count` increments at step 5 and resets at step 2 on success. Since step 2 always fails, the counter grows. After 3 replans, it waits `plan_interval_sec` (15s default) before replanning again. This creates an infinite loop of: plan -> fail -> replan -> fail -> ... with 15s pauses every 3 attempts, consuming VLM API credits indefinitely until `max_iterations` is hit.

**Verdict**: Not a hard infinite loop (bounded by `max_iterations=100`), but a very expensive degenerate loop that wastes API credits and time when the executor can't handle planned actions.

### 6.3 [HIGH] `_resample_current_state_after_action` called even when claim verification is disabled

**File**: `agent/autonomous_task_brain.py:454-456, 472-476`

When `require_claim_verification=False` (which is the default in the Genshin factory at `genshin_game_agent.py:407`), the `_execute_node` method still calls `_resample_current_state_after_action()` which makes a VLM call. This means every action triggers a VLM call for resampling, even though the claim verification result is never used (the method returns `True` immediately after resampling at line 474-475).

The `post_action_resample` config defaults to `True`, which is the trigger for this behavior. This doubles the VLM API cost per action.

### 6.4 [HIGH] Classifier and VLM state names are both misaligned with ScreenStateClaim

**File**: `perception/genshin_screen_classifier.py:49-61` vs `planning/screen_state_claim.py:7-22`

The classifier produces: `loading_screen`, `dialog`, `world_hud`, `full_menu`, `paimon_menu`, `no_hud`.

The VLM prompt asks for: `loading_screen`, `dialog`, `world_hud`, `full_menu`, `paimon_menu`, `no_hud`, `combat`.

`ScreenStateKind` accepts: `overworld`, `combat`, `turn_based_combat`, `dialog`, `menu`, `map`, `loading`, `inventory`, `shop`, `quest_log`, `reward_screen`, `boss_fight`, `cutscene`, `unknown`.

Cross-reference:
| Classifier/VLM Output | In ScreenStateKind? | Falls through to? |
|---|---|---|
| `loading_screen` | No | `"unknown"` (not `"loading"`!) |
| `dialog` | Yes | `"dialog"` |
| `world_hud` | No | `"unknown"` |
| `full_menu` | No | `"unknown"` |
| `paimon_menu` | No | `"unknown"` |
| `no_hud` | No | `"unknown"` |
| `combat` | Yes | `"combat"` |

Only 2 out of 7 states map correctly. The rest all become `"unknown"`, triggering the `"unknown"` affordance rules (only `observe` action), which means the brain can only observe in most game states.

**Verdict**: This is the single most damaging bug in the pipeline. The classifier's output vocabulary is completely disconnected from the claim type system. The brain operates in `"unknown"` mode for most game states, preventing any meaningful action selection.

---

## Consolidated Findings Table

| # | Severity | File:Line | Issue |
|---|----------|-----------|-------|
| 4.2 | **CRITICAL** | `planning/screen_state_claim_builder.py:91-95` | Classifier state names (`world_hud`, `loading_screen`, `full_menu`) don't match `ScreenStateKind` (`overworld`, `loading`, `menu`). All classifier results become `"unknown"`. |
| 6.4 | **CRITICAL** | `perception/genshin_screen_classifier.py:49-61` | Same root cause as 4.2 -- the classifier's output vocabulary is completely misaligned with the type system. |
| 5.1 | **CRITICAL** | `planning/hierarchical_planner.py:210-216` | Three-way mismatch: affordance deriver produces actions (`attack`, `use_burst`, `dodge`) that planner doesn't allow; planner produces actions (`claim_all`, `move_forward`, `open_map`, `select_waypoint`) that executor can't handle. |
| 6.1 | **CRITICAL** | `agent/autonomous_task_brain.py:240` | VLM call blocks main loop 2-30s per state sample, making real-time game control impossible. |
| 1.2 | **HIGH** | `perception/genshin_screen_classifier.py:63-80` | HoughCircles unlikely to detect Genshin minimap reliably due to filled-circle-with-texture vs clean-circle-edge mismatch. |
| 2.1 | **HIGH** | `agent/genshin_game_agent.py:72-73` | No window-region capture for windowed mode; captures full desktop including non-game windows. |
| 4.1 | **HIGH** | `planning/screen_state_claim_builder.py:62` + `planning/action_affordance.py:185` | VLM returns `"monster"` but affordance check looks for `"enemy"` -- attack affordances never derived. |
| 5.2 | **HIGH** | `agent/genshin_game_agent.py:251-256` | `navigate_to` always returns False, stalling plans that need navigation. |
| 6.2 | **HIGH** | `agent/autonomous_task_brain.py:299-308` | Degenerate replan loop wastes API credits when executor can't handle planned actions. |
| 6.3 | **HIGH** | `agent/autonomous_task_brain.py:454-456` | VLM resampling called after every action even when claim verification is disabled, doubling API cost. |
| 1.3 | **MEDIUM** | `perception/genshin_screen_classifier.py:82-94` | HP bar threshold math wrong: `cv2.inRange` returns 0/255 but threshold assumes 0/1. Detector is 255x more sensitive than intended. |
| 1.4 | **MEDIUM** | `perception/genshin_screen_classifier.py:113-122` | Dialog detection thresholds are loose; false positives likely on scenes with text overlays. |
| 2.2 | **MEDIUM** | `perception/dxcam_capture.py:52-55` | Raises exception when not started, violating `ScreenCapturer` protocol. |
| 3.1 | **MEDIUM** | `agent/genshin_game_agent.py:179-198` | `_extract_json` is fragile but adequate for common VLM response formats. |
| 4.3 | **MEDIUM** | `planning/screen_state_claim_builder.py:62` | VLM `suggested_action` field is discarded; could be useful as planner hint. |

---

## Recommended Priority Fixes

1. **[P0] Fix classifier-to-claim state name mapping** (issues 4.2, 6.4). Add a mapping dict: `{"world_hud": "overworld", "full_menu": "menu", "paimon_menu": "menu", "loading_screen": "loading", "no_hud": "unknown"}` in the builder's `_resolve_screen_state`.

2. **[P0] Fix the three-way action vocabulary** (issue 5.1). Align affordance deriver, planner whitelist, and executor map. Either update the executor to handle all planner outputs, or restrict the planner to only produce actions the executor can handle.

3. **[P1] Make VLM calls non-blocking** (issue 6.1). Use a background thread for VLM analysis. Let the classifier drive fast loop iterations and merge VLM results when available.

4. **[P1] Fix HP bar threshold math** (issue 1.3). Change `total > threshold` to `total > threshold * 255` or use `.astype(float) / 255` on masks.

5. **[P1] Fix `"monster"` vs `"enemy"` mismatch** (issue 4.1). Standardize on one term across VLM prompt and affordance rules.
