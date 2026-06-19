# Deep Dive: Scaffold 基础设施

**成熟度: 7.5/10** — 超出原型阶段，正在向生产系统演进。80-85% 可跨游戏复用。

## 核心发现

### 多层级恢复系统（节点→任务→会话→账号）
- **CheckpointStore**: 原子写入 + SHA256 校验 + 滚动窗口
- **QuestContextPersistence**: 完整任务上下文快照（20+ 字段）
- **SessionLifecycle**: INITIALIZING → RUNNING → PAUSED/RECOVERING → SHUTTING_DOWN
- **AccountState**: UID、AR、角色、武器、资源完整快照
- **实际证据**: checkpoints/ 目录约 200+ 检查点，跨度 24 小时

### 三层可靠性度量（最精密的 QA 机制）
1. VerifierReliability — Wilson 区间估计
2. RecipeReliability — claim+recipe 组合成功率
3. SkillClaimReliability — skill+claim+recipe 组合跟踪
- 0-5 级上下文粒度自动降级
- DriftDetector 监控 4 类漂移

### VLM/LLM 认知 Scaffold
- ModelRoutePolicy 四级路由：确定性→本地VLM→云LLM→用户确认
- VLMPostProcessor 3秒节流 + 异步调用 + 结果缓存
- LLMRequestGuard: 每分钟6次、每任务3次、6000 token 预算
- VisionOutputGuard: 拒绝包含物理动作指令的 VLM 输出

### Claim-Centric Runtime（1222 行）
- ClaimGraph 级联失效、UncertaintyPolicy 7 种行动、StabilizationTracker 自适应窗口
- DelayedAuditEngine 延迟审计、RunJournal → DecisionMemoryPacket

### 长程运行保障
- AgentLoop L0-L9 多层神经系统（100Hz 反射 → 0.1Hz 战略规划）
- LongRunWatchdog: 内存256MB/h、过时帧率10%、队列深度4096
- SentinelRuntime: 8 个恢复配方 + 预算制
- SomaticStateSupervisor: 体力/HP/氧气/环境危险 HSV 检测

## 7 个关键 Gap

1. **Sentinel 恢复验证空操作** — verify_restabilized() 全返回 True
2. **缺少全局 API 成本预算** — 只有 per-minute/per-task，无每小时/每天上限
3. **CrashRecovery 逻辑成功而非物理成功** — 无实际游戏进程重启
4. **遥测回放缺失** — replay_index.py 和 video_recorder.py 是空文件
5. **AgentLoop 迭代上限过低** — max_plan_iterations=20，主线需要更多
6. **ReliabilityStore 快照恢复 bug** — setattr 修改 frozen dataclass
7. **Scaffold 通用性** — 约 15-20% 代码需换游戏时修改（HSV 阈值、按键序列、游戏知识）
