# Agent4 Gap-Fill Audit Report

**Commit:** `be8e370` — "Fill all 9 execution gaps: mail, quest, combat, daily, exploration, abyss"

**Audit Date:** 2026-06-01

**Auditor:** Claude Opus 4.7

---

## Executive Summary

The gap-fill commit delivers substantial new functionality across 9 execution gaps (G1-G9), but contains **8 critical bugs** and **4 medium-priority issues** that require immediate attention. The code integrates cleanly with existing infrastructure, but several gaps fail to deliver their intended behavior due to missing backend methods, unwired code paths, and logic errors.

**Overall Assessment:** The implementation is 70% complete. G1, G2, G3, G5, and G7 deliver working functionality. G4, G6, G8, and G9 have significant issues.

---

## Gap-by-Gap Analysis

### G1: OCR Fail-Open → Fail-Safe in UIFlowEngine ✓ PASS

**File:** `interaction/ui_flow_engine.py`

**Changes:** Modified `_step_verify_ocr_number` and `_step_verify_screen_contains` to raise `UIFlowTimeout` instead of passing silently when verification fails.

**Analysis:**
- Lines 558-562: When `ocr_expected_min` or `ocr_expected_max` is specified but no screen claim is available, now raises `UIFlowTimeout` with clear error message.
- Lines 584-588: When OCR expected range is specified but no number found, raises `UIFlowTimeout`.
- Lines 604-622: Similar fail-safe behavior for `verify_screen_contains`.

**Integration:** Clean. Uses existing `UIFlowTimeout` exception and `StateBus.screen_claim` interface.

**Confidence:** HIGH — Correct implementation of fail-safe semantics.

---

### G2: Mail System UIFlows ✓ PASS

**File:** `interaction/ui_flows/__init__.py` (lines 1169-1210)

**Changes:** Added three new UIFlows: `OPEN_MAIL`, `MAIL_CLAIM_ATTACHMENT`, `MAIL_CLAIM_ALL`. Registered in `ALL_FLOWS`.

**Analysis:**
- `OPEN_MAIL`: Opens Paimon menu → Adventure → Mail tab
- `MAIL_CLAIM_ALL`: Full flow including claim-all button click
- `MAIL_CLAIM_ATTACHMENT`: Individual mail claim flow
- All flows use normalized coordinates consistent with existing flows
- Registered in `ALL_FLOWS` dictionary

**Handler:** `execution/ui_flow_skill_adapter.py` lines 782-789
- `_handle_mail` routes mail actions to appropriate UIFlow via `execute_flow_as_semantic`
- Clean integration with existing handler infrastructure

**Confidence:** HIGH — Well-implemented UIFlows with proper handler wiring.

---

### G3: Quest Tracking with Real Coords ✓ PASS

**File:** `interaction/ui_flows/__init__.py` (lines 1212-1238)

**Changes:** Added `QUEST_SELECT_AND_TRACK` UIFlow and `OPEN_QUEST_LOG`.

**Analysis:**
- `QUEST_SELECT_AND_TRACK`: Opens quest log (J key) → clicks first quest → clicks track button
- Track button coordinate (0.85, 0.15) is reasonable for top-right UI area
- Handler in `_handle_quest_track` (line 774-780) routes to UIFlow

**Test Update:** `test_adapter_quest_track_executes_flow` correctly validates J-key press and track button click.

**Confidence:** HIGH — Correct coordinates and proper handler wiring.

---

### G4: DailyCommissionExecutor ⚠️ MIXED

**File:** `agent_kernel/daily_commission_executor.py` (315 lines)

**Analysis:**
**✓ Good:**
- Well-structured executor with clear commission type dispatch (combat, dialogue, puzzle, interaction)
- Proper use of `HybridOpenWorldNavigator`, `RealTimeCombatPolicy`, `CombatModeDetector` from embodied_runtime
- `_chunked_sleep` for interruptible waits
- Lazy imports avoid circular dependencies

**✗ Issues:**

1. **CRITICAL: Unwired Code Path (line 24 of goal_executor.py)**
   - `_get_daily_commission_executor` function is defined but never called
   - `_execute_via_commission_executor` method (lines 507-582) is defined but never invoked
   - The actual `execute_goal` path uses AgentLoop, not the commission executor
   - Result: All this commission executor code exists but is **never executed**

2. **CRITICAL: Function Call Mismatch (line 24)**
   ```python
   return _DailyCommissionExecutor(ui_adapter, teleport, teleport)
   ```
   Function is called with `(ui_adapter, teleport, capture_frame)` but passes `teleport` twice. The third parameter `capture_frame` is lost.

3. **CRITICAL: Backend Method Missing (line 207)**
   - `self._combat_key("shift", "s")` calls `key_down("shift")` then `key_down("s")`
   - But dodge should be: `key_down("shift")` → `key_down("s")` → `key_up("s")` → `key_up("shift")`
   - The `_combat_key` method only sends down/up for one key
   - This will result in malformed dodge sequences

4. **HIGH: Missing NavigationFrame Fields (line 196)**
   - Creates `NavigationFrame` with only `target_label` and `screen_state`
   - Missing `target_bbox_norm`, `target_confidence`, `threats`, etc. required by `mode_detector.detect()`
   - The detector will receive incomplete frame data

**Confidence:** LOW — Executor is well-structured but completely unwired and has backend integration bugs.

---

### G5: Exploration UIFlows ✓ PASS

**File:** `interaction/ui_flows/__init__.py` (lines 1241-1346)

**Changes:** Added 9 exploration UIFlows: `EXPLORE_STATUE_ACTIVATE`, `EXPLORE_OPEN_CHEST`, `EXPLORE_ELEMENT_MONUMENT`, `EXPLORE_TORCH_PUZZLE`, `EXPLORE_PRESSURE_PLATE`, `EXPLORE_TIMED_CHALLENGE`, `EXPLORE_OCULUS_COLLECT`, `EXPLORE_WITHERING_ZONE`, `EXPLORE_UNDERWATER`. All registered in `ALL_FLOWS`.

**Analysis:**
- All flows use consistent F-key interaction pattern
- `EXPLORE_UNDERWATER` uses F-dive + W-swim-forward sequence (lines 1336-1345)
- Test `test_adapter_explore_underwater_sends_dive_key` validates F-key behavior
- Handler `_handle_explore` routes to UIFlow for flows in `ALL_FLOWS`

**Confidence:** HIGH — All 9 flows properly defined and registered.

---

### G6: Combat Real Key Execution ✗ FAIL

**File:** `execution/ui_flow_skill_adapter.py` (lines 603-676)

**Analysis:**
**✗ CRITICAL: Backend Method Missing (lines 621-629)**
```python
if action in ("basic_attack", "attack", "combo_normal_attack"):
    # Hold LMB for auto-attack
    try:
        backend.left_click_down(reason="combat_attack")  # ← METHOD DOES NOT EXIST
        self._chunked_sleep(0.5)
        backend.left_click_up(reason="combat_attack_done")  # ← METHOD DOES NOT EXIST
```
The `InputBackend` protocol only defines:
- `left_click(reason)` — full click with hold delay
- `hold_click(duration_sec, reason)` — hold for duration

There is NO `left_click_down` or `left_click_up` method. The exception is caught and execution falls through to action_intent, but the attack never happens.

**✗ CRITICAL: Action Routing Issue**
The `_handle_combat` method is only invoked for these actions:
- `combat_basic`, `combat_shield_break`, `combat_boss`, `combat_abyss_mage`, `combat_world_boss`, `combat_weekly`

But NOT for `attack` or `basic_attack`. Those route to `_handle_action_intent` instead. So the combat key code is unreachable from the semantic action "attack".

**✗ Issue: Shift+S Dodge (lines 632-640)**
```python
if action in ("dodge", "dash"):
    try:
        backend.key_down("shift", reason="dodge_modifier")
        backend.key_down("s", reason="dodge_back")
        self._chunked_sleep(0.1)
        backend.key_up("s", reason="dodge_back_done")
        backend.key_up("shift", reason="dodge_modifier_done")
```
This code works correctly (key_down/up exist). But `dodge` is not in the primitive_handlers mapping, so it routes to `_handle_action_intent` instead.

**Confidence:** LOW — Core combat functions call non-existent backend methods and are unreachable via semantic action routing.

---

### G7: World Boss + Wave Defense UIFlows ✓ PASS

**File:** `interaction/ui_flows/__init__.py` (lines 1348-1374)

**Changes:** Added `WORLD_BOSS_ROTATION_CLAIM` and `WAVE_DEFENSE_START` UIFlows. Registered in `ALL_FLOWS`.

**Analysis:**
- `WORLD_BOSS_ROTATION_CLAIM`: F to claim → confirm → ESC to close
- `WAVE_DEFENSE_START`: F to interact → click start button → wait loading
- Uses `wait_loading` and `wait_not_loading` for proper loading screen handling
- No dedicated handler needed (uses default UIFlow executor)

**Confidence:** HIGH — Correct UIFlow definitions.

---

### G8: NpcShopInteractor + Buy Specific ✗ FAIL

**File:** `interaction/npc_shop_interactor.py` (111 lines)

**Analysis:**
**✓ Good:**
- Clean grid-based shop navigation
- `select_item_by_index` works correctly with 2-column layout
- `_chunked_sleep` for interruptible waits

**✗ CRITICAL: Backend Method Missing (line 54)**
```python
self._backend.click_at(int(nx * 1920), int(ny * 1080), ...)
```
The `_Backend` mock in tests has `click_at`, but the real `InputBackend` protocol does NOT define `click_at`. Only `SafeWindowInputBackend` has this method.

**✗ HIGH: Handler Integration Issue (ui_flow_skill_adapter.py lines 484-492)**
```python
def _init_shop_interactor(self) -> None:
    backend = self._backend()
    if backend is not None and hasattr(backend, "click_at"):
        try:
            self._shop_interactor = NpcShopInteractor(backend=backend, state_bus=self._bus)
        except Exception as exc:
            log.warning("[UIFlowSkillAdapter] NpcShopInteractor init failed: %s", exc)
```
The handler is initialized but `_handle_npc_shop_buy_specific` (lines 929-945) expects `self._shop_interactor` to be non-None. If the backend lacks `click_at`, the handler will log a warning and return False for all shop operations.

**✗ Issue: Primitive Handler Registration (line 364)**
The handler is registered, but `npc_shop_buy_specific` is not in the `_DEFAULT_ALIASES` mapping. Users must invoke it with the exact action name.

**Confidence:** LOW — Interactor uses backend method not defined in protocol, making it unsafe for general use.

---

### G9: AbyssChamberExecutor ⚠️ MIXED

**File:** `agent_kernel/abyss_chamber_executor.py` (145 lines)

**Analysis:**
**✓ Good:**
- Clear chamber-by-chamber execution structure
- Uses `_ui.execute_semantic` for all interactions
- `_chunked_sleep` for interruptible waits

**✗ CRITICAL: Tuple Unpacking Bug (lines 123-125)**
```python
return (results[0], results[1], results[2]) if len(results) == 3 else (
    results[0] if results else ChamberResult(floor=floor, chamber=1, success=False, stars_earned=0, duration_sec=0.0)
)
```
This will fail when `len(results) == 1` or `len(results) == 2` because the function returns a 3-tuple but the else clause returns a single `ChamberResult` or a 1-tuple. Type annotation says `tuple[ChamberResult, ChamberResult, ChamberResult]` but that's not always true.

**✗ HIGH: Unwired semantic action (line 59)**
```python
self._ui.execute_semantic("combat_abyss", "", {})
```
`combat_abyss` is registered as a primitive handler but routes to `_handle_combat`, which only sends action_intent. The real Abyss chamber combat logic would need to invoke the actual combat system.

**✗ MEDIUM: Placeholder combat (lines 127-131)**
```python
def _run_combat_tick(self) -> None:
    """Run one tick of combat — basic auto-attack + skill."""
    self._ui.execute_semantic("basic_attack", "", {})
    self._ui.execute_semantic("cast_skill_e", "", {})
    self._chunked_sleep(1.0)
```
This is a placeholder that doesn't use real combat decision-making or visual feedback.

**✗ MEDIUM: Star reading stub (lines 133-139)**
```python
def _read_stars(self) -> int:
    """Read star rating from Abyss completion UI.
    Placeholder — real impl would use OCR/visual detection on the
    chamber complete overlay, integrating with the perception pipeline.
    """
    return 3  # Optimistic default
```

**Confidence:** MEDIUM — Structure is sound but has tuple unpacking bug and placeholder implementations.

---

## Cross-Cutting Issues

### 1. Backend Protocol Mismatch

The `InputBackend` protocol (`execution/input_backend_base.py`) defines these methods:
- `key_down`, `key_up`, `release_all`, `is_target_focused`
- `mouse_move`, `mouse_move_to`, `left_click`, `right_click`, `mouse_scroll`, `hold_click`
- Various advanced methods (drag, double_click, type_text, execute_combo)

But the gap-fill code uses:
- `left_click_down`, `left_click_up` — **NOT DEFINED** (G6)
- `click_at` — **NOT DEFINED** in protocol, only in `SafeWindowInputBackend` (G8)

**Impact:** Code paths that call these methods will raise `AttributeError` and fall through to action_intent, failing silently.

**Recommendation:** Either add these methods to the `InputBackend` protocol or refactor the calling code to use the protocol-defined methods.

---

### 2. Semantic Action Routing Gap

Several combat-related actions are registered in primitive_handlers but don't route to `_handle_combat`:
- `attack`, `basic_attack` → route to `_handle_action_intent`
- `dodge`, `dash` → route to `_handle_action_intent`

Only `combat_basic`, `combat_shield_break`, etc. route to `_handle_combat`.

**Impact:** The real combat key execution code in `_handle_combat` is unreachable for the basic combat actions.

**Recommendation:** Add alias mappings or update `_primitive_handlers` to route these actions to `_handle_combat`.

---

### 3. Unwired Functions in goal_executor.py

Functions `_get_daily_commission_executor` and `_execute_via_commission_executor` are defined but never called. The actual `execute_goal` method uses AgentLoop path.

**Impact:** The `DailyCommissionExecutor` is never used.

**Recommendation:** Either wire the commission executor into `execute_goal` or remove the dead code.

---

## Test Coverage

### Tests Updated:
- `test_adapter_quest_track_executes_flow` — Validates G3 J-key + track button click ✓
- `test_adapter_explore_underwater_sends_dive_key` — Validates G5 F-key for dive ✓

### Tests Missing:
- No test for G1 OCR fail-safe behavior
- No test for G2 mail flows
- No test for G4 DailyCommissionExecutor
- No test for G6 combat key execution (existing tests don't cover new `_handle_combat` paths)
- No test for G7 world boss/wave defense flows
- No test for G8 NpcShopInteractor
- No test for G9 AbyssChamberExecutor

**Recommendation:** Add tests for each gap's new functionality.

---

## Recommendations by Priority

### P0 (Critical — Must Fix):
1. **G6:** Fix `left_click_down`/`left_click_up` calls → use `hold_click` instead
2. **G6:** Add semantic action routing so `attack`/`basic_attack` reach `_handle_combat`
3. **G8:** Fix `NpcShopInteractor` to use protocol-compliant backend methods
4. **G9:** Fix tuple unpacking bug in `execute_floor`
5. **G4:** Either wire `DailyCommissionExecutor` into execution path or remove dead code
6. **G4:** Fix `_combat_key` to handle multi-key sequences (Shift+S)

### P1 (High):
7. **G1:** Add test for OCR fail-safe behavior
8. **G4:** Fix `NavigationFrame` construction in combat commission
9. **G8:** Add protocol check in `_init_shop_interactor` and handle backends without `click_at`

### P2 (Medium):
10. **G9:** Replace placeholder combat tick with real combat integration
11. **G9:** Replace stub `_read_stars` with OCR-based star detection
12. Add comprehensive tests for G2, G4, G6, G7, G8, G9

---

## Gap Confidence Ratings

| Gap | Confidence | Status |
|-----|------------|--------|
| G1: OCR fail-safe | HIGH | ✓ Working |
| G2: Mail UIFlows | HIGH | ✓ Working |
| G3: Quest tracking | HIGH | ✓ Working |
| G4: DailyCommissionExecutor | LOW | ✗ Unwired, bugs |
| G5: Exploration UIFlows | HIGH | ✓ Working |
| G6: Combat keys | LOW | ✗ Backend methods missing |
| G7: Boss/Wave UIFlows | HIGH | ✓ Working |
| G8: NpcShopInteractor | LOW | ✗ Backend methods missing |
| G9: AbyssChamberExecutor | MEDIUM | ⚠️ Tuple bug, placeholders |

**Overall Confidence:** MEDIUM (5/9 gaps fully functional)

---

## Conclusion

The gap-fill commit delivers working UIFlows for mail, quest, exploration, world boss, and wave defense scenarios. However, the combat and shop integration gaps have critical backend protocol mismatches, and the daily commission and abyss executors are either unwired or contain bugs. The most urgent fixes are:

1. Refactor G6 to use protocol-compliant backend methods
2. Fix G9 tuple unpacking before it causes runtime errors
3. Decide whether to wire G4 into the execution path or remove dead code

With these fixes, the gap-fill implementation would achieve 85% functionality (8/9 gaps working, 1 with placeholders).
