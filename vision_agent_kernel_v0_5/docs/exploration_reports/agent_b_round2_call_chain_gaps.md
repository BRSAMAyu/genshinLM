# Agent B Round 2: 端到端调用链验证

## 1. GoalExecutor → AgentLoop 调用链

### execute_goal() 执行路径 (goal_executor.py:99)
1. `_compile_goal()` -> CompiledGoal (MissionGraphV4 + strategy + skill_candidates)
2. 每日委托分支 (line 118-125): 关键词匹配 -> `_execute_via_commission_executor()`
3. 未知目标分支 (line 128-258): `create_live_genshin_loop()` -> `agent_loop.run()`
4. G4 shortcut (line 206-224): 标准化每日委托节点列表

**发现**: 每日委托关键词被扫描两次（execute_goal 和 _compile_goal），浪费图构建。

### _compile_goal() 图构建
- `_build_daily_commission_graph()` (line 323): 15 节点线性 DAG
- `_build_unknown_goal_graph()` (line 382): 3 节点图 (observe -> iterate -> verify)

### AgentLoop.run() (loop.py:114)
- 入参: AgentGoal + optional TaskSpec
- 返回: GoalResult (achieved, steps, verified_claims, node_traces)
- live_factory.py:230 注入预编译图到 CerebrumPlannerAdapter

### 学习补丁提取
- `_extract_learning_from_claims()` (line 413): 仅 unknown_autonomous_exploration 激活
- **GAP-1 (Medium)**: 创建通用 fallback_basic_loop 技能，而非从执行中学到的实际动作序列

## 2. MainlineRunner → MainlineSkillExecutor → UIFlowSkillAdapter

### MainlineRunner._execute_node() (mainline_runner.py:469)
1. 验证 input_claims
2. 重试循环 (max_retries)
3. 类型处理器路由 -> skill_execute_fn(node)
4. 无 skill_execute_fn 时标记 "blocked"（Phase 8 安全特性）
5. 验证 output_claims + 体感更新

### MainlineSkillExecutor.execute_node_skill() (mainline_skill_executor.py:84)
1. 解析 semantic_action (metadata -> skill_candidates[0] -> node_type)
2. 解析 target (metadata -> output_claims -> input_claims -> "")
3. Pre-flight claim gate
4. BAGEL belief commit
5. `self._executor.execute_semantic(semantic_action, target, context)`
6. 失败时 RecoveryOrchestrator
7. Claim recording

### UIFlowSkillAdapter 动作映射 (ui_flow_skill_adapter.py:387)
- 192 个别名, 136 个处理程序
- **有实际逻辑**: UIFlow-routed (68), Combat (12+), Explore (8+), Quest dialog (6+), Mail (4), Wait/confirm (12+)
- **GAP-2 (High)**: ~34 个语义动作是 action_intent 透传 stub（日常、任务章节、主线路径）——无实际键盘输入，无法在生产环境运行
- **GAP-3 (Medium)**: Boss 专用战斗别名只记录 Boss ID，不调用 BossCombatBridge

## 3. MainlineLiveBridge 组件初始化 (mainline_live_bridge.py:44)

9 个组件按序初始化:
1. SafeWindowInputBackend
2. InputWorker
3. QuestMarkerFollower + MinimapQuestReader
4. GenshinScreenClassifier
5. SomaticStateSupervisor + SentinelRuntime
6. SkillRegistry (executor=None, later patched)
7. UIFlowSkillAdapter
8. MainlineSkillExecutor
9. BossCombatBridge
10. MainlineRunner

- **GAP-4 (Low)**: SkillRegistry._executor 通过直接属性赋值回填，跳过构造函数验证
- **GAP-5 (Medium)**: BossCombatBridge 默认只有无属性旅行者队伍
- **GAP-6 (Medium)**: BossCombatBridge 独立于任务图执行，存在输入 lease 竞争风险

## 4. MissionGraphV4 生成路径

- `_build_daily_commission_graph()`: 15 节点，无 risk_level/fallbacks/belief_templates
- `_build_unknown_goal_graph()`: 3 节点探索图
- run_mainline.py: 单节点图
- **GAP-7 (Medium)**: run_mainline.py 构建无 ClaimContracts 的最小图，完全绕过 claim-gated 验证

### MissionGraphValidatorV4 规则 (9 条)
1. Unique IDs (error)
2. Valid risk_level (error)
3. Terminal output_claims (error)
4. High risk fallbacks (error)
5. Acyclic (error)
6. Edge references (error)
7. Belief template structure (warning)
8. Required belief templates (error)
9. Deterministic serialization (error)

## 5. 检查点与状态恢复

### MainlineCheckpointPublisher (mainline_runner.py:161)
- 写 StateBus.checkpoint_state + 磁盘 (CheckpointStore 或 JSONL fallback)
- **GAP-8 (Medium)**: 不存储 ActiveQuestContext 或图序列化

### QuestContextPersistence (quest_context_persistence.py)
- 完整实现: save/load/prune (保留 20 个快照)

### CrashRecovery (crash_recovery.py)
- 状态机: DETECT -> ASSESS -> LAUNCH -> RECONNECT -> RESTORE -> RESUME
- **GAP-9 (High)**: CrashRecoveryOrchestrator 未连接到 MainlineRunner/MainlineLiveBridge
- **GAP-10 (Medium)**: 三套独立检查点系统 (MainlineCheckpoint, QuestContextPersistence, CheckpointStore) 使用不同格式

## Gap 汇总

| ID | Severity | Description |
|---|---|---|
| GAP-1 | Medium | 学习补丁提取是肤浅的占位实现 |
| GAP-2 | High | ~34 个语义动作是 action_intent 透传 stub |
| GAP-3 | Medium | Boss 专用战斗别名不调用 BossCombatBridge |
| GAP-4 | Low | SkillRegistry._executor 通过直接属性赋值 |
| GAP-5 | Medium | BossCombatBridge 默认无属性旅行者队伍 |
| GAP-6 | Medium | BossCombatBridge 与任务图输入 lease 竞争 |
| GAP-7 | Medium | run_mainline.py 绕过 claim-gated 验证 |
| GAP-8 | Medium | MainlineCheckpoint 和 QuestContextPersistence 解耦 |
| GAP-9 | High | CrashRecovery 未连接到 MainlineRunner |
| GAP-10 | Medium | 三套独立检查点系统无统一恢复 |
