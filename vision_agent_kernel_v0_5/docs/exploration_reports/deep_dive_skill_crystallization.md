# Deep Dive: Skill 自主沉淀与自我成长能力

**成熟度: 5/10** — 架构完整但落地薄弱，核心验证和泛化机制仍是 stub。

## 核心发现

### 三套并行归纳系统未统一
1. `learning/skill_induction/pipeline.py` — InductionPipeline (TraceRecorder → EpisodeSegmenter → AnchorBinder → PromotionGate)
2. `learning/skill_induction_gate.py` + `recording/semantic_distiller.py` — SkillInductionGate (面向 AutonomousTaskBrain)
3. `planning/skill_inductor.py` — SkillInductor (基于 Experience + SkillRecipe 类型)

三套系统使用不同类型 (SkillDef vs SkillCatalogEntry vs SkillRecipe)，互不关联。

### 完整归纳管道存在但关键环节空洞
- **TraceRecorder**: 设计良好，支持锚点和坐标两种粒度
- **EpisodeSegmenter**: 仅按 screen_state 字符串变化分割，过于粗糙
- **AnchorBinder**: claim 推断是硬编码关键词匹配
- **PromotionGate**: 六层阶梯设计严格 (raw_trace → draft → experimental → candidate → stable → trusted)，但 InductionPipeline 传入的 successes/failures 始终为 0
- **verify_in_sandbox**: 对 induced_ 前缀技能只做结构检查

### 失败修复飞轮
EvolutionEngine: 失败 → 签名 → 修复会话 → 补丁 → 沙盒验证 → 版本化技能
- 但 SkillPatchSuggester 仅两个 if 分支
- RepairValidator 只做结构检查
- RepairBenchmarkRunner 返回合成数据
- **补丁批准后不影响实际执行逻辑**

### Skill 泛化性有限
归纳出的技能是固定步骤序列，没有参数提取、条件分支、循环结构。

### DecisionMemory 未闭环
best_strategy_for 查询结果没有直接影响 planner 的计划生成。

## 8 个关键 Gap

1. **三套归纳系统未统一** — 统一为 SkillDef 输出
2. **沙盒验证空壳** — 实现录制回放验证器
3. **补丁不反馈执行** — 批准后生成新版本 SkillDef
4. **缺乏参数化归纳** — 从多次成功 trace 提取可变部分
5. **DecisionMemory 未闭环** — 注入 planner 作为优先策略
6. **失败分析过简** — 引入 LLM 分析或语义聚类
7. **SkillRegistry 无持久化** — 重启后归纳技能丢失
8. **GenshinFailureAnalyzer 硬耦合** — 抽象为 FailureAnalyzer 协议
