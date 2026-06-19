# Sparkle 项目完整实探（2026-06-02）

> 方法：逐目录读取真实代码，记录实际发现。不预设结论。
> 覆盖：agent_kernel/ core/ execution/ app_service/ agent/ llm/ combat/ navigation/ perception/ bagel/ learning/ planning/ capsules/ scripts/ tests/ data/ knowledge/

---

## 一、项目全景

**总规模**: ~1200+ Python 文件，覆盖 30+ 顶级目录
**总测试**: 4323 tests collected，262 个测试文件
**数据资产**: data/ 4.3MB + knowledge/ 913KB
**LLM 集成**: 智谱 GLM-4V-Flash (VLM) + GLM-5.1 (LLM) + MiniMax-M2.7

---

## 二、agent_kernel/ — 神经运行时（6,427 行）

### live_factory.py (474 行) — 生产入口

**这是整个系统最关键的文件。** 把所有组件 wire 起来：

| 行号 | 组件 | 类型 |
|------|------|------|
| 262-263 | DxcamCapturer | 真实屏幕抓帧 |
| 280 | VLMPerceptionProvider | VLM 感知 |
| 287 | ZhipuVLMProvider | 智谱 VLM 真接入 |
| 308 | CerebrumAgentImpl | **keyword fallback**（非 LLM） |
| 315 | GenshinActionExecutor | 真实原神执行 |
| 320 | VLMSuccessChecker | VLM 验证 |
| 343 | SpinalReflexAgentImpl | 脊髓反射 |
| 356 | DailyCommissionDryRunRuntime | 日常委托 |
| 364 | UnknownSceneHandler | 未知场景处理 |
| 368-372 | **BAGEL 整链** (FIG + BeliefProposer + MetaLearningBridge + SkillInductor) | **还在生产** |

**关键事实**: CerebrumAgentImpl 是 keyword fallback，不是 LLM 大脑。BAGEL 整链接在生产主路上。

### loop.py (821 行) — AgentLoop 主循环

- tick 周期: Observe → Dialogue → Plan → Contract → Safety → Execute → Verify → Learn
- `max_plan_iterations=100`
- 未知场景处理: `_run_unknown_probe()` 触发 UnknownSceneHandler → MetaLearningBridge
- BAGEL 调用在 L319-335: `classify_failure_mode` + `meta_learning_bridge.on_exploration_result`

### cerebrum_agent.py (142 行) — **keyword fallback**

- **自述**: "Provides rule-based strategic planning with LLM/VLM fallback. This implementation provides the offline fallback: keyword-based goal decomposition."
- L42-56: hardcoded `_GOAL_SKILL_MAP`（goal → skill 的固定映射）
- L58-79: hardcoded `_FAILURE_PATTERNS`（失败模式匹配）
- L125-142: fixed 3-action fallback
- **结论: 这不是 LLM 驱动。CLAUDE.md 声称的 L7-L8 大脑是过度声明。**

### unknown_scene_handler.py (196 行)

- 6 次 probe 尝试，0.45 置信度阈值
- set_meta_learning_bridge() 已接线
- probe 结果流入 MetaLearningBridge.on_exploration_result()

### 其他文件

- `spinal_reflex_agent.py` — 脊髓反射层
- `dialogue_controller.py` — 对话控制 + OptionRegistry
- `embodied_runtime.py` — 具身运行时（**接线不完整**）
- `abyss_chamber_executor.py` — 深境回廊（**placeholder combat**）
- `cerebellum_controller.py` — 小脑控制（**parsing stub**）

---

## 三、core/ — 基础设施（~630 行核心）

### state_bus.py (304 行) — 中央事件总线

- **LatestSlot[T]**: 线程安全最新值存储（RLock）
- **RingBuffer[T]**: 有界历史缓冲（300 帧）
- **PriorityEventQueue[T]**: 优先级队列 + FIFO + 容量溢出丢弃
- 15+ 注册 slots: latest_observation, observation_ring, event_queue, mission_graph, claim_graph_state, quest_state...
- **182 个导入者** — 真正的中央骨干

### types.py (167 行) — 类型系统

- 12 个 dataclass: Observation, TargetTrack, TargetCandidate, ObstacleField, CameraIntent, MovementIntent, InputLease, ProgressState, SkillResult...
- Observation 有 `image: Any = None` 字段（已修复）
- **所有 dataclass 都用 slots=True**

### mode_arbiter.py (123 行) — 12 模式状态机

- 优先级抢占: EMERGENCY_STOPPED 只能转到自己
- 7 个优先级级别: P0(0) → P6(100)

### events.py (37 行) — 中断和模式请求

---

## 四、execution/ — 执行层

### input_worker.py (337 行) — **生产级**

- 后台线程 `input-worker` 处理命令队列
- lease 机制: submit → validate → execute → deadman check → focus check
- RLock + 原子队列操作
- **所有物理输入都经过这里**

### safe_window_backend.py (907 行) — **生产级**

- Windows SendInput 后端
- 焦点验证: FindWindowW + AttachThreadInput + SetForegroundWindow
- 冷却期 2s 防振荡
- ALT key trick + topmost 技巧

### console_backend.py (173 行) — 干跑模式

- 所有操作只 print + 记录到 deque
- `is_target_focused()` 永远返回 True
- **默认后端**

### execution_runtime.py (421 行) — **原型**

- SemanticAction → ActionContract → InputLease → PhysicalReceipt → VerifierResult
- **只有 4 个导入者**，主生产流不用它
- 主 agents 用直接 InputWorker

### crash_recovery.py (434 行) — **部分接入**

- CrashDetector: 检测 stuck/black screen/process termination
- 6 阶段恢复状态机: DETECT → ASSESS → LAUNCH → RECONNECT → RESTORE → RESUME
- **检测在生产活跃**，完整恢复循环接入不完整

---

## 五、app_service/ — 应用服务层（6,330 行，32 文件）

### agent_controller.py (763 行) — **生产级核心控制器**

- 50+ 方法覆盖: 生命周期、技能 CRUD、校准、规划、战斗、E2E 测试
- 状态机: STOPPED → RUNNING → PAUSED → EMERGENCY_STOPPED
- **不直接调 LLM**，委托给 Planner
- 真 statethread 管理 PerceptionPipeline + ControllerLoop + Orchestrator
- **这是 self-programming agent 的潜在基础**

### skill_manager.py (778 行) — **生产级技能管理**

- 34 字段 SkillDefinition 数据模型
- 完整生命周期: 录制 → 编辑 → 验证 → 干跑 → 重放 → 版本 → 回滚
- JSON 持久化 + 版本管理
- **这是 capsule/skill 库的真实实现**

### api.py (380 行) — **真实 REST API**

- 45+ FastAPI 端点
- 覆盖: 健康检查、代理控制、校准、技能、规划、战斗、E2E、目标执行
- **Tauri GUI 的接入层**

### coding_agent.py (137 行) — **stub（LLM = None）**

- LLMProvider protocol，**默认 None**
- LLM None 时返回空结果
- 有 CodeSandboxExecutor 集成
- **基础设施在，但默认不工作**

### capsule_forge.py (312 行) — **partial stub**

- 可选 LLM 后端（默认 StubLlmBackend 返回空字符串）
- 生成 6 文件骨架: capsule.yaml, keymap.yaml, skills/index.json, classifiers, detectors, providers
- **无 LLM 时生成模板代码**

### universal_entry_agent.py (172 行) — **纯关键词匹配**

- 中英文关键词: daily/quest/combat/explore/upgrade/dialog/navigation
- 置信度 = 0.5 + (关键词数 × 0.2)，上限 1.0
- 7 个硬编码模板
- **没有 LLM**

### web_search_service.py (177 行) — **真实双后端**

- MiniMax MCP (127.0.0.1:15721) + SerpAPI + Stub fallback
- 自动检测: MiniMax → SerpAPI → Stub
- **真接了，不是 mock**

### goal_executor.py (697 行) — **生产级**

- 两条路径: DailyCommissionExecutor (快捷) 或 AgentLoop (完整)
- 学习补丁提取 + 持久化
- trust_level promotion: candidate → verified (2+ 验证)

### launcher.py (300 行) — **生产级**

- 一键启动: diagnostics → auto_repair → uvicorn backend → vite/tauri frontend
- 检查 Python/Node/npm/依赖/端口
- 进程监控 + 清理关闭

### mainline_api.py (195 行) — 任务控制 Cockpit

- 暴露: runner state, claims, beliefs, skills, benchmarks
- 线程安全状态管理

---

## 六、agent/ — Agent 实现（~2,300 行）

### autonomous_task_brain.py (663 行) — **生产级任务大脑**

- Plan → Execute → Verify 循环
- 用 HierarchicalPlanner (GLM-5.1) 做 LLM 规划
- DecisionMemory (SQLite) 存储成功/失败策略
- ClaimGraphWorker 做运行时验证
- ExplorationAgent 做慢路径探索
- SkillInductionGate 做技能归纳
- **这是最复杂的 agent 实现**

### zero_shot_agent.py (683 行) — **真实 VLM/LLM 集成**

- 直接 VLM → LLM → execute 管道
- 用 glm-4v-flash (VLM) + glm-5.1 (LLM)
- 内置 _ZhipuAPIClient 做 HTTP 调用
- **硬编码 keymaps**: GAME_KEYMAPS 字典（genshin + hsr）
- 最大 30 次迭代
- **没有 DecisionMemory 或 claim 验证**

### genshin_game_agent.py (748 行) — **原神专属代理**

- 连接 AutonomousTaskBrain 到原神感知/执行
- 异步 VLM 管道（3 秒间隔）
- 50+ semantic action handlers
- 电路断路器保护 VLM 故障
- **可共享外部 capturer（用于 live_factory 集成）**

### exploration_agent.py (190 行) — 慢路径探索

- VLM 驱动动作建议 + 安全过滤
- 关键词匹配回退
- **仅白名单动作**

---

## 七、llm/ — LLM 集成层（~700 行，13 文件）

### tool_schema.py (33 行)

- 15 ALLOWED_TOOLS + 5 FORBIDDEN_TOOLS
- **self-programming agent 的工具控制基础已存在**

### planner.py (116 行) — **真实 LLM 规划**

- GLM / MiniMax / Mock 三 provider + 自动 failover
- plan_combat() 用硬编码 playbook 模板
- explain_failure() 生成用户友好摘要

### model_router.py (58 行) — 4 级路由

- deterministic → local_vlm → cloud_llm → ask_user
- 阈值: 简单 ≤0.35, 本地 ≤0.75, 延迟 ≤1800ms, grounding ≥75%

### zhipu_vlm_provider.py (174 行) — **真实 VLM API**

- OpenAI 兼容 API
- 模型: glm-4v-flash
- 超时: 30s, max_tokens: 800-1024
- VisionOutputGuard 验证输出

### minimax_provider.py (43 行) — **真实 MiniMax API**

- 模型: MiniMax-M2.7
- 用于规划和失败解释

### vision_provider.py (111 行) — 协议定义

- VisionBackend, VisionLLMProvider protocols
- ImageInput, VisionResult, UIGroundingResult, ScreenStateResult 数据类

---

## 八、combat/ — 战斗系统

### genshin_combat_planner.py (324 行) — **规则驱动**

- 分析队伍元素能力 → 匹配敌人弱点 → 评分反应链 → 构建轮换
- 14 种元素反应定义（Vaporize 2.0x, Melt 2.0x, Overloaded 1.2x...）
- Boss-aware 保守 playbook
- **不用 LLM，纯规则**

### playbook_runtime.py (84 行)

- 优先级节点执行: 反射(100) → 高危(60-80) → 正常(30-50)
- 支持中断和检查点恢复

### reflex_evasion.py (59 行) — 50Hz 闪避反射

- DangerDetector → 危险评分 → 触发闪避
- DodgePolicy: 冷却 500ms, 最多连闪 3 次, 恢复窗口 1.2s

### danger_detector.py (295 行) — CV 危险检测

- 6 种信号: 地面危险区域(0.35), HP 下降(0.30), 弹幕(0.20), Boss 前摇(0.10), 体力临界(0.05)
- HSV 色彩空间分析 + 帧差法运动检测

---

## 九、navigation/ — 导航系统

### genshin_navigator.py (395 行) — **生产级原神导航**

- 世界图 Dijkstra 路径规划
- 小地图任务标记检测
- 传送序列生成
- 3D 相机扫描避障
- 预测性航向伺服
- DepthAnythingEstimator 深度估计

### universal_navigator.py (312 行) — 游戏无关门面

- adapter 模式: GenshinNavigatorAdapter, HsrNavigatorAdapter, NullNavigator
- `from_capsule()` 工厂方法
- **干净架构**

### quest_marker_follower.py (162 行) — 实时任务跟随

- 小地图 → 角度 → 相机伺服 → WASD 映射
- 逐步执行 + 到达检查

---

## 十、perception/ — 感知层（94 Python 文件）

### pipeline.py — 完整捕获管线

- ScreenCapturer → ViewportTransformer → FramePostProcessor → Observation
- 可配置 max_fps, stale_threshold
- 支持 add/remove post_processor（**热重载基础**）

### auto_calibrator.py — **硬编码原神**

- 原神 UI 地标: 小地图、HP 条、任务追踪器
- 参考分辨率: 1920x1080
- HSV 色彩启发式
- **不通用**

### auto_calibrator_v2.py (175 行) — **VLM 驱动通用校准**

- VLM 发现 UI 地标（health_bar, minimap, skill_icons, dialog_box）
- 启发式回退
- **比 V1 通用**

### generic_screen_classifier.py (125 行)

- VLM 屏幕状态分类 + 通用分类法
- 9 种状态: overworld, combat, dialog, menu, map, loading, cutscene, death, unknown
- 64 帧缓存

**genshin 专用文件: 4 个。通用文件: 89 个。**

---

## 十一、bagel/ — 信念归因系统（~2,255 行）

### fig_schema.py (625 行)

- 11 种信念状态: provisional, committed, confirmed, survived, suspect, falsified, noise_disturbance, retired, stale, posthoc_invalid, challenged
- DAG: BeliefNode, ActionNode, FeedbackNode, ProbeNode, TypedEdge
- 线程安全: threading.Lock + 原子版本号
- **生产级实现**

### runtime.py (698 行)

- 16 步 API（不是单个函数）: commit_belief → propose_action → materialize_action → receive_feedback → run_attribution_cycle...
- JIT 重新生成、延迟反馈桥、子图压缩
- **被 MainlineRunner 在失败时调用**

### belief_proposer.py (335 行) — **规则驱动，不是 LLM**

- 6 种失败模式分类: strategy, perception, execution, environment, resource, precondition
- 查询 DecisionMemory 获取相似成功策略
- 模板化假设生成（非 LLM）
- 置信度: 0.6 基础 + DecisionMemory 匹配提升到 0.9

### arbiter.py (220 行) — 阈值仲裁

- 核心反驳 → 立即证伪
- 分数 ≤ -1.0 → falsified, < -0.1 → suspect, ≥ 0.3 + ≥2 信号 → confirmed
- 3 次转换后振荡阻尼

### evidence_matrix.py (377 行) — 非对称评分

- 公式: `score = C_i - S_i + α × tanh(R_i / (ε + S_i))`
- 核心探测 3 倍权重否决

---

## 十二、learning/ — 学习系统（~2,000 行）

### meta_learning_bridge.py (305 行)

- `on_falsification_cycle()`: 分类失败 → 生成假设 → 提交 FIG → 记录 DecisionMemory → 检查技能归纳候选
- `on_exploration_result()`: 记录探索结果到 DecisionMemory
- **在 live_factory.py 真接线**

### parameterized_skill_induction.py (360 行)

- LCS 跟踪对齐
- 可变性 > 0.3 → 参数, 固定部分 → 字面量, 3+ 连续相似步 → 循环
- `induce_from_patterns()` 已实现（审计中添加）
- **在 live_factory.py 真接线**

### game_knowledge_store.py (543 行)

- SQLite: facts + source_trust + conflict_log 三表
- 源优先级: manual(100) > wiki(80) > vlm(50) > exploration(30) > inferred(20)
- 衰减: `conf × exp(-age×ln2/half_life) × (1 + log(1+access_count)×0.1)`
- prune_decayed() 自动清理
- **完整实现**

### decision_memory.py (246 行)

- SQLite: strategies 表（goal, capsule_id, screen_state, plan_json, success, duration, confidence）
- **被 MainlineRunner._inject_learned_strategy() 实际消费**
- **当前数据库: 0 条策略**（空库，准备好但没积累）

### evolution_engine.py (427 行)

- 失败 → 签名 → 修复会话 → 补丁草稿 → 沙盒验证 → 基准测试
- 订阅 StateBus "skill_result" 事件
- **修复循环存在但补丁不反馈执行**

### skill_induction/pipeline.py (97 行)

- TraceRecorder → EpisodeSegmenter → AnchorBinder → PromotionGate → SkillRegistry
- 6 级晋升: raw_trace → draft → experimental → candidate → stable → trusted
- **坐标专用技能被拒绝**

---

## 十三、planning/ — 规划系统

### mainline_runner.py (880 行) — **生产级主线执行**

执行循环:
1. 检查 input_claims
2. 注入 DecisionMemory 学习策略
3. 执行节点 + 重试
4. 验证 output_claims
5. 记录到 DecisionMemory
6. 更新 somatic state
7. Sentinel 干预检查
8. 发布 checkpoint（StateBus + 磁盘）
9. 失败时 BAGEL JIT 路由器图愈合

### mainline_live_bridge.py (254 行) — 真机桥接

接线: SafeWindowInputBackend + InputWorker + QuestMarkerFollower + SomaticStateSupervisor + SkillRegistry + UIFlowSkillAdapter + MainlineSkillExecutor + BossCombatBridge + CrashRecovery

### hierarchical_planner.py (257 行) — **真调 LLM**

- 用 GLM-5.1 做目标分解
- JSON 输出: steps + preconditions + verifiers
- 65+ semantic actions 列表
- learned_strategy 注入（来自 DecisionMemory）
- **回退**: 观察-行动循环

### mission_graph_v4.py (375 行)

- DAG + Kahn 拓扑排序
- 每个节点: input_claims + output_claims + belief_templates + budgets + fallbacks + probe_policy
- **claim-gated 执行**

---

## 十四、capsules/ — 游戏适配包

### capsule_protocol.py (187 行) — 干净协议

- Capsule 接口: install/activate/deactivate/uninstall
- CapsuleManifest: YAML 声明式
- CapsuleContext: StateBus + Pipeline + Orchestrator + ModeArbiter

### capsule_registry.py (329 行) — 完整生命周期

- register/activate/deactivate/unregister + rollback
- 动态 provider 加载 + 健康监控

### genshin/capsule.yaml (192 行)

- 能力: arpg_navigation, arpg_combat, danger_reflex, quest_following
- 技能: genshin_combat, genshin_dodge, genshin_navigation, genshin_daily_commission
- 7 个 providers
- UI anchors: map_button, inventory_button, teleport_confirm
- 完整 ARPG keymap

### genshin/providers.py (149 行) — **混合**

- ScreenClassifierProvider: **真实**（包裹 GenshinScreenClassifier）
- CombatDetectorProvider: **stub**（永远健康，无实际检测）
- CombatPlannerProvider: **简单**（危险→闪避 + 基础攻击循环）
- NavigatorProvider: **stub**（单步合成导航）
- DialogHandlerProvider: **stub**（合成对话状态）
- KnowledgeProvider: **简单**（keymap 查询）

### hsr/capsule.yaml (184 行)

- 技能: hsr_combat, hsr_navigation, hsr_claim_rewards, hsr_dialog
- 6 个 providers

### hsr/providers.py (261 行) — **比原神更完整**

- CombatPlannerProvider: **完整**（队伍分析 + 弱点匹配 + SP 预算 + 终极技能中断）
- NavigatorProvider: **真实**（传送规划 + 回退）
- 5 个 verifiers

---

## 十五、data/ + knowledge/ — 真实数据资产

### data/ (4.3MB)

| 文件 | 大小 | 内容 |
|------|------|------|
| combat_profiles/character_profiles.yaml | 48KB | 角色战斗数据（元素、武器、冷却、策略） |
| combat_profiles/team_profiles.yaml | 32KB | 队伍配置 |
| combat_profiles/hsr_team_profiles.yaml | 36KB | HSR 队伍 |
| decision_memory.db | 28KB | SQLite 策略存储（**0 条策略**） |
| skills/genshin_combat_skills.yaml | 6.4KB | 战斗技能 |
| skills/genshin_navigation_skills.yaml | 6.9KB | 导航技能 |
| skills/genshin_collection_skills.yaml | 5.4KB | 收集技能 |
| skills/versions/ | 8 个版本文件 | **技能版本管理** |
| bagel_events/events.jsonl | **3.85MB** | **大量 BAGEL 事件记录** |

### knowledge/ (913KB)

| 文件 | 大小 | 内容 |
|------|------|------|
| genshin_monsters.yaml | **92KB** | 160+ 怪物百科 |
| genshin_world_graph.yaml | **83KB** | 230+ waypoint, 420+ edge 导航图 |
| genshin_ui_system.yaml | **72KB** | UI 系统定义 |
| persona_characters.yaml | **48KB** | 角色人格 |
| genshin_resources.yaml | **38KB** | 资源数据 |
| hsr_enemies.yaml | **79KB** | HSR 敌人 |
| hsr_characters.yaml | **23KB** | HSR 角色 |
| online_guide_system.py | **26KB** | 在线攻略（**mock**） |
| genshin_character_progression.py | **22KB** | 角色培养 |
| genshin_f2p_builds.py | **21KB** | 0 氪构建 |
| weapon_refinement_priority.py | **15KB** | 武器精炼 |

---

## 十六、scripts/ — 入口脚本

### run_mainline.py (159 行)

- 主线任务执行入口
- 两种模式: 干跑(ConsoleInputBackend) vs 真机(SafeWindowInputBackend)
- 加载 GenshinScreenClassifier + QuestStateMachine
- 通过 MainlineLiveBridge 接真实游戏窗口
- **生产入口**

### run_kernel.py (267 行)

- 完整 5 平面内核
- dxcam(真实) 或 DemoCapturer(合成)
- YOLO + Tracker 可选
- **生产入口**

### run_final_demo.py (51 行) + run_testbed.py (14 行)

- pygame 测试窗口演示
- **非生产**

---

## 十七、tests/ — 测试分析

| 指标 | 数值 |
|------|------|
| 测试文件数 | 262 |
| 总测试数 | 4323 |
| 使用 mock 的文件 | 80 (30%) |
| 引用 genshin 的文件 | 74 (28%) |
| **连接真实游戏窗口的文件** | **0** |

最大测试文件:
1. test_closed_loop_runner.py — 949 行
2. test_quest_systems.py — 848 行
3. test_gap_fill_integration.py — 745 行

**关键事实**: 没有任何测试真正启动游戏窗口或连接真实 API。所有 SafeWindowInputBackend 测试用 mock SendInput。

---

## 十八、诚实评估

### 真实能做到的

1. **干跑闭环**: 从屏幕捕获到动作输出的完整管线，在 console backend 下能跑
2. **5 平面架构**: StateBus 是真正的中央骨干，182 个导入者
3. **安全输入层**: InputWorker + SafeWindowBackend + Deadman Switch 是生产级的
4. **capsule 插件系统**: 协议干净，生命周期完整，HSR 比原神更完整
5. **知识数据资产**: 400KB+ 真实游戏数据（怪物、世界图、UI 系统）
6. **LLM 集成**: 智谱 GLM-4V + GLM-5.1 真接入，有 4 级路由
7. **BAGEL 事件记录**: 3.85MB 真实事件数据，说明在某种场景下跑过

### 真实做不到的（或严重存疑）

1. **原神真实游戏自主跑通**: 没有**任何**测试连接真实游戏窗口。DecisionMemory 是空的（0 条策略）。Genshin providers 多数是 stub。
2. **CerebrumAgentImpl 做 LLM 规划**: 它是 keyword fallback。真正的 LLM 规划在 HierarchicalPlanner 和 zero_shot_agent，但 CerebrumAgent 是 live_factory 用的。
3. **CodingAgent 生成代码**: LLM 默认 None，返回空结果。
4. **在线攻略搜索**: online_guide_system.py 是 mock。
5. **自主 skill 归纳→执行闭环**: EvolutionEngine 的补丁不反馈执行。DecisionMemory 空。
6. **self-programming**: 完全不存在。没有 agent 能修改自己的代码。

### 架构成熟度 vs 功能成熟度

| 维度 | 架构 | 功能 |
|------|------|------|
| 5 平面管线 | **90%** | **40%**（干跑能跑，真机未验证） |
| Capsule 系统 | **95%** | **50%**（协议完美，Genshin providers 半 stub） |
| 战斗系统 | **80%** | **60%**（规则驱动可用，无 LLM 战术） |
| 导航系统 | **85%** | **65%**（Dijkstra + 传送可用，真机未验证） |
| LLM 集成 | **75%** | **50%**（真接入，但 CerebrumAgent 没用 LLM） |
| 学习系统 | **80%** | **20%**（代码完整，DecisionMemory 空，没实际积累） |
| BAGEL | **90%** | **40%**（代码完整，3.85MB 事件，但归因→学习→执行闭环没验证） |
| 知识资产 | **70%** | **60%**（400KB+ 数据存在，但没被 LLM prompt 消费） |

### 一句话总结

**这是一个架构完善、安全层生产级、知识资产丰富、但功能验证严重不足的系统。** 架构骨架 90%，实际能跑的功能约 40-50%。最关键的缺口：没有真机验证、没有 self-programming 能力、CerebrumAgent 是 keyword fallback、DecisionMemory 是空的。
