# Verifier And Learning

## Skill Binding

`execution/skill_binder.py` maps plan nodes to available Skills. Missing Skills produce a user demonstration request instead of raw input generation.

## Verifier

Every MissionNode must run a verifier. Failure is not reported as complete.

Verifier families:

- UI
- Visual
- Combat
- Collection

## Snapshot And Compensation

`MissionNodeExecutor` captures a `StateSnapshot` before high-risk nodes. If verifier failure occurs under `recover_or_skip`, the executor reports the configured cleanup Skill, such as `return_to_safe_anchor_v1`, before skipping.

## Privacy Mask

`learning/failure_signature.py` includes `PrivacyMask`. Observation screenshots must be masked before LLM review, report generation, or export. Export defaults to local-only review.

