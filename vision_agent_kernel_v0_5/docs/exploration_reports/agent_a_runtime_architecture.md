# Agent A: 核心运行时架构探索报告

## Round 1 — 模块摸底

### 1. 文件清单

#### core/ (11 files, ~1050 lines)

| File | Lines | Description |
|------|-------|-------------|
| `core/__init__.py` | 0 | Empty init |
| `core/enums.py` | 1 | Single import |
| `core/events.py` | 36 | Interrupt, ModeRequest, KernelEvent |
| `core/timebase.py` | 35 | Timebase, perf_counter helpers |
| `core/types.py` | 165 | Observation, InputLease, ProgressState etc. |
| `core/state_bus.py` | 302 | StateBus: LatestSlot, RingBuffer, PriorityEventQueue |
| `core/mode_arbiter.py` | 122 | ModeArbiter: priority-based mode state machine |
| `core/watchdog.py` | 92 | Watchdog: heartbeat timeout monitoring |
| `core/proof_carrying_action.py` | 162 | ProofCarryingAction: verification-wrapped action |
| `core/local_secret_store.py` | 135 | DPAPI-backed secret storage |
| `core/runtime_health.py` | 0 | Empty placeholder |

#### execution/ (35 files, ~9170 lines)

| File | Lines | Description |
|------|-------|-------------|
| `execution/input_backend_base.py` | 109 | InputBackend Protocol |
| `execution/input_lease.py` | 95 | InputLeaseStore: validation, expiry, key tracking |
| `execution/input_worker.py` | 315 | InputWorker: background thread for lease/interrupt |
| `execution/execution_runtime.py` | 415 | ExecutionRuntime: contract-validated action execution |
| `execution/ui_flow_skill_adapter.py` | 955 | UIFlowSkillAdapter: semantic action bridge (190+ aliases) |
| `execution/closed_loop_runner.py` | 980 | ClosedLoopRunner: full observe-plan-execute-verify loop |
| `execution/daily_loop_executor.py` | 1372 | DailyLoopExecutor: commission/resin/expedition |
| `execution/safe_window_backend.py` | 902 | SafeWindowInputBackend: Win32 SendInput |
| `execution/directinput_backend.py` | 527 | DirectInputBackend |
| `execution/background_input_backend.py` | 480 | BackgroundInputBackend |
| `execution/visual_action_block.py` | 269 | VisualActionBlockExecutor |
| `execution/computer_use_controller.py` | 220 | ComputerUseController: VLM-grounded |
| `execution/crash_recovery.py` | 416 | CrashRecoveryOrchestrator |
| `execution/semantic_action.py` | 90 | SemanticAction, ActionContract |
| `execution/composed_verifier.py` | 205 | And/Or/Not/Vote Verifiers |
| `execution/declarative_verifier.py` | 263 | DeclarativeVerifierEngine |
| `execution/ui_action_executor.py` | 250 | UIAnchorActionExecutor |
| `execution/intent_bridge.py` | 199 | IntentBridge: camera/movement to InputLease |
| `execution/mouse_motor.py` | 122 | MousePathPolicy, CoordinateMapper |
| `execution/console_backend.py` | 172 | ConsoleInputBackend: dry-run |

#### control/ (18 files, ~2446 lines)

| File | Lines | Description |
|------|-------|-------------|
| `control/controller_protocol.py` | 142 | Controller Protocol, ControllerRouter |
| `control/controller_loop.py` | 91 | ControllerLoop: threaded obs-progress-recovery |
| `control/camera_model.py` | 76 | CameraModel: pixel-to-angular math |
| `control/camera_servo.py` | 252 | CameraServo: PID-like camera controller |
| `control/progress_supervisor.py` | 257 | ProgressSupervisor: EWMA + frustration |
| `control/recovery_policy.py` | 155 | RecoveryPolicy: tiered recovery |
| `control/obstacle_policy.py` | 55 | ObstaclePolicy: front-pressure sidestep |
| `control/navigation_runtime.py` | 127 | NavigationController, HeadingServo, StuckDetector |
| `control/sentinel/somatic_state.py` | 76 | SomaticState: embodied self-knowledge |
| `control/sentinel/somatic_state_supervisor.py` | 573 | SomaticStateSupervisor: stamina/HP/hazard |
| `control/sentinel/sentinel_runtime.py` | 151 | SentinelRuntime: anomaly detection |
| `control/sentinel/recipes.py` | 339 | 8 built-in recovery recipes |
| `control/sentinel/recovery_recipe.py` | 61 | RecoveryRecipe base protocol |

#### agent_kernel/ (22 files, ~6328 lines)

| File | Lines | Description |
|------|-------|-------------|
| `agent_kernel/types.py` | 467 | SemanticAction, PhysicalReceipt, TaskSpec |
| `agent_kernel/protocols.py` | 280 | 13 Protocol definitions |
| `agent_kernel/loop.py` | 779 | AgentLoop: L0-L9 neurological runtime |
| `agent_kernel/operator_agent.py` | 626 | OperatorAgent: NL-to-TaskSpec |
| `agent_kernel/adapters.py` | 551 | VLMPerceptionProvider, GenshinExecutionProvider |
| `agent_kernel/embodied_runtime.py` | 549 | EmbodiedAction, HybridOpenWorldNavigator |
| `agent_kernel/live_factory.py` | 441 | Live Genshin factory |
| `agent_kernel/minimal_closed_loop.py` | 367 | SparkleClosedLoopRunner |
| `agent_kernel/daily_commission_executor.py` | 314 | DailyCommissionExecutor |
| `agent_kernel/dialogue_controller.py` | 392 | DialogueController, OptionRegistry |
| `agent_kernel/claim_bridge.py` | 145 | KernelClaimBridge |
| `agent_kernel/cerebrum_agent.py` | 142 | CerebrumAgentImpl: task planning |
| `agent_kernel/cerebellum_controller.py` | 131 | CerebellumControllerImpl: route execution |
| `agent_kernel/brainstem_navigator.py` | 110 | BrainstemNavigatorImpl: heading servo |
| `agent_kernel/spinal_reflex_agent.py` | 131 | SpinalReflexAgentImpl: reflexive combat |
| `agent_kernel/skill_lookup.py` | 160 | KernelSkillRecipeLookup |
| `agent_kernel/input_lease_manager.py` | 138 | InputLeaseManagerImpl: L0 lease lifecycle |
| `agent_kernel/abyss_chamber_executor.py` | 150 | AbyssChamberExecutor |
| `agent_kernel/unknown_scene_handler.py` | 223 | UnknownSceneHandler |

### 2. 核心类与接口

#### StateBus (core/state_bus.py:155)

Slots:
- `latest_observation` (LatestSlot[Observation])
- `observation_ring` (RingBuffer[Observation], capacity=300)
- `progress_ring` (RingBuffer[ProgressState], capacity=300)
- `event_queue` (PriorityEventQueue[Interrupt], capacity=1024)
- `mode_request_queue` (PriorityEventQueue[ModeRequest], capacity=128)
- `runtime_health`, `current_goal`, `current_mode`
- `screen_claim`, `affordances`, `frame_quality`
- `navigation_signal`, `combat_signal`
- `mission_graph`, `claim_graph_state`, `checkpoint_state`
- `navigation_plan`, `runtime_overrides`
- Dynamic slot registry + Pub/Sub

#### ModeArbiter (core/mode_arbiter.py:59)

12 modes: IDLE, CALIBRATING, RUNNING_ACTION_BLOCK, ACQUIRING_TARGET, TRACKING_TARGET, APPROACHING_TARGET, EXECUTING_VISUAL_ACTION, RECOVERING, PAUSED, COMPLETE, FAILED, EMERGENCY_STOPPED

Terminal: COMPLETE, FAILED, EMERGENCY_STOPPED (only EMERGENCY_STOPPED can preempt EMERGENCY_STOPPED)

Priority preemption: lower number = higher priority. Same priority = FIFO.

#### InputWorker/InputLease Lifecycle

1. SemanticAction created -> ActionContract validated
2. ExecutionRuntime._build_lease() converts to InputLease
3. InputWorker.submit_lease(lease) -> _apply_lease(): validate, execute physical input, register in store
4. Deadman check auto-expires leases past expires_at
5. Focus loss triggers release_all + FOCUS_LOST interrupt

#### AgentLoop (agent_kernel/loop.py:46)

L0-L9 neurological runtime. Wires: PerceptionProvider, CerebrumPlanner, ExecutionProvider, SuccessChecker, CompanionAgent.

### 3. 模块依赖图

```
core/ (foundation)
  ├── execution/ (input pipeline, backends)
  ├── control/ (camera servo, progress, sentinel)
  └── agent_kernel/ (neurological runtime, adapters)
```

- core/ has no cross-plane imports (pure foundation)
- execution/ <- core/ (events, state_bus, types)
- control/ <- core/ + execution/ (physical_receipt, semantic_action)
- agent_kernel/ <- core/ + execution/ + control/

### 4. Recovery Recipes (8 types)

UILostRecovery, StuckRecovery, TargetLostRecovery, LoadingTimeoutRecovery, CombatDefeatRecovery, LowHealthRecovery, DriftRecovery, ModelProviderFailureRecovery
