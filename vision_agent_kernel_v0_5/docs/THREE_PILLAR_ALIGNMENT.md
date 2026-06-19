# 三支柱实景化对齐文档 (Three-Pillar Live-Build Alignment)

> 受众：项目所有者 + 后续 coding agent。
> 目的：在「自主通关原神主线」北极星下，把系统从**仿真验证态**推进到**真机可投入运行态**，
> 并补齐两根新支柱——**玩家交互界面**与**Claude-Code 式自我修改**。
> 本文是审查与续跑的基准。分支 `codex/pre-realworld-closure`，截至 commit `247e195`。

---

## 0. 一句话现状

前 6 个阶段产出了一套**测试充分但只跑在仿真里、没接进活体运行时**的参考栈（4 位独立评审一致确认）。
本轮（bagel-genesis 驱动）已经**接通了第一批 sim→live 缝隙**，并把两根新支柱落到可运行的地基上：
姿态层已实景接线、战斗/解谜/交互的协议适配层已建、玩家可发自然语言指令并能打断、伴游会"说话"、
**自我修改闭环已闭合到强制人工门控为止**。真机战斗"出招"仍被有意挡在真机标定之后（安全优先）。

---

## 1. 北极星与问题重述

**北极星**：无需专门训练的通用游戏 agent，在授权/单机研究环境中，通过「试错—归因—修正—复跑」闭环
持续自我改进，使「人工干预次数 / 通关目标 → 0」，最终自主推进并通关原神主线。

**本轮问题重述**：北极星的瓶颈不再主要是"缺能力模块"，而是三件事——
1. **能力在仿真里、没接进活体回路**（pose / 战斗 / 解谜 / 导航 / 任务编排各自为政）；
2. **没有玩家↔agent 的双向交互界面**（GUI 只读、语音空转、persona 单向）；
3. **没有真正的运行时自我迭代**（CodingAgent/CapsuleForge/HotReload 都是死代码，失败→修复闭环断在最后一步）。

---

## 2. 差距盘点（审计结论，三集群）

> 以下是开工前用并行只读审计 agent 得到的「真值」，区分"代码存在" vs "已接线可运行"。

### 集群 C — 地基与活体接线（最高杠杆）
- **活体回路确实存在**：`scripts/run_neurological_agent.py` → `create_live_genshin_loop` → `AgentLoop.run`，
  做 capture→VLM 分类→VLM 规划→执行→VLM 验证。但**最小化、云依赖、慢（~5–10Hz）**。
- **pose substrate**：`attach_pose_estimation` 此前**零活体调用方**；导航仍是开环像素朝向。← #1 杠杆缺口。
- **域协议适配缺失**：`ReactiveCombatController`/`PuzzleController`/`InteractionController` 此前**只被 sim 驱动**，
  无适配器把活体感知（`GenshinScreenClassifier` 输出字符串）翻译成 `CombatView`/`PuzzleView`。
- **YOLO 检测**在活体里被静默丢弃（`VLMPerceptionProvider` 没有 `_fusion`）。
- **两套任务系统**：`planning/mainline/MissionGraphV4` 与 `mission/` 并存；活体跑的是扁平语义动作而非 claim-gated DAG。

### 集群 A — 玩家交互界面（脚手架、单向、未接通）
- 桌面 GUI（Tauri+React + FastAPI）此前是**只读监视器**；无自然语言指令入口接到执行。
- `/goals/execute` 端点存在但 UI 从不调用；`UniversalEntryAgent` 从未被实例化。
- 语音 STT/TTS 是真实 API 客户端但**无消费者/无 UI**；persona 对白可用但**单向、仅 demo**。
- 完全缺失：玩家→agent 的指令/反馈/打断通道，以及 agent→玩家的提问/解释。

### 集群 B — 自我修改（"内置 Claude Code"）
- `CodingAgent` 存在但**从未用真实 LLM 实例化、从未被调用**；`CapsuleForge` 仅测试用；`HotReloadManager` 死代码。
- `CodeSandboxExecutor` 真实但**无硬超时**（安全缺口）。
- `EvolutionEngine` 做了 失败→补丁→沙盒→落盘，但**补丁从不重载/重试**——闭环断在最后一步。
- `ParameterizedSkillInductor` 产出的是**数据模板**，不是可执行代码。
- 结论：失败→合成代码→校验→热加载→重试→度量 的闭环此前 **0% 闭合**。

---

## 3. 已锁定的决策（你 2026-06-19 确认）

| 维度 | 决策 | 含义 |
|---|---|---|
| **运行目标** | 本机单人研究、自担风险 | 安全模型**不变**：dry-run 默认、InputLease/DeadmanSwitch/F9/focus/watchdog 永不削弱。这是硬红线。 |
| **首要焦点** | 三根支柱并行推进 | 路径不相交分片并行；共享接线文件（live_factory/loop/api/agent_controller）由集成者串行编辑。 |
| **自改授权** | **门控** | 生成+沙盒校验+提案；任何热加载进活体须人工批准。自动热加载驱动输入的代码=禁止。 |
| **Stop Contract** | 深度多支柱、跑到预算、存档可续 | 每分片提交+推送；测试常绿；过早停=失败。 |

宪法落在 `.bagel/constitution.yaml`（本地控制面，已 gitignore）。

---

## 4. 已完成的工作（验证状态）

> 原则：纯增量；安全模型不动；每个新模块带测试；零回归。两波均已提交+推送。

### Wave 1 — commit `475b8bf`
| 支柱 | 分片 | 之前 → 现在 |
|---|---|---|
| C | **pose substrate（C1）★** | 零活体调用 → `perception/live_pose_wiring.py`(`GenshinPoseWiring`) 每循环把融合 `PoseEstimate` 发布到真实 `StateBus.latest_pose`；`loop.py` 加守护式 tick；`live_factory.py` 建总线+接线。**纯感知、不驱动输入**。dry-run 构建已验证带 pose。 |
| C | 域协议适配（C2） | 仅 sim → `capsules/genshin/control_adapters.py`：活体感知→Combat/Interaction/Puzzle View，Action→`SemanticAction`（走胶囊 keymap）。 |
| A | 指令入口（A1） | GUI 只读 → `/command`(NL→`UniversalEntryAgent`→`execute_goal`) + `/interrupt`(P0 急停/P2 人工接管→StateBus) + 桌面指令组件。 |
| B | 沙盒安全（B1） | 杀不掉失控代码 → 进程隔离、Windows-spawn 安全的**硬超时**；`SandboxResult` 形状不变。自改的前置安全件。 |

### Wave 2 — commit `247e195`
| 支柱 | 分片 | 内容 |
|---|---|---|
| B | **门控自改闭环 ★** | `learning/self_modification_coordinator.py`：gap→合成(CodingAgent/LLM 或 EvolutionEngine 模板)→沙盒校验→**PROPOSE(PENDING)**。`approve()` 是**唯一**落地路径（写文件+`HotReloadManager.reload`+返回带度量槽的 `RetrySignal`）。已加固：**module_path 白名单+穿越防护**（自生成代码只能落到 `capsules/`、`skills/generated/`；绝对路径/`..`/逃逸→FAILED）。活体接线：`live_factory` 建协调器+HotReloadManager，`loop.py` ~0.2Hz tick 热重载（批准前为 no-op）。审查后端：`agent_controller` list/get/approve/reject + `api` `GET/POST /self_modifications[...]`。 |
| C | 队伍状态感知 | `capsules/genshin/party_state_reader.py`：从 HUD 读每角色 在场/血/能量/大招就绪/小技能就绪（经典 CV）；注入 `Observation.extensions["party_state"]`，使 `build_combat_view` 产出多角色 `CombatView`（控制器可放大招/小技能，不再只平 A）。阈值可调。 |
| A | 伴游"开口" | `persona/companion_feed.py`：活体 StateBus 中断→`DialogueGenerator` 台词→ws AgentState 的 `companion_message`→桌面气泡。`/command` 改为**非阻塞**（后台 job + `/command/status/{job_id}`）；回复走 persona 语气。 |

**测试**：两波合计 +60 个新测试（含 4 个自改路径守护用例）；各定向套件常绿，4493→4500+ collected，零回归。

---

## 5. 诚实的残留（还没做 / 还不能做）

> 这是续跑的工作清单。**没有任何一项被伪装成已完成。**

**集群 C**
- pose 的 **flow 符号/比例、行走世界速度** 需要真机小地图标定（`wire_genshin_pose(flow_world_scale=...)` 已留旋钮）。
- 活体无 `MotionCommand` 发射器（执行层发 `MovementIntent`）；死路推算暂用 shim + 名义速度。
- `NavigationCoordinator` 尚未消费 `StateBus.latest_pose`（pose 已发布，消费端待接）。
- **真机战斗"出招"仍被挡住**：队伍状态 CV 阈值是合理猜测，未经真机标定；适配器+读取器已建已测但**尚未在 loop 里驱动输入**（安全：不让未标定的大招乱放）。
- 两套任务系统未合并；活体仍跑扁平动作而非 claim-gated DAG。

**集群 B**
- gap→propose 的**自动触发**尚未从学习层（MetaLearningBridge 候选）接出；`CodingAgent` 暂以 `llm=None` 运行（仅模板兜底），待确认/接入文本 LLM provider。**门控落地机制本身已活体可用。**
- 批准后的**自动重试**已暴露（`RetrySignal`）但尚未在 loop 内驱动执行+度量。

**集群 A**
- 语音 STT 输入 + TTS 播放尚未接到指令入口/伴游输出（providers 真实但无消费者）。
- ws 仍是 0.2s 轮询；如需 <200ms 伴游延迟需改为事件推送。
- `/interrupt` 的 "override(改做 X)" 目前只入队 P2，loop 对 HUMAN_OVERRIDE 的消费（重规划）待接。

---

## 6. 安全态势

- 两波新增代码**安全洁净**：pose tick 纯感知不碰输入；沙盒进程隔离有硬超时；接口默认 dry-run；`/interrupt` 复用既有急停管线。
- 自改**门控是结构性的**（非劝告）：`propose_*` 路径下无任何模块写入/热重载；`approve()` 是唯一落地点，且有白名单+穿越防护。已有用例证明 PENDING 不改任何模块、不安全路径被拒。
- 既有遗留：`interaction/ui_flow_engine.py:525` 的 `SetCursorPos` InputLease 旁路（**非本轮引入**，待修）。
- 未削弱任何安全栏杆；未新增任何会自动驱动输入的路径。

---

## 7. 前向计划（Wave 3+）与待你决策的开放问题

### Wave 3 候选（按杠杆排序）
- **B**：把 gap→propose 从 MetaLearningBridge 候选自动接出；给 `CodingAgent` 接一个文本 LLM；在 loop 内驱动 `RetrySignal` 重试+度量 → 真正闭合"失败即自我编码改进"。
- **C**：`IntentBridge` 处发 `MotionCommand`；`NavigationCoordinator` 消费 `latest_pose`；**一个真机标定 pass**（pose 比例 + 队伍状态阈值），过后再开"战斗出招"开关。
- **A**：STT/TTS 真正接通双向语音；ws 事件推送；HUMAN_OVERRIDE→重规划。

### 待你决策的开放问题（这些会改变我怎么做）
1. **真机标定怎么进行**：你愿意提供真机小地图/HUD 截图（或一段录像）让我把 pose 比例与队伍状态阈值标定到可用吗？这是解锁"真机战斗/导航出招"的必要且唯一的门槛。
2. **文本 LLM provider**：CodingAgent 用哪个（GLM / MiniMax / 其他）？给定后自改可从"模板兜底"升级为"真合成新技能"。
3. **自改审查 UI**：是否要我在桌面 GUI 里加一个"自我修改提案"审查面板（列出待批补丁+代码 diff+一键 approve/reject）？后端端点已就绪。
4. **任务编排合并**：是否在本轮合并 `mission/` 与 `planning/mainline/`，让活体跑 claim-gated DAG（更强但工作量中等）？还是先把单原语打磨好再说？
5. **战斗出招的启用边界**：标定后，第一次让战斗适配器真正驱动输入，你希望先在 dry-run 录像里看决策、还是直接小心实跑？

---

## 8. 如何审查 / 如何续跑

- **看代码**：两波 commit `475b8bf`、`247e195`（分支 `codex/pre-realworld-closure`，已推送）。
- **跑测试**：`pytest tests/ -k "self_mod or party or companion or command or pose or control_adapters or interrupt"`。
- **看活体构建**：`python -c "from agent_kernel.live_factory import create_live_genshin_loop; l,c,b=create_live_genshin_loop(goal='探索', window_title='原神', dry_run=True); print(type(l._pose_wiring).__name__, type(l._self_mod_coordinator).__name__)"`。
- **续跑**：本地控制面在 `.bagel/`（`STATUS.md` 有活账本、`BUILD_PLAN.md` 有分片、`constitution.yaml` 有决策与 Stop Contract）。续跑时回到 §7 的 Wave 3 + 开放问题。
- **记忆**：跨会话要点已存入 agent 记忆 `three-pillar-live-build`。
