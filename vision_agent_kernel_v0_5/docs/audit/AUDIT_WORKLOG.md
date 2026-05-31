# 文档体系审查工作流

> 审查人: Claude Opus 4.7 | 分支: 验收文档清单实现情况 | 日期: 2026-05-31

## 审查对象

共 17 份新生成文档 + 1 份原始 checklist，分四类：

### A. 核心场景文档 (7份)
| ID | 文件 | 行数 | 内容 |
|----|------|------|------|
| A1 | GENSHIN_UI_OPERATION_SCENARIOS.md | 1335 | 9个UI操作场景 |
| A2 | GENSHIN_QUEST_SCENARIO_BREAKDOWN.md | 1374 | 16个任务场景 |
| A3 | GENSHIN_COMBAT_SCENARIO_BREAKDOWN.md | 550 | 16个战斗场景 |
| A4 | GENSHIN_EXPLORATION_SCENARIO_BREAKDOWN.md | 480 | 11个探索场景 |
| A5 | GENSHIN_DAILY_ROUTINE_SCENARIOS.md | 1252 | 3层日常循环 |
| A6 | GENSHIN_PUZZLE_ENCYCLOPEDIA.md | 1009 | 29类解谜 |
| A7 | GENSHIN_LONG_CHAIN_SCENARIOS.md | 708 | 5个长程串联 |

### B. 进阶链路文档 (2份)
| ID | 文件 | 行数 | 内容 |
|----|------|------|------|
| B1 | GENSHIN_CHARACTER_PROGRESSION_CHAIN.md | 612 | 角色养成链 |
| B2 | GENSHIN_MAINLINE_PROGRESSION_CHAIN.md | 459 | 主线推进链 |

### C. 分析文档 (2份)
| ID | 文件 | 行数 | 内容 |
|----|------|------|------|
| C1 | GENSHIN_CAPABILITY_GAP_ANALYSIS.md | ~600 | 能力缺口分析 |
| C2 | GENSHIN_PERCEPTION_PRECISION_MATRIX.md | 431 | 感知精度矩阵 |

### D. 系统架构文档 (6份)
| ID | 文件 | 行数 | 内容 |
|----|------|------|------|
| D1 | GENSHIN_ERROR_RECOVERY_ARCHITECTURE.md | 1365 | 错误恢复架构 |
| D2 | GENSHIN_SESSION_PERSISTENCE_MODEL.md | 1752 | 会话持久化 |
| D3 | GENSHIN_HUMAN_AGENT_COLLABORATION.md | 813 | 人机协作协议 |
| D4 | GENSHIN_CONTENT_VERSIONING.md | 883 | 内容版本适配 |
| D5 | GENSHIN_IMPLEMENTATION_ROADMAP.md | 1759 | 实现路线图 |
| D6 | GENSHIN_E2E_VALIDATION_FRAMEWORK.md | 1273 | 端到端验证 |

### E. 基础文档 (1份)
| ID | 文件 | 内容 |
|----|------|------|
| E1 | GENSHIN_AUTONOMOUS_COMPLETION_CAPABILITY_CHECKLIST.md | 274项能力+210 corner cases |

---

## 审查维度

### D1: 内容完整性
- 承诺的章节是否全部存在
- 每个场景是否包含所有必需字段（子步骤、能力映射、验收标准、异常处理）
- 附录是否完整

### D2: 跨文档一致性
- 能力 ID 在各文档间是否一致（同一 ID 指向同一能力）
- 统计数字是否对得上（如场景数、能力数）
- 交叉引用是否正确

### D3: 内部一致性
- 文档内部是否有矛盾
- 表格数据是否自洽
- 编号是否连续无遗漏

### D4: 实用性
- 场景描述是否足够具体可实施
- 能力映射是否合理（不过度也不缺失）
- 失败恢复策略是否可行

### D5: 与代码库对齐
- 引用的 Sparkle 架构组件是否与实际代码一致
- 能力 ID 是否与 checklist 中定义的匹配

---

## 审查执行计划

### Round 1: 初始审查 (3 agent + 主线)
- **Agent-A**: 审查 A1-A7 (核心场景文档) → 输出 `audit/audit_A_core_scenarios.md`
- **Agent-B**: 审查 B1-B2 + C1-C2 (进阶链路+分析文档) → 输出 `audit/audit_B_chains_analysis.md`
- **Agent-C**: 审查 D1-D6 (系统架构文档) → 输出 `audit/audit_D_architecture.md`
- **主线**: 审查 E1 (checklist 基础文档) + 汇总交叉一致性

### Round 2: 修复
- 根据审查报告修复问题
- 每类修复独立 git commit

### Round 3: 修复验证 (3 agent)
- 验证 Round 1 发现的问题是否全部修复
- 检查修复是否引入新问题
- 输出 `audit/verify_R1_fixes.md`

### Round 4: 深度交叉审查
- 能力 ID 全量交叉比对
- 场景覆盖完整性验证
- 输出 `audit/cross_reference_audit.md`

---

## 进度追踪

| 阶段 | 状态 | 开始时间 | 完成时间 |
|------|------|----------|----------|
| R1 初始审查 | ✅ 完成 | 2026-05-31 | 2026-05-31 |
| R1 修复 | ✅ 完成 | 2026-05-31 | 2026-05-31 |
| R3 修复验证 | 🔄 进行中 | 2026-05-31 | - |
| R4 深度交叉 | 🔄 进行中 | 2026-05-31 | - |
| 最终报告 | ⏳ 待开始 | - | - |

## R1修复详情

### P0修复 (6项，全部完成)
- ✅ P0-1: AQ-005「璃月港的繁星」已补入（90行新内容）
- ✅ P0-2: 统计表已修正（8→9，16→17）
- ✅ P0-3: 层级命名已修复（2处引用）
- ✅ P0-4: 周本/秘境已区分（雷音权现+最胜紫晶）
- ✅ P0-5: AR关系已修正（改为逐级描述）
- ✅ P0-6: AR经验值已修正（294,200→~329,200）

### R1修复Git提交
- commit `ec05f89`: fix: 修复审查发现的P0问题

## R3/R4 验证Agent (3个并行)

1. **P0修复验证** (agent aefeec38)
   - 验证6个P0修复是否完成
   - 检查是否引入新问题

2. **交叉引用一致性** (agent a80207c3)
   - 能力ID系统一致性
   - 数据一致性（公子等级、AR范围等）
   - 场景数量验证

3. **技术参数深度验证** (agent a7a26398)
   - 错误恢复架构priority值
   - 会话持久化JSON Schema
   - 人机协作F8热键
   - 实现路线图工时核算
