# ROADMAP — 自主通关原神主线（北极星路线）

> 本文件是连接 `PROJECT_ALIGNMENT.md`（宪法）与日常代码决策的**长程方向锚**。
> 当某一步的工作让人忘记全局时，回到这里。
> 视角：本路线以 **coding agent 的执行节奏**编写，而非人类工时——回合以"自动化迭代轮次"和"可并行 agent 数"计，远快于人类 sprint。

---

## 0. 北极星的精确定义

**目标**：一个*无需专门训练*的通用游戏 agent，自主通关原神主线。

"自主"≠首次即通关。它的定义是：

> 系统能在**试错—归因—修正—复跑**的闭环中持续自我改进，在给定的（授权测试 / QA 单机 / 自建沙盒）环境里，使**人工干预次数/通关目标 → 0**，最终独立推进并通关主线章节。

因此本项目有**两个交织的回路**，路线必须同时服务两者：

| 回路 | 是什么 | 衡量 |
|---|---|---|
| **产品自主回路** | 运行时 agent 通过试错自学打游戏（探索→信念→技能→学习，已有 BAGEL/skill induction 骨架） | 固定基准上的失败率随自动迭代下降，且**无人工改码** |
| **开发迭代回路** | 我（coding agent）构建/加固框架，可多 agent 并行 | 每阶段 exit gate 达成的墙钟时间 |

**关键洞察**：真正的瓶颈不是某个能力模块，而是**自动迭代的承载力**——能否自动地"跑一局→自动评分→自动归因失败→派 fix→复跑"，并能并行。所以 `Phase 1` 不是某个游戏能力，而是**试错引擎本身**。它一旦就位，后续每个能力阶段都从"人推"变成"自我打磨"。

---

## 1. 能力分解与现状盘点

通关主线 = 若干**可靠原语**的可编排组合。现状（仓库已有大量骨架，多数缺端到端验证）：

| 原语 | 现有资产 | 状态 |
|---|---|---|
| **P-感知/世界状态** | 截屏→YOLO→tracker→OCR；screen classifier；**pose substrate（刚落地）** | 🟡 骨架在，pose 刚建需接入 |
| **P-导航** | Navigator 协议、Waypoint(3D)、WaypointGraph、MinimapFlowTracker、MinimapQuestReader、LostRecovery | 🟡 零件全，但开环、未用 pose 闭环 |
| **P-战斗** | PlaybookSchema/Runtime、Genshin 元素反应、boss 机制、reflex_evasion | 🟡 深但未端到端验证 |
| **P-交互/剧情** | DialogueController、quest context、daily commission executor | 🟡 大体在，待加固 |
| **P-解谜** | 几乎空白；VLM 可用 | 🔴 待建（视觉伺服） |
| **编排** | MainlineRunner、MissionGraphV4、claim-gated 节点 | 🟡 引擎在，缺真实主线分解 |
| **学习/恢复** | BAGEL、UnknownSceneHandler、ParameterizedSkillInductor、GameKnowledgeStore | 🟡 闭环骨架在，缺规模化喂养 |
| **试错引擎** | telemetry JSONL+录像、AuroraBench 任务名 | 🔴 缺自动评分/归因/复跑/并行 harness |

> 结论：**绝大多数是"接线 + 加固 + 验证"，而非从零造**。路线据此安排。

---

## 2. 阶段路线（每阶段有可观测 exit gate）

所有验证默认在**授权测试环境**（3D 沙盒 / 自建 ARPG / QA 单机）进行，符合 `SAFETY.md`、默认 dry-run。

### Phase 0 — 空间地基 + 导航闭环【当前】
- **建**：pose substrate（✅ 已落地）→ Genshin 小地图 LocalizationProvider → 导航用 pose 闭环 → 最后一公里视觉重捕。
- **Exit gate**：测试环境中，给定任意 waypoint，agent 能"传送→拓扑寻路→pose 闭环行走→卡住自恢复→视觉重捕逼近特定目标"，在 N≥50 次自动试验中到达成功率 ≥ 80%。
- **并行性**：低（步骤有依赖：导航闭环依赖 pose 流动）。我串行做这三步。

### Phase 1 — 试错引擎（自主迭代 harness）★ 全局杠杆
- **建**：场景 runner（可 checkpoint/reset）；自动评分/验证器；失败自动捕获（录像+JSONL replay）；失败聚类；**fix 派发回路**（每个失败簇 → 一个 fix-agent 消费 replay）。
- **Exit gate**：我能一条命令启动一个场景，自动得到 pass/fail + 归因后的失败簇；多场景并行执行；fix-agent 能仅凭 replay 复现并修复。
- **并行性**：**极高**——这是把"人推"变"自走"的转折点。此后所有阶段可 fan-out。

### Phase 2 — 战斗可靠性
- **建/加固**：playbook executor + 反应层（闪避/回血基于视觉，目标"几乎闪避一切"）+ 配队/元素反应 + boss 机制；skill induction 录制"完美连招"为可复用资产，处理冷却/卡位/外扰。
- **Exit gate**：标准战斗集（杂兵→精英→单 boss）自动复跑通过率 ≥ 80%；一条录制连招回放成功率 ≥ 95%；HP 低时能自动回血/撤退。
- **并行性**：高（多敌人/多配队场景并行刷）。

### Phase 3 — 交互 / 剧情 / 任务推进
- **加固**：对话推进、选项选择、奖励领取、任务目标追踪、过场处理。
- **Exit gate**：完整每日委托循环（接取→传送→战斗/任务→提交→领奖）端到端自主、可重复 ≥ 90%。
- **并行性**：中。

### Phase 4 — 解谜（最高精度域）
- **建**：VLM 视觉伺服闭环（VLM 提议目标→本地检测/OCR 精修像素→操作→重观察→纠偏），空间推理 + 精确点击/操控 + 迭代纠错。
- **Exit gate**：代表性解谜集（元素方碑、光路、简单平台跳跃、连线/拼图）通过率 ≥ 70%。
- **并行性**：中（不同谜题类型并行）。

### Phase 5 — 主线编排
- **接线**：MainlineRunner 把一个真实主线任务分解为原语调用，claim-gated 执行 + BAGEL 恢复 + ActiveQuestContext。
- **Exit gate**：在测试/QA 环境中端到端自主完成**一个完整主线小章节**。
- **并行性**：低（编排有强时序），但其下的原语失败可并行修。

### Phase 6 — 收口与规模化：迭代至通关
- **跑**：章节接章节，让 Phase 1 的试错引擎 + 学习引擎持续打磨；知识库扩张；跨章节/场景并行刷。
- **Exit gate**：**北极星**——自主连续推进并通关主线。
- **并行性**：极高。

---

## 3. 横切轨道（贯穿所有阶段，持续推进）

- **安全**：InputLease/DeadmanSwitch/F9/focus 校验/watchdog 永不退化；任何新执行路径先过 dry-run。
- **遥测与回放**：每局可录、可复盘、可 reset——这是试错引擎的燃料，优先级等同核心功能。
- **学习/知识**：BAGEL 归因 + skill 归纳 + GameKnowledgeStore 必须吃到每局失败；昂贵的云多模态调用一律**结晶成可缓存资产**（pose 航点/路线/playbook/解谜图）。
- **评测基准**：AuroraBench（reflex / long_horizon / repair）固化为回归基准，度量"自我改进速度"。
- **胶囊通用化**：每个能力先在 core 做游戏无关抽象，Genshin 只是首个胶囊实现（守住"通用框架"，避免 Genshin 硬编码）。

---

## 4. 我（coding agent）如何执行——节奏与并行策略

- **依赖链串行，叶子节点 fan-out**：编排/时序强的阶段我串行推进；其下相互独立的能力修复用并行 agent（Phase 1 就位后，每个失败簇一个 fix-agent）。
- **工作流模式**：探索（多 reader 并行测绘）→ 设计 → 实现 → **对抗式验证**（独立 agent 试图证伪我的修复）→ 复跑。研究/审计型任务倾向多 agent 彻底覆盖。
- **每步必带测试**：仓库是 4359+ 测试的生产代码库，TDD 风格；新增一律纯增量、不破坏既有收集。
- **回到锚点**：每完成一个 exit gate，回本文件勾掉并校准下一步。

---

## 5. "完成"的度量（自主性指标）

1. **自我改进速度**：固定基准（AuroraBench）失败率随自动迭代轮次单调下降，**且过程零人工改码**。
2. **干预密度**：人工干预次数 / 已通关目标 → 0。
3. **资产复用率**：复用已沉淀技能/航点/playbook 的占比上升，新生成（昂贵）调用占比下降。
4. **端到端**：每个 Phase 的 exit gate 在 N 次自动试验上稳定达标，而非单次侥幸。

---

## 6. 风险登记与决策原则

| 风险 | 应对 |
|---|---|
| 实时控制 vs 长程规划撕裂 | 五平面/L0–L9 分层；云多模态只做战略与资产产出，绝不进实时回路 |
| "无训练"约束在精细控制/反应战斗最吃亏 | 用经典控制+工程化 CV 推到极限；必要时仅在这两处考虑小型学习组件 |
| 小地图非真值/最后一公里 | pose 带不确定度；低置信即切视觉重捕 |
| 骨架多但未验证 | 路线主轴是"接线+加固+验证"，Phase 1 试错引擎优先 |
| Genshin 硬编码侵蚀通用性 | core 游戏无关 + 胶囊实现的纪律 |

**决策原则**：每个昂贵调用结晶成耐久资产；每个动作默认会失败、靠视觉 checkpoint 推进；不做单帧决策；只用单调时钟。

---

## 7. 当前焦点（Phase 0 收尾，本轮开工）

1. **Genshin 小地图 LocalizationProvider**：包装 MinimapFlowTracker + MinimapQuestReader，作为 FramePostProcessor 每帧产出 `PoseEstimate` → `StateBus.latest_pose`。
2. **导航 pose 闭环改造**：航向误差 = `bearing_to(pose→target) − pose.heading`；到达 = 距离+置信度；卡住 = 指令 vs 实测位移不一致。
3. **最后一公里视觉重捕**：pose 置信度低或接近目标 → 转视角扫描 → YOLO/VLM 找目标 → 视觉伺服逼近。

> 三步有依赖（2、3 依赖 1 的 pose 流动），故串行实现，各自带测试。完成即达 Phase 0 exit gate，解锁 Phase 1 试错引擎。
