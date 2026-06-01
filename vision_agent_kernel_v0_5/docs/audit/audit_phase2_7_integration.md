# Phase 2-7 Integration Audit Report

**Auditor**: Independent Opus audit
**Date**: 2026-06-01
**Scope**: 7 files across agent_kernel, planning, and tests

---

## 1. agent_kernel/loop.py

### Summary
Added `embodied_runtime` parameter to `AgentLoop.__init__()`, imported `KernelClaimBridge`, and added the embodied fast-path block (B2) in the main loop between dialogue interception (B) and Cerebrum planning (C).

### Findings

**[HIGH] F1: SemanticAction.kind Literal mismatch**
- `SemanticAction.kind` is typed as `Literal["ui", "navigation", "combat", "system"]`
- `EmbodiedAction.kind` uses `Literal["navigation", "combat", "interaction", "dialogue", "puzzle", "loot", "reward", "system"]`
- At line 189, `embodied_action.kind` is passed directly as `SemanticAction(kind=embodied_action.kind, ...)`
- When the embodied runtime returns `"interaction"`, `"dialogue"`, `"puzzle"`, `"loot"`, or `"reward"`, the frozen dataclass will raise no runtime error (Literal is a type-check hint, not enforced at runtime), but the kind value silently falls outside the valid contract. Downstream consumers that pattern-match on kind will miss these cases entirely.
- **Recommendation**: Add a mapping layer (e.g., `{"interaction": "ui", "dialogue": "ui", "puzzle": "ui", "loot": "ui", "reward": "ui"}`) before constructing the SemanticAction, or widen the SemanticAction.kind Literal.

**[MEDIUM] F2: embodied fast-path skips claim adjudication**
- The embodied fast-path (lines 183-211) executes the contract and increments `steps_succeeded` based on `receipt.focus_maintained`, but never runs claim adjudication (`_checker.adjudicate_delta`). No claims are appended to `verified_claims`.
- This means embodied actions are never verified via the L5-L6 claim pipeline. If the embodied runtime takes a wrong action (e.g., attacks the wrong target), there is no post-action verification to catch it.
- **Recommendation**: Add post-embodied-action claim adjudication, even if simplified. At minimum, capture the frame and run a lightweight check.

**[MEDIUM] F3: embodied fast-path can starve the Cerebrum planner indefinitely**
- If `obs.screen_state` stays in `("overworld", "exploration", "combat", "boss_fight")`, the embodied fast-path `continue` at line 211 means the code never reaches the Cerebrum throttle check at line 216.
- In a continuous overworld/combat scenario, the strategic planner is permanently bypassed. This may be intentional for local reflex, but if the agent gets stuck in a loop of embodied decisions, there is no escape hatch.
- **Recommendation**: Add a counter or timer-based escape hatch: if the embodied path has been active for N consecutive ticks without Cerebrum input, force one Cerebrum cycle.

**[LOW] F4: ClaimEvidence constructor call in claim_bridge.py missing keyword args**
- In `claim_bridge.py` line 44, `ClaimEvidence(claim_id=..., evidence_type=..., value=ref, confidence=..., source=...)` is called but the `ClaimEvidence` dataclass has additional fields: `timestamp` (default 0.0) and `evidence_id` (default `""`) and `payload` (default `{}`). These have defaults so the call is valid, but `timestamp` will be 0.0 rather than the actual time, which could confuse downstream consumers comparing timestamps.
- **Recommendation**: Pass `timestamp=time.perf_counter()` in the ClaimEvidence constructor.

**[LOW] F5: Runtime claim bridge import is deferred and silently fails**
- `claim_bridge.py` line 73 does `from runtime.claim_runtime import StateDeltaClaim as RuntimeStateDeltaClaim` inside the method body. This is fine for optional dependency management, but `loop.py` line 429-437 wraps it in a try/except that logs at DEBUG and swallows all errors.
- If the runtime module is importable but has a breaking schema change, the bridge failure is invisible at normal log levels.
- **Recommendation**: Log at WARNING on first failure, then suppress subsequent failures.

---

## 2. agent_kernel/embodied_runtime.py

### Summary
Added `tick_embodied()` method and `_obs_to_nav_frame()` to `DailyCommissionDryRunRuntime`. These methods convert a `SemanticObservation` into a `NavigationFrame`, then produce an `EmbodiedAction` via the navigation/combat policy.

### Findings

**[HIGH] F6: _obs_to_nav_frame distance estimation is hardcoded to 5.0**
- At line 401-402, if `ws.targets` is non-empty and has a `bbox_norm`, `distance` is hardcoded to `5.0`. The `bbox_norm` is a bounding box, not a distance metric.
- This means any visible target from `world_state.targets` is always reported as 5.0 meters away, regardless of actual apparent size. Navigation decisions based on distance (approach vs. interact vs. turn) will be incorrect for targets that are very close (should be ~0.5m) or far away (should be 50m+).
- **Recommendation**: Estimate distance from bbox size. E.g., `distance = max(0.5, 10.0 / max(0.01, (bbox[2]-bbox[0])*(bbox[3]-bbox[1])))` or accept distance as an explicit field on SceneObject.

**[MEDIUM] F7: tick_embodied creates a fresh TeamCombatRuntime on every call**
- At lines 370-373, a hardcoded single-member team is constructed every tick: `TeamCombatRuntime(active_slot=1, members=(TeamMemberRuntime(slot=1, role="driver"),))`.
- Combat decisions (healer check, burst/skill readiness) are always against this dummy team. Healer will never exist, food is always available, and HP is always 100%.
- This means the `RealTimeCombatPolicy` low-HP branches are dead code in the tick path. The only combat actions produced will be `cast_active_burst` (never, because burst_ready=False), `cast_active_skill` (always, because skill_ready=True), or `combo_normal_attack`.
- **Recommendation**: Accept team state as a parameter or maintain it as instance state that gets updated from observations.

**[MEDIUM] F8: tick_embodied returns None for dialogue/menu but embodied_runtime itself could handle them**
- Line 362 returns `None` for `"dialog"`, `"dialogue"`, `"menu"`, `"inventory"` states.
- This is by design (delegating to the DialogueController), but the `"inventory"` state is handled nowhere. If the agent opens inventory during an embodied action, tick_embodied returns None, the main loop falls through to Cerebrum, and Cerebrum may not know how to close inventory either.
- **Recommendation**: Add a fallback action for inventory/menu states, or document that the caller must handle these states.

**[LOW] F9: _obs_to_nav_frame ignores world_state targets when desktop_tree has high-confidence nodes**
- Lines 387-392 extract the highest-confidence button/icon from desktop_tree, but this overwrites `target_label` even when `world_state.targets` has a more relevant target. The subsequent block (lines 394-401) only fills `target_label` if it's empty (`target_label or t.label`), but `target_bbox` and `target_conf` remain from the desktop_tree button/icon.
- This means if a UI button has higher confidence than a combat target, the navigation will prioritize turning toward the button instead of the enemy.
- **Recommendation**: Separate UI target selection from world target selection, or use a priority scheme.

---

## 3. agent_kernel/skill_lookup.py

### Summary
Added `__len__()` method to `KernelSkillRecipeLookup` returning `len(self._recipes)`.

### Findings

**[LOW] F10: __len__ counts unique recipes, not registered capabilities**
- `self._recipes` is keyed by `recipe.skill_id`, but multiple capabilities can map to the same recipe. `len(self._recipes)` returns the number of unique recipes, not the number of registered capabilities.
- This is fine for the intended use (answering "how many recipes do we have?"), but `len(lookup) < len(capability_index)` in most cases. The tests only check `len(lookup) > 0`, so this is consistent.
- **Recommendation**: No action needed, but consider documenting that `__len__` returns recipe count, not capability count.

**[LOW] F11: find_applicable substring matching can produce false positives**
- Line 102: `any(token in haystack or haystack in token for token in tokens)` -- the `haystack in token` check means a single-character token would match almost anything. The tokens come from context, goal_id, description, and `str(goal)`. If `str(goal)` is e.g. `"1"`, then `"1" in haystack` matches everything.
- **Recommendation**: Add a minimum token length threshold (e.g., skip tokens shorter than 2 characters) or use word-boundary matching.

---

## 4. agent_kernel/claim_bridge.py

### Summary
Provides `KernelClaimBridge` with bidirectional conversion between kernel `StateDeltaClaim` and runtime `StateDeltaClaim`, plus `screen_claim_to_observation` for converting `ScreenStateClaim` to `SemanticObservation`.

### Findings

**[MEDIUM] F12: from_runtime_state_delta maps status to "verified" via string check**
- Line 55: `verified=status in {"verified", "audited", "locked"}` -- this is correct for the runtime `ClaimStatus` type, but the runtime also has `"reverified"` as a valid status that should arguably map to `verified=True`. Currently `"reverified"` would map to `verified=False`.
- **Recommendation**: Add `"reverified"` to the verified-status set.

**[MEDIUM] F13: screen_claim_to_observation uses getattr with broad fallbacks**
- The method is defensive (lines 94-145) but heavily uses `getattr(claim, ..., default)`. If the `ScreenStateClaim` schema changes (e.g., `ui_elements` is renamed), the method silently returns empty data rather than raising an error. This can make debugging very difficult.
- **Recommendation**: Log a warning when expected attributes return defaults, or validate the claim shape before conversion.

**[LOW] F14: to_runtime_state_delta uses lazy import but doesn't catch ImportError**
- Line 73: `from runtime.claim_runtime import StateDeltaClaim as RuntimeStateDeltaClaim` -- if `runtime.claim_runtime` is not installed, this raises `ImportError`. The caller in `loop.py` catches this via the outer try/except, but the error message would be confusing.
- **Recommendation**: Wrap in try/except ImportError with a clear error message.

---

## 5. planning/npc_affection_persistence.py

### Summary
New file providing JSON-based save/load/reset for `AffectionDialogManager` state.

### Findings

**[MEDIUM] F15: save() uses time.perf_counter() for the saved_at timestamp**
- Line 36: `"saved_at": time.perf_counter()` -- per CLAUDE.md, `time.perf_counter()` is the correct monotonic clock for logic, but a persisted file should use a wall-clock timestamp (e.g., `time.time()` or ISO format) for human readability. `perf_counter()` values are meaningless across process restarts.
- **Recommendation**: Use `time.time()` or `datetime.datetime.now().isoformat()` for the `saved_at` field in the persisted file. This is the one legitimate use of `time.time()` -- for human-facing timestamps in persisted data.

**[MEDIUM] F16: save() uses atomic write (tmp + replace) but tmp file may leak on crash**
- Lines 48-50: The pattern `tmp.write_text(...)` followed by `tmp.replace(self._path)` is correct for atomic writes on POSIX, but on Windows, `replace()` can fail if the target file is held open by another process (e.g., antivirus scanner). The `.tmp` file would remain.
- **Recommendation**: Add a try/except around the replace, and clean up the tmp file on failure. Consider using `os.replace()` directly.

**[LOW] F17: load() does not validate schema of loaded JSON**
- Lines 68-74: The load method reads `relationships` from the JSON and accesses `affection`, `dialog_count`, etc. with `.get()`. If the JSON was saved by a different version with a different schema, fields may be missing or have unexpected types. The `int()` calls at lines 71-74 will raise `TypeError` if values are non-numeric (e.g., `"high"`).
- **Recommendation**: Wrap the per-field extraction in try/except ValueError/TypeError and log a warning for skipped entries.

**[LOW] F18: reset(npc_name) does not persist the reset**
- `reset()` only modifies the in-memory manager. The checkpoint file is not updated. If the process crashes after reset but before the next `save()`, the reset is lost.
- **Recommendation**: Call `self.save()` at the end of `reset()`, or document that callers must save explicitly.

---

## 6. tests/test_npc_affection_persistence.py

### Summary
10 tests covering save/load roundtrip, missing file, corrupt file, reset, affection levels, directory creation, and overwrite.

### Findings

**[LOW] F19: Tests import AffectionDialogManager and AffectionLevel from interaction.dialog_driver**
- This is correct, but it means the test file has a hard dependency on `interaction.dialog_driver`. If that module is refactored, these tests break. This is standard and acceptable.
- No action needed.

**[LOW] F20: No test for concurrent save/load**
- There is no test for thread safety of the persistence layer. Since `AffectionDialogManager` uses a plain dict with no locking, concurrent save + on_dialog could produce inconsistent snapshots.
- **Recommendation**: If this module will be used from multiple threads, add a threading test or a lock to the save method.

---

## 7. tests/test_skill_lookup_capsule_integration.py

### Summary
4 tests verifying that `GenshinGameCapsule.skill_library()` output can be loaded into `KernelSkillRecipeLookup` and queried.

### Findings

**[MEDIUM] F21: Test imports GenshinGameCapsule directly -- capsule coupling**
- The tests import from `capsules.genshin.genshin_game_capsule`. This means the integration tests in `tests/` are coupled to a specific game capsule. If the capsule is moved or renamed, these tests break.
- **Recommendation**: Consider using a fixture or conftest to provide the capsule, or make the test parameterized.

**[LOW] F22: test_all_capsule_skills_are_valid_recipes iterates library directly**
- Line 40: `for capability, recipe in library.items():` -- the `recipe` is actually a `SkillRecipe` object (from `_build_skill_recipes()`), so the isinstance check always passes. This test is really verifying that `_build_skill_recipes()` returns `SkillRecipe` instances, which is trivially true given the code.
- **Recommendation**: This test adds marginal value. Consider testing edge cases like missing fields or invalid context instead.

---

## Cross-Cutting Concerns

### Thread Safety

**[HIGH] F23: loop.py embodied fast-path reads obs without lock, but obs is derived from shared frame capture**
- The main loop thread reads `obs.screen_state` at line 183 without holding `self._lock`. Meanwhile, background threads (`_run_human_intercept_monitor`, `_run_spinal_combat_reflex_loop`) also call `self._capture_frame()` and may modify shared state. The `obs` object itself is immutable (frozen dataclass), but the capture and perception pipeline behind it may not be thread-safe if they share mutable state.
- The `_state_bus` dict is accessed under lock for `running` and `user_intervened`, but the embodied path does not re-check `running` after obtaining `obs`. If `_state_bus["running"]` is set to `False` by the finally block while the embodied path is executing a contract, the contract will still execute.
- **Recommendation**: Add a `self._state_bus["running"]` check after obtaining `obs` and before executing the embodied contract.

### Type Safety

**[MEDIUM] F24: SemanticAction created with kind outside Literal range**
- As noted in F1, the embodied fast-path creates `SemanticAction(kind=embodied_action.kind, ...)` where embodied kinds include values not in the SemanticAction.kind Literal. Static type checkers (mypy) will flag this if run in strict mode.
- **Recommendation**: Add an explicit mapping or widen the type.

### Error Handling

**[LOW] F25: embodied_runtime.tick_embodied can raise and is not caught**
- Line 184: `self._embodied_runtime.tick_embodied(obs)` is called without a try/except. If the embodied runtime raises (e.g., due to malformed observation), the entire main loop crashes.
- **Recommendation**: Wrap in try/except with a log warning and fallback to the Cerebrum path.

---

## Summary Table

| ID | Severity | File | Description |
|----|----------|------|-------------|
| F1 | HIGH | loop.py | SemanticAction.kind Literal mismatch with EmbodiedAction.kind |
| F6 | HIGH | embodied_runtime.py | Distance hardcoded to 5.0m for all world_state targets |
| F23 | HIGH | loop.py | embodied path does not re-check running flag before contract execution |
| F2 | MEDIUM | loop.py | Embodied fast-path skips claim adjudication entirely |
| F3 | MEDIUM | loop.py | Embodied path can starve Cerebrum indefinitely |
| F7 | MEDIUM | embodied_runtime.py | Fresh dummy team on every tick -- combat policy branches dead |
| F8 | MEDIUM | embodied_runtime.py | inventory/menu states unhandled by both embodied and Cerebrum |
| F12 | MEDIUM | claim_bridge.py | "reverified" status not mapped to verified=True |
| F13 | MEDIUM | claim_bridge.py | Silent fallback on schema changes makes debugging hard |
| F15 | MEDIUM | npc_affection_persistence.py | perf_counter() in persisted file is meaningless across restarts |
| F16 | MEDIUM | npc_affection_persistence.py | Windows atomic write can fail, tmp file leaks |
| F21 | MEDIUM | test_skill_lookup | Tests coupled to GenshinGameCapsule location |
| F24 | MEDIUM | loop.py | mypy will flag kind Literal mismatch |
| F4 | LOW | claim_bridge.py | ClaimEvidence.timestamp defaults to 0.0 instead of actual time |
| F5 | LOW | loop.py | Runtime bridge failure logged at DEBUG, invisible at normal levels |
| F9 | LOW | embodied_runtime.py | Desktop button/icon can override world target priority |
| F10 | LOW | skill_lookup.py | __len__ returns recipe count, not capability count |
| F11 | LOW | skill_lookup.py | find_applicable substring matching too permissive |
| F14 | LOW | claim_bridge.py | Lazy import without clear error message |
| F17 | LOW | npc_affection_persistence.py | No schema validation on loaded JSON |
| F18 | LOW | npc_affection_persistence.py | reset() does not persist to disk |
| F20 | LOW | test_npc_affection | No thread safety test for persistence layer |
| F22 | LOW | test_skill_lookup | Trivial isinstance test adds no real coverage |
| F25 | LOW | loop.py | tick_embodied not wrapped in try/except |

---

## Recommendations (Priority Order)

1. **Fix SemanticAction.kind mapping** (F1/F24) -- Add a 5-line mapping dict from EmbodiedActionKind to SemanticAction.kind Literal values. This is a correctness issue that affects every embodied action.

2. **Add running-flag check before embodied contract execution** (F23) -- Single-line guard prevents executing contracts after shutdown.

3. **Fix distance estimation** (F6) -- Replace hardcoded 5.0 with a bbox-size-based heuristic or accept distance as an explicit parameter.

4. **Add post-embodied claim adjudication** (F2) -- At minimum, capture post-frame and run lightweight verification.

5. **Wrap tick_embodied in try/except** (F25) -- Prevent embodied runtime exceptions from crashing the main loop.

6. **Fix perf_counter in persisted file** (F15) -- Change to `time.time()` or ISO format for human-readable timestamps.

7. **Add "reverified" to verified-status set** (F12) -- One-line fix.

8. **Add Cerebrum escape hatch** (F3) -- Counter or timer to force Cerebrum cycle after N consecutive embodied ticks.
