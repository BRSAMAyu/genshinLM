# Aurora Implementation Contract Addendum

This addendum turns the critical review items into hard implementation contracts. Coding agents should treat these as non-negotiable acceptance criteria before extending the layered runtime.

## Controller Routing

`ControllerRouter.can_handle() == False` means "skip this controller". It is not an execution failure and must not be surfaced as a task failure. Router failure only happens when no controller accepts the action.

Ambiguous controller matches are deterministic: the first registered controller wins, while `ControllerRouteTrace.ambiguous_matches` records lower-priority matches for audit.

## Confirmation Policy

CP-1 low-confidence confirmation defaults to `confidence < 0.75`.

CP-2 requires confirmation for:

- `risk_level in {"high", "human_confirm"}`.
- fallback visual-agent proposals.
- invalid Skill/Controller boundary checks.

## Skill And Controller Boundary

Skills emit `SemanticAction` and `ActionContract`. Controllers translate them into bounded physical receipts.

Skills must not call OS input directly or rely on raw xy coordinates as their main path. Raw coordinates are only allowed as last-resort fallback material with explicit verifier and confirmation policy.

## Mouse Policy Mapping

Mouse movement policy is selected by action family:

- `ui_click`: bezier, human-like, 160 ms default.
- `fallback_visual_agent`: bounded jitter, slower and confirm-gated.
- `calibration`: short straight path.
- `navigation_hold`: short straight path.
- `combat_reflex`: fastest short straight path.
- `instant`: dry-run/testbed only.

Controllers must not invent per-controller mouse movement styles.

## Checkpoint Resume Contract

Checkpoints must carry enough facts to revalidate safe resume:

- profile id/version.
- capsule id/version.
- window id.
- screen state.
- evidence refs.
- skill versions.
- verifier id/result.
- semantic action id.
- controller id.
- allowed next actions.

Unverified checkpoints or checkpoints without evidence must not be resumed.

## Context Compression Correctness

LLM context is a projection, not the fact source. `RunSummaryValidator` must reject:

- unknown current/completed/next nodes.
- duplicate completed nodes.
- verified facts without evidence refs.
- mission id mismatch.

Historical facts must be retrieved from evidence, checkpoints, record sessions, or capsule knowledge.

## Local VLM Routing

Model routing must be quantitative. Route decisions use:

- local provider health.
- local latency budget.
- local VLM smoke-bench grounding success.
- task complexity score.
- safety risk policy.

The runtime must not rely on vague "simple vs complex" prose.

## VLM Output Guard

VLM outputs are untrusted. UI grounding candidates must pass:

- normalized bbox bounds.
- confidence bounds.
- label/reason length limits.
- action-directive and prompt-injection filters.

The VLM can propose candidates, but it cannot issue physical-action instructions.

## Controller Result Verification

Controller self-reported success is untrusted unless it carries evidence refs or a verifier request. Failed or blocked controller results must carry a `failure_code`.

## Core Boundary Scan

Core boundary checks must use AST scanning, not grep only. The scanner rejects:

- game-specific imports.
- wildcard imports in `core/`.
- dynamic import strings.
- non-literal dynamic imports.
- game-specific string literals.
