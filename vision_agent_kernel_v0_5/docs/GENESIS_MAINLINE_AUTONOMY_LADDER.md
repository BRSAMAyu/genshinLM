# GenesisAgent: 大主线自主通关阶梯与任务事实链治理架构设计规范
## —— 走向无监督三维开放世界自主通关的终极设计白皮书

> **文档目的**：针对 Codex 的深度技术批判进行全面架构收束，将 GenesisAgent 的核心演化方向从“过度关注 3D SLAM (V-NavMesh)”纠偏为“**主线任务事实链治理**”与“**多级经验蒸馏（3-Tier Skill Induction）**”。  
> **核心原则**：用 Claim 约束事实，用 Skill 固化经验，用 Capsule 承载领域知识，用快慢脑分离解决实时性，用 Benchmark 驱动真实进步。

---

## 摘要

在 3D 开放世界（如《原神》、《红死救赎 2》）中，阻碍智能体自主通关的核心痛点**绝不是三维重建的缺乏，而是系统缺乏一条可长期治理、具备因果闭环的“任务事实链（Quest Fact Chain）”**。

如果系统不能稳定理解“当前主线节点是什么、下一步为什么做、完成条件是什么”，任何高频的局部导航与动作录制都只是沙滩上的城堡。

本规范提出 **Mainline Autonomy Ladder（大主线自主阶梯）**，作为 GenesisAgent 终极形态的系统级架构蓝图。本设计将保证系统的“无顽疾高泛化性”，使得游戏特异性知识被彻底隔离在 Capsule 中，而通用内核则专注于事实链流转与经验自蒸馏。

---

## 一、 Mainline Autonomy Ladder（七层自主阶梯架构）

GenesisAgent 放弃扁平化的 “视觉-动作（Vision-to-Action）” 单步循环，重构为高度分层的七层自主阶梯：

```
+--------------------------------------------------------------------------+
| Tier 7: Mainline Benchmark Curriculum (主线课程评测体系)                     |
| - 追踪：Success Rate / Human Intervention Rate / Token Cost Decay         |
+--------------------------------------------------------------------------+
                                    ^
                                    |
+--------------------------------------------------------------------------+
| Tier 6: Reliability Gate (可靠度安全网关)                                  |
| - 评估：P(Success | Page, Party, Resolution) 门控过滤，高风险自动降级           |
+--------------------------------------------------------------------------+
                                    ^
                                    |
+--------------------------------------------------------------------------+
| Tier 5: Local Runtime Controllers (本底快控制器)                             |
| - UIAnchor / Heading Servo / CombatRuntime / Recovery Recipe             |
+--------------------------------------------------------------------------+
                                    ^
                                    |
+--------------------------------------------------------------------------+
| Tier 4: Skill Evolution Flywheel (三层经验蒸馏飞轮)                          |
| - 慢探索轨迹 -> 事实链 Claim 验证 -> 蒸馏为 Macro/Procedure/Motor Skills     |
+--------------------------------------------------------------------------+
                                    ^
                                    |
+--------------------------------------------------------------------------+
| Tier 3: Claim-Gated MissionGraph (契约式任务流图)                           |
| - LLM 只生成 Graph; 每个 Node 必须声明 Input/Output Claim 及 Fallback       |
+--------------------------------------------------------------------------+
                                    ^
                                    |
+--------------------------------------------------------------------------+
| Tier 2: Quest State Tracker (任务语义状态机)                               |
| - 汇聚对话、地图标记、目标文本，持续维护 “当前任务事实链”                      |
+--------------------------------------------------------------------------+
                                    ^
                                    |
+--------------------------------------------------------------------------+
| Tier 1: Screen State Tree (SC-UPG 统一 UI 状态树)                          |
| - 图像 -> OCR/检测结构化 JSON -> LLM 只能发出符号化 Action (Action Masking)  |
+--------------------------------------------------------------------------+
```

---

### Tier 1: Screen State Tree (SC-UPG 统一 UI 状态树)
* **设计意图**：消除多模态大模型的视觉空间幻觉与点击坐标漂移。
* **实现机制**：
  * 本地视觉引擎高频运行轻量级 OCR（字符定位）与目标检测器，将画面转义为结构化的 UI State JSON 树（包含页面 ID、按钮文本、位置边界框、可交互状态）。
  * 大脑 VLM **仅允许** 输出符号化动作（例如：`Click(Button(text="追踪"))`），禁止直接输出物理像素点 `(x, y)`。
  * 本地 `UIAnchorResolver` 负责根据当前分辨率和实时 UIAnchor 偏移，将符号化动作转化为物理坐标点击。

### Tier 2: Quest State Tracker (任务语义状态机)
* **设计意图**：消除 LLM 对当前主线进度的“单帧重猜”。
* **实现机制**：
  * 该状态机是一个**持续滚动的语义黑板**，汇聚四个维度的感知输入：任务追踪标题、当前追踪具体指示文本、最近 3 轮 NPC 对话记录、小地图/大世界中的金色路标方向。
  * 状态机维护一个强类型的 `ActiveQuestContext` 对象，作为大脑决策的持久化因果源泉。

### Tier 3: Claim-Gated MissionGraph (契约式任务规划)
* **设计意图**：杜绝大模型“盲目自信推进”导致的逻辑断裂。
* **实现机制**：
  * 大脑 VLM 不直接发送动作，而是通过读入 `ActiveQuestContext`，生成/修正一个 **MissionGraph（契约式任务流图）**。
  * 每个 Mission 节点必须绑定显式的**契约断言**：
    * `InputClaim`（前置条件，如 `Item(SweetFlowerChicken) >= 1`）
    * `OutputClaim`（完成标志，如 `QuestStatusText == "与派蒙对话完成"`）
    * `Fallback`（失败回退策略）与 `RiskLevel`。
  * **节点通过标准**：不以 VLM 猜想为准，只有当 `ClaimGraph` 中生成了经过 Audit 审计的 Terminal Claim 时，当前节点才被标记为 Completed 并向后推进。

### Tier 4: Skill Evolution Flywheel (三层经验蒸馏飞轮)
* **设计意图**：将高成本的“慢推理”逐步固化为低成本的“快运行”。
* **实现机制**：
  * 当进入未知页面或面对强力 Boss 时，系统触发慢思考（VLM 探索）。
  * 探索成功后，`SkillInductionGate` 提取成功的输入/输出证据链，将原有的单步探索轨迹，**自动蒸馏为三层 Skill**，并写入持久化 Catalog 中。下次遇到同类任务，优先直接执行 Skill。

### Tier 5: Local Runtime Controllers (本底快执行器)
* **设计意图**：确保毫秒级实时控制与避险。
* **实现机制**：
  * **UI交互器**：执行 `ProcedureSkill` 连招。
  * **跑图导航器**：大地图 teleport 决策 + 罗盘追踪 Heading Servo + 进程卡死/Stuck 局部避障。
  * **实时战斗器**：`CombatRuntime` 自动切人、卡 CD 连招 + `ReflexScheduler` 毫秒级闪避。
  * **生存与恢复器**：`Sentinel Recovery` 强行阻断并恢复健康度。

### Tier 6: Reliability Gate (可靠度安全网关)
* **设计意图**：防止不可靠技能在关键节点掉链子。
* **实现机制**：
  * 每一个 Skill 在被 Catalog 注册时，都会维护一个**多维可靠度矩阵**：
    $$\text{Reliability} = P(\text{Success} \mid \text{Page}, \text{PartyComposition}, \text{ScreenResolution})$$
  * 任务规划器（Planner）在分配节点 Skill 时，必须通过 Reliability Gate 过滤。如果当前环境匹配的 Skill 可靠度低于风险阈值（Risk Threshold），系统会自动将当前节点**降级**为“人工辅助（Supervised）”或“慢探索（Exploration）”模式。

### Tier 7: Mainline Benchmark Curriculum (主线课程评测体系)
* **设计意图**：用真实的客观数据（而非单元测试数量）驱动智能体能力增长。
* **实现机制**：
  * 建立渐进式的主线评估课程表：
    `新手教程` $\rightarrow$ `第一次世界对话` $\rightarrow$ `第一次锚点激活与传送` $\rightarrow$ `大世界跑图导航` $\rightarrow$ `遭遇战与野外Boss` $\rightarrow$ `角色装备养成` $\rightarrow$ `第一章主线全自主通关`。
  * 对每一门课程，评测引擎收集六维硬性指标，直接作为顶会论文的实验图表来源：
    $$\text{Metrics} = \{ TSR, VCR, HIC, RSR, SRR, CTR \}$$
    - **TSR (Task Success Rate)**：任务节点通关率。
    - **VCR (Verified Completion Rate)**：有 Claim 证据链锁定的真实通关率。
    - **HIC (Human Intervention Count)**：平均每小时人类被迫干预次数。
    - **RSR (Recovery Success Rate)**：SRP 面对卡墙/死亡等状态的恢复成功率。
    - **SRR (Skill Reuse Rate)**：蒸馏技能的重复调用率（证明飞轮收敛性）。
    - **CTR (Token Cost Reduction)**：随着技能库完善，单次任务平均消耗 Token 的衰减曲线。

---

## 二、 三层 Skill 体系表达 (3-Tier Skill System)

为保证高度泛化与精确调用，Skill 被形式化地定义为三个层次：

```
                              +---------------------------------------+
                              |              MacroSkill               |
                              |   - Quest / Leveling / Strategy Graph |
                              +-------------------+-------------------+
                                                  | (Decoupled to Tasks)
                                                  v
                              +---------------------------------------+
                              |            ProcedureSkill             |
                              |   - Relocatable UIAnchor click chains |
                              +-------------------+-------------------+
                                                  | (Translated to Inputs)
                                                  v
                              +---------------------------------------+
                              |              MotorSkill               |
                              |   - Keyboard / Mouse WASD & Combat    |
                              +---------------------------------------+
```

### 1. MacroSkill (战略/规划级)
* **结构定义**：表达长程的任务树与养成逻辑。
* **示例**：`induced_mainline_act1_chapter2`。
* **表达内容**：包含宏观的 `MissionGraph`，定义如何配队、圣遗物优先级、以及遇到特定 Boss 时的元素切人 playbook。

### 2. ProcedureSkill (流程/面板级)
* **结构定义**：表达界面/面板级的确定性跳转及交互，**完全依赖 UIAnchor 描述，实现跨分辨率迁移**。
* **示例**：`proc_upgrade_character`。
* **执行步骤**：
  1. `WaitState(Page("Character_Menu"))`
  2. `Click(UIAnchor("btn_upgrade_tab"))`
  3. `Click(UIAnchor("item_exp_book_hero_wit"), duration=2.5)` (长按)
  4. `Click(UIAnchor("btn_confirm_upgrade"))`
  5. `VerifyState(Claim("char_level_increased"))`

### 3. MotorSkill (动作/执行级)
* **结构定义**：表达毫秒级、高频的运动与物理反射操作。
* **示例**：`motor_heading_servo` (罗盘寻路导航)、`motor_diluc_e_cancel` (迪卢克 E 技能接平 A 取消后摇连招)。
* **表达内容**：直接映射到 `InputLease` 占用的虚拟键盘/鼠标原生指令流。

---

## 三、 通用故障恢复配方体系 (Recovery Recipes)

为彻底解决主线推进中高频发生的异常，SRP（哨兵恢复协议）设计了一套通用的 **Recovery Recipes（故障恢复配方）**，避免让 LLM 面对异常盲目决策，而是执行高度确定性的自稳流：

```python
class RecoveryRecipe(Protocol):
    def check_precondition(self, state: TaskStateSnapshot) -> bool: ...
    def execute_recovery(self, executor: ActionExecutor) -> bool: ...
    def verify_restabilized(self, perception: PerceptionProvider) -> bool: ...
```

### 1. `DEATH_RECOVERY` (死亡/战败恢复配方)
* **前置触发**：`StateDeltaClaim` 检测到队伍全灭，或者画面出现复活提示。
* **恢复流程**：
  1. 释放所有输入，等待复活传送加载界面结束（判定 `Loading_Screen == False`）。
  2. 读取体感记忆中最近激活的七天神像 ID。
  3. 打开大地图，符号化点击 `Click(MapAnchor(statue_id))` 并确认传送。
  4. 控制角色走向神像，触发满血回复。
  5. 打开食物面板，调用 `proc_consume_food` 重置防御/攻击 buff。
  6. 根据任务追踪，重新计算大地图 GPS 方向并跑图返回死亡坐标点。

### 2. `STUCK_RECOVERY` (卡墙/导航卡死恢复配方)
* **前置触发**：连续 3 秒进度斜率（Progress Slope）为 0，且角色有 WASD 输出。
* **恢复流程**：
  1. 停止一切向前输入 0.5 秒。
  2. 执行 `Space` (跳跃) + `S` (后退) 尝试拉开碰撞箱距离。
  3. 将视野水平旋转 90 度，向前移动 1 秒，再重新对齐小地图罗盘方向。
  4. 若仍卡死，则强制传送回最近的地图锚点（Teleport Reset）。

### 3. `UI_LOST_RECOVERY` (UI 迷路恢复配方)
* **前置触发**：页面深度 > 2，找不到目标返回按钮，或者出现意料之外的阻断弹窗。
* **恢复流程**：
  1. 连续发送两次 `Esc` / `B` (安卓物理返回键) 尝试强制退出子菜单。
  2. 若屏幕状态依然未知，执行 `Click(UIAnchor("btn_close_overlay"))`。
  3. 回退到 `大世界大视口（World_Viewport）` 稳态。

---

## 四、 彻底解耦的 Capsule（领域知识库）边界

为了保持 GenesisAgent 在底层架构上的**绝对通用性与高泛化度**，我们将所有与《原神》或特定游戏强相关的背景资料、配置信息全部剥离到外部的 **Capsule 库** 中。

通用内核与游戏 Capsule 通过标准接口进行强契约交互：

```
+--------------------------------------------------------------------------+
|                        GenesisAgent General Kernel                       |
|  - Claim adjudication, VLM spec script parser, SC-UPG mapping, SRP      |
+------------------------------------+-------------------------------------+
                                     |
                          (Standard Capsule API)
                                     |
                                     v
+------------------------------------+-------------------------------------+
|                      Genshin Impact Capsule                              |
| - configs/profiles/genshin_ui.json: UIAnchor template textures & offsets |
| - configs/quest_vocabulary.yaml: quest log parser dictionary             |
| - data/combat_profiles/pyro_diluc.yaml: Diluc execution playbooks        |
| - data/skills/proc_teleport_statue.json: predefined ProcedureSkills      |
+--------------------------------------------------------------------------+
```

由此，若要移植到《GTA 5》，只需插拔式替换为 `gta5_capsule`（包含车速 UIAnchor、驾车 MotorSkill、任务词汇表），而内核的代码行无需做出任何重构。

---

## 五、 大主线最小闭环（The Milestone Checkpoint）

在进行复杂的 Boss 自进化测试之前，我们必须**首先跑通且完美固化“主线任务最小闭环（Quest Minimum Closed Loop）”**。这是衡量系统是否开始走向“事实链治理”的分水岭：

```
                                  +---------------------------------------+
                                  |    1. Identify World State Stabilized |
                                  |       - Parse UI: World Viewport      |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |    2. Parse Quest Log & Target Text   |
                                  |       - OCR: "Talk to Amber"          |
                                  |       - Commit to ActiveQuestContext  |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |    3. Compass-guided Teleport/Nav     |
                                  |       - UIAnchor: Click map marker    |
                                  |       - Motor: Heading Servo to Amber |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |    4. NPC Dialogue Loop Execution     |
                                  |       - Visual: Dialogue Overlay seen |
                                  |       - Auto-select option #1         |
                                  +-------------------+-------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |    5. Audit State Delta & Verify      |
                                  |       - Target text -> "Clear Camp"   |
                                  |       - Commit Verified Claim to Graph|
                                  +---------------------------------------+
```

### 闭环验证硬性标准
* **无模型决策介入**：前四步必须完全依赖本地 `ProcedureSkill` 与 `MotorSkill` 自动闭环。
* **不可证伪性**：第五步的 Claim 必须具有确凿的 OCR/图像变动证据，不允许 LLM 猜想。

只有通过了这个最小闭环的实机验证，GenesisAgent 的引擎齿轮才算真正卡入卡槽。
