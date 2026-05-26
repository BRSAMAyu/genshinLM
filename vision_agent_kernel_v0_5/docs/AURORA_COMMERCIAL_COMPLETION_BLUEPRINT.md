# Aurora 商业完成度蓝图 (Coding Agent 执行版)

> **文档性质**: 可直接交给 Coding Agent 执行的工程蓝图。所有文件路径、类名、方法签名均基于代码审计确认。
> **代码基线**: branch `codex/pre-realworld-closure`, commit `7324883`, 458 个 Python 文件, 57K 行, 995 个测试全部通过。
> **最后更新**: 2026-05-26

---

## A. 代码现状全景

### A.1 数字概览

| 指标 | 数值 |
|------|------|
| Python 文件数 | 458 |
| Python 总行数 | ~57,000 |
| 测试文件数 | 79 |
| 测试用例数 | 995 (全部通过) |
| Capsule 包数 | 4 (genshin, hsr, desktop_ui, demo_arpg) |
| REST API 端点数 | ~40 |
| WebSocket 通道 | 1 (`/ws/state`) |
| 桌面应用页面数 | 10 (React/Tauri, 单文件 1057 行) |
| 配置文件数 | 14+ |
| ROI 校准 Profile | 8 (覆盖 1080p/4K, Genshin/HSR) |
| 角色/团队 Profile | Genshin: 80+ 角色 + 22 队伍; HSR: 60+ 角色 + 20 队伍 |
| 世界图 | Genshin: 3415 行, 7 区域, 230+ waypoint, 420+ edge |

### A.2 模块实现状态矩阵

图例: **[DONE]** 完整实现 | **[PARTIAL]** 有代码但不完整 | **[STUB]** 空文件或只有 import | **[MISSING]** 不存在

#### Core (`core/`) — 10 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `core/state_bus.py` | `StateBus`, `LatestSlot[T]`, `RingBuffer[T]`, `PriorityEventQueue[T]`, `RuntimeHealth` | **[DONE]** 284 行 |
| `core/types.py` | `Observation`, `TargetTrack`, `TargetCandidate`, `ObstacleField`, `CameraIntent`, `MovementIntent`, `InputLease`, `ProgressState`, `SkillResult` | **[DONE]** 160 行 |
| `core/events.py` | `Interrupt`, `ModeRequest`, `KernelEvent` | **[DONE]** |
| `core/mode_arbiter.py` | `ModeArbiter` (P0-P6 优先级抢占, 终态保护) | **[DONE]** |
| `core/watchdog.py` | `Watchdog` (心跳超时 → P0 中断) | **[DONE]** |
| `core/proof_carrying_action.py` | `ProofCarryingAction`, `ActionIntent`, `ExpectedStateDelta`, `VerifierContract` | **[DONE]** 163 行 |
| `core/timebase.py` | `Timebase`, `perf_counter_seconds/ms()` | **[DONE]** |
| `core/enums.py` | — | **[STUB]** |
| `core/runtime_health.py` | — | **[STUB]** |

#### Perception (`perception/`) — 29 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `perception/dxcam_capture.py` | `DxcamCapturer` (多线程 DXcam 截屏) | **[DONE]** |
| `perception/yolo_detector.py` | `YoloDetector` (Ultralytics YOLO, detect/track/safe_detect) | **[DONE]** 161 行 |
| `perception/ultralytics_tracker.py` | `UltralyticsTracker` (BoT-SORT, coasting/lost 状态) | **[DONE]** 294 行 |
| `perception/target_selector.py` | `TargetSelector` (多标准评分: 置信度/中心距离/类别) | **[DONE]** |
| `perception/visual_trigger_detector.py` | `VisualTriggerDetector`, `ColorTargetTracker` (颜色触发, 连通组件) | **[DONE]** 361 行 |
| `perception/pipeline.py` | `PerceptionPipeline` (线程化 capture loop + 后处理器) | **[DONE]** 175 行 |
| `perception/viewport.py` | `ViewportTransformer` (坐标归一化, 窗口映射) | **[DONE]** |
| `perception/depth_base.py` | `HeuristicObstacleEstimator` (扇区障碍压力) | **[DONE]** |
| `perception/observation_graph.py` | `ObservationGraph`, `ObservationBuilder` (14 种观察节点) | **[DONE]** 258 行 |
| `perception/frame_source.py` | `DemoFrameSource`, `Win32WindowCapturer`, `FrameSourceFactory` | **[DONE]** |
| `perception/genshin_screen_classifier.py` | `GenshinScreenClassifier` (HSV 屏幕状态分类) | **[DONE]** |
| `perception/hsr_screen_classifier.py` | HSR 屏幕分类 | **[PARTIAL]** |
| `perception/region_aware_detector.py` | `RegionAwareDetector` (7 区域色调检测) | **[DONE]** |
| `perception/ocr_engine.py` | OCR 引擎 | **[PARTIAL]** |
| `perception/ocr_router.py` | OCR 路由 | **[PARTIAL]** |
| `perception/glm_ocr_provider.py` | GLM OCR provider | **[PARTIAL]** |
| `perception/vlm_post_processor.py` | VLM 后处理 | **[PARTIAL]** |
| `perception/mss_capture.py` | — | **[STUB]** |
| `perception/depth_anything_estimator.py` | — | **[STUB]** |
| `perception/ui_detector.py` | — | **[STUB]** |

#### Control (`control/`) — 11 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `control/camera_servo.py` | `CameraServo` (P-controller, dead zone, 平滑, 加速度补偿) | **[DONE]** 253 行 |
| `control/progress_supervisor.py` | `ProgressSupervisor` (EWMA + slope + oscillation + frustration) | **[DONE]** 258 行 |
| `control/obstacle_policy.py` | `ObstaclePolicy` (扇区避障) | **[DONE]** |
| `control/recovery_policy.py` | `RecoveryPolicy` (MICRO_RECOVERY/LOCAL_REROUTE/ESCALATE) | **[DONE]** |
| `control/controller_loop.py` | `ControllerLoop` (线程化 loop 集成 progress/recovery/servo) | **[DONE]** |
| `control/navigation_runtime.py` | `HeadingServo`, `StuckDetector`, `NavigationController` | **[DONE]** |
| `control/camera_model.py` | `pixel_to_yaw_pitch_error_deg()`, FOV 转换 | **[DONE]** 77 行 |
| `control/movement_controller.py` | — | **[STUB]** |

#### Execution (`execution/`) — 24 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `execution/input_lease.py` | `InputLeaseStore` (线程安全, 验证, 过期, key tracking) | **[DONE]** 96 行 |
| `execution/input_worker.py` | `InputWorker` (后台线程, lease 处理, deadman, focus check) | **[DONE]** 226 行 |
| `execution/human_override.py` | `HumanOverride` (紧急停止 P0, 暂停 P1) | **[DONE]** |
| `execution/visual_action_block.py` | `VisualActionBlockExecutor` (视觉触发条件动作执行) | **[DONE]** 256 行 |
| `execution/semantic_action.py` | 语义动作 | **[PARTIAL]** |
| `execution/safe_window_backend.py` | 安全窗口后端 | **[PARTIAL]** |
| `execution/declarative_verifier.py` | 声明式验证 | **[PARTIAL]** |
| `execution/ui_action_executor.py` | UI 动作执行器 | **[PARTIAL]** |
| `execution/physical_receipt.py` | 物理操作回执 | **[PARTIAL]** |
| `execution/mouse_motor.py` | 鼠标马达 | **[PARTIAL]** |
| `execution/real_input_backend.py` | — | **[STUB]** |

#### Runtime/Claims (`runtime/`) — 12 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `runtime/claim_runtime.py` | `StateDeltaClaim`, `ObservationClaim`, `ClaimGraph`, `ClaimProducingExecutor`, `EpisodeAnalyzer`, `ReliabilityStore`, `DriftDetector`, `UncertaintyPolicy`, 22+ 类型 | **[DONE]** 1093 行 |
| `runtime/claim_adjudicator.py` | `ClaimAdjudicator` (evidence voting, noisy-or, family correlation discount), 8 `CORE_RECIPES` | **[DONE]** 363 行 |
| `runtime/claim_worker.py` | `ClaimGraphWorker` (单线程 writer, 命令模式) | **[DONE]** 218 行 |
| `runtime/audit_scheduler.py` | `DelayedAuditScheduler` (JSONL 持久化, 3 种触发类型) | **[DONE]** 292 行 |
| `runtime/verifier_compiler.py` | `VerifierCompiler`, `VerifierBundle`, 8 `CORE_BUNDLES` | **[DONE]** 195 行 |
| `runtime/mission_graph.py` | `MissionGraph` (DAG, BFS 路径, 备选路径, 环检测) | **[DONE]** 261 行 |
| `runtime/claim_schema.py` | `SkillClaimDeclaration`, `ProducedClaimDecl`, `InputClaimDecl` | **[DONE]** 79 行 |
| `runtime/claim_events.py` | `ClaimEvent`, `ClaimGraphState`, `ClaimEventPublisher` | **[DONE]** 89 行 |

#### Orchestration (`orchestration/`) — 8 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `orchestration/orchestrator.py` | `Orchestrator` (线程化 loop, skill dispatch, evidence guard) | **[DONE]** 186 行 |
| `orchestration/graph.py` | `OrchestrationGraph` (10 态 FSM) | **[DONE]** 117 行 |
| `orchestration/skills.py` | 7 个内置 Skill (LoadTask, EnterTarget, AcquireTarget, Track, Execute, Verify, Recover) | **[DONE]** 154 行 |
| `orchestration/task_spec.py` | `TaskSpec`, `load_task_spec()` | **[DONE]** |
| `orchestration/failure_policy.py` | `FailurePolicy` | **[DONE]** |
| `orchestration/interrupt_handler.py` | — | **[STUB]** |

#### Agent (`agent/`) — 2 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `agent/autonomous_task_brain.py` | `AutonomousTaskBrain` (感知-规划-执行-验证主循环, 7 步迭代) | **[DONE]** 453 行 |
| `agent/zero_shot_agent.py` | 零样本 agent | **[PARTIAL]** |

#### Planning (`planning/`) — 16 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `planning/hierarchical_planner.py` | `HierarchicalPlanner` (GLM-5.1 LLM 规划, JSON 解析, fallback) | **[DONE]** 227 行 |
| `planning/mission_graph_v3.py` | `MissionGraph`, `MissionNode` (7 种节点类型), `MissionGraphBuilder` | **[DONE]** 232 行 |
| `planning/screen_state_claim.py` | `ScreenStateClaim` (14 种屏幕状态), `ActionAffordance` | **[DONE]** 106 行 |
| `planning/action_affordance.py` | `AffordanceDeriver` (14 屏幕状态 → 可用动作推导) | **[DONE]** 239 行 |
| `planning/mission_runner.py` | Mission runner | **[PARTIAL]** |
| `planning/capability_planner.py` | 能力规划器 | **[PARTIAL]** |
| `planning/plan_validator.py` | 计划验证器 | **[PARTIAL]** |

#### LLM (`llm/`) — 15 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `llm/glm_provider.py` | `GLMProvider` (GLM-5.1, 安全防护) | **[DONE]** |
| `llm/zhipu_vlm_provider.py` | `ZhipuVLMProvider` (GLM-4V, describe_image/ground_ui/classify_screen/explain_failure) | **[DONE]** 174 行 |
| `llm/minimax_provider.py` | `MiniMaxProvider` (MiniMax-M2.7) | **[DONE]** |
| `llm/http_provider.py` | `ChatHTTPClient` (通用 HTTP, JSON 解析, retry) | **[DONE]** |
| `llm/planner.py` | `Planner` (多 provider, guard, fallback) | **[DONE]** |
| `llm/vision_provider.py` | `ImageInput`, `VisionResult`, `UIGroundingResult` | **[PARTIAL]** |
| `llm/local_vlm_provider.py` | 本地 VLM | **[PARTIAL]** |
| `llm/model_router.py` | 模型路由 | **[PARTIAL]** |

#### App Service (`app_service/`) — 22 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `app_service/agent_controller.py` | `AgentController` (735 行, 25+ 子系统, 线程安全) | **[DONE]** |
| `app_service/api.py` | ~40 REST 端点 (生命周期/校准/模型/Skill/Persona/规划/战斗/Product) | **[DONE]** 345 行 |
| `app_service/ws.py` | `/ws/state` WebSocket (200ms 推送) | **[DONE]** 25 行 |
| `app_service/main.py` | FastAPI app 创建, CORS 配置 | **[DONE]** |

#### Reliability (`reliability/`) — 3 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `reliability/reliability_store.py` | `ThreeLayerReliabilityStore` (verifier/recipe/skill-claim 三层, Wilson lower bound, JSONL 持久化) | **[DONE]** 661 行 |
| `reliability/drift_detector.py` | 漂移检测 | **[PARTIAL]** |

#### Combat (`combat/`) — 27 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `combat/boss_combat_runtime.py` | `BossCombatRuntime` (10 态 FSM, reflex/survival/checkpoint/evidence) | **[DONE]** 255 行 |
| `combat/survival_runtime.py` | `SurvivalPolicyEngine` (优先级决策树: dodge/shield/heal/retreat/food/abort) | **[DONE]** 112 行 |
| `combat/playbook_schema.py` | CombatPlaybook 图结构 | **[DONE]** |
| Genshin combat | 技能加载器, 元素反应, 冷却管理, combat planner, playbook executor | **[DONE]** |
| HSR combat | 弱点表, 回合制 combat planner, SP 预算, 终极技中断 | **[DONE]** |

#### Learning/Repair (`learning/`, `repair/`) — 18 文件

| 文件 | 类/函数 | 状态 |
|------|---------|------|
| `learning/failure_signature.py` | 失败签名 | **[PARTIAL]** |
| `learning/decision_memory.py` | 决策记忆 | **[PARTIAL]** |
| `learning/evolution_engine.py` | 进化引擎 | **[PARTIAL]** |
| `repair/skill_patch_builder.py` | Skill 补丁构建 | **[PARTIAL]** |
| `repair/repair_session.py` | 修复会话 | **[PARTIAL]** |

#### Desktop UI (`desktop/`) — Tauri v2 + React

| 文件 | 内容 | 状态 |
|------|------|------|
| `desktop/src/main.tsx` | 10 页面 SPA: Dashboard, RunMonitor, Reports, Settings, CalibrationWizard, SkillLibrary, TaskPlanner, CompanionOverlay, CombatPanel, ProductChecklist | **[DONE]** 1057 行 |
| `desktop/src/styles/tokens.css` | Pixel art 设计系统 (冷色调, aurora green accent, 4px grid) | **[DONE]** |
| `desktop/src/styles/components.css` | 完整组件库 (shell, sidebar, card, btn, combat-node, danger-meter, toast, dialog, wizard...) | **[DONE]** |
| `desktop/src/i18n/zh.ts` + `en.ts` | 90+ UI 字符串国际化 | **[DONE]** |
| `desktop/src-tauri/` | Tauri 2.x 配置, 1280x820 窗口, minimal Rust entry | **[DONE]** |

---

## B. Gap Analysis: 代码缺口 vs 商业需求

### B.1 Critical Path Gaps (阻塞商业发布)

| # | 缺口 | 现状 | 影响 | 涉及文件 |
|---|------|------|------|----------|
| G1 | **Claim 主链路未贯通到真实执行** | `AutonomousTaskBrain` 有完整循环但只在 dry-run 框架内; `AgentController._run_real_loop` 未接入 ClaimGraphWorker | 用户无法看到 claim chain 证据 | `app_service/agent_controller.py`, `runtime/claim_runtime.py` |
| G2 | **真实屏幕输入后端为空** | `execution/real_input_backend.py` 是空文件; `execution/mouse_motor.py` 有代码但未连接 SafeWindow | 无法在真实窗口执行物理操作 | `execution/real_input_backend.py`, `execution/mouse_motor.py`, `execution/safe_window_backend.py` |
| G3 | **UI 检测器为空** | `perception/ui_detector.py` 是空文件; UI 元素检测完全依赖 VLM fallback 或手工 anchor | 不能自动发现 UI 元素 | `perception/ui_detector.py` |
| G4 | **Skill 录制→语义蒸馏闭环不完整** | `recording/semantic_distiller.py` 只处理 mouse_click, 不处理 keyboard; 无自动分段; 无 anchor 绑定自动验证 | 录制的 Skill 质量不可控 | `recording/semantic_distiller.py`, `recording/record_session.py` |
| G5 | **Capsule 校准向导无后端逻辑** | 前端 `CalibrationWizard` 页面存在, 后端 API 端点存在 (`/calibration/profile`), 但自动检测候选锚点的逻辑缺失 | 用户无法完成校准 | `interaction/calibration.py`, `perception/ui_detector.py` |
| G6 | **Verifier Studio 不存在** | `execution/declarative_verifier.py` 有引擎代码, 但无可视化编辑器或 recipe 管理 UI | 开发者体验差 | 新建 `desktop/src/` 组件 |
| G7 | **Mission Composer 不存在** | `planning/mission_graph_v3.py` 有 DAG builder, 但无 GUI 拖拽编辑器 | 高门槛 | 新建 `desktop/src/` 组件 |
| G8 | **Profile Preflight 检查不强制** | 校准 profile 存在但运行时不强制校验关键 anchor 可用性 | 不安全 unattended 风险 | `execution/safe_window_backend.py`, `app_service/agent_controller.py` |
| G9 | **OCR 三层路由未完整接线** | `perception/ocr_router.py` 有路由逻辑, `perception/glm_ocr_provider.py` 有 GLM OCR, 但 PaddleOCR provider 不存在, 三层降级逻辑未端到端测试 | OCR 可靠性无保障 | `perception/ocr_engine.py`, `perception/ocr_router.py` |
| G10 | **长程任务无 checkpoint resume** | `persistence/mission_checkpoint.py` 有类型定义, 但无实际 checkpoint save/restore 逻辑接入运行时 | 长任务失败不可恢复 | `persistence/mission_checkpoint.py`, `persistence/hot_resume.py` |

### B.2 Content Gaps (阻塞用户体验)

| # | 缺口 | 现状 | 影响 |
|---|------|------|------|
| C1 | **HSR 官方 Skill 数量不足** | 仅 3 个基础 skill (basic_attack, skill, ultimate); 缺少 reward_claim, dialog_continue, daily_mission, screen_navigation | HSR Capsule 不够支撑日常 |
| C2 | **Genshin Skill 为 data 层而非 Skill Contract** | `data/skills/` 有 9 个 YAML 定义, 但缺少 claim declaration, verifier recipe, fallback policy | Skill 不可验证 |
| C3 | **Verifier Recipe Library 仅 8 个核心 recipe** | `runtime/claim_adjudicator.py` 的 `CORE_RECIPES` 覆盖了 8 种 claim type, 但缺少 reward_claimed, dialog_advanced, loading_finished, route_segment_arrived 等产品必需 recipe | 验证覆盖不足 |
| C4 | **Benchmark 场景不足** | 5 个 benchmark task (genshin: 3, hsr: 2), 无标准场景 seed, 无 expected claim chain 定义 | 无法证明能力 |
| C5 | **Persona Pack 仅有 5 个基础 persona** | `configs/personas.json` 有 5 persona, 但无游戏角色 persona, 无 TTS 接入 | 伴游体验不足 |

### B.3 Architecture Gaps (技术债)

| # | 缺口 | 现状 | 影响 |
|---|------|------|------|
| T1 | **Telemetry 大面积为空** | `telemetry/event_schema.py`, `replay_index.py`, `video_recorder.py`, `metrics.py` 均为空 | 无可回放记录, 无性能指标 |
| T2 | **MSS capture 为空** | `perception/mss_capture.py` 空, 只能用 DXcam | 跨平台截屏无备选 |
| T3 | **Movement controller 为空** | `control/movement_controller.py` 空, 导航依赖 `navigation_runtime.py` | 缺少独立移动控制抽象 |
| T4 | **SQLite store 极简** | `persistence/sqlite_store.py` 仅 29 行, KV only, 无事务/schema 版本/查询 | 持久化能力不足 |
| T5 | **Desktop 单文件 1057 行** | `desktop/src/main.tsx` 包含全部 10 页面 | 维护困难, 应拆分 |
| T6 | **WS 只有一个状态通道** | `app_service/ws.py` 仅推送 agent state, 无日志流/帧流/事件流 | 前端实时性差 |

---

## C. 商业产品定义

### C.1 产品定位

> **Aurora**: Local-first, verifier-first visual agent runtime for safe, replayable, extensible desktop and game workflows.

产品不是"让大模型直接操控键鼠"，而是"用可验证的本地运行时、可校准的 UI/视觉锚点、可复用的 Skill/Capsule 内容和可审计的任务闭环，降低大模型负担"。

### C.2 不做什么 (红线)

1. 不做反作弊绕过、内存读取、进程注入、驱动级输入。
2. 不承诺"任意游戏零配置全自动通关"。
3. 不把 VLM/LLM 的单次判断当作事实源。
4. 不把未验证的鼠标轨迹当成稳定 Skill。
5. 不在没有授权窗口 + Profile Preflight + InputLease + ReleaseAll 兜底的情况下运行 unattended 自动化。

### C.3 四级自主能力

| 等级 | 名称 | 定义 | 可 unattended |
|------|------|------|:---:|
| G1 | Supervised Visual Agent | VLM/OCR 提议候选动作, 用户确认后执行 | 否 |
| G2 | Capsule Guided Automation | 已校准 anchor + verifier + skill 驱动 | 低/中风险可 |
| G3 | Mission Automation | MissionGraph 串联多 Skill, 支持恢复 | 已验证任务可 |
| G4 | Adaptive Agent | 从失败和审计中改进, 自动生成修复候选 | 仅 testbed/低风险 |

**当前应主推 G2-G3。G1 是兜底。G4 是研发卖点。**

### C.4 内容资产体系 (7 类)

1. **Capsule Pack**: 游戏/应用特调包 (manifest + resources + skills + providers + benchmarks)
2. **Skill Pack**: 可验证能力库 (claim declaration + verifier recipe + fallback + risk level)
3. **Knowledge Pack**: 游戏知识库 (物品/任务/地图/NPC/配方/失败签名)
4. **Verifier Recipe Library**: 验证模式库 (screen_state, anchor_exists, text_match, numeric_delta 等)
5. **Persona Pack**: 伴游角色 (话术 + 播报 + 失败解释 + TTS 风格, 不污染执行事实)
6. **Benchmark Pack**: 可复现场景 (seed + expected claim chain + failure injection + metrics)
7. **Learning Pack**: 失败学习资产 (failure signature + evidence refs + suggested fix + regression case)

---

## D. 实施阶段 (Phase Plan)

每个 Phase 包含: 目标、具体文件级任务、验收标准、估算工作量。

### Phase 1: Claim 主链路贯通

**目标**: 所有公开流程走 Claim 主路径, 终端节点必须有 verified/audited Claim。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 1.1 | AgentController 接入 ClaimGraphWorker | 在 `_run_real_loop()` 中创建并持有 `ClaimGraphWorker` 实例; 每个 skill 执行后产生 `StateDeltaClaim` | `app_service/agent_controller.py` |
| 1.2 | Skill 执行后提交 claim | 扩展 `Orchestrator._execute_skill_step()`, 执行完 skill 后调用 `ClaimProducingExecutor` 产生 claim, 提交到 `ClaimGraphWorker` | `orchestration/orchestrator.py` |
| 1.3 | Terminal 节点必须有 verified claim | 在 `OrchestrationGraph` 的 COMPLETE 转换前, 检查 `ClaimGraph` 中 terminal claim 是否为 verified/audited; 否则转为 FAILED | `orchestration/graph.py` |
| 1.4 | Claim event 通过 StateBus 发布 | `ClaimGraphWorker` 已有 `ClaimEventPublisher` 桥接, 确认 StateBus 发布 `claim_event` 和 `claim_graph_state` slot | 验证 `runtime/claim_events.py` + `core/state_bus.py` |
| 1.5 | HSR UI testbed flow 产生完整 claim chain | 新建测试: 模拟 HSR reward claim 流程, 验证每步产生 claim 并最终 terminal claim 为 verified | `tests/test_claim_hsr_flow.py` (新建) |
| 1.6 | Genshin collection testbed flow 产生完整 claim chain | 新建测试: 模拟采集流程, 验证每步 claim | `tests/test_claim_genshin_flow.py` (新建) |

**验收标准**:
- [ ] `pytest tests/test_claim_hsr_flow.py tests/test_claim_genshin_flow.py` 通过
- [ ] 没有 claim evidence 的 terminal success 触发 FAILED 转换
- [ ] StateBus `claim_event` slot 可订阅
- [ ] 所有 995 个已有测试仍然通过

---

### Phase 2: 真实执行后端贯通

**目标**: 物理输入链路 InputLease → MouseMotor → SafeWindow → PhysicalActionReceipt 可端到端运行。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 2.1 | 实现 `RealInputBackend` | 基于 `pyautogui` 或 `ctypes`/`win32api`, 实现 `press_key()`, `click()`, `move_to()`, `release_all()`; 集成 `InputLease` 验证 | `execution/real_input_backend.py` |
| 2.2 | 完善 `MouseMotor` | 实现贝塞尔曲线鼠标路径 (非直线), 支持速度/加速度参数, 产生 `PhysicalActionReceipt` | `execution/mouse_motor.py` |
| 2.3 | 完善 `SafeWindowBackend` | 在每次输入前验证: 目标窗口前台 + 标题匹配 + 焦点未丢失; 否则触发 `release_all` | `execution/safe_window_backend.py` |
| 2.4 | `PhysicalActionReceipt` 结构化 | 确认 receipt 包含: action_type, timestamp, target_window, lease_id, duration_ms, evidence_ref | `execution/physical_receipt.py` |
| 2.5 | 集成测试: ConsoleBackend → Claim chain | 在 dry-run 模式下验证完整链路 | `tests/test_real_input_chain.py` (新建) |

**验收标准**:
- [ ] `RealInputBackend` 通过单元测试 (mock OS 输入)
- [ ] `SafeWindowBackend` 在窗口失焦时触发 `release_all`
- [ ] `MouseMotor` 产生非直线路径
- [ ] `PhysicalActionReceipt` 包含所有必需字段
- [ ] 所有已有测试仍然通过

---

### Phase 3: Profile Preflight 与安全门禁

**目标**: 每次运行前强制校验关键 anchor 可用性, 失败则阻止 unattended。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 3.1 | 实现 `ProfilePreflight` | 抽检关键 anchor: 截屏 → 模板匹配/OCR → 置信度阈值; 通过/失败/降级 | `interaction/calibration.py` 或新建 `execution/profile_preflight.py` |
| 3.2 | AgentController 启动时调用 Preflight | 在 `_run_real_loop()` 开始前调用 `ProfilePreflight.run()`; 失败时只允许 supervised 或拒绝启动 | `app_service/agent_controller.py` |
| 3.3 | API 端点暴露 preflight 结果 | `GET /calibration/preflight/{capsule_id}` 返回每个 anchor 的检查结果 | `app_service/api.py` |
| 3.4 | 测试: Preflight 失败阻止 unattended | 新建测试 | `tests/test_profile_preflight.py` (新建) |

**验收标准**:
- [ ] Profile 缺失或 anchor 检测失败时, API 返回明确的 preflight failure
- [ ] unattended 模式下 preflight 失败拒绝启动
- [ ] supervised 模式下 preflight 失败给出警告但不阻止
- [ ] 所有已有测试仍然通过

---

### Phase 4: HSR 官方 Capsule 内容收口

**目标**: HSR 作为 UI-first 标杆, 至少覆盖 8 个核心 UI flow。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 4.1 | HSR Skill 扩充 | 新建 skill YAML: `reward_claim`, `dialog_continue`, `daily_mission`, `screen_navigation`, `auto_battle_toggle`, `battle_result_claim` | `capsules/hsr/skills/*.yaml` |
| 4.2 | HSR UI Anchor 补充 | 为每个新增 skill 定义锚点: menu/quest/reward/dialog/battle_result/confirm/back | `capsules/hsr/resources/screen_regions.yaml`, `capsules/hsr/resources/task_patterns.yaml` |
| 4.3 | HSR Verifier Recipe 补充 | 新增 recipe: `reward_claimed`, `dialog_advanced`, `screen_state_transition` (HSR-specific) | `runtime/claim_adjudicator.py` (扩展 `CORE_RECIPES`) 或新建 `capsules/hsr/resources/verifier_recipes.yaml` |
| 4.4 | HSR Claim Declaration | 为每个 HSR skill 注册 `SkillClaimDeclaration`: input_claims, produced_claims, risk_level | `capsules/hsr/skills/*.yaml` 的 `claims` section |
| 4.5 | HSR Benchmark 扩充 | 新建至少 10 个 benchmark flow: 每个覆盖一个 UI flow, 有 expected claim chain | `capsules/hsr/benchmarks/*.yaml` |
| 4.6 | HSR 多分辨率 Profile | 至少 1080p 和 4K 两个 profile, 验证 anchor 归一化 | `configs/profiles/hsr_1920x1080.json`, `configs/profiles/hsr_3840x2160.json` (新建) |
| 4.7 | HSR Provider 增强 | 在 `capsules/hsr/providers.py` 中为新增 skill 注册 provider | `capsules/hsr/providers.py` |

**验收标准**:
- [ ] `pytest tests/test_hsr_*.py` 全部通过
- [ ] 至少 10 个 benchmark flow 有 expected claim chain
- [ ] 每个 flow 有 terminal claim (verified 或 audited)
- [ ] 低置信度 anchor 不自动点击
- [ ] 2 种分辨率 profile 校准数据完整

---

### Phase 5: Genshin UI + Collection R1

**目标**: 传送 → 短导航 → 采集 → 验证 testbed 可跑。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 5.1 | Genshin Skill 升级为 Skill Contract | 将 `data/skills/` 的 9 个 YAML 迁移到 `capsules/genshin/skills/`, 添加 claim declaration, verifier recipe, fallback policy | `capsules/genshin/skills/*.yaml` |
| 5.2 | Genshin UI Anchor 补充 | 扩展 anchor 定义: world_map, teleport_confirm, inventory, craft, collection_prompt, toast | `interaction/capsule_anchors.py` 或 `capsules/genshin/resources/ui_anchors.yaml` |
| 5.3 | Genshin Verifier Recipe 补充 | 新增: `collection_pickup`, `teleport_loaded`, `route_segment_arrived`, `danger_cleared` | `runtime/claim_adjudicator.py` 扩展 |
| 5.4 | Genshin Benchmark 扩充 | 新建 benchmark: UI flow (地图→传送→确认), Collection flow (传送→导航→采集→验证) | `capsules/genshin/benchmarks/*.yaml` |
| 5.5 | Collection 验证多信号 claim | 采集成功必须同时有: toast OCR + 物品数量 delta + 交互提示消失 | `execution/collection_verifier.py` |
| 5.6 | 移动 lease timeout 强制 | 所有移动动作的 `InputLease` 设置合理 timeout, stuck recovery 有次数上限 | `control/navigation_runtime.py` |

**验收标准**:
- [ ] 传送 → 短导航 → 采集 testbed flow 可跑 (dry-run)
- [ ] 每个 Genshin skill 有 `SkillClaimDeclaration`
- [ ] 采集成功有多信号 claim
- [ ] 移动失败触发 safe abort
- [ ] 所有已有测试仍然通过

---

### Phase 6: OCR 三层路由 + Local Model Center

**目标**: OCR 可靠降级, 本地 VLM 可用。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 6.1 | 实现 PaddleOCR provider | 封装 `paddleocr` Python 包, 实现 `OCRProvider` protocol | `perception/paddle_ocr_provider.py` (新建) |
| 6.2 | 完善 OCR 三层路由 | O1(PaddleOCR) → O2(GLM-OCR) → O3(VLM OCR); 实现置信度阈值驱动的自动升级 | `perception/ocr_router.py` |
| 6.3 | OCR 指标收集 | 每次调用记录: latency, confidence, correction_needed, layer_used | `perception/ocr_engine.py` |
| 6.4 | 完善 Local VLM provider | 支持任意 OpenAI-compatible endpoint, health check (text/image/JSON smoke test) | `llm/local_vlm_provider.py` |
| 6.5 | Model Capability Profile | `ModelCapabilityProfile` dataclass: supports_image, supports_json, max_image_size, avg_latency_ms, reliability_score | `llm/vision_provider.py` 或新建 `llm/model_capability.py` |
| 6.6 | Model health dashboard API | `GET /models/status` 返回各模型健康状态, `POST /models/smoke_test` 触发 smoke test | `app_service/api.py` |

**验收标准**:
- [ ] PaddleOCR provider 单元测试通过
- [ ] 三层路由: O1 失败自动升级到 O2, O2 失败升级到 O3
- [ ] 本地 VLM 不可用时 fallback 到 human confirm
- [ ] Smoke test (text + image + JSON) 通过
- [ ] OCR latency 和 confidence 指标可查询

---

### Phase 7: Skill Studio 最小闭环

**目标**: 录制 UI Skill, 换分辨率后通过 anchor 执行。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 7.1 | 录制管道完善 | `recording/record_session.py` 支持 keyboard 事件, 不仅限 mouse_click | `recording/record_session.py` |
| 7.2 | 自动分段器 | 根据屏幕状态变化自动将录制轨迹分段 | `recording/segmenter.py` (新建) |
| 7.3 | 语义蒸馏增强 | `recording/semantic_distiller.py` 支持 keyboard 事件, 自动绑定 anchor, 验证 anchor 可达 | `recording/semantic_distiller.py` |
| 7.4 | Claim binding | 蒸馏后的 Skill 自动声明 input_claims 和 produced_claims | `recording/semantic_distiller.py` |
| 7.5 | Skill 版本管理 | Skill 保存时自动 version + benchmark_stats | `app_service/agent_controller.py` 的 skill 相关方法 |
| 7.6 | Dry-run replay | Skill 保存后自动触发 dry-run replay 验证 | `app_service/agent_controller.py` |
| 7.7 | 缺 verifier 的 Skill 不允许标 stable | 在 Skill validate 时检查: 高风险 Skill 必须有 verifier recipe | `execution/skill_binder.py` 或 `app_service/agent_controller.py` |

**验收标准**:
- [ ] 录制一个包含 mouse + keyboard 的 Skill, 蒸馏成功
- [ ] 换分辨率后 Skill 通过 anchor 归一化执行
- [ ] 缺 verifier 的 Skill validate 报错
- [ ] Skill 保存触发 dry-run replay
- [ ] 所有已有测试仍然通过

---

### Phase 8: Verifier Studio 最小闭环

**目标**: 开发者无需写 Python 创建 reward_claimed, dialog_advanced, inventory_delta verifier。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 8.1 | Recipe template 管理 | 从 `CORE_RECIPES` 抽取为独立 YAML 文件, 支持加载/保存/校验 | `resources/verifier_recipes/*.yaml` (新建) 或 `capsules/*/resources/verifier_recipes.yaml` |
| 8.2 | Recipe editor API | CRUD 端点: `GET/POST/PUT/DELETE /verifier/recipes/{id}`, 包含 source family 预览, stabilization window 配置 | `app_service/api.py` |
| 8.3 | Frame fixture runner | 用历史帧批量测试 recipe: `POST /verifier/recipes/{id}/test_frames` | `app_service/api.py`, `execution/declarative_verifier.py` |
| 8.4 | Recipe 可视化调试 (前端) | 前端页面: ROI 选择 → recipe 类型 → 预览结果 → 配置参数 → 批量测试 | `desktop/src/` (新建组件) |
| 8.5 | Recipe 校验规则 | 必须声明: source_families, required families, risk_thresholds, fallback if unverifiable | `runtime/verifier_compiler.py` 扩展 |

**验收标准**:
- [ ] 通过 API 创建 reward_claimed recipe, 无需写 Python
- [ ] recipe 可批量跑历史 frame
- [ ] recipe 缺少 required families 时校验失败
- [ ] 所有已有测试仍然通过

---

### Phase 9: 长程任务 + Checkpoint Resume

**目标**: 长任务中断后可从 checkpoint 恢复。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 9.1 | Checkpoint save 实现 | 每个 MissionNode 完成后保存: node_id, state, claim_snapshot, profile_version, capsule_version | `persistence/mission_checkpoint.py` |
| 9.2 | Checkpoint restore 实现 | 从最新 checkpoint 恢复: profile revalidation + window revalidation + skill version revalidation | `persistence/hot_resume.py` |
| 9.3 | Context compaction | 长任务上下文超过阈值时自动压缩: 保留最近 N 帧 + 关键 claim + decision summary | `runtime/context_compactor.py` |
| 9.4 | Audit pending queue recovery | 恢复时重放未完成的 delayed audit | `runtime/audit_scheduler.py` |
| 9.5 | Memory growth bound | 每小时检查内存增长, 超过阈值触发 compaction 或 safe abort | `runtime/long_run_policy.py` |
| 9.6 | 测试: checkpoint save/restore | 新建测试 | `tests/test_checkpoint_resume.py` (新建) |

**验收标准**:
- [ ] 任务中断后可从最新 checkpoint 恢复
- [ ] profile/capsule version 变化时阻止自动恢复 (需用户确认)
- [ ] 内存增长有界 (测试: 模拟 1 小时运行, 验证 memory_growth_mb_per_hour 在阈值内)
- [ ] 所有已有测试仍然通过

---

### Phase 10: Open Beta 质量门禁

**目标**: 新用户 15 分钟内完成 demo。

**任务**:

| # | 任务 | 具体操作 | 涉及文件 |
|---|------|----------|----------|
| 10.1 | 首次启动向导 | 前端: 语言选择 → 安全边界阅读 → 模型配置 → Capsule 安装 → 健康检查 → 校准 → 60s dry-run demo → 报告 | `desktop/src/` (新建组件) |
| 10.2 | 失败反馈包完善 | `open_beta/feedback_package.py` 增加: screenshot (脱敏), claim graph slice, failed verifier votes, controller receipts | `open_beta/feedback_package.py` |
| 10.3 | Benchmark dashboard | 前端页面: 每个公开能力有 benchmark result, pass/fail, metrics | `desktop/src/` (新建组件或扩展 Reports 页面) |
| 10.4 | Crash recovery | 异常退出后重启时检测: dirty state → offer to resume or clean | `persistence/sqlite_store.py` 或 `runtime/run_state_store.py` |
| 10.5 | Privacy/export settings | 前端页面: 数据本地/不上传, 截图脱敏, 导出/删除 | `desktop/src/` |
| 10.6 | Release notes 自动生成 | 从 git log 生成变更摘要, 标注 breaking change | `scripts/package_release.py` |

**验收标准**:
- [ ] 新用户 15 分钟内完成首次 demo (dry-run)
- [ ] 每个公开 demo 有 benchmark
- [ ] safety_violation_count = 0 (所有测试)
- [ ] 所有失败可生成反馈包

---

## E. 优先级排序

资源有限时按此顺序推进:

| 优先级 | Phase | 理由 |
|--------|-------|------|
| **P0** | Phase 1 (Claim 贯通) | 没有它, 成功不可证明 |
| **P0** | Phase 3 (Profile Preflight) | 没有它, 真机不安全 |
| **P1** | Phase 2 (真实执行后端) | 没有它, 无法真机执行 |
| **P1** | Phase 4 (HSR 内容) | 最快形成用户可感知价值 |
| **P2** | Phase 5 (Genshin UI/Collection) | 比战斗更早产生真实价值 |
| **P2** | Phase 6 (OCR/Model) | 降低长期成本, 增强本地体验 |
| **P3** | Phase 7 (Skill Studio) | 没有内容生产工具, 项目无法扩张 |
| **P3** | Phase 8 (Verifier Studio) | 没有验证生产工具, 稳定性无法扩张 |
| **P4** | Phase 9 (Checkpoint) | 长程任务需要 |
| **P4** | Phase 10 (Open Beta) | 在证据足够后再扩大 |

---

## F. Coding Agent 执行规则

后续 Coding Agent **必须**遵守:

1. **不得把游戏特定逻辑写入 `core/`**。已有 `tests/test_core_has_no_game_specific_imports.py` 守护。
2. **不得用旧布尔 `success=True` 作为 terminal success**。必须走 Claim → Adjudicator → verified/audited。
3. **不得让 VLM 直接输出物理坐标执行**。VLM 只产出候选 UIElement 和 screen state proposal。
4. **不得绕过 InputLease、SafeWindow、release_all**。所有物理输入必须经过 lease。
5. **不得新增无 Benchmark 的 public demo**。每个公开能力必须有 benchmark case。
6. **不得新增无 Profile Preflight 的 unattended flow**。
7. **每个新 Skill 必须有 failure path** (fallback policy)。
8. **每个新 Verifier 必须声明 source_family 和 risk ceiling**。
9. **每个新 Capsule 必须有 `docs/user_guide.md` 和 `docs/developer_notes.md`**。
10. **每个真实能力宣称必须有 dry-run/testbed 或授权窗口证据**。
11. **测试必须全部通过**: `pytest tests/ -x` 不允许失败。
12. **代码风格**: `ruff check .` 和 `mypy core/ perception/ control/ execution/ orchestration/` 必须通过。

---

## G. 最小商业可发布版本 (MCPV)

MCPV 应包含:

- [x] 桌面 GUI 可启动 (Tauri + React, 10 页面)
- [x] ~40 REST API 端点 + WebSocket
- [x] Capsule 安装/注册/激活 (4 个 capsule pack)
- [x] Claim-Centric Runtime (StateDeltaClaim, ClaimGraph, Adjudicator, Delayed Audit)
- [x] 三层可靠性 (Verifier/Recipe/SkillClaim)
- [x] ROI 校准 Profile (8 个, 覆盖 1080p/4K)
- [x] Genshin/HSR 战斗系统 (playbook, reflex, survival, boss)
- [x] AutonomousTaskBrain (感知-规划-执行-验证循环)
- [ ] **本地模型/OCR 健康检查** (Phase 6)
- [ ] **Capsule 校准向导后端逻辑** (Phase 3)
- [ ] **HSR UI-first 官方 flow** (Phase 4)
- [ ] **Genshin UI/collection testbed flow** (Phase 5)
- [ ] **Claim 主链路端到端贯通** (Phase 1)
- [ ] **Profile Preflight 强制门禁** (Phase 3)
- [ ] **Skill Studio 最小版** (Phase 7)
- [ ] **Verifier Studio 最小版** (Phase 8)
- [ ] **AuroraBench v2 dashboard** (Phase 10)
- [ ] **失败反馈包完善** (Phase 10)
- [ ] **用户指南 + 开发者指南** (已有 `docs/USER_GUIDE.md`, 需更新)
- [ ] **明确安全边界声明** (已有 `SAFETY.md`, 需更新)

---

## H. 核心成功指标

### H.1 Runtime 指标

| 指标 | 目标 | 当前基线 |
|------|------|----------|
| verified_task_completion_rate | ≥ 0.85 (已验证任务) | 未测量 |
| claim_verified_rate | ≥ 0.90 | 未测量 |
| claim_audited_rate | ≥ 0.70 | 未测量 |
| release_all_success_rate | 1.00 | 未测量 |
| safety_violation_count | 0 | 0 (测试) |
| OCR latency p95 | < 500ms (本地) | 未测量 |
| VLM latency p95 | < 3s (本地) | 未测量 |
| memory_growth_mb_per_hour | < 50 | 未测量 |

### H.2 内容指标

| 指标 | 目标 | 当前 |
|------|------|------|
| official capsule count | ≥ 4 | 4 (demo_arpg 不算) |
| stable skill count (HSR) | ≥ 10 | 3 |
| stable skill count (Genshin) | ≥ 9 (upgraded to Skill Contract) | 0 (data layer only) |
| benchmark-backed skill % | ≥ 80% | ~0% |
| verifier recipe coverage | ≥ 16 recipes | 8 |
| profile compatibility count | ≥ 4 (2 game × 2 res) | 2 |
| supported screen resolutions | 1080p + 4K | 已有 profile |

### H.3 体验指标

| 指标 | 目标 | 当前 |
|------|------|------|
| first-run demo completion time | ≤ 15 min | 未测量 |
| calibration wizard completion | ≤ 5 min | 未测量 |
| failure report readability | 用户可懂原因 + 下一步 | 未测量 |

---

## I. 关键架构决策 (已确定, 不可绕过)

1. **五平面架构**: Perception → Control → Execution → Orchestration → Telemetry, 跨平面通信只通过 StateBus。
2. **InputLease 安全模型**: 所有物理输入经过 lease, lease 过期/线程死/焦点丢失 → `release_all`。
3. **Claim 作为事实源**: LLM context 不是事实源。事实源 = MissionGraph + ClaimGraph + EvidenceGraph + RunJournal。
4. **VLM 产出候选, 不产出执行**: VLM 只能提议 UIElement/screen state, 最终执行走 anchor + semantic action。
5. **Capsule 隔离**: 游戏特定代码在 `capsules/` 下, core 不得引入游戏 import。
6. **Monotonic clock**: 全局 `time.perf_counter()`, 禁止 `time.time()` 用于逻辑。
7. **EWMA + time-window slope**: 不用单帧判断进度/挫折, 用指数加权移动平均。
8. **Verifier voting + noisy-or**: 不追求单个 verifier 永远正确, 通过 adjudicator 多证据投票裁决。
9. **Delayed audit**: 宣称成功后仍可被延迟审计推翻, 维护系统自诚实性。

---

## J. 文件索引: 关键实现文件速查

| 领域 | 文件 | 行数 | 核心类型 |
|------|------|------|----------|
| StateBus | `core/state_bus.py` | 284 | `StateBus`, `LatestSlot[T]`, `RingBuffer[T]` |
| 类型系统 | `core/types.py` | 160 | `Observation`, `TargetTrack`, `InputLease`, `SkillResult` |
| Claim 运行时 | `runtime/claim_runtime.py` | 1093 | `StateDeltaClaim`, `ClaimGraph`, `ClaimProducingExecutor` |
| Claim 裁决 | `runtime/claim_adjudicator.py` | 363 | `ClaimAdjudicator`, `EvidenceVote`, 8 CORE_RECIPES |
| Claim Worker | `runtime/claim_worker.py` | 218 | `ClaimGraphWorker` (单线程命令模式) |
| 延迟审计 | `runtime/audit_scheduler.py` | 292 | `DelayedAuditScheduler` (JSONL 持久化) |
| Verifier 编译 | `runtime/verifier_compiler.py` | 195 | `VerifierCompiler`, 8 CORE_BUNDLES |
| Mission DAG | `runtime/mission_graph.py` | 261 | `MissionGraph`, `UnverifiablePolicy` |
| Mission v3 | `planning/mission_graph_v3.py` | 232 | `MissionGraph`, `MissionGraphBuilder` |
| 自主任务脑 | `agent/autonomous_task_brain.py` | 453 | `AutonomousTaskBrain` (7 步循环) |
| 层级规划器 | `planning/hierarchical_planner.py` | 227 | `HierarchicalPlanner` (GLM-5.1) |
| 屏幕状态 | `planning/screen_state_claim.py` | 106 | `ScreenStateClaim`, `ActionAffordance` |
| 可供性推导 | `planning/action_affordance.py` | 239 | `AffordanceDeriver` (14 状态规则) |
| 三层可靠性 | `reliability/reliability_store.py` | 661 | `ThreeLayerReliabilityStore` |
| Agent 控制器 | `app_service/agent_controller.py` | 735 | `AgentController` (25+ 子系统) |
| REST API | `app_service/api.py` | 345 | ~40 端点 |
| Boss 战斗 | `combat/boss_combat_runtime.py` | 255 | `BossCombatRuntime` (10 态 FSM) |
| 生存策略 | `combat/survival_runtime.py` | 112 | `SurvivalPolicyEngine` |
| VLM Provider | `llm/zhipu_vlm_provider.py` | 174 | `ZhipuVLMProvider` (GLM-4V) |
| 证据图 | `evidence/evidence_graph.py` | 73 | `EvidenceGraph` |
| 桌面前端 | `desktop/src/main.tsx` | 1057 | 10 页面 React SPA |

---

## K. 商业表达原则

### 宣传什么

- **Claim-Centric Runtime**: 每个动作有可验证的证据链。
- **Capsule 体系**: 一个 Capsule 装载一个游戏/应用的全部特调。
- **Skill Contract**: 可验证、可迁移的能力单元。
- **Safety-first**: InputLease + SafeWindow + release_all + emergency stop。
- **Local-first**: 本地 OCR/VLM, 隐私可控, 成本可控。

### 不宣传什么

- "任意游戏零配置全自动通关"
- "完全无人值守" (除非已通过 Phase 3 preflight + Phase 1 claim chain)
- 高难 Boss 真实胜率 (直到 BossBench synthetic 稳定 + 真机 supervised 验证)
- VLM 直接执行能力

### 每个 demo 必须标注

- 支持 Capsule (id + version)
- 支持任务 (task name)
- 自动化等级 (G1-G4)
- 是否需要用户监督
- benchmark success rate
- 已测分辨率/语言
- 失败时是否可恢复
