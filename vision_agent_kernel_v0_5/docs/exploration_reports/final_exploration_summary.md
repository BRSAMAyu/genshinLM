# Sparkle 项目代码库探索最终汇总报告

**日期**: 2026-06-02
**分支**: codex/pre-realworld-closure
**规模**: 909 个 .py 文件, 50+ 顶级目录, 918 个分支文件变更 (207k+ 行新增)
**探索方式**: 3 个 opus agent x 3 轮 + 1 轮架构合规审查

## 探索报告索引

详细内容请参阅各独立报告：
- [Agent A Round 1: 核心运行时架构摸底](agent_a_runtime_architecture.md)
- [Agent A Round 2: 跨平面调用链验证](agent_a_round2_crossplane_gaps.md)
- [Agent B Round 1: 规划与任务系统摸底](agent_b_planning_task_system.md)
- [Agent B Round 2: 端到端调用链验证](agent_b_round2_call_chain_gaps.md)
- [Agent C Round 1: 交互与感知层摸底](agent_c_interaction_perception.md)
- [Agent C Round 2: 感知到动作管线验证](agent_c_round2_perception_action_gaps.md)
- [Round 3: 架构合规性审查](round3_architecture_compliance.md)

## 项目架构概览

```
core/ (11 files) — StateBus, types, events, mode_arbiter, watchdog
  ↑
execution/ (35 files) — InputWorker, ExecutionRuntime, UIFlowSkillAdapter, backends
control/ (18 files) — CameraServo, ProgressSupervisor, Sentinel, Navigation
agent_kernel/ (22 files) — AgentLoop L0-L9, protocols, adapters, live_factory
planning/ (77 files) — MainlineRunner, MissionGraphV4, SkillRegistry, 40+ game modules
perception/ (80 files) — Pipeline, YOLO, screen classifier, OCR, VLM, 30+ detectors
interaction/ (17 files) — UIFlowEngine, dialog, shop, puzzle, menu flows
combat/ (52 files) — Playbook, boss, elemental, team, abyss, dodge
navigation/ (14 files) — Navigator, dialog handler, quest follower, teleport
capsules/ (4 capsules) — genshin, hsr, demo_arpg, desktop_ui
```

## P0 — 阻断性问题 (4 个)

必须修复才能运行端到端闭环：

| ID | 描述 | 文件 | 详情 |
|---|---|---|---|
| P0-1 | Observation 无 image 字段，UIFlowSkillAdapter 5 处 obs.image 访问将崩溃 | core/types.py, execution/ui_flow_skill_adapter.py | [Agent C R2](agent_c_round2_perception_action_gaps.md) GAP-7 |
| P0-2 | detect_dialog_end() 总返回 True，对话永远无法正确结束 | navigation/genshin_dialog_handler.py:91 | [Agent C R2](agent_c_round2_perception_action_gaps.md) GAP-18 |
| P0-3 | SomaticStateSupervisor 紧急治疗绕过 StateBus，创建独立 InputWorker+StateBus | control/sentinel/somatic_state_supervisor.py:335-342 | [Agent A R2](agent_a_round2_crossplane_gaps.md) Critical-1 |
| P0-4 | core/state_bus.py 反向依赖 planning 层 (硬导入 ScreenStateClaim) | core/state_bus.py:11 | [Agent A R2](agent_a_round2_crossplane_gaps.md) Critical-4 |

## P1 — 高优先级问题 (14 个)

严重影响功能完整性或安全性：

| ID | 描述 | 来源 |
|---|---|---|
| P1-1 | SentinelRuntime 恢复动作发布通道断路 (executor=None) | A-R2 Critical-2 |
| P1-2 | CrashRecovery 完全隔离于 StateBus，CrashDetector 无调用者 | A-R2 Critical-3 |
| P1-3 | CrashRecoveryOrchestrator 未连接 MainlineRunner/LiveBridge | B-R2 GAP-9 |
| P1-4 | ~34 个语义动作是 action_intent 透传 stub | B-R2 GAP-2 |
| P1-5 | Boss 战斗 actions 是 stub，不与 BossCombatRuntime 集成 | C-R2 GAP-5 |
| P1-6 | CombatAction vs InputLease 类型不匹配，无适配器 | C-R2 GAP-16 |
| P1-7 | 无 visual combat_ended 检测 | C-R2 GAP-14 |
| P1-8 | GenshinCombatDetector 未连接 FusionRuntime | C-R2 GAP-15 |
| P1-9 | 两个同名 SomaticState 类字段不兼容 | A-R2 High-5 |
| P1-10 | InputWorker focus check 竞态条件 | A-R2 High-8 |
| P1-11 | time.time() 用于 InputLease 安全时间戳 | R3 |
| P1-12 | time.time() 用于调度逻辑 | R3 |
| P1-13 | time.time() 用于决策记忆时间比较 | R3 |
| P1-14 | Lease 被驱逐后 InputLeaseStore 条目残留 | A-R2 High-9 |

## P2 — 中优先级问题 (28 个)

影响代码质量或架构合规。详见 [Round 3 报告](round3_architecture_compliance.md)。

## P3 — 低优先级问题 (8 个)

清理和改进。详见 [Round 3 报告](round3_architecture_compliance.md)。

## 架构合规总结

| 规则 | 状态 | 关键问题 |
|------|------|---------|
| 五平面通信纪律 | 4 Critical, 4 High, 2 Medium 违规 | SomaticStateSupervisor 绕过 StateBus 最严重 |
| No blocking waits | 1 严重, 4 中等 | evolution_engine 30s 阻塞 |
| No single-frame decisions | 合规 | 无违规 |
| Monotonic clock only | 3 P1, ~20 P2 违规 | InputLease 安全时间戳用 time.time() |
| LLM stays strategic | 合规 | 无违规 |
| Every action has a fallback | 4 P1 违规 | stub 动作、恢复断路、crash 隔离 |
| slots=True dataclass | core 合规, 5 处非核心缺失 | — |
| Protocol-only (no ABC) | 高度合规 | RecoveryRecipe 使用具体基类但合理 |
| from __future__ import annotations | 45% 缺失 (278 files) | 大规模合规性问题 |

## 关键发现

1. **战斗管线未完整打通**: GenshinCombatDetector -> FusionRuntime -> BossCombatBridge -> PlaybookExecutor 这条链存在 3 处断裂（未连接、类型不匹配、无结束检测）
2. **检查点系统三足鼎立**: MainlineCheckpoint、QuestContextPersistence、CheckpointStore 三套系统互不协调
3. **Crash Recovery 是死代码**: 有完整的状态机设计但无调用者，无实际恢复动作
4. **Sentinel 恢复通道断路**: 8 个 recovery recipe 的 StateBus 发布因 executor=None 而全部短路
5. **34 个语义动作是空壳**: daily/chain/mainline 路径的动作只有 log 没有执行
6. **类型系统关键缺口**: Observation 缺 image 字段、双 SomaticState 命名冲突、CombatAction/InputLease 不兼容
