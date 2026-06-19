# Deep Dive: 元学习 (BAGEL) 与未知场景推理

**成熟度: 6.5/10** — 理论设计卓越，但缺少关键的信念生成机制和元学习闭环。

## 核心发现

### BAGEL 信念系统（fig_schema.py 624行，评分 9/10）
- 10 种信念生命周期状态、5 种节点类型、9 种边类型
- 事后插入拒绝（防止事后合理化）
- CausalBridgeNode、CondensedNode、BeliefIdentity 两阶段身份
- 线程安全、快照一致性
- **缺失：假设生成机制** — fig_schema 定义了如何存储信念，但没有任何东西创建新信念

### Evidence Matrix（376行，评分 8/10）
- 非对称评分公式：`C_i - S_i + alpha * tanh(R_i / (epsilon + S_i))`
- 核心反驳 3 倍权重否决
- Beta-Bernoulli 审计员可靠性跟踪（存在但未使用）

### Arbiter + Safe Revision（评分 8/10）
- 振荡阻尼（6 次转换后抑制）、临时到期
- 级联风险评估：`cascade_risk = affected_ratio * coupling * coupling_weight`
- 双阈值（safe_mode kappa=0.35 vs performance_mode 0.55）

### UnknownSceneHandler（评分 5/10）
- SPARKLE §11 安全探索循环设计正确
- 但：探测执行是模拟的、假设生成浅显（每 affordance 一个）、无假设修正
- **与 BAGEL 完全断开** — 探索结果不反馈到信念系统

### ExplorationAgent（评分 5/10）
- VLM 延迟不匹配检测（生产就绪特性）
- 三级回退：VLM → OCR → 首个可交互元素
- 但：无状态、无学习、无信息增益计算

### ZeroShotAgent（评分 5/10）
- 完整 VLM→LLM→Action 循环
- 但：无 BAGEL、无记忆（仅 5 步历史）、无归因修正

## 6 个关键 Gap

1. **信念提出者缺失（Critical）** — 信念被证伪后无替代假设生成。需要 BeliefProposer 模块。
2. **归因精度不足（High）** — 无法区分失败模式（策略 vs 感知 vs 执行 vs 环境变化），纯定量无语义。
3. **元学习闭环断裂（High）** — BAGEL 信念修订结果不流入 DecisionMemory 或 SkillInductionGate。
4. **omitted_belief.py 孤立（Medium）** — 良好的不变量发现设计但从未被调用。
5. **探索策略浅显（Medium）** — affordance 驱动而非假设驱动，无信息增益计算。
6. **JIT 路由器脆弱（Medium）** — 三种硬编码修复模式，基于关键词匹配。
