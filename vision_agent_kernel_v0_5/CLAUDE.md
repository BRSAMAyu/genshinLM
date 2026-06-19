# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

**Sparkle Project** — 端侧视觉交互 Agent 内核 (Vision Agent Kernel v0.5)。面向 ACG 玩家的桌面端赛博伴游与具身智能控制中枢的内核 MVP。仅限授权 3D 沙盒 / 自建 ARPG 测试环境 / QA 单机研究环境。

完整产品愿景与架构哲学见 `PROJECT_ALIGNMENT.md`，该文件是本项目的"宪法"，所有代码决策必须符合其原则。

## Commands

```bash
# Install
pip install -e ".[dev]"          # core + dev tools
pip install -e ".[testbed]"      # + pygame testbed

# Test
pytest                           # all tests (4323 collected)
pytest tests/test_state_bus.py   # single file
pytest -x                        # stop on first failure
pytest -k "test_pattern"         # by keyword

# Lint / Type
ruff check .
mypy core/ perception/ control/ execution/ orchestration/

# Run demos (all default to dry-run / console backend)
python scripts/run_kernel.py
python scripts/run_final_demo.py
python scripts/run_testbed.py
```

## Architecture: The 5-Plane Model

All cross-plane communication goes exclusively through **StateBus** (thread-safe) or event queues. Direct cross-plane calls are forbidden.

```
Perception (high-freq)  →  Observation  →  StateBus
Control (mid-freq)      ←  TargetTrack/Progress/Frustration  →  Interrupts
Execution (strict seq)  ←  InputLease/DeadmanSwitch  →  InputWorker
Orchestration (event)   ←  SkillResult/TaskGraph  →  ModeTransitions
Telemetry (async)       ←  JSONL + video recording (bounded queue)
```

**StateBus** (`core/state_bus.py`): Central hub with `LatestSlot[T]`, `RingBuffer[T]`, `PriorityEventQueue[T]`. Holds `latest_observation`, `observation_ring` (300 frames), `event_queue` (priority interrupts), `mode_request_queue`, `heartbeat_table`, `shutdown_flag`.

**Interrupt priorities** (lower = higher urgency):
- P0 (0): Emergency stop, focus loss — requires input release
- P1 (10): Watchdog timeout
- P2 (20): Human override
- P3 (30): Action block exclusive
- P4 (40): Recovery
- P5 (50): Tracking
- P6 (100): Idle

**Mode state machine** (`core/mode_arbiter.py`): Priority-based preemption with terminal mode protection. `EMERGENCY_STOPPED` can only transition to itself.

## Key Design Rules

1. **No blocking waits** — Use chunked waits (~50ms loops) checking StateBus interrupts. Never `time.sleep()` for long durations.
2. **No single-frame decisions** — Progress/frustration uses EWMA + time-window slopes, never `current_frame vs previous_frame`.
3. **Monotonic clock only** — `time.perf_counter()` everywhere. `time.time()` is banned for logic.
4. **LLM stays strategic** — LLM decides *which skill to use*, never *how many pixels to move*.
5. **Every action has a fallback** — Default assumption is failure. Drive state forward via visual feedback (Visual Checkpoint), not timers.

## Safety Model

- Default mode is **dry-run** (`ConsoleInputBackend` — prints actions, never touches OS input).
- `SafeWindowInputBackend` must be explicitly selected; verifies target window focus before input.
- All physical input flows through `InputLease` → `InputWorker`. Controllers never call OS input APIs directly.
- **Deadman switch**: lease expiry, thread death, or focus loss triggers immediate `release_all`.
- Emergency stops: F9 key, Ctrl+C/SIGTERM, watchdog timeout — all call `release_all`.
- See `SAFETY.md` for the full safety policy.

## Execution Contract (Phase 2+)

The execution pipeline is claim-gated: every action must pass through verification before the state advances.

```
SemanticAction
    ↓ ActionContractValidator
ActionContract (validated)
    ↓ InputWorker.submit_lease()
PhysicalReceipt (PENDING → SUBMITTED → LEASE_ACCEPTED → FOCUS_OK → EXECUTED)
    ↓ post-action ScreenStateClaimBuilder
VerifierResult (VERIFIED or FAILED)
```

- `ExecutionRuntime` (`execution/execution_runtime.py`) orchestrates this pipeline.
- `PhysicalReceipt` tracks the full lifecycle of each action with timestamps at every stage.
- Verifiers are composable: `ComposedVerifier` chains UI, visual, observation, and collection verifiers.
- `ScreenStateClaim` (`planning/screen_state_claim.py`) is the unit of verified world state — claims carry uncertainty, audit status, and cascade policies.

## Capsule System

Game-specific logic lives in **capsules** (`capsules/`) — self-contained modules that plug into the kernel without polluting core. Each capsule declares a `capsule.yaml` manifest.

- **Capsule Protocol** (`capsules/capsule_protocol.py`): `Capsule.install()` / `activate()` / `deactivate()` lifecycle.
- **CapsuleManifest**: Declares skills, frame processors, StateBus slots, verifiers, keymaps, resources, transitions.
- Existing capsules: `genshin`, `hsr` (Honkai: Star Rail), `demo_arpg`, `desktop_ui`.
- `CapsuleRegistry` loads manifests and manages capsule lifecycle.
- **Domain Protocols** (`capsules/domain_protocols.py`): Game-agnostic interfaces — `ScreenClassifierProtocol`, `CombatPlannerProtocol`, `NavigatorProtocol`, `DialogHandlerProtocol`, `KnowledgeProviderProtocol`.

## AgentLoop (L0-L9 Neurological Runtime)

`agent_kernel/loop.py` implements a multi-layer control loop inspired by neuroscience:

```
L0 (100Hz): Reflex — dodge, emergency stop
L1 (30Hz):  Sensorimotor — tracking, camera servo
L2 (10Hz):  Perception — observation, state classification
L3 (3Hz):   Tactical — combat rotation, navigation correction
L4 (1Hz):   Task — skill execution, dialog handling
L5 (0.3Hz): Mission — quest progress, mission graph advancement
L6 (0.1Hz): Strategy — plan revision, BAGEL attribution
L7 (event): Recovery — crash recovery, sentinel healing
L8 (event): Learning — skill induction, knowledge update
L9 (event): Meta — belief revision, mechanism discovery
```

Each tick: `Observe → Dialogue → Plan → Contract → Safety → Execute → Verify → Learn`. `max_plan_iterations=100`.

**Live Factory** (`agent_kernel/live_factory.py`): Production factory that wires all components — creates AgentLoop with DxcamCapture, ZhipuVLM, SafeWindowBackend, BAGEL FIG, BeliefProposer, MetaLearningBridge, ParameterizedSkillInductor, and UnknownSceneHandler. All wired together at construction time.

## Mainline Execution Loop

`MainlineRunner` (`planning/mainline/mainline_runner.py`) is the continuous mission execution engine. It runs `MissionGraphV4` — a claim-gated node graph where each node must satisfy:

```
input claim verified → execute → post-action resample → output claim verified → checkpoint
```

Failure never produces silent dry-run success — it enters BAGEL attribution + recovery. The runner cycles through phases: `observe → update_context → select_graph → commit_beliefs → execute → verify → attribute_recover → checkpoint → condense`.

- `MainlineLiveBridge` (`planning/mainline/mainline_live_bridge.py`) wires the runner to real gameplay.
- `MainlineSkillExecutor` binds capsule skills to mission node execution.
- `ActiveQuestContext` tracks the current quest state across nodes.

## Bagel Belief System

`bagel/` implements a belief attribution and failure recovery framework. When a mission node fails, BAGEL determines *why* through evidence-gathered belief nodes, then proposes a recovery path rather than blindly retrying.

- `FigSchema`: `BeliefIdentity` / `BeliefNode` — structured belief representation (10 lifecycle states, 5 node types, 9 edge types).
- `BagelRuntime`: Manages belief lifecycle, attribution, and revision.
- `EvidenceMatrix`: Tracks evidence quality and coverage for belief validation.
- `Arbiter`: Resolves conflicting beliefs and decides on recovery strategy.
- `BeliefProposer` (`bagel/belief_proposer.py`): Generates alternative hypotheses after belief falsification. Analyzes failure modes, queries DecisionMemory for related strategies, commits new beliefs to FIG.

## Cognitive Closed Loop (Exploration → Belief → Skill → Learning)

The system implements a full autonomous learning cycle:

```
UnknownSceneHandler.probe()           # Explore unknown scene
  → MetaLearningBridge.on_exploration_result()   # Feed result to learning
    → DecisionMemory.record()         # Store experience
    → _check_skill_induction_candidates()  # Detect 3+ failure patterns
      → ParameterizedSkillInductor.induce_from_patterns()  # Generate skill
        → SkillTemplate with parameters/loops/conditions

BAGEL falsification cycle:
  → BeliefProposer.propose()          # Generate alternative hypotheses
    → New belief committed to FIG      # Feed back to decision making
```

Key files:
- `learning/meta_learning_bridge.py` — Orchestrates the full attribution→learning pipeline
- `learning/parameterized_skill_induction.py` — Extracts variable parts from traces into parameterized SkillTemplates
- `learning/game_knowledge_store.py` — SQLite knowledge base with source priority (manual>wiki>vlm>exploration), trust tracking, conflict logging, exponential decay forgetting (`conf × exp(-age×ln2/half_life) × access_reinforcement`), and `prune_decayed()` auto-cleanup
- `learning/generic_failure_analyzer.py` — Game-agnostic failure categorization (TARGET_LOST, COMBAT_TIMEOUT, HP_DEPLETED, etc.)
- `agent_kernel/unknown_scene_handler.py` — SPARKLE §11 safe exploration: Observe→Hypothesize→Probe→Verify→Attribute→Learn→Escalate

## Sentinel (Control Plane)

`control/sentinel/` provides somatic monitoring — the "body awareness" layer.

- `SomaticState`: Represents the agent's physical situation (health, stamina, position, danger).
- `SentinelRuntime`: Monitors somatic state against thresholds, emits interrupts when conditions degrade.
- `SomaticStateSupervisor`: EWMA-based state tracking with recovery recipes. Accepts external StateBus + InputWorker to avoid bypassing the main pipeline.
- `RecoveryRecipe`: Declarative recovery strategies (reposition, heal, retreat, etc.) with `_verify_screen_stable()` visual verification.

## Combat Subsystem

`combat/` is a deep tactical layer with game-specific implementations.

- **Playbook System**: `PlaybookSchema` (graph-validated combat logic) + `PlaybookRuntime` (execution). Playbooks define rotation, priority, and fallback chains.
- **Genshin-specific**: `GenshinCombatPlanner`, `GenshinPlaybookExecutor`, elemental reactions (`GenshinElementReactions`), cooldown/energy management, character switching, dodge reflexes.
- **HSR-specific**: `HsrCombatPlanner`, `HsrPlaybookExecutor`, weakness/break system.
- **Boss Mechanics**: `BossCombatRuntime`, `BossTracker`, `BossEnrageManager`, `BossMechanicRouter` — per-boss phase tracking and mechanic handlers.
- **Reflex Evasion** (`combat/reflex_evasion.py`): Danger detection → P1 `DODGE_REFLEX` interrupt → dodge → cooldown → reacquire.

## Navigation Subsystem

`navigation/` handles in-game navigation across different games.

- `UniversalNavigator` (`navigation/universal_navigator.py`): Game-agnostic facade that delegates to capsule-specific navigators via adapter pattern. Falls back to `NullNavigator` when no capsule is loaded.
- `MapNavigationRuntime`: High-level map → waypoint → arrival pipeline.
- `QuestMarkerFollower`: Vision-guided quest marker tracking.
- Game-specific: `GenshinNavigator`, `HsrNavigator`, plus handlers for climbing stamina, chess puzzles, etc.

## Application Services (`app_service/`)

Higher-level services supporting the universal game agent vision:

- `UniversalEntryAgent` — Natural language intent → executable mission graph. Parses goals (daily, combat, explore, quest, etc.) in English/Chinese.
- `WebSearchService` — Pluggable web search with auto-detect: MiniMax MCP → SerpAPI → Stub fallback.
- `CapsuleForge` — Auto-generates capsule skeletons (capsule.yaml, keymap.yaml, skills/index.json, screen classifier, combat detector, provider) from game descriptions. LLM-driven code generation for 6 output files.
- `CodingAgent` — LLM-powered skill code generation + `CodeSandboxExecutor` validation (import whitelist, restricted builtins, timeout protection).

## Runtime Infrastructure (`runtime/`)

- `HotReloadManager` (`runtime/hot_reload_manager.py`): Runtime module replacement for perception post-processors, capsule providers, and skills without restart. Thread-safe file watching with rollback support.
- `ClaimRuntime` (`runtime/claim_runtime.py`): Core claim verification with RiskLevel, ClaimStatus, and UncertaintyAction types.
- `ContentVersioning` (`runtime/content_versioning.py`): Detects game version changes (UI/mechanic/content/system) and tracks compatibility state (green/yellow/red).

## Perception

- `AutoCalibratorV2` (`perception/auto_calibrator_v2.py`): VLM-driven UI landmark discovery for any game (not hardcoded to Genshin).
- `GenericScreenClassifier` (`perception/generic_screen_classifier.py`): VLM-based screen state classification with game-agnostic taxonomy (overworld, combat, dialog, menu, map, etc.).
- Core pipeline: `ScreenCapture → FramePacket → YOLO Detector → TargetCandidate[] → BoT-SORT Tracker → TargetTrack → VisualTriggerDetector → Observation → StateBus`

## Core Data Flow

```
TargetTrack → CameraServo (FOV-aware pixel→yaw/pitch) → CameraIntent
            → ProgressSupervisor → ProgressState (frustration, slope, oscillation)
            → RecoveryPolicy / ObstaclePolicy → MovementIntent or Interrupt
```

## Config

YAML configs in `configs/`: `default.yaml`, `control.yaml`, `perception.yaml`, `input.yaml`, `telemetry.yaml`, `testbed.yaml`, `model.yaml`. Action block definitions in `action_blocks/`. Task specs loaded from YAML via `orchestration/task_spec.py`. Capsule manifests in `capsules/<game>/capsule.yaml`.

## Type System

- All core types use `@dataclass(slots=True)` in `core/types.py` — `Observation`, `TargetTrack`, `TargetCandidate`, `ObstacleField`, `CameraIntent`, `MovementIntent`, `InputLease`, `ProgressState`, `SkillResult`.
- Events: `Interrupt(priority, code, source, ...)` and `ModeRequest` in `core/events.py`.
- Protocols (not ABCs) for pluggable components: `Detector`, `Tracker`, `ScreenCapturer`, `ObstacleEstimator` in their respective `*_base.py` files.

## Python Style

- Python 3.11+, `from __future__ import annotations` in all files.
- `slots=True` on all dataclasses.
- Ruff: line-length 100, target py311, rules E/F/I/B/UP/ANN (ignore ANN101/ANN102).
- MyPy: strict mode, `disallow_untyped_defs = true`.
- Pytest: `testpaths = ["tests"]`, `pythonpath = ["."]`.
