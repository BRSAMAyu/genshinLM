# Aurora Unified Execution Plan: Autonomous Skill Evolution & Long-Horizon Progression

This unified execution plan establishes a pragmatic, academically rigorous, and code-grounded roadmap to transition Aurora from a human-configured skill executor into a self-evolving visual agent capable of long-horizon autonomous task completion. 

Rather than proposing sweeping architectural rebuilds, this plan is designed to **consume** and **wire together** Aurora's existing, highly mature core infrastructure.

---

## A. Code Reality Audit: What Exists vs. What is Truly Missing

A rigorous audit of the `vision_agent_kernel_v0_5` codebase reveals that the core infrastructure is highly complete. Many modules believed to be missing are already fully implemented, meaning our actual development focus is exceptionally narrow.

### 1. Existing Production-Quality Infrastructure (To Consume, Not Rebuild)
The following robust components are already implemented and must be leveraged directly:
* **Evidence & Claim Runtime (`runtime/claim_runtime.py`, `runtime/claim_worker.py`):** A 1,000+ line, fully thread-safe evidence-evaluation system. It handles `StateDeltaClaim`, `ObservationClaim`, `AdjudicationEvent`, and the `ClaimGraph` with cluster demotion, delayed audits, and reliability estimation.
* **Skill Evolution Base (`learning/evolution_engine.py`):** An orchestration engine that currently processes execution failures, constructs failure signatures, proposes skill repairs via `SkillPatchBuilder`, and runs sandbox validation runs.
* **Perception & Local OCR Pipeline (`perception/`):** Existing integration with high-frequency template matchers, local OCR providers (PaddleOCR), and YOLO-based entity detectors.
* **Input Safeties & OS Bindings (`control/`, `core/state_bus.py`):** A rigid safety framework consisting of `InputLease`, `DeadmanSwitch`, and window-focus verification to prevent unsafe physical inputs.
* **Semantic Anchor Binding (`recording/semantic_distiller.py`):** A mechanism (`SemanticSkillDistiller`) to map raw coordinate clicks to symbolic `UIAnchor` references based on current viewport coordinates.
* **Trace Segmentation (`repair/demo_segmenter.py`):** An existing class (`DemoSegmenter`) designed to partition contiguous streams of user/agent events into logical, task-oriented action segments.

### 2. The 6 Commonly-Believed "Gaps" That Are Already Implemented
Many elements thought to require new development already exist in the codebase:
1. **Real Input Capabilities:** Handled by `control/` plane via focus-locked OS wrappers.
2. **OCR Routing & Calibration Wizard:** Fully built into `perception/` and `app_service/`.
3. **Combat Loop & Danger Tracking:** Implemented as high-priority `Reflex` triggers.
4. **VLM Integration & Prompts:** Implemented in `perception/` and `llm/` wrappers.
5. **Sandbox Verification Loops:** Supported in `repair/repair_validator.py` and `repair/repair_benchmark_runner.py`.
6. **Task/Mission Graphs:** Graph-based sequential executing loops exist in `planning/mission_graph_v3.py`.

### 3. The 4 True Gaps
The only gaps separating Aurora from top-conference-level autonomous performance are:
1. **ExplorationAgent Intelligence:** A structured slow-loop explorer that proposes structured, safe actions when no known skills apply.
2. **Skill Applicability Gate:** A gate that evaluates context matching, success records, and risk to choose between fast-path execution or slow-path exploration.
3. **QuestStateTracker & GoalStack:** A long-horizon state tracker to maintain high-level mission goals, resolve prerequisites, and manage failure recovery.
4. **End-to-End Wiring:** Integrating these components cleanly into the main loop inside `AutonomousTaskBrain` (`agent/autonomous_task_brain.py`).

---

## B. Research Thesis: Verifier-First Visual Agent Runtime

The implementation of this plan will address a core scientific question suitable for top-tier AI/Robotics conferences (e.g., NeurIPS, ICLR, CoRL):

> **Core Research Question:** *Can a verifier-first visual agent runtime autonomously convert slow multimodal reasoning into reusable hierarchical skills, enabling long-horizon completion in complex 3D game environments without task-specific fine-tuning?*

```
                 [ User Goal: "Clear Quest" ]
                             │
                             ▼
                 [ QuestStateTracker / Stack ] ◄──┐ (Resets Goal Stack)
                             │                    │
                             ▼                    │ (Skill Promoted)
               [ Skill Applicability Gate ]       │
               /                         \        │
       (Skill Exists)                (No Skill)   │
             /                             \      │
            ▼                               ▼     │
   [ Fast-Path Execution ]        [ Slow-Path Exploration ]
   ┌─────────────────────┐        ┌───────────────────────┐
   │ Skill Runtime       │        │ ExplorationAgent (VLM)│
   │ Claim Verification  │        │ Human-in-Loop Probe   │
   └─────────────────────┘        └───────────┬───────────┘
                                              │ (Saves Successful Trace)
                                              ▼
                                   [ Skill Induction Gate ]
                                   │ Trace Segmenter
                                   │ Anchor Binder
                                   │ Verifier Compiler
                                   └──────────┬────────────┘
                                              │ (Sandbox Dry-Run Validated)
                                              ▼
                                   [ Skill Library Update ] ───┘
```

### Key Conference-Level Contributions
1. **Hierarchical Skill Induction:** Proving that slow VLM reasoning can be distilled into structured, cross-resolution symbolic skills.
2. **Claim-Gated Skill Promotion:** Enforcing that skills are promoted only when their execution is verified by explicit observations, preventing hallucinated success.
3. **Slow-to-Fast Transfer:** Demonstrating an order-of-magnitude reduction in execution latency and token costs by replacing repetitive VLM calls with compiled local skills.
4. **Embodied Long-Horizon Mission OS:** Combining a hierarchical goal stack with a visual quest tracker to maintain operational continuity over multi-hour runs.
5. **Verifier-First Self-Improvement Loop:** Showing that agent performance scales monotonically over time as its skill catalog expands through experience.

---

## C. Four-Phase Implementation Plan

All additions must be purely additive. New modules will be placed in existing directories (`agent/`, `planning/`), ensuring zero disruption to existing tests.

---

### Phase 1: Skill Applicability Gate

This phase builds the gatekeeper that determines whether to execute a fast skill or fall back to slow exploration.

#### 1. Path and Class Name
* `planning/applicability_gate.py` -> `class SkillApplicabilityGate`
* `planning/skill_capability_catalog.py` -> Extend `SkillCapabilityCatalog`

#### 2. Proposed Method Signatures & Logic
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from planning.screen_state_claim import ScreenStateClaim
from planning.skill_capability_catalog import SkillCatalogEntry, SkillCapabilityCatalog
from runtime.claim_runtime import ReliabilityStore, RISK_THRESHOLDS, RiskLevel

@dataclass(frozen=True, slots=True)
class ApplicabilityScore:
    skill_entry: SkillCatalogEntry
    score: float
    confidence: float
    risk_level: RiskLevel
    allowed: bool
    reason: str

class SkillApplicabilityGate:
    """Evaluates and ranks available skills for a given goal and screen state."""
    
    def __init__(self, catalog: SkillCapabilityCatalog, store: ReliabilityStore) -> None:
        self.catalog = catalog
        self.store = store

    def evaluate_skills(
        self,
        goal: str,
        state: ScreenStateClaim,
        risk_policy: RiskLevel = "medium"
    ) -> list[ApplicabilityScore]:
        """Filters, scores, and ranks skills based on current state and goal context.
        
        Algorithm:
        1. Query catalog for entries matching capabilities needed for 'goal'.
        2. Filter out skills whose 'capabilities_required' are not met by state.ui_elements.
        3. Query ReliabilityStore for historical reliability in current context.
        4. Compute multidimensional score:
           score = 0.4 * goal_match + 0.3 * reliability + 0.3 * anchor_coverage
        5. Check safety gate: If reliability < RISK_THRESHOLDS[risk_policy],
           allowed=False, requiring slow-path exploration or human confirmation.
        """
        pass
```

#### 3. Execution Integration
Add to `AutonomousTaskBrain._execute_node`:
```python
# Before raw execution, pass current node and claim to ApplicabilityGate
scores = self._applicability_gate.evaluate_skills(node.semantic_action, self._current_claim)
best_match = scores[0] if scores else None

if best_match and best_match.allowed:
    # Execute Fast-Path local Skill
    return self._execute_fast_skill(best_match.skill_entry)
else:
    # Trigger Slow-Path Exploration
    return self._trigger_slow_exploration(node)
```

#### 4. Verification Plan
* **Unit Test:** `tests/test_applicability_gate.py`
* **Assertion:** Mock a reliability score of `0.2` for a high-risk skill and assert that `allowed` is returned as `False`. Verify a score of `0.9` returns `allowed=True`.

---

### Phase 2: ExplorationAgent & Skill Induction

When the gate denies fast execution, this component triggers structured exploration and compiles successful trials into reusable skills.

#### 1. Path and Class Names
* `agent/exploration_agent.py` -> `class ExplorationAgent`
* `learning/skill_induction_gate.py` -> `class SkillInductionGate`

#### 2. Proposed Method Signatures & Logic
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np
from planning.screen_state_claim import ScreenStateClaim
from recording.semantic_distiller import SemanticSkillDraft

@dataclass(frozen=True, slots=True)
class ExplorationAction:
    action_type: str
    target: str
    rationale: str
    expected_claim: dict[str, Any]
    requires_human_approval: bool

class ExplorationAgent:
    """Handles slow-path multi-modal exploration using VLM and OCR inputs."""
    
    def __init__(self, perception: Any, risk_level: str = "medium") -> None:
        self._perception = perception
        self._risk_level = risk_level

    def explore_next_step(self, frame: np.ndarray, goal: str, state: ScreenStateClaim) -> ExplorationAction:
        """Invokes high-accuracy VLM reasoning to propose a safe exploratory action.
        
        Algorithm:
        1. Compile available UI interactive elements from 'state.actionable_elements()'.
        2. Construct a prompt presenting 'goal', current 'state.scene_description', and available buttons.
        3. Query VLM to select the most logical UI action.
        4. If risk_level is high/critical, flag 'requires_human_approval=True' to protect user environments.
        """
        pass

class SkillInductionGate:
    """Segment, distill, and compile successful exploration runs into reusable skills."""
    
    def __init__(self, distiller: Any, engine: Any) -> None:
        self._distiller = distiller  # Consumes SemanticSkillDistiller
        self._engine = engine        # Consumes EvolutionEngine

    def induce_skill_from_trace(
        self,
        session_events: list[Any],
        goal: str,
        screen_state: str
    ) -> SemanticSkillDraft | None:
        """Processes a successful sequence of exploration steps into a verified Skill.
        
        Algorithm:
        1. Filter session events down to successful mouse click inputs.
        2. Invoke SemanticSkillDistiller to bind coordinates to robust UIAnchors.
        3. Compile verifier contracts asserting that screen state transitions occur post-click.
        4. Submit draft to EvolutionEngine for pytest-driven sandbox verification.
        5. Upon sandbox success, promote skill draft to candidate status in the catalog.
        """
        pass
```

#### 3. Verification Plan
* **Unit Test:** `tests/test_exploration_and_induction.py`
* **Assertion:** Mock a successful VLM execution trace of 3 clicks, pass it to `SkillInductionGate.induce_skill_from_trace`, and verify it produces a valid `SemanticSkillDraft` containing exactly 3 semantic UI actions.

---

### Phase 3: QuestState Tracker & GoalStack

This phase implements the long-horizon state machine that breaks a main quest goal into manageable sub-goals.

#### 1. Path and Class Names
* `planning/quest_tracker.py` -> `class QuestStateTracker`
* `planning/goal_stack.py` -> `class GoalStack`

#### 2. Proposed Method Signatures & Logic
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from planning.screen_state_claim import ScreenStateClaim

@dataclass(frozen=True, slots=True)
class QuestState:
    active_quest_id: str
    objective_text: str
    tracked_target: str
    is_blocked: bool
    failure_count: int

class GoalStack:
    """Simple LIFO goal stack with duplicate and cycle prevention."""
    
    def __init__(self) -> None:
        self._stack: list[str] = []

    def push(self, goal: str) -> None:
        if goal in self._stack:
            self._stack.remove(goal)  # Move to top to avoid cycle lockups
        self._stack.append(goal)

    def pop(self) -> str | None:
        return self._stack.pop() if self._stack else None

    def peek(self) -> str | None:
        return self._stack[-1] if self._stack else None

    def clear(self) -> None:
        self._stack.clear()

class QuestStateTracker:
    """Fuses OCR and VLM data to track active quest line objectives."""
    
    def __init__(self) -> None:
        self._current_state = QuestState("unknown", "", "", False, 0)

    def update_state(self, claim: ScreenStateClaim) -> QuestState:
        """Parses screen claims to extract quest titles, directions, and sub-objectives.
        
        Algorithm:
        1. Scan claim.raw_ocr_texts for quest keyword indicators (e.g., "Quest", "目标", "追踪").
        2. Use regex-based parser or VLM fallback to extract objective text.
        3. Track UI indicators to see if the path is blocked (e.g., 'stuck' notifications or map prompt warnings).
        """
        pass
```

#### 3. Verification Plan
* **Unit Test:** `tests/test_quest_state_tracker.py`
* **Assertion:** Pass a mock `ScreenStateClaim` containing the raw OCR text `"Quest: Go to the beach"` and assert that the returned `QuestState.objective_text` is correctly parsed as `"Go to the beach"`.

---

### Phase 4: End-to-End Wiring & Thesis Demo

This phase wires the new components into the main execution loop in `AutonomousTaskBrain` and establishes a thesis-ready validation benchmark.

#### 1. Path and Class Name
* `agent/autonomous_task_brain.py` -> Modify `AutonomousTaskBrain.run`

#### 2. Wiring Logic Integration
```python
# Fully updated strategic execution loop within AutonomousTaskBrain.run:
def run(self, goal: str) -> TaskBrainResult:
    self._goal_stack.clear()
    self._goal_stack.push(goal)
    
    while not self._shutdown.is_set():
        frame = self._perception.capture_frame()
        if frame is None:
            continue
            
        # 1. Update Quest Tracker and fuse perceptions
        claim = self._sample_perception_claim(frame)
        quest_state = self._quest_tracker.update_state(claim)
        
        active_goal = self._goal_stack.peek()
        if not active_goal:
            return self._build_result(success=True)

        # 2. Check Applicability Gate
        scores = self._applicability_gate.evaluate_skills(active_goal, claim)
        best_skill = scores[0] if scores else None
        
        if best_skill and best_skill.allowed:
            # FAST PATH: Execute local verified skill
            success = self._execute_fast_skill(best_skill.skill_entry)
            if not success:
                # Demote skill on failure to prompt exploration/repair
                self._reliability_store.mark_version_drift(best_skill.skill_entry.skill_id)
        else:
            # SLOW PATH: Multi-modal exploration
            self._trace_recorder.start_session()
            action = self._exploration_agent.explore_next_step(frame, active_goal, claim)
            
            if action.requires_human_approval:
                action = self._prompt_human_approval(action)
                
            success = self._executor.execute_semantic(action.action_type, action.target)
            
            if success:
                # Distill successful exploration run into a reusable skill
                events = self._trace_recorder.end_session(success=True)
                induced_skill = self._skill_induction_gate.induce_skill_from_trace(
                    events, active_goal, claim.screen_state
                )
                if induced_skill:
                    # Dynamically register new skill into the catalog
                    self._catalog.register_induced_skill(induced_skill)
```

#### 3. Thesis Verification Suite
To support scientific publications, we will implement a benchmark suite:
* `benchmarks/thesis_suite.py` -> Runs comparative evaluations.
* **Baselines compared:**
  1. Pure VLM Direct Controller (zero reuse).
  2. Pure Scripted Macro (zero adaptability).
  3. Aurora Unified (Ours - with active gate and skill induction).
* **Thesis Demo Target:** Clear a multi-step game quest (Quest tracker, teleport navigation, dialog progression, battle engagement, and reward claiming) with less than 2 manual human interventions.

---

## D. Critical File Index

The new modules depend heavily on existing core files:

| New Component | Path | Key Dependency | Dependency Description |
|---|---|---|---|
| **SkillApplicabilityGate** | `planning/applicability_gate.py` | `runtime/claim_runtime.py` | Imports `ReliabilityStore` and `RISK_THRESHOLDS` to match and check safety bounds. |
| **SkillApplicabilityGate** | `planning/applicability_gate.py` | `planning/skill_capability_catalog.py` | Imports `SkillCapabilityCatalog` to query capabilities. |
| **ExplorationAgent** | `agent/exploration_agent.py` | `planning/screen_state_claim.py` | Uses `ScreenStateClaim` to extract available actionable buttons. |
| **SkillInductionGate** | `learning/skill_induction_gate.py` | `recording/semantic_distiller.py` | Leverages `SemanticSkillDistiller` for anchor binding. |
| **SkillInductionGate** | `learning/skill_induction_gate.py` | `learning/evolution_engine.py` | Submits drafted skills to `EvolutionEngine` for sandboxed pytest verification. |
| **QuestStateTracker** | `planning/quest_tracker.py` | `planning/screen_state_claim.py` | Fuses OCR output and VLM descriptions from `ScreenStateClaim`. |
| **AutonomousTaskBrain** | `agent/autonomous_task_brain.py` | `runtime/claim_runtime.py` | Coordinates execution validation with the `ClaimGraph`. |

---

## E. Acceptance Gate

To ensure rigorous quality control, the unified implementation must pass the following multi-stage verification pipeline:

```
[ Phase 1-3 Unit Tests ] ──► [ Pytest Testbed Replay ] ──► [ Quest Thesis Demo ]
      (100% Pass)                  (Zero Failures)             (AR < 2, SR > 90%)
```

### 1. Verification Milestone 1: Automated Unit Tests
* Run `pytest tests/test_applicability_gate.py` -> Must compile and return 100% success.
* Run `pytest tests/test_exploration_and_induction.py` -> Must verify that raw traces are successfully distilled into verified `SemanticSkillDrafts` using synthetic data.
* Run `pytest tests/test_quest_state_tracker.py` -> Must confirm OCR text is correctly mapped to quest objective structures.

### 2. Verification Milestone 2: Pytest Testbed Sandbox Replay
* Run `python scripts/run_testbed.py` using `ConsoleInputBackend` (dry-run).
* The dynamic task brain must successfully transition from the `menu` state to the `overworld` state, trigger exploration when no skill exists, compile a new skill draft, and run a fast reuse test without throwing an unhandled exception.

### 3. Verification Milestone 3: Quest Thesis Demo
* Target Quest: Clear the opening story progression sequence.
* **Success Criteria (Observable Bar):**
  * **Success Rate (SR):** $\ge 90\%$ quest completion rate across 10 sequential trial runs.
  * **Exploration vs. Reuse Speedup:** Trials 2-10 must execute at least **5x faster** (in seconds) and use **80% fewer LLM/VLM tokens** than Trial 1 by successfully reusing induced skills.
  * **Human Intervention Rate (AR):** Averaging $< 2.0$ human manual overrides per quest run.

---

## F. Explicitly Out of Scope

To guarantee timely delivery and target core scientific contributions, the following items are strictly out of scope:
1. **Bypassing Commercial Anti-Cheat Systems:** All developments must strictly adhere to the safety policy. Execution is confined entirely to self-hosted sandboxes, Godot/Unity testbeds, and local QA environments.
2. **End-to-End Reinforcement Learning (RL):** Training deep RL models for raw camera or mouse control is out of scope. High-frequency movement and camera adjustment remain strictly decoupled and handled by the local reflex servos (`control/`).
3. **General-Purpose Web/Desktop Automation:** This system is specialized for complex 3D virtual environments. Extending the perception model to generic web applications or desktop tools is excluded.
4. **Creating a New UI Framework:** Rebuilding the Tauri/FastAPI front-end dashboard is out of scope. The integration will utilize existing command-line reporters and telemetry channels.
