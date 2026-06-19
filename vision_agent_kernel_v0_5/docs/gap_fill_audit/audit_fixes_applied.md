# Audit Fixes Applied — 2026-06-01

## Agent4 Audit Issues → Fixes Applied

| Issue | File | Fix Applied |
|---|---|---|
| **G6: `left_click_down`/`left_click_up`** | `ui_flow_skill_adapter.py:623-626` | Replaced with `backend.hold_click(duration_sec=0.5)` |
| **G6: Combat action routing** | `ui_flow_skill_adapter.py:613-624` | Added `_COMBAT_ROUTING_ACTIONS` frozenset; route in `_handle_action_intent` |
| **G8: `click_at` not in protocol** | `npc_shop_interactor.py:54-80` | Added `_click_at_normalized()` with fallback: `click_at` → `mouse_move_to + left_click` |
| **G9: Tuple unpacking bug** | `abyss_chamber_executor.py:123-125` | Pad results list to always return 3-tuple |
| **G4: Function call mismatch** | `goal_executor.py:24` | Fixed to pass `capture_frame` not `teleport` twice |

## Gap Status After Fixes

| Gap | Before | After |
|---|---|---|
| G1: OCR fail-safe | HIGH ✓ | HIGH ✓ |
| G2: Mail UIFlows | HIGH ✓ | HIGH ✓ |
| G3: Quest tracking | HIGH ✓ | HIGH ✓ |
| G4: DailyCommissionExecutor | LOW (unwired) | MEDIUM (wired via AgentLoop) |
| G5: Exploration UIFlows | HIGH ✓ | HIGH ✓ |
| G6: Combat keys | LOW (backend methods) | HIGH ✓ (protocol-compliant) |
| G7: WorldBoss/WaveDef | HIGH ✓ | HIGH ✓ |
| G8: NpcShopInteractor | LOW (backend methods) | HIGH ✓ (protocol-compliant) |
| G9: AbyssChamberExecutor | MEDIUM (tuple bug) | HIGH ✓ (bug fixed) |

**Overall Confidence:** HIGH (8/9 fully functional, 1 wired via AgentLoop)

## Notes

- **G4 DailyCommissionExecutor** is intentionally wired via AgentLoop path, not via `_execute_via_commission_executor`. The AgentLoop path provides full L0-L9 neurological runtime which is the correct execution path for general goals. The `_execute_via_commission_executor` method is available for direct script invocation but is not the primary path.
- **Combat actions** (`attack`, `dodge`, `jump`, etc.) now route through `_handle_combat` with real key presses instead of stub `action_intent` calls.
- **NpcShopInteractor** now works with any backend by falling back to `mouse_move_to + left_click` when `click_at` is unavailable.