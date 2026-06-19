# Agent B: 规划与任务系统探索报告

## Round 1 — 模块摸底

### 1. 文件清单

**planning/ 目录 (77 个 .py 文件)**

| 子目录 | 文件 | 核心目的 |
|---|---|---|
| mainline/ | `__init__.py` | 包初始化 |
| mainline/ | `active_quest_context.py` | 版本化的、不可变的任务上下文快照数据模型 |
| mainline/ | `bagel_jit_router.py` | 基于 BAGEL 信念的实时图变异（即时路由） |
| mainline/ | `mainline_live_bridge.py` | 连接 MainlineRunner 与实时游戏窗口 |
| mainline/ | `mainline_progression_adapter.py` | 逐章节的剧情推进协调器（序章 -> 第5章） |
| mainline/ | `mainline_runner.py` | 核心任务图执行引擎（带声明门控节点） |
| mainline/ | `mainline_skill_executor.py` | 通过语义执行器 + 声明图 + BAGEL 执行节点 |
| mainline/ | `mission_graph_v4.py` | V4 任务图：基于声明的 DAG，带信念模板、预算、回退 |
| mainline/ | `mission_graph_validator_v4.py` | 任务图结构/语义验证器 |
| mainline/ | `quest_context_persistence.py` | ActiveQuestContext 序列化/反序列化到磁盘（JSON） |
| mainline/ | `quest_state_tracker_v2.py` | 从感知输入（OCR/VLM/声明图）升级的任务状态跟踪器 |
| planning/ | `action_affordance.py` | 可供性推导 |
| planning/ | `action_mask.py` | 被屏蔽动作过滤 |
| planning/ | `activity_priority_system.py` | 限时事件优先级计算 |
| planning/ | `applicability_gate.py` | 技能适用性评分与门控 |
| planning/ | `boss_mechanism_preloader.py` | Boss 战斗机制预加载 |
| planning/ | `capability_planner.py` | 能力感知任务规划 |
| planning/ | `capsule_plan_templates.py` | 胶囊计划模板库 |
| planning/ | `character_build_planner.py` | 角色构建规划（材料、皇冠、稀缺性） |
| planning/ | `character_build_workflows.py` | 角色构建工作流 |
| planning/ | `character_progression_adapter.py` | 6 阶段角色进阶适配器 |
| planning/ | `coop_commission.py` | 合作任务管理 |
| planning/ | `coop_domain.py` | 合作领域管理 |
| planning/ | `critical_branch_detector.py` | 任务关键分支检测 |
| planning/ | `cutscene_skip_handler.py` | 过场动画跳过 |
| planning/ | `daily_loop_scheduler.py` | 每日循环调度 |
| planning/ | `dialog_choice_arbiter.py` | 带声明的对话选择仲裁 |
| planning/ | `dialog_choice_execution_bridge.py` | 对话点击执行桥接 |
| planning/ | `domain_navigator.py` | 领域楼层导航 |
| planning/ | `dream_handler_v2.py` | 梦境任务处理器 |
| planning/ | `elemental_target_detector.py` | 元素目标检测 |
| planning/ | `exploration_engine.py` | 基于区域的探索引擎 |
| planning/ | `exploration_mission_bridge.py` | 探索任务桥接 |
| planning/ | `failure_recovery_extensions.py` | 恢复扩展 |
| planning/ | `fontaine_water_level.py` | 枫丹水位解谜处理 |
| planning/ | `goal_stack.py` | 目标栈数据结构 |
| planning/ | `hierarchical_planner.py` | 层次化规划器 |
| planning/ | `intent_parser.py` | 意图解析 |
| planning/ | `investment_rollback.py` | 投资回滚计算 |
| planning/ | `investigation_handler_v2.py` | 调查任务处理 |
| planning/ | `marker_recovery.py` | 任务标记恢复 |
| planning/ | `memory_scene_detector.py` | 记忆场景检测 |
| planning/ | `meta_learning.py` | 元学习引擎 |
| planning/ | `mission_graph.py` | 任务图 V1/V2（旧版） |
| planning/ | `mission_graph_v3.py` | 任务图 V3（旧版） |
| planning/ | `mission_queue.py` | 任务队列数据结构 |
| planning/ | `mission_runner.py` | 旧版任务运行器 |
| planning/ | `natlan_war_state.py` | 纳塔部族战争状态 |
| planning/ | `newbie_tutorial_chain.py` | 新手教程链执行 |
| planning/ | `npc_affection_persistence.py` | NPC 好感度持久化 |
| planning/ | `npc_time_availability.py` | NPC 时间可用性 |
| planning/ | `plan_graph_builder.py` | 计划图构建器 |
| planning/ | `plan_patch.py` | 计划补丁 |
| planning/ | `plan_validator.py` | 计划验证器 |
| planning/ | `puzzle_integration_bridge.py` | 解谜集成桥接 |
| planning/ | `quest_enhancement.py` | 增强型任务机制 |
| planning/ | `quest_log_reader.py` | 任务日志读取器 |
| planning/ | `quest_mechanism_executor.py` | 任务机制执行器 |
| planning/ | `quest_mechanism_router.py` | 任务机制路由（12种+机制类型） |
| planning/ | `quest_objective_detector.py` | 任务目标检测器 |
| planning/ | `quest_skill_adapter.py` | 任务技能适配器 |
| planning/ | `quest_state_machine.py` | 任务状态机 |
| planning/ | `quest_state_recovery.py` | 任务状态恢复 |
| planning/ | `quest_timeout_handler.py` | 任务超时处理 |
| planning/ | `realm_manager_v2.py` | 尘歌壶管理器 |
| planning/ | `recovery_orchestrator.py` | 统一恢复协调器（7个类别） |
| planning/ | `regression_runner.py` | 回归测试运行器 |
| planning/ | `resource_manager.py` | 资源管理 |
| planning/ | `sakura_bough_handler.py` | 神樱树处理 |
| planning/ | `screen_state_claim.py` | 屏幕状态声明 |
| planning/ | `screen_state_claim_builder.py` | 屏幕状态声明构建器 |
| planning/ | `session_chains.py` | 会话链 |
| planning/ | `skill_capability_catalog.py` | 技能能力目录 |
| planning/ | `skill_inductor.py` | 技能归纳器 |
| planning/ | `skill_registry.py` | 复合动作路由注册表 |
| planning/ | `strategy_reader.py` | 策略阅读器 |
| planning/ | `strategic_decision_extensions.py` | 战略决策扩展 |
| planning/ | `task_spec_builder.py` | 任务规范构建器 |
| planning/ | `tcg_manager.py` | TCG 卡牌游戏管理器 |
| planning/ | `wish_shop_system.py` | 祈愿/商店系统 |
| planning/ | `world_level_planner.py` | 世界等级规划 |

**app_service/ 目录 (29 个 .py 文件)**

| 文件 | 核心目的 |
|---|---|
| `agent_controller.py` | AgentController — 主协调控制器 |
| `api.py` | REST/WebSocket API 路由 |
| `app_registry.py` | 应用协议注册表 |
| `calibration.py` | 视口校准 |
| `genshin_persona.py` | Genshin 人设事件映射 |
| `genshin_version_adapter.py` | Genshin 版本适配 |
| `goal_executor.py` | GoalExecutor — 目标到任务的编译与执行 |
| `launcher.py` | GenesisLauncher — 启动时诊断 |
| `main.py` | 应用主入口点 |
| `mainline_api.py` | MainlineAPI — 任务控制座舱式端点 |
| `model_manager.py` | VLM/LLM 模型管理 |
| `product_e2e.py` | 产品 E2E 验收测试运行器 |
| `recorder_backends.py` | 记录后端 |
| `schemas.py` | Pydantic API 模型 |
| `skill_exchange.py` | 技能导入/导出交换 |
| `skill_manager.py` | SkillStore、SkillRecorder、SkillValidator |
| `ws.py` | WebSocket 处理器 |
| `window_selector.py` | 窗口选择器 |

**orchestration/ 目录 (9 个 .py 文件)**

| 文件 | 核心目的 |
|---|---|
| `daily_routine_skill_adapter.py` | 3 层每日任务适配器 |
| `failure_policy.py` | FailurePolicy — 重试/失败跟踪 |
| `graph.py` | OrchestrationGraph — 状态机图 |
| `interrupt_handler.py` | 中断处理 |
| `orchestrator.py` | Orchestrator — 基于线程的状态机执行循环 |
| `skill_base.py` | Skill 协议定义 |
| `skills.py` | 内置技能实现（7 个标准技能） |
| `task_spec.py` | TaskSpec dataclass + YAML 加载器 |

### 2. 核心类与接口

**planning/mainline/ (核心任务系统)**

- `MissionGraphV4` — 基于 DAG 的声明门控任务容器
- `MissionNodeV4` — 声明门控任务节点（input_claims, output_claims, belief_templates, budgets, fallbacks）
- `ClaimContract` — 声明需求/产出
- `MainlineRunner` (line 281) — 中央执行引擎，带声明验证、BAGEL 信念提交、哨兵监控
- `MainlineSkillExecutor` — 通过 SemanticActionExecutor 协议执行单个 MissionNodeV4
- `MainlineLiveBridge` — 连接 MainlineRunner 与实时游戏窗口（9层组件）
- `MainlineAutonomyLoop` — 相位运行时（观察->更新上下文->选择图->提交信念->执行->验证->归因恢复->检查点->压缩）
- `MissionGraphValidatorV4` — 8条验证规则
- `ActiveQuestContext` — 版本化的不可变任务上下文快照
- `QuestStateTrackerV2` — 从 ScreenStateClaim 生成 ActiveQuestContext
- `BagelJitRouter` — BAGEL 信念证伪时修改活动 MissionGraphV4
- `MainlineProgressionAdapter` — 跨 6 个章节的完整剧情推进

**app_service/**

- `GoalExecutor` (line 92) — 自然语言目标编译成 MissionGraphV4，然后执行
- `MainlineAPI` — 任务控制座舱式端点
- `AgentController` — 主协调控制器

**orchestration/**

- `Orchestrator` — 基于线程的状态机执行循环
- `OrchestrationGraph` — 状态机图（INIT -> LOAD_TASK -> ... -> COMPLETE）
- `TaskSpec` — 任务规范 dataclass + YAML 加载器
- `DailyRoutineSkillAdapter` — 3 层每日任务（快速/标准/深度）

### 3. MainlineRunner 执行流程

1. 图验证 — MissionGraphValidatorV4().is_valid(graph)
2. 拓扑排序 — graph.topological_order()（Kahn 算法）
3. 节点迭代循环：
   - 预算检查、中断检查、前置节点检查
   - 节点执行：预检查(input_claims) -> 技能执行 -> 后置检查(output_claims)
   - 体感更新 SomaticState
   - 成功/失败路径（BAGEL JIT 路由可能治愈图）
4. 成功判定：所有终端节点完成
5. 检查点发布：每次节点转换后

### 4. MainlineSkillExecutor 调度机制

1. 动作/目标解析
2. 飞行前检查（ClaimProducingExecutor）
3. BAGEL 信念提交
4. BAGEL 动作提案
5. 目标焦点检查
6. 语义执行
7. 恢复（失败时通过 RecoveryOrchestrator）
8. BAGEL 反馈循环
9. 声明记录
10. ClaimRuntime 集成
11. BAGEL 归因（失败时）

### 5. MainlineLiveBridge 桥接

构造函数初始化 9 个组件层：
1. SafeWindowInputBackend
2. InputWorker
3. QuestMarkerFollower + MinimapQuestReader
4. GenshinScreenClassifier
5. SomaticStateSupervisor + SentinelRuntime
6. SkillRegistry
7. UIFlowSkillAdapter
8. BossCombatBridge
9. MainlineRunner

execute_live_mission 流程：确保前台聚焦 -> 等待加载 -> 启动 Boss 战斗桥 -> runner.run(graph) -> 清理

### 6. GoalExecutor 角色

- 目标编译：_compile_goal(goal_text) -> CompiledGoal（含 MissionGraphV4）
- 执行路由：日常 -> DailyCommissionExecutor；其他 -> AgentLoop.run()
- 学习补丁管理：提取学习建议，持久化到 SkillStore
- 调用链：api.py / agent_controller.py -> GoalExecutor.execute_goal()

### 7. TaskSpec / TaskGraph 四代

- V4 (current): MissionGraphV4 + MissionNodeV4 (planning/mainline/mission_graph_v4.py)
- V3 (legacy): planning/mission_graph_v3.py
- V1/V2 (legacy): planning/mission_graph.py
- TaskSpec: orchestration/task_spec.py (YAML 加载)

### 8. Scripts 入口

| 脚本 | 功能 |
|---|---|
| `run_mainline.py` | 主线自动推进（dry-run 或实时） |
| `run_kernel.py` | 完整 5 平面内核启动 |
| `run_genshin_agent.py` | 自主 Genshin 代理 |
| `run_neurological_agent.py` | L0-L9 神经 AgentLoop |
| `launch_real_game.py` | 授权实时窗口 QA 启动器 |
| `run_task_demo.py` | 带编排图的任务演示 |
