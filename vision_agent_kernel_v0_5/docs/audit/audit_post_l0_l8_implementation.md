# Audit: Post L0-L8 Implementation Gap Analysis

Date: 2026-06-01
Auditor: automated architecture audit
Scope: `SPARKLE_AGENT_KERNEL_DESIGN.md` + `AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md` vs. codebase
Baseline: M0-M7 milestones complete, L0-L8 layers have concrete files in `agent_kernel/`

---

## Summary

| Category | Total | HAS_IMPL | PROTOCOL_ONLY | NOT_IN_PROTOCOL | TYPE_ONLY |
|----------|------:|---------:|--------------:|----------------:|----------:|
| Protocols (agent_kernel/protocols.py) | 13 | 12 | 1 | 0 | 0 |
| Types (agent_kernel/types.py) | 27 | 22 | 0 | 0 | 5 |
| ADR concepts not in agent_kernel | 8 | 3 | 5 | 0 | 0 |
| Signature mismatches | 4 | - | - | - | - |

---

## 1. Protocol Implementation Status

### 1.1 Protocols WITH concrete implementations

| # | Protocol | Impl Class | Impl File | Line | Severity |
|---|----------|-----------|-----------|------|----------|
| 1 | InputLeaseManager | InputLeaseManagerImpl | agent_kernel/input_lease_manager.py | 25 | OK |
| 2 | SpinalReflexAgent | SpinalReflexAgentImpl | agent_kernel/spinal_reflex_agent.py | 20 | OK |
| 3 | BrainstemNavigator | BrainstemNavigatorImpl | agent_kernel/brainstem_navigator.py | 23 | OK |
| 4 | DialogueController | DialogueController | agent_kernel/dialogue_controller.py | 137 | OK |
| 5 | CerebellumController | CerebellumControllerImpl | agent_kernel/cerebellum_controller.py | 27 | OK |
| 6 | CerebrumAgent | CerebrumAgentImpl | agent_kernel/cerebrum_agent.py | 27 | OK |
| 7 | CompanionAgent | OperatorAgent / SimpleOperatorAgent | agent_kernel/operator_agent.py | 223/500 | OK |
| 8 | PerceptionProvider | VLMPerceptionProvider | agent_kernel/adapters.py | 32 | OK |
| 9 | Planner | LLMPlanner | agent_kernel/adapters.py | 212 | OK |
| 10 | SuccessChecker | VLMSuccessChecker | agent_kernel/adapters.py | 144 | OK |
| 11 | ExecutionProvider | GenshinExecutionProvider | agent_kernel/adapters.py | 351 | OK |
| 12 | MemoryStore | FileMemoryStore | agent_kernel/memory.py | 14 | OK |
| 13 | GameCapsule | GenshinGameCapsule / HSRGameCapsule | capsules/genshin/genshin_game_capsule.py:245, capsules/hsr/hsr_game_capsule.py:208 | OK |

### 1.2 Protocols WITHOUT concrete implementations

| # | Protocol | Status | File | Line | Severity |
|---|----------|--------|------|------|----------|
| 1 | ClaimAdjudicator | **SIGNATURE MISMATCH** — protocol says `adjudicate(claim: StateDeltaClaim) -> StateDeltaClaim` but runtime/claim_adjudicator.py:180 defines `adjudicate(claim, observations, *, ...) -> AdjudicationResult` | agent_kernel/protocols.py | 407-413 | **P0** |
| 2 | SkillRecipeLookup | **PARTIAL** — protocol requires `find_applicable(context, goal) -> list[SkillRecipe]` but no implementation has this method. `SimpleSkillRecipeLookup` in execution/closed_loop_runner.py:421 only has `lookup(capability)` | agent_kernel/protocols.py | 391-404 | **P1** |

---

## 2. Signature Mismatches (P0 Critical)

### GAP-01: ClaimAdjudicator.adjudicate() signature divergence

**Files:**
- Protocol: `agent_kernel/protocols.py:407-413`
- Runtime impl: `runtime/claim_adjudicator.py:180-260`

**Protocol says:**
```python
def adjudicate(self, claim: StateDeltaClaim) -> StateDeltaClaim: ...
```

**Runtime impl says:**
```python
def adjudicate(self, claim: StateDeltaClaim, observations: list[ObservationClaim],
               *, dependency_health: float = 1.0, drift_penalty: float = 1.0,
               sample_sufficiency: float = 1.0) -> AdjudicationResult: ...
```

**Impact:** `isinstance(runtime_adjudicator, agent_kernel.protocols.ClaimAdjudicator)` will FAIL at runtime. The runtime adjudicator is a richer, production-quality class but it does NOT structurally conform to the kernel protocol. No code imports the protocol version; the runtime version is used directly.

**Severity: P0** — This is the core verification primitive (SPARKLE 5.4). The protocol and implementation must agree.

---

### GAP-02: RepairPatch.runtime_overrides type divergence

**Files:**
- ADR doc: `docs/AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md:225` — `runtime_overrides: dict[str, Any]`
- Kernel types: `agent_kernel/types.py:371` — `runtime_overrides: tuple[tuple[str, str], ...]`

**Impact:** Any code expecting dict access (`patch.runtime_overrides["key"]`) will crash when receiving the tuple version. The CerebrumAgentImpl in cerebrum_agent.py uses neither.

**Severity: P1**

---

### GAP-03: DialogueController.select_best_option() return type divergence

**Files:**
- Protocol: `agent_kernel/protocols.py:155-163` — returns `dict[str, Any] | None`
- ADR doc: `docs/AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md:192` — returns `DesktopNode | None`
- Implementation: `agent_kernel/dialogue_controller.py:292-331` — returns `DialogueActionResult` (not matching either signature)

**Impact:** The DialogueController class does not have `tick_dialogue_skip`, `is_option_present`, or `select_best_option` methods matching the protocol. Instead it has `tick()` returning `DialogueActionResult`. It will not pass `isinstance(dc, DialogueController)`.

**Severity: P1** — Protocol conformance check will fail.

---

### GAP-04: CerebellumController missing ADR method `align_ui_anchor`

**Files:**
- ADR doc: `docs/AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md:176` defines `align_ui_anchor(tree, target_label, active_overrides) -> DesktopNode | None`
- Kernel protocol: `agent_kernel/protocols.py:173-215` — does NOT include `align_ui_anchor`
- Impl: `agent_kernel/cerebellum_controller.py:27` — does NOT implement `align_ui_anchor`

**Impact:** The ADR specifies a method that neither the protocol nor the implementation provides. This is the template-anchoring + override-alignment method critical for SPARKLE 2.1.

**Severity: P1**

---

## 3. Types Without Production Code Usage (TYPE_ONLY)

These types are defined in `agent_kernel/types.py` but only used in tests, never in production code:

| # | Type | Defined (types.py line) | Used in production? | Severity |
|---|------|----------------------:|--------------------:|----------:|
| 1 | ClaimEvidence | 242 | NO — only in tests/test_agent_kernel_types.py | P2 |
| 2 | OperatorCommand | 228 | NO — only used internally in operator_agent.py, never imported by other modules | P3 |
| 3 | GoalResult | 268 | NO — only in agent_kernel/loop.py, never used by orchestration or closed loop | P2 |
| 4 | PlannedStep | 51 | NO — only in agent_kernel/loop.py and adapters.py | P3 |
| 5 | ActionableElement | 16 | NO — only in adapters.py for VLM output, never consumed by other modules | P2 |

**Severity rationale:** These are not bugs, but represent unused contractual types. If the closed-loop orchestration (ClosedLoopRunner, AutonomousTaskBrain) does not consume them, they are spec placeholders.

---

## 4. ADR Concepts Not Implemented in agent_kernel/

### GAP-05: DesktopTree / DesktopNode (ADR 2.1, 4)

**Status:** EXISTS OUTSIDE agent_kernel

- `interaction/desktop_tree.py` has a `DesktopNode` and `DesktopTree` with different fields than the ADR
- `agent_kernel/types.py` has `SceneGraph` / `SceneObject` as a different abstraction
- The ADR doc defines `DesktopNode` with `role: Literal["button", "list_item", ...]` but the implementation uses a different `DesktopNodeRole` literal

**Files:**
- ADR: `docs/AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md:98-164`
- Existing: `interaction/desktop_tree.py:14-36`

**Severity: P1** — Two parallel UI tree representations exist. The agent_kernel CerebellumControllerImpl.parse_desktop_tree() returns SceneGraph, not DesktopTree. The real DesktopTreeBuilder is in interaction/, not wired to the CerebellumController.

---

### GAP-06: NormalizedCoordinate (ADR 4)

**Status:** NOT IMPLEMENTED

- ADR defines `NormalizedCoordinate(nx, ny)` as a core L0 type
- No code in agent_kernel/ or anywhere else defines this

**File:** `docs/AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md:99-100`

**Severity: P3** — No production code needs it yet; all coordinates use raw tuples.

---

### GAP-07: PhysicalActionReceipt (ADR 4)

**Status:** PARTIALLY EXISTS — `agent_kernel/types.py:300-314` has `PhysicalReceipt` with different fields than ADR's `PhysicalActionReceipt`

- ADR requires `lease_id: UUID`, `issued_at`, `expires_at`, `action_type: Literal[...]`, `execution_latency_ms`, `focus_maintained`
- types.py has `action_id: str`, `success: bool`, `reason: str`, `execution_latency_ms`, `focus_maintained`, `is_verified`, `timestamp`
- Missing: lease_id, expires_at, action_type literal

**File:** `docs/AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md:104-111`

**Severity: P2** — The types diverge but serve similar purposes.

---

### GAP-08: UserIntervention / CompanionResponse (ADR 4)

**Status:** NOT IN agent_kernel

- ADR defines `UserIntervention` and `CompanionResponse` dataclasses
- The OperatorAgent uses its own `OperatorSession` + dict returns instead
- These ADR types exist only in the document, not in code

**File:** `docs/AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md:238-252`

**Severity: P2** — OperatorAgent has functionally equivalent structures but does not match the ADR spec.

---

### GAP-09: Bezier mouse trajectory (ADR 3, L0)

**Status:** NOT IMPLEMENTED

- ADR 3 specifies "Bezier mouse trajectory humanization" as part of L0
- No code exists for Bezier-curve mouse movement generation

**Severity: P3** — The existing InputWorker uses linear movement. Humanization is a quality feature, not safety-critical.

---

### GAP-10: SkillRecipeLookup.find_applicable()

**Status:** PROTOCOL_ONLY

- `agent_kernel/protocols.py:398-404` requires `find_applicable(context, goal) -> list[SkillRecipe]`
- No implementation exists
- `skills/registry.py:67` has a `find_applicable` but with a completely different signature

**File:** `agent_kernel/protocols.py:391-404`

**Severity: P1** — The planner cannot discover applicable skills without this method.

---

## 5. GameCapsule Protocol Completeness

### GAP-11: GameCapsule missing SPARKLE 6 methods

**Files:**
- SPARKLE doc: `docs/SPARKLE_AGENT_KERNEL_DESIGN.md:351-361` requires `screen_vocabulary()`, `action_vocabulary()`, `world_knowledge()`, `verifier_bundle()`, `skill_library()`, `risk_policy()`
- Protocol: `agent_kernel/protocols.py:420-447` only has `screen_vocabulary()`, `action_vocabulary()`, `skill_library()`, `risk_policy()`
- Missing from protocol: `world_knowledge()`, `verifier_bundle()`

**Severity: P1** — The Kernel has no standard way to access game world knowledge or domain verifiers through the capsule interface.

---

### GAP-12: Genshin/HSR Capsule test coverage

**Genshin Capsule tests:** `tests/test_genshin_game_capsule.py` — 20+ tests covering protocol conformance, vocabulary, skills, risk policy, operator integration. PASS.

**HSR Capsule tests:** `tests/test_hsr_game_capsule.py` — 15+ tests covering protocol conformance, HSR-specific states, no-Genshin-leakage, vocabulary isolation. PASS.

**Gap:** Neither capsule has integration tests that wire the capsule through the full agent_kernel stack (PerceptionProvider -> Planner -> ExecutionProvider -> SuccessChecker with capsule data). Tests exist only for isolated capsule protocol conformance.

**Severity: P2**

---

## 6. Cross-Cutting Concerns

### GAP-13: AgentLoop not used in production orchestration

**Files:**
- `agent_kernel/loop.py:26` — AgentLoop class
- Only referenced in `tests/test_agent_kernel.py`

**Status:** The production closed-loop path goes through `execution/closed_loop_runner.py:657` (ClosedLoopRunner), which does NOT use AgentLoop. These are two parallel loop implementations.

**Severity: P1** — Architectural ambiguity: which loop is canonical?

---

### GAP-14: SkillRecipe type duplication

**Files:**
- `agent_kernel/types.py:163-176` — canonical `SkillRecipe` with steps, verifiers, recovery_policies
- `execution/closed_loop_runner.py:86-93` — local `SkillRecipe` with capsule_id, parameters, verifier_contract

**Impact:** Two different SkillRecipe types exist. The ClosedLoopRunner uses its own simpler version. The Capsules use the richer agent_kernel version. No adapter bridges them.

**Severity: P1** — Type fragmentation. ClosedLoopRunner cannot consume Capsule SkillRecipes directly.

---

### GAP-15: UnknownSceneHandler not wired to any loop

**Files:**
- `agent_kernel/unknown_scene_handler.py` — complete implementation of SPARKLE 11
- Only tested in `tests/test_unknown_scene_handler.py`
- Neither AgentLoop nor ClosedLoopRunner invokes it

**Severity: P2** — The safe exploration loop (SPARKLE 11) exists as code but is not part of any production execution path.

---

## 7. Severity Classification

### P0 (Critical — architecture contract broken)
1. **GAP-01:** ClaimAdjudicator protocol/impl signature mismatch

### P1 (High — missing capability or structural gap)
2. **GAP-02:** RepairPatch.runtime_overrides type divergence
3. **GAP-03:** DialogueController protocol method signature mismatch
4. **GAP-04:** Missing CerebellumController.align_ui_anchor
5. **GAP-05:** DesktopTree/SceneGraph parallel representations
6. **GAP-10:** SkillRecipeLookup.find_applicable() unimplemented
7. **GAP-11:** GameCapsule missing world_knowledge/verifier_bundle
8. **GAP-13:** AgentLoop vs ClosedLoopRunner duplication
9. **GAP-14:** SkillRecipe type duplication

### P2 (Medium — spec drift or unused types)
10. **GAP-07:** PhysicalActionReceipt/PhysicalReceipt field divergence
11. **GAP-08:** UserIntervention/CompanionResponse not in agent_kernel
12. **GAP-12:** No end-to-end Capsule integration test through agent_kernel stack
13. **GAP-15:** UnknownSceneHandler not wired to production loop
14. **TYPE-01:** ClaimEvidence unused in production
15. **TYPE-04:** GoalResult unused outside loop.py
16. **TYPE-05:** ActionableElement not consumed by downstream modules

### P3 (Low — minor or future)
17. **GAP-06:** NormalizedCoordinate not implemented
18. **GAP-09:** Bezier mouse trajectory not implemented
19. **TYPE-02:** OperatorCommand internal-only
20. **TYPE-03:** PlannedStep internal-only

---

## 8. Recommendations (Priority Order)

1. **Fix ClaimAdjudicator protocol** — align `agent_kernel/protocols.py` with `runtime/claim_adjudicator.py` signature, or create an adapter. The runtime version is richer; the protocol should match it.

2. **Unify SkillRecipe** — remove the local `SkillRecipe` in `execution/closed_loop_runner.py` and use `agent_kernel.types.SkillRecipe` everywhere. Add a CapsuleSkillAdapter that bridges Capsule recipes to the closed loop.

3. **Fix DialogueController protocol** — update `agent_kernel/protocols.py` DialogueController to match the actual `tick()` / `is_option_present()` / option-detection API in the implementation.

4. **Add align_ui_anchor to CerebellumController** — either add to the protocol and implementation, or explicitly document it as a Capsule-layer concern.

5. **Add world_knowledge() and verifier_bundle() to GameCapsule protocol** — these are specified in SPARKLE 6 but missing from the protocol. At minimum, add stub methods.

6. **Wire UnknownSceneHandler into the agent loop** — when no skill matches, invoke the safe exploration loop instead of failing.

7. **Resolve AgentLoop / ClosedLoopRunner ambiguity** — document which is canonical, or merge them.

8. **Add end-to-end Capsule integration tests** — wire GenshinGameCapsule through PerceptionProvider -> Planner -> ExecutionProvider -> SuccessChecker.
