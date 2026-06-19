# Sparkle 通用长程复杂任务执行能力 — 综合评估

**日期**: 2026-06-02
**评估维度**: 自我成长、Skill 自主沉淀、元学习、Scaffold
**最终目标**: 通用游戏主线通关（原神为当前测试游戏）

---

## 一、四大核心能力成熟度评分

| 能力维度 | 评分 | 状态 |
|---------|------|------|
| **Scaffold 基础设施** | 7.5/10 | 超出原型，80-85% 可跨游戏复用 |
| **元学习 (BAGEL)** | 6.5/10 | 理论卓越，闭环缺失 |
| **Skill 自主沉淀** | 5/10 | 架构完整，落地薄弱 |
| **未知场景推理** | 5/10 | 循环设计正确，执行浅显 |

**综合评分: 6/10** — 系统已有扎实的骨架，但关键的认知闭环尚未打通。

---

## 二、能力现状详析

### 2.1 Scaffold: 可靠的长程运行骨架 ✅ (7.5/10)

**已具备:**
- L0-L9 多层神经系统（100Hz 反射 → 0.1Hz 战略规划）
- 多层级恢复（节点→任务→会话→账号），CheckpointStore 原子写入+SHA256
- 三层可靠性度量（Wilson 区间 + 上下文粒度自动降级）
- Claim-Centric Runtime（声明式执行保证，1222 行）
- VLM/LLM 认知 scaffold（四级路由、节流、预算、输出安全校验）
- Sentinel 体感监控（8 个恢复配方 + 预算制）

**短板:**
- CrashRecovery 逻辑成功而非物理成功（不重启游戏进程）
- Sentinel 恢复验证 verify_restabilized() 全返回 True
- 遥测回放缺失（replay_index.py 和 video_recorder.py 空文件）
- 全局 API 成本预算缺失（只有 per-minute/per-task）

### 2.2 元学习 BAGEL: 理论卓越但闭环缺失 ⚠️ (6.5/10)

**已具备:**
- FIG Schema（624 行，10 种状态、5 种节点、9 种边）— 9/10
- 非对称证据评分（核心反驳 3 倍权重否决）— 8/10
- 安全信念修订（级联风险评估、双阈值、振荡阻尼）— 8/10
- Popperian 证伪探测（健全性检查、禁忌探针家族）— 7/10
- EventStore（图重建、审计追溯）— 9/10

**致命缺失:**
- **无信念提出者**: 信念被证伪后，系统无法生成替代假设。这是"元学习"的最核心缺失——没有假设生成就没有学习循环。
- **元学习闭环断裂**: BAGEL 归因结果不流入 DecisionMemory 或 SkillInductionGate。信念修订和 skill 学习是两条平行线。
- **归因精度不足**: 无法区分失败模式（策略/感知/执行/环境），纯定量无语义分析。
- **omitted_belief.py 孤立**: 不变量发现设计良好但从未被调用。

### 2.3 Skill 自主沉淀: 架构完整但落地薄弱 ⚠️ (5/10)

**已具备:**
- 完整归纳管道：TraceRecorder → EpisodeSegmenter → AnchorBinder → PromotionGate
- 六层晋升阶梯（raw_trace → trusted）带 Wilson 统计检验
- 失败修复飞轮：EvolutionEngine 自动捕获失败 → 补丁建议 → 沙盒验证
- DecisionMemory（SQLite 持久化 + 修剪）
- SkillDef 数据模型（适用性、步骤、claim、信念模板、回退）

**关键问题:**
- **三套并行归纳系统未统一**: InductionPipeline / SkillInductionGate / SkillInductor 使用不同类型互不关联
- **沙盒验证空壳**: RepairValidator 只做结构检查，RepairBenchmarkRunner 返回合成数据
- **补丁不反馈执行**: 批准的补丁不影响实际技能执行逻辑
- **归纳出的 skill 无参数化**: 固定步骤序列，无参数提取、条件分支、循环
- **SkillRegistry 无持久化**: 重启后归纳的技能丢失

### 2.4 未知场景推理: 循环设计正确但执行浅显 ⚠️ (5/10)

**已具备:**
- SPARKLE §11 安全探索循环（Observe → Hypothesize → Probe → Verify → Attribute → Learn → Escalate）
- ExplorationAgent VLM 延迟不匹配检测（生产就绪）
- ZeroShotAgent 完整 VLM→LLM→Action 循环

**致命缺失:**
- **假设生成是浅显的**: 每 affordance 一个假设，无组合推理
- **探测执行是模拟的**: probe() 只检查目标是否存在，不实际交互
- **无假设修正**: 探测失败后无修正假设的代码路径
- **与 BAGEL 完全断开**: 探索结果不反馈到信念系统
- **ExplorationAgent 无状态**: 不维护世界模型，不计算信息增益

---

## 三、从 P0 问题到通用能力的阻碍分析

要实现"像人一样在陌生环境里思考、推理、探索、交互、验证、学习成长"，当前系统需要跨越 **5 个关键鸿沟**：

### 鸿沟 1: 信念生成 → 假设驱动探索（当前完全缺失）

人在陌生环境中会**提出假设**（"这个 NPC 可能需要先完成前置任务"），然后设计实验验证。当前 BAGEL 只能**证伪**已有信念，不能**生成新假设**。

**需要**: `BeliefProposer` 模块 — 分析证伪证据 → 提出 1-3 个结构化替代假设 → 注入 FIG → 驱动新行动

### 鸿沟 2: 归因 → 学习闭环（当前断裂）

人能从失败中**抽象出规律**（"水元素史莱姆免疫水攻击"），形成可迁移的知识。当前 BAGEL 归因和 learning 系统是两条平行线。

**需要**: BAGEL 归因结果 → DecisionMemory（含失败模式）→ SkillInductionGate（含信念上下文）→ 新 SkillDef

### 鸿沟 3: Skill 泛化（当前硬编码）

人的技能是**参数化**的（"打 Boss" 不限于特定 Boss，而是有通用策略模板）。当前归纳出的 skill 是固定步骤序列。

**需要**: 从多次成功 trace 中提取可变部分作为参数，固定部分作为模板；支持条件分支和循环。

### 鸿沟 4: 探索 → 信念 → 技能 全链路（当前三段独立）

人探索未知场景 → 积累经验 → 形成直觉 → 沉淀为技能。当前探索（UnknownSceneHandler）、信念（BAGEL）、技能（learning/）三段独立。

**需要**: 探索结果作为信念证据 → 信念修订触发学习 → 学习产生新技能 → 新技能减少未来探索需求

### 鸿沟 5: 长程知识积累与遗忘（当前缺失）

人在数十小时游戏中会建立**世界模型**（地图知识、NPC 关系、任务链依赖）。当前 DecisionMemory 用 SQLite + LIKE 模糊匹配，粒度粗、无冲突处理。

**需要**: 结构化世界知识图谱 + 增量更新 + 冲突消解 + 遗忘机制

---

## 四、优先级路线图

### Phase 1: 打通 P0 阻断问题（1-2 周）
1. 修复 Observation 无 image 字段（P0-1）
2. 修复 detect_dialog_end() bug（P0-2）
3. 修复 SomaticStateSupervisor 绕过 StateBus（P0-3）
4. 修复 core/state_bus.py 反向依赖（P0-4）

### Phase 2: 打通核心闭环（3-4 周）
1. **实现 BeliefProposer** — BAGEL 的假设生成模块
2. **统一归纳系统** — 合并三套归纳为一条管道
3. **实现元学习桥梁** — BAGEL 归因 → DecisionMemory → SkillInduction
4. **实现沙盒验证** — 录制回放验证器
5. **连接 UnknownSceneHandler → BAGEL** — 探索结果作为信念证据

### Phase 3: 增强泛化能力（3-4 周）
1. **参数化 Skill 归纳** — 从多次 trace 提取可变参数
2. **归因细化** — 失败模式分类（策略/感知/执行/环境）
3. **假设驱动探索** — 信息增益计算 + 世界模型
4. **JIT 路由器泛化** — 可扩展修复策略注册表

### Phase 4: 长程成长（2-3 周）
1. **SkillRegistry 持久化** — JSON/SQLite 后端
2. **全局 API 成本预算** — 每小时/每天上限
3. **Sentinel 恢复验证** — 实际视觉验证
4. **DriftDetector 自动化** — 周期性检测

---

## 五、与"通用游戏主线通关"目标的差距

当前系统距离"通用游戏主线通关"还差多远？

**已能做的:**
- 预定义的日常任务闭环（DailyLoopExecutor 已实现 15+ 节点 DAG）
- 预定义的战斗执行（Playbook + BossCombatRuntime）
- 预定义的导航和传送（Dijkstra + QuestMarkerFollower）
- 简单的对话处理（GenshinDialogHandler）
- 崩溃后状态恢复（检查点系统）

**不能做的（关键缺失）:**
- 面对从未见过的任务类型，自主规划执行路径
- 从失败中抽象出可迁移的规律（而非简单重试）
- 在探索中积累世界知识（而非每次都从头开始）
- 根据当前场景动态调整策略（而非遵循固定模板）
- 长程任务中的上下文累积和决策优化

**根本原因:** 系统缺乏**假设驱动的探索→归因→学习→成长**的完整认知闭环。当前架构是"精心编排的自动化"，不是"自主学习的智能体"。

**实现目标的核心突破点:** BeliefProposer + 元学习桥梁 + 参数化 Skill 归纳。这三者打通后，系统将从"执行预定义任务的自动化工具"进化为"能自主学习成长的智能体"。

---

## 探索报告索引

| 报告 | 内容 |
|------|------|
| [final_exploration_summary.md](final_exploration_summary.md) | Round 1-3 全部 gap 汇总（P0-P3） |
| [agent_a_runtime_architecture.md](agent_a_runtime_architecture.md) | 核心运行时架构摸底 |
| [agent_a_round2_crossplane_gaps.md](agent_a_round2_crossplane_gaps.md) | 跨平面调用链验证 |
| [agent_b_planning_task_system.md](agent_b_planning_task_system.md) | 规划与任务系统摸底 |
| [agent_b_round2_call_chain_gaps.md](agent_b_round2_call_chain_gaps.md) | 端到端调用链验证 |
| [agent_c_interaction_perception.md](agent_c_interaction_perception.md) | 交互与感知层摸底 |
| [agent_c_round2_perception_action_gaps.md](agent_c_round2_perception_action_gaps.md) | 感知到动作管线验证 |
| [round3_architecture_compliance.md](round3_architecture_compliance.md) | 架构合规性审查 |
| [deep_dive_skill_crystallization.md](deep_dive_skill_crystallization.md) | Skill 沉淀与自我成长深度审查 |
| [deep_dive_meta_learning_bagel.md](deep_dive_meta_learning_bagel.md) | BAGEL 元学习深度审查 |
| [deep_dive_scaffold.md](deep_dive_scaffold.md) | Scaffold 基础设施深度审查 |
