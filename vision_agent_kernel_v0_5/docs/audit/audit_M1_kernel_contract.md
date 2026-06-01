# M1 Kernel Contract Package Audit

**Auditor**: Independent Opus architecture auditor
**Date**: 2026-06-01
**Branch**: `codex/pre-realworld-closure`
**Scope**: `agent_kernel/types.py`, `agent_kernel/protocols.py`, `agent_kernel/__init__.py`, `tests/test_agent_kernel_types.py`
**Against**: `SPARKLE_AGENT_KERNEL_DESIGN.md` (总纲), `AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md` (L0-L9 ADR)

---

## Verdict: CONDITIONAL PASS

The M1 package is structurally sound, all 44 tests pass, the core contract files (`types.py`, `protocols.py`) have zero game-specific imports, and the naming is internally consistent. However, there are notable gaps against the architecture documents that should be tracked as follow-up items.

---

## 1. Type Completeness Check

### Types present in `types.py` (20 dataclasses)

| # | Type | Category | Spec ref | Status |
|---|---|---|---|---|
| 1 | `ActionableElement` | Perception | general | OK |
| 2 | `SemanticObservation` | Perception | general | OK |
| 3 | `AgentGoal` | Planning | ADR S4 | OK |
| 4 | `PlannedStep` | Planning | general | OK |
| 5 | `ActionPlan` | Planning | general | OK |
| 6 | `ActionPrimitive` | Execution | general | OK |
| 7 | `StepResult` | Execution | general | OK |
| 8 | `Experience` | Memory | S5.7 | OK |
| 9 | `SceneObject` | Scene | S5.3 | OK - matches spec exactly |
| 10 | `Affordance` | Scene | S5.3 | OK - matches spec exactly |
| 11 | `SceneGraph` | Scene | S5.3 | OK |
| 12 | `SkillStep` | Skill | S8.1 | OK - matches spec exactly |
| 13 | `SkillRecipe` | Skill | S8.1 | OK - matches spec exactly |
| 14 | `TaskSpec` | Task | S10.1 | OK |
| 15 | `RuntimeOverride` | Override | general | OK |
| 16 | `CapsulePatchProposal` | Override | general | OK |
| 17 | `OperatorCommand` | Operator | S10 | OK |
| 18 | `ClaimEvidence` | Claim | S5.4 | OK |
| 19 | `StateDeltaClaim` | Claim | S5.4 | OK |
| 20 | `GoalResult` | Result | general | OK |

### Types in ADR S4 but NOT in types.py

| Type | ADR ref | Severity | Notes |
|---|---|---|---|
| `NormalizedCoordinate` | ADR S4 | INFO | Simple `tuple[float, float]` suffices; not needed as standalone type |
| `PhysicalActionReceipt` | ADR S4 | WARNING | Used in execution flow (`Receipt + ObservationClaims -> StateDeltaClaim`). Absent from types.py |
| `ThreatSignal` | ADR S4 | WARNING | SpinalReflexAgent returns `list[dict[str, Any]]` instead of structured `ThreatSignal`. Type safety gap |
| `CombatCommand` | ADR S4 | WARNING | SpinalReflexAgent returns `dict[str, Any] | None` instead of structured `CombatCommand`. Type safety gap |
| `DesktopNode` | ADR S4 | INFO | Folded into `SceneObject` / `ActionableElement`. Acceptable generalization |
| `DesktopTree` | ADR S4 | INFO | Folded into `SceneGraph`. Acceptable generalization |
| `RouteSegment` | ADR S4 | WARNING | BrainstemNavigator uses `dict[str, Any]` instead of structured `RouteSegment`. Type safety gap |
| `MissionNode` | ADR S4 | WARNING | CerebrumAgent uses `dict[str, Any]` for mission nodes. Should be a typed dataclass |
| `MissionGraph` | ADR S4 | WARNING | CerebrumAgent returns `dict[str, Any]` instead of typed `MissionGraph`. Referenced in S13.1 as existing asset |
| `RepairPatch` | ADR S4 | WARNING | diagnose_failure returns `dict[str, Any]` instead of typed `RepairPatch` |
| `UserIntervention` | ADR S9 | INFO | CompanionAgent uses raw `str` for messages. Acceptable simplification |
| `CompanionResponse` | ADR S9 | INFO | CompanionAgent returns `dict[str, Any]` instead of typed response. Minor gap |
| `ActionContract` | S1.1, S5.6, S14 | WARNING | Referenced 6 times in design doc as the core execution unit. Not defined in types.py. `ActionPrimitive` partially fills this role |

---

## 2. Protocol Completeness Check

### L0-L9 Protocols (9 layer protocols)

| Layer | Protocol | ADR S4 | Status |
|---|---|---|---|
| L0 | `InputLeaseManager` | YES | OK |
| L1-2 | `SpinalReflexAgent` | YES | OK |
| L3-4 | `BrainstemNavigator` | YES | OK |
| L3-4 | `DialogueController` | YES | OK |
| L5-6 | `CerebellumController` | YES | OK |
| L7-8 | `CerebrumAgent` | YES | OK |
| L9 | `CompanionAgent` | YES | OK - has extra methods beyond ADR |

### Cross-cutting Protocols (5+2)

| Protocol | Status | Notes |
|---|---|---|
| `PerceptionProvider` | OK | frame -> SemanticObservation |
| `Planner` | OK | observation + goal -> ActionPlan |
| `ExecutionProvider` | OK | primitive -> StepResult |
| `SuccessChecker` | OK | observation + criteria -> (bool, float) |
| `MemoryStore` | OK | experience record/recall |
| `SkillRecipeLookup` | OK | skill ID -> SkillRecipe |
| `ClaimAdjudicator` | OK | StateDeltaClaim verification |

### Missing Protocol from S6

| Protocol | Spec ref | Severity |
|---|---|---|
| `GameCapsule` | S6 | WARNING - explicitly listed in M1 acceptance: "GameCapsule, SceneGraph, Affordance, SkillRecipe, TaskSpec, ActionContract, ClaimEvidence, OperatorCommand" |

---

## 3. Method Signature Correctness

### L0 InputLeaseManager
- ADR: `acquire_lease(owner: str, duration_sec: float, priority: int) -> UUID | None`
- Code: `acquire_lease(owner: str, duration_sec: float, priority: int) -> str | None`
- **INFO**: Code uses `str` for lease IDs instead of `UUID`. Acceptable for JSON serialization, but diverges from ADR.

### L1-2 SpinalReflexAgent
- ADR: `evaluate_threats(latest_frame: Any) -> Sequence[ThreatSignal]`
- Code: `evaluate_threats(latest_frame: object) -> list[dict[str, Any]]`
- **WARNING**: `Any` -> `object` is an improvement, but return type loses structure.

- ADR: `tick_combat_reflex(threats: Sequence[ThreatSignal], current_combo_step: int) -> CombatCommand | None`
- Code: `tick_combat_reflex(threats: list[dict[str, Any]], current_combo_step: int) -> dict[str, Any] | None`
- **WARNING**: Loses typed return.

### L3-4 DialogueController
- ADR: `tick_dialogue_skip(tree: DesktopTree) -> None`
- Code: `tick_dialogue_skip(scene_graph: SceneGraph) -> None`
- **OK**: Uses generalized `SceneGraph` instead of game-specific `DesktopTree`.

- ADR: `select_best_option(tree: DesktopTree, option_registry: Dict[str, Any]) -> DesktopNode | None`
- Code: `select_best_option(scene_graph: SceneGraph, option_registry: dict[str, Any] | None = None) -> dict[str, Any] | None`
- **WARNING**: Return type should be `SceneObject | None` or `ActionableElement | None`, not raw dict.

### L5-6 CerebellumController
- ADR: `parse_desktop_tree(frame, active_roi) -> DesktopTree`
- Code: `parse_desktop_tree(frame, active_roi) -> SceneGraph`
- **OK**: Generalized type.

- ADR: `align_ui_anchor(tree, target_label, active_overrides) -> DesktopNode | None`
- Code: Missing this method.
- **WARNING**: `align_ui_anchor` method is absent from CerebellumController.

### L7-8 CerebrumAgent
- ADR: `compile_mission(goal: AgentGoal) -> MissionGraph`
- Code: `compile_mission(goal: AgentGoal) -> dict[str, Any]`
- **WARNING**: Untyped return.

### L9 CompanionAgent
- ADR: `handle_user_message(message: UserIntervention, current_graph: MissionGraph) -> CompanionResponse`
- Code: `handle_user_message(message: str, current_context: dict[str, Any]) -> dict[str, Any]`
- **WARNING**: All structured types collapsed to `str`/`dict`.

- Code adds 3 extra methods not in ADR: `propose_override`, `propose_capsule_patch`, `explain_current_state`.
- **INFO**: These are reasonable extensions for the companion agent.

---

## 4. Game-Specific Import Check

| File | Game imports? | Notes |
|---|---|---|
| `agent_kernel/types.py` | NO | Clean |
| `agent_kernel/protocols.py` | NO | Clean |
| `agent_kernel/__init__.py` | NO | Clean |
| `agent_kernel/adapters.py` | YES (expected) | Contains `GenshinExecutionProvider`, references `GenshinScreenClassifier`. This is correct - adapters bridge game-specific code to generic protocols |

**PASS**: Core contract package has zero game-specific imports. `adapters.py` is correctly the boundary layer.

---

## 5. Test Coverage Assessment

44 tests, all passing. Coverage breakdown:

| Type/Protocol | Instantiation | Frozen | Slots | Params |
|---|---|---|---|---|
| `SceneObject` | YES | YES | YES | YES |
| `Affordance` | YES | YES | - | YES |
| `SceneGraph` | YES | YES | - | YES |
| `SkillStep` | YES | YES | - | YES |
| `SkillRecipe` | YES | YES | - | YES |
| `TaskSpec` | YES | YES | - | YES |
| `RuntimeOverride` | YES | YES | - | YES |
| `CapsulePatchProposal` | YES | YES | - | YES |
| `OperatorCommand` | YES | YES | - | YES |
| `ClaimEvidence` | YES | YES | - | - |
| `StateDeltaClaim` | YES | YES | - | YES |
| `ActionableElement` | - | - | - | - |
| `SemanticObservation` | - | - | - | - |
| `AgentGoal` | - | - | - | - |
| `PlannedStep` | - | - | - | - |
| `ActionPlan` | - | - | - | - |
| `ActionPrimitive` | - | - | - | - |
| `StepResult` | - | - | - | - |
| `Experience` | - | - | - | - |
| `GoalResult` | - | - | - | - |

**Protocols**: Not tested (structural subtyping makes this less critical, but runtime_checkable allows `isinstance` checks).

### Test gaps

| Item | Severity | Notes |
|---|---|---|
| 9 existing types untested | INFO | `ActionableElement`, `SemanticObservation`, `AgentGoal`, `PlannedStep`, `ActionPlan`, `ActionPrimitive`, `StepResult`, `Experience`, `GoalResult` have zero tests |
| Protocols untested | INFO | None of the 14 protocols have structural conformance tests |
| `ActionableElement.state` field | INFO | No test for state values beyond default |
| No negative tests | INFO | No tests for invalid field values |

---

## 6. Naming Consistency

| Check | Status |
|---|---|
| types.py names <-> __init__.py exports | PASS - all 20 types exported |
| protocols.py names <-> __init__.py exports | PASS - all 14 protocols exported |
| __all__ list matches actual imports | PASS |
| ADR type names -> code type names | See below |

### ADR -> Code naming deltas

| ADR Name | Code Name | Status |
|---|---|---|
| `DesktopNode` | `SceneObject` / `ActionableElement` | OK - generalization |
| `DesktopTree` | `SceneGraph` | OK - generalization |
| `ThreatSignal` | `dict[str, Any]` | WARNING - lost type |
| `CombatCommand` | `dict[str, Any]` | WARNING - lost type |
| `RouteSegment` | `dict[str, Any]` | WARNING - lost type |
| `MissionNode` | `dict[str, Any]` | WARNING - lost type |
| `MissionGraph` | `dict[str, Any]` | WARNING - lost type |
| `RepairPatch` | `dict[str, Any]` | WARNING - lost type |
| `UserIntervention` | `str` | INFO - simplification |
| `CompanionResponse` | `dict[str, Any]` | INFO - simplification |

---

## 7. Field Type Safety

### types.py: No `Any` usage -- PASS
All 20 dataclasses use concrete types. No `typing.Any` in any field.

### protocols.py: Heavy `Any` usage -- WARNING
`protocols.py` imports `Any` and uses it in **17 method signatures**. The ADR defines structured types for these; the code collapses them to `dict[str, Any]` or raw `str`. This weakens the contract:

- `SpinalReflexAgent.evaluate_threats` -> `list[dict[str, Any]]` (should be `list[ThreatSignal]`)
- `SpinalReflexAgent.tick_combat_reflex` -> `dict[str, Any] | None` (should be `CombatCommand | None`)
- `BrainstemNavigator.update_heading_servo` -> `dict[str, Any]` (should be `RouteSegment`)
- `CerebellumController.compile_route` -> `list[dict[str, Any]]` (should be `list[RouteSegment]`)
- `CerebrumAgent.compile_mission` -> `dict[str, Any]` (should be `MissionGraph`)
- `CerebrumAgent.diagnose_failure` -> `dict[str, Any]` (should be `RepairPatch`)
- `CompanionAgent.handle_user_message` -> `dict[str, Any]` (should be structured)
- `CompanionAgent.handle_user_message` param `current_context` -> `dict[str, Any]`
- `CompanionAgent.propose_override` param `current_state` -> `dict[str, Any]`
- `CompanionAgent.explain_current_state` param `state` -> `dict[str, Any]`

---

## Summary of Issues

### CRITICAL (0)
None.

### WARNING (9)

1. **W1**: `ActionContract` type missing -- referenced 6 times in design doc as the core execution unit. `ActionPrimitive` partially covers this but lacks the contract wrapper (lease, validator, receipt).
2. **W2**: `GameCapsule` protocol missing -- explicitly listed in M1 acceptance criteria (S14).
3. **W3**: 6 ADR dataclass types collapsed to `dict[str, Any]` in protocols: `ThreatSignal`, `CombatCommand`, `RouteSegment`, `MissionNode`, `MissionGraph`, `RepairPatch`. These weaken the contract and lose IDE/linter support.
4. **W4**: `CerebellumController.align_ui_anchor` method absent -- defined in ADR S4.
5. **W5**: `InputLeaseManager.acquire_lease` returns `str | None` instead of `UUID | None` per ADR.
6. **W6**: `DialogueController.select_best_option` returns `dict[str, Any]` instead of a typed element.
7. **W7**: `CompanionAgent.handle_user_message` signature diverges significantly from ADR (str/dict vs typed UserIntervention/MissionGraph/CompanionResponse).
8. **W8**: 9 existing types (pre-M1) have zero test coverage.
9. **W9**: 17 `dict[str, Any]` usages in protocols.py weaken type safety.

### INFO (5)

1. **I1**: `DesktopNode`/`DesktopTree` generalized to `SceneObject`/`SceneGraph` -- good design decision.
2. **I2**: `CompanionAgent` has 3 extra methods beyond ADR -- reasonable extensions.
3. **I3**: `NormalizedCoordinate` folded into `tuple[float, float]` -- acceptable.
4. **I4**: `UserIntervention`/`CompanionResponse` simplified to primitives -- acceptable for MVP.
5. **I5**: No negative tests for invalid field values -- minor coverage gap.

---

## Recommended Follow-ups (Priority Order)

1. Define `ActionContract` dataclass (wraps `ActionPrimitive` with lease_id, validator, receipt)
2. Define `GameCapsule` protocol per S6
3. Add structured types for `ThreatSignal`, `CombatCommand`, `RouteSegment`, `MissionNode`, `MissionGraph`, `RepairPatch` and update protocol signatures
4. Add `align_ui_anchor` to `CerebellumController`
5. Add tests for the 9 pre-existing types and protocol conformance
