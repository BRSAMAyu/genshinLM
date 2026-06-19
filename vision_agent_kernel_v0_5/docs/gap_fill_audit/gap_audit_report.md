# Gap Fill Audit Report — 2026-06-01

## Executive Summary

System has solid infrastructure (AgentLoop L0-L9, UIFlow engine, combat handlers) but significant capability gaps in execution layer. The fundamental issue: many systems are "designed but not wired" — handlers exist but delegate to unimplemented protocols.

---

## Gap Status (Pre-Fill)

| Gap | Severity | Status | Fix |
|-----|----------|--------|-----|
| G1 OCR fail-open | 🔴 Critical | ✅ FIXED | `ui_flow_engine.py` lines 545-610 → fail-safe |
| G2 Mail system | 🔴 Critical | 🔲 PENDING | Add OPEN_MAIL, MAIL_CLAIM_ALL flows + adapter |
| G3 Quest tracking | 🟡 High | 🔲 PENDING | Implement QUEST_SELECT_AND_TRACK + real coords |
| G4 Daily commission | 🟡 High | 🔲 PENDING | Connect embodied_runtime + GoalExecutor chain |
| G5 Exploration (9/11) | 🟡 High | 🔲 PENDING | 9 new UIFlow + adapter handlers |
| G6 Combat execution | 🔴 Critical | 🔲 PENDING | Real execute_semantic for combat types |
| G7 WorldBoss+WaveDef | 🟢 Medium | 🔲 PENDING | Two missing handlers |
| G8 Shop NPC item | 🟢 Low | 🔲 PENDING | Grid navigation for item selection |
| G9 Abyss chamber loop | 🟡 High | 🔲 PENDING | Concrete chamber execution |

---

## Gap 1: OCR Verification Fail-Open — FIXED ✅

**File**: `interaction/ui_flow_engine.py:545-610`

**Change**: Both `_step_verify_ocr_number` and `_step_verify_screen_contains` now raise `UIFlowTimeout` instead of warn-pass when verification fails or no data available.

- When `ocr_expected_min/max` specified but no OCR number found → FAIL
- When `expected_text` specified but not found → FAIL
- When no screen claim available with strict criteria → FAIL

---

## Gap 2: Mail System — COMPLETE GAP

**Missing**: No OPEN_MAIL flow, no adapter handler, no alias for mail operations.

**Files to create/modify**:
- `interaction/ui_flows/__init__.py`: Add OPEN_MAIL, MAIL_CLAIM_ATTACHMENT, MAIL_CLAIM_ALL
- `interaction/menu_flows.py`: Add "mail" button position to _MENU_BUTTONS dict
- `execution/ui_flow_skill_adapter.py`: Add "mail" to _DEFAULT_ALIASES, add `_handle_mail` handler

**Menu button position** (Genshin 1920x1080): "mail" button is at approximately (0.55, 0.84) in Paimon menu grid — between "shop" (0.35, 0.84) and "settings" (0.55, 0.84). Actually in Paimon menu there's no "mail" button — mail is accessed via Adventure menu. Need to check actual position.

**Action plan**: Add mail flows and integrate into adapter.

---

## Gap 3: Quest Tracking — STUB → REAL

**Current state**: `_handle_quest_track` sends `action_intent("quest:track")` only. No actual menu navigation.

**Need**:
1. Add OPEN_QUEST_LOG flow (J key → quest menu)
2. Add QUEST_SELECT_AND_TRACK flow (select quest + click track button at (0.85, 0.15))
3. Implement `_handle_quest_track` with real coordinates, not just action_intent
4. Add "open_quest_log" / "track_quest" aliases

**Action plan**: Add flows, implement real handler with coordinate clicks.

---

## Gap 4: Daily Commission Executor — DISCONNECTED

**Current state**: `DailyCommissionDryRunRuntime` exists in `agent_kernel/embodied_runtime.py` but is a dry-run shell. Not wired to GoalExecutor chain. No real commission type handler (combat/dialogue/puzzle/collection).

**Need**:
1. `DailyCommissionExecutor` class that connects embodied_runtime to real execution
2. Implement 4 commission type handlers: combat, dialogue, puzzle, interaction
3. Wire into GoalExecutor's execute_goal() chain
4. Commission tracking with claim adjudication

**Action plan**: Build commission executor from embodied_runtime, connect to GoalExecutor.

---

## Gap 5: Exploration Handlers — 9/11 MISSING

**Missing UIFlows** (need to add to `interaction/ui_flows/__init__.py`):

| Flow | Description |
|------|-------------|
| EXPLORE_STATUE_ACTIVATE | Press F near statue → offer/activate |
| EXPLORE_OPEN_CHEST | Press F → open chest |
| EXPLORE_ELEMENT_MONUMENT | Press F → element puzzle |
| EXPLORE_TORCH_PUZZLE | Light torches in sequence |
| EXPLORE_PRESSURE_PLATE | Multi-target coordination |
| EXPLORE_TIMED_CHALLENGE | Real-time path optimization |
| EXPLORE_OCULUS_COLLECT | Collect oculus, offer at statue |
| EXPLORE_WITHERING_ZONE | Dendro skill to clear |
| EXPLORE_UNDERWATER | Fontaine diving + oxygen |

**Adapter integration**: `_handle_explore` in `ui_flow_skill_adapter.py` already handles exploration actions via `action_intent`. Need to add real coords for the new flows and ensure they map to explore_* aliases.

**Action plan**: Add 9 new UIFlows, extend adapter handlers.

---

## Gap 6: Combat Execution — UNWIRED

**Current state**: All boss handlers call `execute_semantic("combat_*", ...)` but adapter's `_handle_combat` just sends `action_intent` and returns True. No actual key presses for basic attack, dodge, elemental skill, burst, character switch.

**Need**: Implement real combat execution:
1. `basic_attack` → hold LMB or tap LMB in sequence
2. `dodge` → double-tap direction or Shift+direction
3. `cast_skill_e` → E key
4. `cast_burst_q` → Q key
5. `switch_char` → 1-4 number keys
6. `lock_target` → Tab key
7. `auto_attack` → toggle via game setting

**Integration point**: `ui_flow_skill_adapter.py` `_handle_action_intent` and `_handle_combat` / `_handle_boss_combat` need real key press implementations.

**SpinalReflexAgentImpl**: Currently evaluates threats from frame dict metadata only. Needs integration with real visual detection pipeline for combat reflex.

**Action plan**: Implement combat key handlers in adapter, wire SpinalReflexAgentImpl.

---

## Gap 7: World Boss + Wave Defense — MISSING

**World Boss Rotation**: No handler for iterating through world bosses. Need rotation management: which boss → teleport → defeat → claim → next.

**Wave Defense**: No dedicated handler. Need state machine for multi-wave survival.

**Action plan**: Add WORLD_BOSS_ROTATION_CLAIM and WAVE_DEFENSE_START UIFlows.

---

## Gap 8: NPC Shop Item Grid — STUB

**Current state**: `NPC_SHOP_BUY_ITEM` clicks first item blindly. No item grid navigation for selecting specific items.

**Need**: Implement item grid scanning (scroll + click specific slot) with VLM/OCR fallback for item name.

**Action plan**: Extend NPC_SHOP_BUY_ITEM with real item selection logic.

---

## Gap 9: Abyss Chamber Loop — MISSING

**Current state**: `SpiralAbyssRunner` has planning (team building, time pressure) but no actual chamber-by-chamber execution loop.

**Need**: Implement chamber execution: enter → fight → claim → next floor.

**Action plan**: Build chamber loop from existing planning infrastructure.

---

## Implementation Priority

```
Priority 1 (Critical - block all):
  G1: OCR fail-safe              ← FIXED ✅
  G6: Combat execution           ← WIRES BOSS HANDLERS

Priority 2 (High - block daily use):
  G2: Mail system                ← MAIL IS BASIC FUNCTION
  G3: Quest tracking             ← NAVIGATION IS BASIC
  G4: Daily commission executor  ← CORE LOOP

Priority 3 (Medium - block content):
  G5: Exploration handlers       ← 9/11 MISSING
  G9: Abyss chamber loop        ← HIGH VALUE CONTENT

Priority 4 (Low - block polish):
  G7: WorldBoss+WaveDefense
  G8: NPC shop item grid
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `interaction/ui_flows/__init__.py` | +20 new UIFlow constants + registry entries |
| `interaction/ui_flow_engine.py` | +mail button to _MENU_BUTTONS |
| `execution/ui_flow_skill_adapter.py` | +mail aliases, +quest_track real coords, +combat key handlers |
| `agent_kernel/embodied_runtime.py` | +DailyCommissionExecutor class |
| `app_service/goal_executor.py` | Wire commission executor |
| `combat/boss_combat_handlers.py` | Verify SemanticExecutor integration |

---

*Generated: 2026-06-01*
*Status: G1 fixed, G2-G9 pending*
*Auditor: Claude Code (parallel agent + main session)*