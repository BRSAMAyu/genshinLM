# 交叉引用一致性检查报告

> **检查日期**: 2026-05-30
> **检查范围**: 原神文档体系关键数据一致性审查

---

## 能力ID系统

| 文档 | 编号系统 | 状态 |
|------|---------|------|
| GENSHIN_UI_OPERATION_SCENARIOS.md | 能力标签 R-01~R-11，同时使用 P-01, P-09 等 P 系列标签 | ⚠️ 混用 R/P 标签 |
| GENSHIN_QUEST_SCENARIO_BREAKDOWN.md | AQ-001~AQ-CH5-01 (不连续，有跳跃) | ⚠️ 编号不连续 |
| GENSHIN_COMBAT_SCENARIO_BREAKDOWN.md | 1-16 连续编号 | ✅ |
| GENSHIN_EXPLORATION_SCENARIO_BREAKDOWN.md | 1-11 连续编号 | ✅ |
| GENSHIN_LONG_CHAIN_SCENARIOS.md | 1-5 连续编号 | ✅ |
| GENSHIN_DAILY_ROUTINE_SCENARIOS.md | DL-01~DL-07 | ✅ |
| GENSHIN_PUZZLE_ENCYCLOPEDIA.md | E/P/R/N/I 多系列标签 | ⚠️ 多系列混用 |

---

## 数据一致性

| 数据项 | 文档A | 文档B | 一致性 |
|--------|-------|-------|--------|
| 公子推荐等级 | GENSHIN_MAINLINE_PROGRESSION_CHAIN.md (Lv 45-50) | GENSHIN_QUEST_SCENARIO_BREAKDOWN.md (Lv 45-50) | ✅ 一致 |
| 第一章AR范围 | GENSHIN_MAINLINE_PROGRESSION_CHAIN.md (AR 23-28) | GENSHIN_QUEST_SCENARIO_BREAKDOWN.md (AR 23-28) | ✅ 一致 |
| 战斗场景数量 | GENSHIN_COMBAT_SCENARIO_BREAKDOWN.md (16个) | 总览表格确认 | ✅ 一致 |
| 探索场景数量 | GENSHIN_EXPLORATION_SCENARIO_BREAKDOWN.md (11个) | 总览表格确认 | ✅ 一致 |
| 解谜类型数量 | GENSHIN_PUZZLE_ENCYCLOPEDIA.md (29类) | 附录C确认 | ✅ 一致 |
| 日常层数 | GENSHIN_DAILY_ROUTINE_SCENARIOS.md (3层) | 第八章确认 | ✅ 一致 |

---

## 角色突破等级与AR对应关系

| 突破阶段 | 等级上限 | AR要求 | 一致性 |
|----------|---------|--------|--------|
| Lv 20突破 | 20→40 | AR 15 | ✅ |
| Lv 40突破 | 40→50 | AR 20 | ✅ |
| Lv 50突破 | 50→60 | AR 25 | ✅ |
| Lv 60突破 | 60→70 | AR 30 | ✅ |
| Lv 70突破 | 70→80 | AR 35 | ✅ |
| Lv 80突破 | 80→90 | AR 40 | ✅ |

---

## 各章节关键Boss等级要求

| 章节 | Boss | 文档A (MAINLINE) | 文档B (QUEST) | 文档C (COMBAT) | 一致性 |
|------|------|------------------|----------------|----------------|--------|
| 序章 | 风魔龙·特瓦林 | Lv 20-35 | Lv 20-35 (无明确标注) | 场景4: ★★级 | ⚠️ 数值一致，但COMBAT无具体等级 |
| 第一章 | 公子·达达利亚 | Lv 40-50 | Lv 45-50 | 场景5: ★★★级 | ⚠️ MAINLINE写Lv40-50，QUEST写Lv45-50 |
| 第二章 | 女士·罗莎琳 | Lv 50-60 | Lv 50-60 (无明确标注) | 场景6: ★★★级 | ⚠️ MAINLINE与QUEST数值不一致 |
| 第三章 | 正机之神·散兵 | Lv 60-80 | Lv 60-80 (无明确标注) | 场景8: ★★★★级 | ✅ 一致 |
| 第四章 | 吞噬一切的巨鲸 | Lv 80-85 | Lv 70-80 (无明确标注) | 场景9: ★★★★级 | ⚠️ MAINLINE写Lv70，QUEST写Lv80-85 |

---

## 发现的问题

### [P1] 公子推荐等级不一致

**问题描述**: `GENSHIN_MAINLINE_PROGRESSION_CHAIN.md` 中公子推荐等级为 Lv 40-50，而 `GENSHIN_QUEST_SCENARIO_BREAKDOWN.md` 中第一章第三幕(AQ-006)推荐等级为 Lv 45-50。

**差异**:
- MAINLINE: "最低角色等级 Lv 40 / 推荐角色等级 Lv 45-50"
- QUEST: "推荐等级 Lv 45-50"

**建议修复**: 统一为 "最低Lv 40，推荐Lv 45-50"。

---

### [P2] 女士推荐等级不一致

**问题描述**: `GENSHIN_MAINLINE_PROGRESSION_CHAIN.md` 中女士推荐等级为 Lv 50-60，但QUEST文档中没有明确标注。

**差异**:
- MAINLINE: "最低角色等级 Lv 50 / 推荐角色等级 Lv 55-60"

**建议修复**: 在QUEST文档中补充女士Boss的推荐等级。

---

### [P3] 巨鲸推荐等级不一致

**问题描述**: `GENSHIN_MAINLINE_PROGRESSION_CHAIN.md` 中巨鲸推荐等级为 Lv 80-85，而 `GENSHIN_QUEST_SCENARIO_BREAKDOWN.md` 中第四章第一幕(AQ-CH4-01)没有明确标注Boss等级。

**差异**:
- MAINLINE: "最低角色等级 Lv 70 / 推荐角色等级 Lv 80-85"

**建议修复**: 在QUEST文档中补充巨鲸Boss的推荐等级。

---

### [P4] 能力标签混用

**问题描述**: UI_OPERATION_SCENARIOS.md 中同时使用 R-01~R-11 和 P 系列标签，造成混淆。

**现状**:
- 文件声称覆盖 R-01 through R-11
- 实际操作中使用 P-01, P-09, P-22 等 P 系列标签

**建议修复**: 统一使用单一标签体系，建议迁移到 P 系列标签。

---

### [P5] 任务场景编号不连续

**问题描述**: `GENSHIN_QUEST_SCENARIO_BREAKDOWN.md` 中的魔神任务编号不连续。

**现状**:
- AQ-001, AQ-002, AQ-003 (序章)
- AQ-004, AQ-005, AQ-006 (第一章)
- 跳过 AQ-007~AQ-009
- AQ-CH2-01 (第二章)
- AQ-CH3-01 (第三章)
- AQ-CH4-01 (第四章)
- AQ-CH5-01 (第五章)

**建议修复**: 统一编号格式，建议使用:
- 序章: AQ-001 ~ AQ-003
- 第一章: AQ-101 ~ AQ-104
- 第二章: AQ-201 ~ AQ-204
- 第三章: AQ-301 ~ AQ-306
- 第四章: AQ-401 ~ AQ-406
- 第五章: AQ-501 ~ AQ-506

---

## 统计总览

| 检查项 | 通过 | 警告 | 错误 |
|--------|------|------|------|
| 能力ID系统格式 | 4 | 3 | 0 |
| 数据数值一致性 | 4 | 3 | 0 |
| 场景数量一致性 | 4 | 0 | 0 |
| 角色突破AR对应 | 6 | 0 | 0 |
| **总计** | **18** | **6** | **0** |

---

## 建议行动项

| 优先级 | 问题 | 行动 |
|--------|------|------|
| P1 | 公子推荐等级 | 在QUEST文档中统一为"最低Lv 40，推荐Lv 45-50" |
| P2 | 女士推荐等级 | 在QUEST文档中补充"推荐等级 Lv 50-60" |
| P3 | 巨鲸推荐等级 | 在QUEST文档中补充"推荐等级 Lv 80-85" |
| P2 | 能力标签混用 | 统一UI_OPERATION_SCENARIOS.md为P系列标签 |
| P2 | 任务编号不连续 | 重新编号为 AQ-101, AQ-201 等连续格式 |

---

*报告生成时间: 2026-05-30*
*检查工具: 文档交叉引用审查*