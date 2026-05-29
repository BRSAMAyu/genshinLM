# Agent F: Action Chain Audit Report

Auditor: Agent F (Opus)
Date: 2026-05-30
Scope: Full action chain trace from affordance rules to executor handlers.

---

## Summary

40 affordance rules traced end-to-end. ALL have handlers in _ACTION_MAP. ALL in _ALLOWED_SEMANTIC_ACTIONS.

## Critical Issues Found (3)

| ID | Issue | Status |
|---|---|---|
| C1 | select_quest/track_quest mapped to advance_dialog (Space) | **Fixed in post-audit patch** |
| C2 | toggle_auto mapped to _handle_unknown (no-op) | **Fixed in post-audit patch** |
| C3 | click_button mapped to advance_dialog (Space) | **Fixed in post-audit patch** |

## High Issues Found (3)

| ID | Issue | Status |
|---|---|---|
| H1 | _handle_skip only ESC, no confirm | **Fixed** (now ESC + Enter) |
| H2 | _handle_dodge no direction | **Fixed** (now Shift + WASD) |
| H3 | select_waypoint hardcoded center | Acknowledged (needs VLM-guided coords) |

## Medium Issues (5)

| ID | Issue |
|---|---|
| M1 | use_ultimate missing from planner prompt | **Fixed** |
| M2 | claim_all just Enter (needs click) | Acknowledged |
| M3 | heal assumes healer in slot 4 | Acknowledged (convention) |
| M4 | turn_based_combat uses real-time keys | N/A for Genshin |
| M5 | sort just Enter | Acknowledged |

## Post-Audit Fix Status

All 3 CRITICAL + 2 HIGH + 1 MEDIUM fixed in subsequent commit.
