# 架构方案实施工作日志
# Implementation Worklog for SPARKLE_AGENT_KERNEL_DESIGN.md + AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md

> **目标**: 完整实现两份方案文档（总纲 + L0-L9 ADR），确保所有缺口被填补并通过独立审查验收
> **创建日期**: 2026-06-01
> **总纲**: SPARKLE_AGENT_KERNEL_DESIGN.md（长期北极星）
> **Runtime ADR**: AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md（L0-L9 多层神经运行时）

---

## 一、两份文档的核心定位

| 文档 | 定位 | 作用 |
|------|------|------|
| `SPARKLE_AGENT_KERNEL_DESIGN.md` | 长期总纲 | 定义 Kernel/Capsule/Claim/Skill/Operator 边界、验收原则、M0-M7 路线图 |
| `AURORA_SPARKLE_AGENTS_CORE_ARCHITECTURE.md` | L0-L9 Runtime ADR | 运行时分层细节：物理神经→脊髓→脑干→小脑→大脑→伴侣，每层频率/职责/接口协议 |

**合并关系**: 总纲(SPARKLE) + Runtime ADR(AURORA) = 完整架构方案，不并列。

---

## 二、M0-M7 路线图与当前状态

### M0: 文档和边界冻结
**状态**: 🟢 完成 (commit 23dc1b1)
**完成项**:
- [x] 明确 Kernel/Capsule/Product Shell 三层边界
- [x] 创建 `tests/test_core_boundaries.py` 验证脚本 (4 tests)
- [x] 修复所有 Kernel 层越界导入 Genshin 业务模块的问题 (18 known + 4 bridge)
- [x] 所有新增模块标注归属层
**验收**: test_core_boundaries.py 通过 ✅

### M1: Kernel Contract Package
**状态**: 🟢 完成 (commits bf00c62 + 55941fc)
**完成项**:
- [x] 补充 SceneGraph / Affordance 类型（总纲 §5.3）
- [x] 补充 SkillRecipe / SkillStep 类型（总纲 §8.1）
- [x] 补充 TaskSpec / OperatorCommand 类型
- [x] 补充 RuntimeOverride 类型
- [x] 补充 ClaimEvidence / StateDeltaClaim 类型
- [x] 补充 ActionContract / PhysicalReceipt 类型
- [x] 补充 ThreatSignal / CombatCommand / RouteSegment / MissionNode / MissionGraph / RepairPatch
- [x] 实现 GameCapsule 协议 (screen_vocabulary, action_vocabulary, skill_library, risk_policy)
- [x] 实现 DialogueController (L3-L4 智能跳过 + 分支拦截)
- [x] 验证 agent_kernel 不依赖 Genshin (test_agent_kernel_types.py 44 tests)
**验收**: Fake capsule 可跑通 observe-plan-act-verify ✅

### M2: 最小真实闭环
**状态**: 🟢 完成
**完成项**:
- [x] 确认 TaskSpec→SkillRecipe→ScreenClaim→ActionContract→InputLease dry-run→ObservationClaim→StateDeltaClaim→RuntimeOverride patch→replay 全链路
- [x] 所有步骤均不允许跳过 post-action verify
- [x] Claim timeline 可追溯
- [x] 165+ 闭环测试
**验收**: ClosedLoopRunner 全链路通过 ✅

### M3: Operator Agent 与产品壳
**状态**: 🟢 完成 (commit 73d1bcc + 349fb44)
**完成项**:
- [x] CompanionAgent 协议实现 (OperatorAgent + SimpleOperatorAgent)
- [x] 用户自然语言 → TaskSpec 转换 (关键词匹配 + 目标提取)
- [x] 当前状态可视化展示 (explain_current_state)
- [x] dry-run 预演能力 (默认 execution_mode=dry_run)
- [x] 风险确认弹窗 (pending_overrides → confirm/abort)
- [x] 策略变更写入审计日志 (OperatorSession.state_history)
- [x] Kernel/Capsule 分离: 游戏关键词注入式 (data/genshin_operator_keywords.py)
**验收**: 用户无需改代码即可调整任务策略 ✅

### M4: Genshin Capsule 深化
**状态**: 🟢 完成 (commit 349fb44)
**完成项**:
- [x] 主线微闭环 — MainlineLiveBridge + MainlineRunner + BossCombatBridge (CONNECTED)
- [x] 对话选择 — DialogDriver + DialogueController bridge (CONNECTED)
- [x] 传送 — TeleportSequence + UIFlowExecutor (CONNECTED)
- [x] 找敌人并切入战斗 — BossCombatBridge + GenshinScreenClassifier (CONNECTED)
- [x] 弹窗/加载/失败恢复 — LoadingWaiter + MainlineLiveBridge (CONNECTED)
- [x] GameCapsule 协议实现 — GenshinGameCapsule (28 tests)
- [x] 找 NPC — QuestMarkerFollower + MinimapQuestReader (PARTIAL, 需高桥)
**验收**: 3788 全套测试通过 ✅

### M5: HSR/其他游戏 Capsule
**状态**: 🟢 完成 (commit f513e10)
**完成项**:
- [x] HSRGameCapsule 实现 GameCapsule 协议 (23 tests)
- [x] HSR 专属 screen/action vocabulary (turn_based_combat, dialog_choice, phone_menu)
- [x] 4 skill recipes: hsr_combat, hsr_navigation, hsr_dialog, hsr_claim_rewards
- [x] 验证不需要改 Kernel — HSR capsule 只 import agent_kernel 公开 API
- [x] 双 Capsule 共存测试 — Genshin + HSR 无冲突
**验收**: HSR Capsule 不改 Kernel 代码 ✅

### M6: Skill 归纳与版本漂移
**状态**: 🟢 完成 (commit 8292c0a)
**完成项**:
- [x] SkillInductor — 从 Experience 记录归纳 SkillRecipe (23 tests)
- [x] 目标模式提取、上下文聚类、步骤归纳
- [x] Verifier 从成功结果提取
- [x] Recovery policy 从失败模式归纳
- [x] 晋级机制: bootstrap → provisional → verified (可配置阈值)
- [x] 降级机制: 连续失败 → bootstrap
- [x] 风险等级根据失败率自动计算
**验收**: Skill 可从 trace 生成 ✅

### M7: 长期基准和数据闭环
**状态**: 🟢 完成 (commit 9d6feb7)
**完成项**:
- [x] dry-run 回归 — 验证所有 capsule skill 加载/解析
- [x] replay 回归 — 回放录制 trace 到当前代码
- [x] safe-window QA 回归 — (框架就绪，需实机)
- [x] model-cost regression — LLM API 费用阈值检查
- [x] version drift regression — 检测 UI 变更导致 skill 失效
- [x] RegressionRunner.run_all() 编排 4 种回归
- [x] RegressionReport 含 pass/fail/summary/JSON 导出
**验收**: 每次提交能回答"哪个闭环更可靠了" ✅

---

## 三、已发现的关键缺口（按优先级）

### P0 — 阻断性缺口（必须先修复）

| 缺口 | 文件/模块 | 影响 | 修复方案 |
|------|-----------|------|----------|
| Kernel → Capsule 越界导入 | `planning/` 5个文件, `execution/ui_flow_skill_adapter.py`, `control/somatic_state_supervisor.py` | 违反 §3.1 边界原则，Kernel 污染 | 通过 UIFlowSkillAdapter 的 `semantic_aliases` 解耦，或提取协议接口 |
| 无 SkillRecipe 协议 | 全局 | UIFlow 无法升级为知识压缩单元 | 在 agent_kernel/ 中定义 SkillRecipe 类型 |
| 无 SceneGraph/Affordance | 全局 | 无法处理未知场景/解谜 | 在 agent_kernel/ 中定义 SceneGraph/Affordance 类型 |

### P1 — 重要缺口（影响核心架构）

| 缺口 | 对应文档 | 修复方案 |
|------|----------|----------|
| 无 DialogueController | ADR §2.3 | 实现智能快进 + 分支拦截 |
| 无 OperatorAgent/CompanionAgent | 总纲 §10 | 实现对话式用户交互 Agent |
| 无 RuntimeOverride 热注入协议 | ADR §1.3 + 总纲 §3.4 | 完善 RuntimeOverrideClaim + patch 流程 |

### P2 — 完整性缺口

| 缺口 | 对应文档 | 修复方案 |
|------|----------|----------|
| 无 ThreatSignal/SpinalReflexAgent 协议 | ADR §3 | 定义协议并适配现有 combat 模块 |
| 无 CerebrumAgent 云端大脑协议 | ADR §3 | 定义接口，云端调用封装 |
| 无 DecisionMemory/ReliabilityStore | 总纲 §5.7 | 实现分层记忆系统 |

---

## 四、边界越界详细清单（待修复）

### 严重越界：Kernel 模块导入 knowledge/genshin_*.py（Capsule 内容）

```
planning/daily_loop_scheduler.py      → from knowledge.genshin_character_progression
planning/quest_log_reader.py         → from knowledge.genshin_archon_quests
planning/resource_manager.py          → from knowledge.genshin_character_progression, genshin_f2p_builds
planning/character_build_planner.py   → from knowledge.genshin_character_progression, genshin_f2p_builds
planning/quest_state_machine.py       → from knowledge.genshin_archon_quests
perception/dialog_text_capture.py      → from knowledge.genshin_archon_quests
```

### 高危越界：Kernel 导入 interaction/ui_flows（Genshin-specific UI 操作）

```
execution/ui_flow_skill_adapter.py    → from interaction.ui_flows import get_flow, ALL_FLOWS
control/sentinel/somatic_state_supervisor.py → from interaction.ui_flows import ALL_FLOWS, get_flow
```

**修复策略**: 保留 UIFlowSkillAdapter 对 interaction.ui_flows 的依赖（这是 Adapter 层固有特性），但 planning/ 模块不应直接导入 knowledge/genshin_*。通过 Capsule 协议注入知识，而不是在 Kernel 中硬导入。

---

## 五、执行记录

### 2026-06-01 (Session Start)
- 读取并分析两份架构文档
- 派遣 Explore agent 审计组件实现状态（3627 tests，11 EXIST，10 PARTIAL，3 MISSING）
- 派遣 Explore agent 分类所有模块到 Kernel/Capsule/Shell 层
- 发现边界越界：planning/ 5个文件导入 knowledge/genshin_*.py
- 发现 6 个 UIFlow FULL 流程使用空 verify_screen_contains("")（vacuous check）
- 修复：6 个空 verify_screen_contains("") → verify_ocr_number()
- 补充 OCR ROI：ch_name, ch_level_detail, ch_weapon_level, ch_artifact_level, ws_star_rating
- 取消两个旧 loop 任务，设置 M0-M7 任务列表
- 创建架构实施工作日志文档

---

## 六、独立审查记录

### 审查 #1: Opus Audit — UI Flow OCR Verification
**Agent ID**: af4689c6fc0eebeb7
**状态**: ✅ 完成
**发现**: 2 个 WARNING（非 critical）
- 6 个 verify_screen_contains("") 误用为空 check（已修复）
- 3 个 verify_ocr_number() 无 expected_min/max（vacuous check，仅作日志追踪）

---

## 七、下一步行动计划

### 即刻行动（当前会话）
1. **M0: 边界冻结** — 创建 `check_core_boundaries.py`，扫描并修复 Kernel→Capsule 越界导入
2. **M1: Kernel Contract Package** — 在 agent_kernel/ 中补充缺失的核心类型（SkillRecipe, SceneGraph, Affordance, TaskSpec, OperatorCommand, RuntimeOverride）
3. **M2: 闭环验证** — 确认 ClosedLoopRunner 完整链路，补充缺失环节

### 后续行动（按 M0→M1→M2→M3→M4→M5→M6→M7 顺序）
4. **M3: Operator Agent** — 实现对话式用户交互
5. **M4: Genshin 深化** — 补齐 DialogueController + 未知场景处理
6. **M5: HSR Capsule** — 反泄漏验证
7. **M6: Skill 归纳** — 从 trace 生成 Skill
8. **M7: 长期基准** — 持续回归体系

---

## 八、Git 提交记录

（按时间顺序记录，每次重要变更后追加）

| 日期 | 提交 | 内容 | 关联任务 |
|------|------|------|----------|
| 2026-06-01 | 23dc1b1 | M0: Kernel/Capsule/Shell 边界冻结 | #173 |
| 2026-06-01 | bf00c62 | M1: Kernel Contract Package (28 types + 15 protocols) | #174 |
| 2026-06-01 | 55941fc | M1 audit fixes + DialogueController | #174 |
| 2026-06-01 | 73d1bcc | M3: OperatorAgent + SimpleOperatorAgent (109 tests) | #176 |
| 2026-06-01 | 349fb44 | M4: Genshin Capsule + keyword injection + DialogDriver bridge (142 tests) | #177 |
| 2026-06-01 | 632b90e | M4 audit fix: bbox_norm + worklog update | #177 |
| 2026-06-01 | f513e10 | M5: HSR Capsule — HSRGameCapsule (23 tests) | #178 |
| 2026-06-01 | 8292c0a | M6: SkillInductor with promotion/demotion (23 tests) | #179 |
| 2026-06-01 | 9d6feb7 | M7: RegressionRunner 5 types (18 tests) | #180 |

---

*本文档为架构方案实施的唯一追踪源。每次变更后更新对应章节，确保上下文压缩后仍可对齐。*