# Aurora Operation Closure Runbook

This runbook defines the no-real-device-ready workflow for UI-heavy and embodied
game capsules. It intentionally stays inside authorized windows, dry-run
backends, and testbeds. It does not rely on memory reads, process injection,
anti-cheat bypasses, or driver-level input.

## Binding Flow

1. Install or select a capsule.
2. Load declared `ui_anchors` from `capsule.yaml`.
3. Capture one authorized-window screenshot through the safe window selector.
4. Run OCR/template/detector discovery and show candidate boxes.
5. Let the user confirm or drag-adjust each box.
6. Save a normalized `CalibrationProfile` with viewport, language, window mode,
   capsule version, anchor text, template crop references, and relative rules.
7. Run anchor validation. Block automation if required anchors are missing or
   below confidence.
8. Start Mission DAG dry-run, then safe-window execution only after profile,
   focus, capsule, and skill-version revalidation.

## Development Flow For A New Game

1. Create a capsule manifest with resources, capabilities, skills, and anchors.
2. Add providers for screen classifier, navigator, combat planner, and cooldowns
   only where the game needs them.
3. Build UI-first plan templates before adding embodied control.
4. Add Skill v2 contracts with semantic actions, anchors, verifiers, fallback,
   cleanup, and benchmark stats.
5. Add AuroraBench v2 dry-run cases for each public demo flow.
6. Add regression cases whenever a real binding failure is found.

## Runtime Invariants

- LLMs may plan MissionNode or SemanticAction objects, never raw coordinates.
- UI clicks must resolve through UIAnchor and pass confidence gates.
- Physical input must use InputLease with a bounded expiry and release policy.
- Terminal success must have observation-grounded verifier evidence.
- Long runs must checkpoint after verified MissionNodes and compact LLM context
  from runtime facts, not from free-form memory.

## Pre-Realworld Gate

Before opening a real game window, the local runtime must pass:

1. `python -m pytest -q`
2. `python .\scripts\check_core_boundaries.py --root .`
3. `python .\scripts\run_aurorabench.py --suite all --mode dry-run --output-dir .\benchmark_reports\pre_realworld_closure`
4. Capsule profile preflight for the target game. Unattended mode is blocked
   unless required anchors, profile metadata, normalized coordinates, and anchor
   validation all pass.
5. Local VLM optional smoke check. If the OpenAI-compatible endpoint is down or
   fails JSON/grounding validation, fallback visual-agent actions require human
   confirmation.

Terminal MissionNode completion must pass through ClaimGraphWorker and
ClaimAdjudicator. Legacy `VerifierResult(ok=True)` can only create an
ObservationClaim; it cannot complete a terminal node by itself.
