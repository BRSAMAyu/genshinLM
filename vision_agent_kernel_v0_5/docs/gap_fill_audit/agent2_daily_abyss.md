# Agent2 Gap Fill Audit: G4 Daily Commission + G9 Abyss Chamber

## Scope

- **G4**: Daily Commission Executor
- **G9**: Abyss Chamber Executor

## G4 — Daily Commission Executor

### Gap

`agent_kernel/embodied_runtime.py` defines `DailyCommissionDryRunRuntime`, a dry-run state machine that only returns `EmbodiedAction` traces — no real input. The codebase lacked a real executor that wires the same decision logic (`HybridOpenWorldNavigator`, `RealTimeCombatPolicy`) to actual game interaction.

### Implementation

**New file: `agent_kernel/daily_commission_executor.py`**

```
agent_kernel/daily_commission_executor.py  (new)
```

Key components:
- `CommissionResult` — frozen dataclass with `objective_id`, `commission_type`, `success`, `duration_sec`, `error`.
- `DailyCommissionExecutor` — class that takes a `ui_adapter` (UIFlowSkillAdapter), optional `teleport_sequence` (TeleportSequence), and optional `capture_frame` callable.
- `accept_commissions()` — teleports to Mondstadt Guild, walks to Katheryne, interacts, selects accept option twice, skips cutscene.
- `execute_commission(objective, frame_source)` — dispatches to type-specific handler based on `objective.objective_type`.
- `_execute_combat_commission` — creates `TeamCombatRuntime` with 4 slots, loops up to 60 steps reading frames, detects combat mode via `CombatModeDetector`, calls `RealTimeCombatPolicy.decide()`, sends real key presses via `backend.key_down/key_up`.
- `_execute_dialogue_commission` — advances dialog and selects option 1 for up to 30 iterations.
- `_execute_puzzle_commission` — calls `explore_puzzle` or `explore_element_monument` semantic action.
- `_execute_interaction_commission` — navigates to target label, then interacts.
- `claim_rewards()` — teleports to Guild, interacts with Katheryne, claims, confirms, skips cutscene.
- `_combat_key()` — sends OS key down/up via `ui_adapter._backend`, with 80ms hold.
- `_chunked_sleep()` — monotonic-clock chunked sleep matching the kernel's no-blocking-wait rule.

**Modified: `app_service/goal_executor.py`**

Added G4 shortcut in `execute_goal()`:
```python
_normalized = goal_text.lower()
if any(tok in _normalized for tok in ("daily commission", "daily", "每日委托", "委托")):
    return self._execute_via_commission_executor(goal_text, live_mode, api_key)
```

New method `_execute_via_commission_executor()`:
- Creates a live `AgentLoop` via `create_live_genshin_loop()` to obtain the `ui_adapter`, `teleport_sequence`, and `capture_frame`.
- Instantiates `DailyCommissionExecutor` from those deps.
- Builds commission objectives via `_build_commission_objectives()` (heuristic: cyclically assigns combat/dialogue/puzzle/interaction to up to 4 commissions).
- Runs each commission via `executor.execute_commission()`, aggregates results.
- Returns `GoalExecutionResult` with per-commission node traces.

### Design Decisions

| Decision | Rationale |
|---|---|
| Lazy imports in `DailyCommissionExecutor.__init__` | Avoids circular import between `embodied_runtime` and this module |
| `TYPE_CHECKING` guard for type hints only | Keeps runtime dep graph clean |
| `Any` for `DailyCommissionObjective` in internal methods | Avoids re-importing the dataclass at runtime when the class is already loaded |
| Per-type dispatch in `execute_commission` | Handles the 4 commission types cleanly; each handler is self-contained |
| Chunked sleep instead of `time.sleep()` | Per CLAUDE.md safety rule: no blocking waits |

---

## G9 — Abyss Chamber Executor

### Gap

`combat/spiral_abyss.py` defines `SpiralAbyssRunner` (team building, room analysis, blessing selection) and `AbyssTimePressureManager` (time-critical strategy). It lacks a real chamber-by-chamber combat execution loop that wires these to actual game input.

### Implementation

**New file: `agent_kernel/abyss_chamber_executor.py`**

```
agent_kernel/abyss_chamber_executor.py  (new)
```

Key components:
- `ChamberResult` — frozen dataclass with `floor`, `chamber`, `success`, `stars_earned`, `duration_sec`, `error`.
- `AbyssChamberExecutor` — class taking `ui_adapter` (UIFlowSkillAdapter) and optional `combat_handler` (BossCombatRuntime).
- `execute_chamber(floor, chamber, max_duration_sec=180)` — opens Abyss menu, clicks Enter, waits for loading, loops combat ticks, claims rewards, reads stars. Returns `ChamberResult`.
- `execute_floor(floor)` — runs chambers 1-3 sequentially, stops on failure, returns tuple of 3 results.
- `_run_combat_tick()` — calls `basic_attack` + `cast_skill_e` semantic actions.
- `_read_stars()` — placeholder returning 3; real impl would use OCR/visual detection on chamber complete overlay.
- `_chunked_sleep()` — same monotonic chunked sleep as G4.

### Integration Points

| From `combat/spiral_abyss.py` | Used By |
|---|---|
| `SpiralAbyssRunner.prepare_floor()` | Not called directly — executor is a lower-level primitive for real input |
| `AbyssTimePressureManager.analyze_time_pressure()` | Available for future time-pressure-driven combat decisions |
| `SpiralAbyssTeamBuilder` | Could be wired in `execute_chamber()` for team-aware rotation |
| `AbyssFloorState`, `ChamberStatus` | Reference types for future floor-state tracking |

The executor does NOT re-implement `SpiralAbyssRunner` — it is a complementary layer that provides real execution while `SpiralAbyssRunner` handles planning.

### Design Decisions

| Decision | Rationale |
|---|---|
| 180s per chamber default | Matches game time limit (`AbyssTimePressureManager.FULL_TIME`) |
| `execute_floor` returns 3-tuple | Compatible with `SpiralAbyssRunner.advance_chamber` API |
| `_read_stars()` placeholder | Visual detection requires live perception pipeline; stub allows integration testing |
| `max_duration_sec` parameter | Allows caller to set tighter limits for lower floors |

---

## Shared Pattern

Both executors follow the same structural pattern:
1. **Constructor takes adapter + optional deps** (avoids hard coupling to full AgentLoop)
2. **Chunked monotonic sleep** (`_chunked_sleep`) — no `time.sleep()` anywhere
3. **Frozen result dataclass** — `CommissionResult` / `ChamberResult`
4. **Semantic action dispatch via `ui_adapter.execute_semantic()`** — all OS input goes through UIFlowSkillAdapter
5. **Exception isolation** — each method catches exceptions and returns a failed result rather than propagating

---

## Files Changed / Created

| Path | Change |
|---|---|
| `agent_kernel/daily_commission_executor.py` | Created (G4) |
| `agent_kernel/abyss_chamber_executor.py` | Created (G9) |
| `app_service/goal_executor.py` | Modified: added `_execute_via_commission_executor`, `_build_commission_objectives`, G4 shortcut in `execute_goal` |

## Verification

```
$ python -m py_compile agent_kernel/daily_commission_executor.py agent_kernel/abyss_chamber_executor.py app_service/goal_executor.py
OK

$ python -c "
from agent_kernel.daily_commission_executor import DailyCommissionExecutor, CommissionResult
from agent_kernel.abyss_chamber_executor import AbyssChamberExecutor, ChamberResult
from agent_kernel.embodied_runtime import DailyCommissionObjective, HybridOpenWorldNavigator, RealTimeCombatPolicy, CombatModeDetector
print('All imports OK')
n = HybridOpenWorldNavigator()
r = RealTimeCombatPolicy()
m = CombatModeDetector()
print('Classes instantiate OK')
"
All imports OK
Classes instantiate OK
```

## Next Steps

1. **G4**: Wire `_capture_frame` to live capture in `execute_goal` when in live mode, so `_execute_combat_commission` reads real frames instead of skipping.
2. **G9**: Implement `_read_stars()` using the perception pipeline OCR or screen state detection — currently a placeholder returning 3.
3. **G4/G9 shared**: Add watchdog timeout interrupt that triggers `release_all()` if a chamber/commission exceeds `max_duration_sec` without progress (using `time.perf_counter()` slope check).
4. **Integration test**: Add pytest fixtures that mock `ui_adapter._backend` and verify semantic action sequences for each commission type.