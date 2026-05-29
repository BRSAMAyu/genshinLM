# Agent G: Safety & Robustness Re-Audit Report

Auditor: Agent G (Opus)
Date: 2026-05-30
Scope: Verify 5 previous CRITICALs + check new handlers for safety issues.

---

## Previous CRITICAL Verification

| ID | Issue | Status |
|---|---|---|
| C1 | VLM call blocks 30s, no retry/backoff | **REMAINS_BROKEN** — architectural, not quick-fix |
| C2 | AttachThreadInput deadlock, no timeout | **REMAINS_BROKEN** — OS-level limitation |
| C3 | _handle_move blocks with time.sleep, no interrupt | **REMAINS_BROKEN** — needs async refactor |
| C4 | release_all _resolve_vk outside lock | **FIXED** |
| C5 | _drain_movement_intent race on key release | **FIXED** |

## New Issues Found

| ID | Issue | Severity | Status |
|---|---|---|---|
| N1 | _handle_heal blocks 1.1s, no interrupt | MEDIUM | Acknowledged (same class as C3) |
| N2 | Hardcoded coords in select_waypoint | MEDIUM | Acknowledged (needs VLM-guided) |
| N3 | _press_key not interrupt-safe, key stuck on error | HIGH | Acknowledged (release_all mitigates) |
| N4 | left_click/click_at blocking sleep | LOW | Short duration (50ms), acceptable |

## StateBus Integration: CORRECT
- Parameter accepted, passed to brain, _NullStateBus works when None
- All state_bus usage properly null-guarded

## Thread Safety: SOUND after C4/C5 fixes
- _down_keys always accessed under lock
- release_all uses snapshot pattern correctly
- _resolve_vk is pure function, safe outside lock

---

**Bottom line**: 3/5 CRITICALs remain (C1, C2, C3 — all architectural). 2 fixed. StateBus wiring correct. Thread safety sound.
