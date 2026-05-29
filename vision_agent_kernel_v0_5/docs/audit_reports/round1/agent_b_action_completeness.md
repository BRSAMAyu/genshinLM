# Audit Report B: Action Completeness & Real-Game Viability

**Auditor**: Agent B
**Date**: 2026-05-30
**Scope**: Genshin Impact autonomous main-story progression -- action executor coverage, planner-executor alignment, input backend completeness, screen classifier coverage

---

## Executive Summary

The Genshin game agent has **13 CRITICAL gaps, 8 HIGH gaps, and 5 MEDIUM gaps** that collectively make autonomous main-story progression impossible in its current state. The most fundamental problems are: (1) the affordance system produces 10 semantic_action values that have no handler in GenshinActionExecutor, (2) essential actions like camera rotation, climbing, gliding, and mouse-based UI navigation are completely missing, and (3) the screen classifier cannot distinguish critical game states (combat, map, quest_log, cutscene, inventory, shop).

---

## 1. GenshinActionExecutor._ACTION_MAP Analysis

**File**: `agent/genshin_game_agent.py:337-365`

### All Registered Actions and Their Input Correctness

| # | Action Key | Handler | Genshin Key/Mouse | Correct? | Notes |
|---|-----------|---------|-------------------|----------|-------|
| 1 | `move` | `_handle_move` | WASD key_down/up | PARTIAL | Hardcoded 1.5s duration (line 246), no camera rotation support, no distance control |
| 2 | `navigate_to` | `_handle_navigate_to` | M key press | BROKEN | Opens map with M but then returns False (line 256). Completely non-functional. |
| 3 | `open_menu` | `_handle_open_menu` | ESC press | OK | Correct for Genshin |
| 4 | `close_menu` | `_handle_close_menu` | ESC press | OK | Correct for Genshin (ESC toggles Paimon menu) |
| 5 | `advance_dialog` | `_handle_advance_dialog` | Space press | OK | Correct for Genshin |
| 6 | `select_option` | `_handle_select_option` | Number key (1-9) | PARTIAL | Only handles digit targets. Cannot click dialog options by position. |
| 7 | `click_button` | `_handle_advance_dialog` | Space press | WRONG | Aliased to advance_dialog -- pressing Space is NOT a generic button click. Most UI buttons require mouse click. |
| 8 | `use_skill` | `_handle_use_skill` | E/Q/1-4 keys | OK | Correct mapping for elemental skill (E), burst (Q), character switch (1-4) |
| 9 | `basic_attack` | `_handle_basic_attack` | Left click | OK | Correct for Genshin normal attack |
| 10 | `observe` | `_handle_observe` | None (sleep 2s) | OK | |
| 11 | `wait` | `_handle_observe` | None (sleep 2s) | OK | |
| 12 | `look` | `_handle_observe` | None (sleep 2s) | WRONG | "look" should rotate camera, not sleep. No camera rotation implemented. |
| 13 | `go_back` | `_handle_go_back` | ESC press | OK | Correct |
| 14 | `confirm` | `_handle_confirm` | Enter press | PARTIAL | Genshin confirm is usually left-click on button or F, not Enter. Enter works in some menus. |
| 15 | `interact` | `_handle_interact` | F press | OK | Correct for NPCs, chests, items |
| 16 | `jump` | `_handle_jump` | Space press (0.15s) | OK | Correct |
| 17 | `dash` | `_handle_dash` | Shift press (0.2s) | OK | Correct for Genshin dash |
| 18 | `sprint` | `_handle_sprint` | Shift hold (2s) | PARTIAL | Should hold sprint WHILE moving (W + Shift), not just Shift alone |
| 19 | `swim` | `_handle_swim` | Shift press (0.3s) | WRONG | Swim sprint is not swimming itself. No actual swim-movement (W held while in water). Just taps Shift. |
| 20 | `select_quest` | `_handle_advance_dialog` | Space press | WRONG | Quest selection requires mouse click on quest entry, not Space. |
| 21 | `claim_reward` | `_handle_confirm` | Enter press | WRONG | Claim buttons in Genshin require mouse click, not Enter. |
| 22 | `select_item` | `_handle_select_option` | Number key | PARTIAL | May work for some list navigation but inventory items usually need mouse click. |
| 23 | `buy_item` | `_handle_confirm` | Enter press | WRONG | Buy buttons require mouse click. |
| 24 | `use_item` | `_handle_confirm` | Enter press | WRONG | Use/Use buttons require mouse click. |
| 25 | `teleport` | `_handle_confirm` | Enter press | WRONG | Teleport confirmation requires mouse click on "Teleport" button. |
| 26 | `track_quest` | `_handle_advance_dialog` | Space press | WRONG | Track quest button requires mouse click. |
| 27 | `toggle_auto` | `_handle_unknown` | None (sleep 1s) | WRONG | Does nothing useful. Should click the auto-battle toggle. |

### Summary of _ACTION_MAP Issues

- **27 entries** total
- **6 entries** functionally correct
- **8 entries** completely wrong input mapping (aliased to Space/Enter when mouse click needed)
- **5 entries** partially correct
- **3 entries** non-functional (navigate_to, toggle_auto, look)
- **0 entries** support mouse-click-at-coordinates, which is the most fundamental UI interaction

---

## 2. Planner-Executor Cross-Reference

### Allowed Semantic Actions from HierarchicalPlanner

**File**: `planning/hierarchical_planner.py:210-216` (`_ALLOWED_SEMANTIC_ACTIONS`)

```
navigate_to, click_button, select_quest, claim_reward, claim_all,
open_menu, close_menu, advance_dialog, select_option, teleport,
track_quest, toggle_auto, use_skill, basic_attack, observe,
go_back, select_item, buy_item, use_item, confirm, interact,
move_forward, open_map, select_waypoint
```

### Affordance System Semantic Actions

**File**: `planning/action_affordance.py:16-98` (`_AFFORDANCE_RULES`)

Additional actions produced by affordance derivation that are NOT in `_ALLOWED_SEMANTIC_ACTIONS`:
- `use_burst` (combat, boss_fight)
- `dodge` (combat, boss_fight)
- `switch_char` (combat)
- `use_ultimate` (turn_based_combat)
- `select_dialog_option` (dialog)
- `close_map` (map)
- `sort` (inventory)
- `heal` (boss_fight)
- `skip` (cutscene)
- `attack` (overworld, boss_fight)
- `move_forward` (overworld)
- `open_map` (overworld)

### Orphan Actions: In Planner/Affordance But NOT in _ACTION_MAP

| Semantic Action | Produced By | In _ACTION_MAP? | Severity |
|----------------|-------------|-----------------|----------|
| `use_burst` | combat, boss_fight affordances | NO | **CRITICAL** -- elemental burst is essential for combat |
| `dodge` | combat, boss_fight affordances | NO | **HIGH** -- no dodge/sprint in combat means taking unnecessary damage |
| `switch_char` | combat affordance | NO | **CRITICAL** -- cannot switch party members |
| `use_ultimate` | turn_based_combat affordance | NO | **HIGH** -- needed for Honkai-style turn-based segments if any |
| `select_dialog_option` | dialog affordance, element-derived | NO | **CRITICAL** -- dialog options are the primary story branching mechanism |
| `close_map` | map affordance | NO | **HIGH** -- after teleport, cannot close map |
| `sort` | inventory affordance | NO | **MEDIUM** -- inventory management edge case |
| `heal` | boss_fight affordance | NO | **HIGH** -- no healing during boss fights |
| `skip` | cutscene affordance | NO | **HIGH** -- cutscenes block gameplay for minutes |
| `attack` | overworld, boss_fight affordances | NO | **CRITICAL** -- the affordance system calls it "attack", executor calls it "basic_attack". Naming mismatch. |
| `open_map` | overworld affordance, planner allowed list | NO | **HIGH** -- pressing M to open map has no dedicated handler |
| `move_forward` | overworld affordance, planner allowed list | NO | **CRITICAL** -- the most basic movement action has no handler; only "move" exists |
| `claim_all` | reward_screen affordance, planner allowed list | NO | **HIGH** -- bulk claiming rewards |
| `select_waypoint` | map affordance, planner allowed list | NO | **CRITICAL** -- cannot select waypoints on map for teleport |

### In _ACTION_MAP But NOT in Planner/Affordance

These are not necessarily problems but indicate the executor supports actions the planner never produces:
- `move` (planner uses `move_forward`)
- `swim`, `sprint`, `dash`, `jump` (not in any affordance rule or planner list)

---

## 3. Essential Main-Story Actions Gap Analysis

### 3.1 Move Character (WASD) with Directional Control

**Status**: PARTIALLY IMPLEMENTED
**File**: `agent/genshin_game_agent.py:224-249`

- `_handle_move` supports forward/back/left/right via WASD
- **CRITICAL GAP**: No camera rotation. In Genshin, WASD moves relative to camera direction. Without mouse_move for camera, the agent can only move in whatever direction the camera happens to face.
- **CRITICAL GAP**: Hardcoded 1.5-second movement duration (line 246). No distance parameter, no visual feedback loop.
- Missing: `move_forward` action from planner has no mapping (only `move` exists).

### 3.2 Interact with NPCs (F Key)

**Status**: OK
**File**: `agent/genshin_game_agent.py:302-305`

- `_handle_interact` presses F key. Correct for Genshin.
- Missing: No detection of whether interaction prompt is visible before pressing F.

### 3.3 Advance Dialog (Space/Click)

**Status**: OK for basic advance
**File**: `agent/genshin_game_agent.py:266-269`

- `_handle_advance_dialog` presses Space. Correct.
- **HIGH GAP**: Some dialog requires clicking to advance (notably, clicking on NPC portraits). Only Space is supported.

### 3.4 Select Dialog Options (Number Keys / Click)

**Status**: CRITICAL GAP
**File**: `agent/genshin_game_agent.py:271-276`

- `_handle_select_option` only handles digit-based targets (presses "1", "2", etc.)
- **CRITICAL**: In Genshin, dialog options are selected by clicking on them with mouse, NOT by pressing number keys. The number keys (1-4) switch characters instead.
- **CRITICAL**: The affordance system produces `select_dialog_option` which has no handler in _ACTION_MAP at all.
- This means the agent CANNOT make any dialog choices, which blocks virtually all story quests.

### 3.5 Open/Close Menus (ESC)

**Status**: OK
**File**: `agent/genshin_game_agent.py:258-264`

- Both open_menu and close_menu press ESC. Correct for Genshin Paimon menu.

### 3.6 Teleport via Map (M -> Select Waypoint -> Click)

**Status**: COMPLETELY BROKEN
**File**: `agent/genshin_game_agent.py:251-256`

- `_handle_navigate_to` presses M then returns False with a warning: "navigate_to is not yet fully implemented"
- **CRITICAL**: No `open_map` handler
- **CRITICAL**: No `select_waypoint` handler
- **CRITICAL**: No mouse click at map coordinates capability
- **CRITICAL**: No `close_map` handler
- Teleportation is the primary way to navigate between quest areas. Without it, the agent is stuck in one location.

### 3.7 Combat: Normal Attack, Elemental Skill (E), Burst (Q), Character Switch (1-4)

**Status**: PARTIALLY IMPLEMENTED

- Normal attack: OK (`_handle_basic_attack` left-clicks)
- Elemental skill (E): OK via `_handle_use_skill` with target="e"
- Elemental burst (Q): OK via `_handle_use_skill` with target="q"
- **CRITICAL**: `use_burst` from affordance system has no _ACTION_MAP entry. The planner could produce "use_burst" which falls through to `_handle_unknown`.
- Character switch (1-4): OK via `_handle_use_skill` with target="1"/"2"/"3"/"4"
- **CRITICAL**: `switch_char` from affordance system has no _ACTION_MAP entry.
- **CRITICAL**: No combat AI logic. The agent just fires single keys with no combo, no timing, no dodge.
- **HIGH**: `dodge` action has no handler.

### 3.8 Use Items / Food

**Status**: WRONG INPUT
**File**: `agent/genshin_game_agent.py:298-299` (via `_handle_confirm`)

- `use_item` is aliased to `_handle_confirm` which presses Enter
- In Genshin, using items requires: (1) open inventory (B key), (2) navigate to item, (3) click Use/Equip button
- None of these steps are implemented. Pressing Enter does nothing useful.
- **HIGH GAP**: The entire food/item usage workflow is missing. Without healing items, the agent will die in combat.

### 3.9 Swim, Climb, Glide

**Status**: CRITICAL GAPS

- **Swim** (`_handle_swim`, line 321-325): Only presses Shift briefly. Does not hold W to actually swim. No stamina management. The agent will drown.
- **Climb**: NOT IMPLEMENTED. No handler exists. In Genshin, climbing requires holding W + Space (to jump-climb) and managing stamina. Completely absent.
- **Glide**: NOT IMPLEMENTED. No handler exists. In Genshin, gliding requires Space to deploy and W to move forward, with stamina management. Completely absent.

### 3.10 Accept/Complete Quests

**Status**: WRONG INPUT

- `select_quest` is aliased to `_handle_advance_dialog` (presses Space)
- `claim_reward` is aliased to `_handle_confirm` (presses Enter)
- In Genshin, quest acceptance and completion require clicking specific UI buttons with the mouse
- **CRITICAL**: The agent cannot accept or complete any quests because it only presses Space/Enter instead of clicking buttons

---

## 4. Input Backend Completeness

**File**: `execution/safe_window_backend.py`

### Supported Input Types

| Input Type | Method | Status |
|-----------|--------|--------|
| Keyboard key down | `key_down()` | OK |
| Keyboard key up | `key_up()` | OK |
| Left mouse click | `left_click()` | OK |
| Click at screen coords | `click_at()` | OK |
| Mouse move (relative) | `mouse_move()` | OK |
| Release all keys | `release_all()` | OK |
| Window focus check | `is_target_focused()` | OK |
| Right mouse click | -- | **MISSING** |
| Mouse scroll | -- | **MISSING** |
| Click-and-drag | -- | **MISSING** |

### Analysis

The backend supports the minimum needed for basic keyboard + left-click + relative mouse movement. However:

1. **No right-click**: Genshin uses right-click for aimed shots (archers). **MEDIUM** severity -- only needed for specific combat situations.

2. **No mouse scroll**: Needed for map zoom in/out. **HIGH** severity for map navigation.

3. **No click-and-drag**: Needed for map panning. **HIGH** severity for map navigation.

4. **click_at uses SetCursorPos**: This moves the OS cursor. Genshin in some configurations may not respond to synthetic cursor positioning. The mouse_move uses relative dx/dy via SendInput which is more reliable.

5. **No hold-click**: No method to hold left mouse button down for a duration (needed for charged attacks). **MEDIUM** severity.

6. **VK map is comprehensive** (line 25-34): Covers all standard Genshin keys (WASD, E, Q, F, Space, Shift, 1-4, Enter, ESC, Tab, arrow keys).

---

## 5. Screen Classifier Coverage

**File**: `perception/genshin_screen_classifier.py`

### Detectable States

| Classifier Output | Detection Method | Confidence | Quality |
|------------------|-----------------|------------|---------|
| `loading_screen` | Dark frame + low std dev | 0.9 | OK |
| `dialog` | Bottom ROI edge density + mean brightness | 0.85 | OK |
| `world_hud` | Minimap circle + HP bar green/red | 0.7-0.9 | OK |
| `full_menu` | HP bar or skill icons without minimap | 0.6 | WEAK -- too broad |
| `paimon_menu` | Dark frame without loading | 0.5 | WRONG -- dark frames could be anything |
| `no_hud` | Fallback | 0.6 | -- |

### States Required for Story Progression That Are NOT Detected

| Required State | Why It Matters | Severity |
|---------------|---------------|----------|
| `combat` | Combat requires different actions than overworld | **CRITICAL** -- agent won't know it's in combat |
| `map` | Teleport navigation requires detecting map screen | **CRITICAL** -- can't navigate map |
| `quest_log` | Quest selection requires detecting quest journal | **CRITICAL** -- can't manage quests |
| `inventory` | Item usage requires detecting inventory screen | **HIGH** |
| `cutscene` | Skip cutscene / wait for completion | **HIGH** |
| `shop` | Buying items from NPCs | **MEDIUM** |
| `boss_fight` | Boss mechanics differ from normal combat | **HIGH** |
| `reward_screen` | Claiming quest rewards | **HIGH** |
| `death_screen` | Revival needed after dying | **CRITICAL** -- agent dead with no recovery |

### Additional Classifier Issues

1. **Hardcoded ROI coordinates** (lines 23-26): All ROIs are hardcoded for 1920x1080. The scaling logic (lines 29-31) scales linearly, which may not work for different aspect ratios or UI scaling settings.

2. **No combat detection at all**: The classifier returns `world_hud` during combat because combat still has minimap + HP bar. There is no way to distinguish overworld exploration from active combat. This is the single biggest classifier gap.

3. **Dialog detection is fragile** (lines 113-122): Uses mean brightness between 30-160 and edge density > 5.0 in bottom 25% of screen. This could false-trigger on many non-dialog screens (inventory, quest log, any screen with UI elements at bottom).

4. **No text/UI element detection**: Purely color/edge based. Cannot detect specific buttons, quest markers, or interaction prompts that require OCR.

### VLM Prompt Screen States

**File**: `agent/genshin_game_agent.py:109`

The VLM prompt asks for: `loading_screen|dialog|world_hud|full_menu|paimon_menu|no_hud|combat`

This includes `combat` but the classifier does not. However, the VLM output states do NOT match the `ScreenStateKind` valid states in `planning/screen_state_claim_builder.py:91-94`:

```
valid_states = {"overworld", "combat", "turn_based_combat", "dialog", "menu",
                "map", "loading", "inventory", "shop", "quest_log",
                "reward_screen", "boss_fight", "cutscene", "unknown"}
```

**CRITICAL mismatch**: The classifier outputs `world_hud` but the valid state set expects `overworld`. The classifier outputs `loading_screen` but the valid set expects `loading`. The classifier outputs `full_menu` and `paimon_menu` but neither exists in the valid set. The VLM prompt asks for `world_hud` which doesn't match `overworld`.

This means `ScreenStateClaimBuilder._resolve_screen_state` (line 85-103) will attempt normalization: `world_hud` -> no match -> lower/underscore -> still no match -> falls through to "unknown". **The classifier's primary output cannot be resolved to a valid state.**

---

## 6. Consolidated Findings

### CRITICAL (Blocks Story Progression) -- 13 Issues

| # | Finding | File:Line | Description |
|---|---------|-----------|-------------|
| C1 | `use_burst` has no handler | agent/genshin_game_agent.py:337 | Affordance produces `use_burst`, _ACTION_MAP has no entry |
| C2 | `switch_char` has no handler | agent/genshin_game_agent.py:337 | Cannot switch characters in combat |
| C3 | `select_dialog_option` has no handler | agent/genshin_game_agent.py:337 | Cannot choose dialog options -- blocks ALL story quests |
| C4 | `attack` vs `basic_attack` naming mismatch | agent/genshin_game_agent.py:337 + planning/action_affordance.py:23,28,85 | Affordance uses "attack", executor uses "basic_attack" |
| C5 | `move_forward` has no handler | agent/genshin_game_agent.py:337 | Planner's primary movement action has no mapping |
| C6 | `select_waypoint` has no handler | agent/genshin_game_agent.py:337 | Cannot select waypoints on map |
| C7 | No camera rotation | agent/genshin_game_agent.py | `look` action is a no-op sleep. No mouse_move integration. Agent cannot steer. |
| C8 | Teleport completely non-functional | agent/genshin_game_agent.py:251-256 | `_handle_navigate_to` returns False immediately after pressing M |
| C9 | No climbing action | agent/genshin_game_agent.py | Completely missing. Required for reaching elevated quest areas. |
| C10 | No gliding action | agent/genshin_game_agent.py | Completely missing. Required for traversal. |
| C11 | Classifier state names mismatch valid states | perception/genshin_screen_classifier.py + planning/screen_state_claim_builder.py:91-94 | `world_hud` != `overworld`, `loading_screen` != `loading`, `full_menu`/`paimon_menu` not in valid set |
| C12 | No combat detection | perception/genshin_screen_classifier.py | Classifier returns `world_hud` during combat, affordance system cannot switch to combat rules |
| C13 | No death/recovery handling | agent/genshin_game_agent.py | Agent has no way to detect death or revive |

### HIGH (Degrades Experience) -- 8 Issues

| # | Finding | File:Line | Description |
|---|---------|-----------|-------------|
| H1 | `dodge` has no handler | agent/genshin_game_agent.py:337 | No dodge in combat |
| H2 | `heal` has no handler | agent/genshin_game_agent.py:337 | No healing in boss fights |
| H3 | `skip` (cutscene) has no handler | agent/genshin_game_agent.py:337 | Cutscenes block for minutes with no skip |
| H4 | `close_map` has no handler | agent/genshin_game_agent.py:337 | After teleport, map stays open |
| H5 | `claim_all` has no handler | agent/genshin_game_agent.py:337 | Cannot bulk-claim rewards |
| H6 | No mouse scroll in backend | execution/safe_window_backend.py | Cannot zoom map |
| H7 | No click-and-drag in backend | execution/safe_window_backend.py | Cannot pan map |
| H8 | Food/item usage workflow missing | agent/genshin_game_agent.py:298-299 | `use_item` just presses Enter; no inventory navigation |

### MEDIUM (Nice to Have) -- 5 Issues

| # | Finding | File:Line | Description |
|---|---------|-----------|-------------|
| M1 | `sort` (inventory) has no handler | agent/genshin_game_agent.py:337 | Cannot sort inventory |
| M2 | `use_ultimate` has no handler | agent/genshin_game_agent.py:337 | Turn-based combat ultimate missing |
| M3 | No right-click in backend | execution/safe_window_backend.py | Aimed shots not possible |
| M4 | No hold-click in backend | execution/safe_window_backend.py | Charged attacks not possible |
| M5 | Hardcoded movement duration | agent/genshin_game_agent.py:246 | 1.5s fixed, no distance control |

---

## 7. Architectural Issues

### 7.1 The Mouse-Click Problem

The fundamental issue is that Genshin's UI is primarily mouse-driven. The executor maps 8 actions (`select_quest`, `claim_reward`, `buy_item`, `use_item`, `teleport`, `track_quest`, `click_button`, `toggle_auto`) to keyboard presses (Space, Enter), but these all require mouse clicks in Genshin. Without a `click_at(x, y)` action that takes coordinates from the perception pipeline (VLM bounding boxes, OCR positions), the agent cannot interact with 90% of the game's UI.

### 7.2 The Camera Problem

WASD movement is relative to camera direction. Without camera rotation (`mouse_move`), the agent has no directional control. It can only move forward in whatever direction the camera faces. Combined with the hardcoded 1.5s movement duration, navigation is essentially blind.

### 7.3 The State Classification Pipeline Break

The screen classifier outputs states (`world_hud`, `loading_screen`, `full_menu`, `paimon_menu`) that do not exist in the valid `ScreenStateKind` set used by `ScreenStateClaimBuilder`. This means the entire classification pipeline degrades to "unknown" state most of the time, which means the affordance system cannot derive correct action sets.

---

## 8. Recommendations (Priority Order)

1. **Fix classifier state name alignment** -- Change classifier output to use `overworld`, `loading`, `menu` etc. to match `ScreenStateKind`.
2. **Add combat detection** -- Use HP bar color change, enemy HP bars, or crosshair presence to detect combat.
3. **Add missing _ACTION_MAP entries** for all orphan actions (`use_burst`, `dodge`, `switch_char`, `select_dialog_option`, `close_map`, `skip`, `heal`, `move_forward`, `open_map`, `select_waypoint`, `claim_all`).
4. **Add mouse-click-at-coordinates action** -- The executor needs a `click_at(x, y)` action that takes screen coordinates from VLM/OCR output.
5. **Add camera rotation action** -- Wire `mouse_move(dx, dy)` to a "look" or "rotate_camera" action.
6. **Add climb, glide, swim-movement handlers** with stamina awareness.
7. **Fix the hardcoded 1.5s movement** -- Accept duration or distance parameters.
8. **Add scroll and drag to input backend** for map navigation.
