# Phase 4 收尾 / Phase 5 / Phase 6 对齐文档

> 范围：本文件汇报 Phase 4 收尾、Phase 5（任务编排）、Phase 6（试错→学习闭环 + 真实数据资产整合）的实际工作、独立审查结论、以及与北极星（自主通关原神主线）之间的诚实差距。
> 视角：以 coding agent 的执行节奏编写。所有"清关率/到达率"均为**离线确定性仿真**下测得，**不是真实游戏表现**——这是本阶段最重要的诚实声明。

---

## 0. 一句话现状

Phase 0–6 的**离线可建部分已全部落地**：空间地基、pose 闭环导航、试错引擎、战斗/交互/解谜/任务四类参考控制器、学习闭环、真实数据资产接入。每个阶段独立提交、推送、带测试、零回归（本轮 117 个测试全绿；全量套件此前 4391 passed/0 failed）。

**但必须诚实说明**：这些控制器目前是**参考实现 + 仿真 oracle**，尚未接入 live 执行栈（`live_factory` / `brainstem_navigator` / `MainlineRunner`），也未实现 `capsules/domain_protocols.py` 的协议契约。从"离线仿真通过"到"真实游戏通关"之间仍有明确的、巨大的集成工作量（见 §6）。两位独立审查者已确认这一判断。

---

## 1. Phase 4 收尾（解谜）

### 1.1 已交付
- `puzzle/puzzle_controller.py`：游戏无关 `PuzzleController`，实现精度迭代闭环 `propose → refine → act → verify → escalate`。核心原则——**精度来自迭代而非一次到位**：每步欠激（under-shoot）剩余误差、重测、在容差内 snap。
- `harness/sim/puzzle_world.py`：确定性对齐/放置类解谜仿真，带高斯测量噪声；`propose` 步是确定性替身（live 时替换为云端多模态调用）。
- 测得解谜率 **0.94（48 场）**：noise≤3 时 100%，noise=5 时 9/12，残留一个真实的高噪声 `timeout` 簇（3 个）。

### 1.2 独立审查驱动的收尾修复（commit 95cd9ba）
审查者发现的真实问题，已修：
- **P2 `min_step` 过冲**：`step = max(step_gain*mag, min_step)` 在容差 < 0.83 时会让步长 > 剩余误差（反而过冲）。改为 `min(max(...), mag)` 钳位。
- **P2 命名误导**：`max_attempts_per_phase` 实为全局计数（无 phase 概念），更名为 `max_attempts`。
- **P1 `escalate` 契约未文档化**：escalate 是终态，调用方必须 `reset()` 并重新 propose（如让云端 VLM 重新命名目标）——已写入 docstring。
- **过度宣称的 docstring**：`puzzle_world` 原宣称"live 环可无缝替换为真实视觉"，实际控制器尚未接 `VisionLLMProvider`。已改为诚实表述：本仿真是参考 oracle，live 接线是独立工作项。

---

## 2. Phase 5（任务编排）

### 2.1 已交付
- `mission/mission_graph.py`：`MissionNode` + `MissionGraph` DAG，带依赖、前置/后置 claim 条件、重试预算、跨节点 quest 上下文。
- `mission/mission_orchestrator.py`：图遍历器——选下一个可运行节点 → claim-gate 执行 → 应用 claimed 上下文 → 验证 postcondition；失败则归因并在预算内重试，否则阻断。是 `MainlineRunner + BAGEL` 的离线预演。
- `harness/sim/mission_world.py`：`ChapterNodeExecutor` 把每个节点派发给 Phase 0–4 真实子栈（nav/combat/interaction/puzzle），`make_chapter_graph` 生成主线章节 DAG（对话→行进→清剿→解谜→行进→boss→交付→领奖），注入一次瞬态故障以验证重试/恢复路径。
- 测得**章节端到端完成率 1.00（15/15）**，含从注入的 boss 瞬态故障中恢复。

### 2.2 独立审查驱动的修复（关键——审查者发现了严重 bug）
**P0（阻断级）`run()` 在任何持续失败时死循环**：`next_runnable()` 无条件返回 `failed` 节点，导致超出重试预算的节点被无限重新执行，只有 `max_total_steps` 能终止。而"预算耗尽即阻断"的测试只检查了最终状态、没检查执行次数，**所以测试通过却掩盖了死循环**。
- 修复：`next_runnable` 跳过超预算节点（terminal）；`_advance` 在执行**前**强制预算；超预算 → `blocked` 并级联到所有后代（`mark_blocked_descendants`）。
- 补强测试：断言执行**有界**——always-fail 节点对 max_retries=0/1/2 恰好执行 1/2/3 次。

**P1 postcondition 回滚丢数据**：回滚直接 `pop(key)`，若该 key 节点运行前就已存在，会删掉原值而非恢复。改为快照 prior 值 + 恢复。

**P1 失败节点的后代静默 stall**：硬失败节点本应让依赖者变 `blocked`，原来留在 `pending` 且 `finished=True`。现级联 `blocked`。

**P1 precondition 未在选择时强制**：`next_runnable` 原本不检查 precondition。已补上 claim-gate。

---

## 3. Phase 6（试错→学习闭环 + 真实数据整合）

### 3.1 学习闭环（失败 → 可复用知识）
- `harness/learning_bridge.py`：把 harness 的失败簇分类为通用 `FailureCategory`（party_wipe→HP_DEPLETED、timeout 按标签→COMBAT_TIMEOUT/NAVIGATION_FAILED/PUZZLE_FAILED 等）→ 喂给现有的 `GenericFailureAnalyzer` 检测重复 `FailurePattern` → 持久化进 `GameKnowledgeStore` 作为可查询 fact。失败不再是丢弃的遥测，而是结构化知识。`CampaignReport` 汇总失败类别分布 + 检测到的模式。

### 3.2 真实数据资产整合（充分利用增强包）
项目此前花了大量精力采集的原神/崩铁数据，此前**几乎没被代码读取**。现已接入：
- `data/game_assets.py`：加载真实 `character_profiles.yaml`（**110 角色**）、`team_profiles.yaml`（**36 队伍**）、怪物库、世界图。Loader 对那一个解析失败的文件（`genshin_monsters.yaml` 第 1110 行 `name_en: Ruin Drake: Earthguard` 未加引号冒号）**健壮跳过**，不影响其余加载。
- `harness/sim/asset_scenarios.py`：用**真实队伍**（国家队、雷神国家队…）生成战斗场景，用**真实世界图航点坐标**（数千单位级真实地理坐标）生成导航场景。
- `team_comp_to_sim`：把轮换首发提升为 dps（因 meta 队多为后台角色），让真实队伍可在战斗仿真中跑。

### 3.3 诚实的数据利用现状
- 已用：角色元素/冷却/能量、队伍成员构成、世界图航点坐标。
- 未用（高价值待接）：怪物 `weaknesses`（本可用于反应瞄准）、队伍 `recommended_rotation`、`data/skills/*_skills.yaml`、HSR 全部数据、`guides/*_combat_guide.yaml`、世界图 `edges/routes`。

---

## 4. 独立审查机制（本阶段过程）

按用户要求，每个阶段完成后派遣独立 agent 审查：
- Phase 4/5：2 位审查者（架构/复用 + 正确性/测试），已返回并修复了上述 P0/P1。
- Phase 6 + 全项目：4 位审查者（架构集成 / 正确性与测试 / 数据利用 / 安全与北极星对齐），**已在后台运行**。其结论返回后我会**逐条对照真实代码核验**（不盲信），有效的即修，然后补入本文件 §5。

## 5. 四位全项目独立审查结论（已逐条核验，非盲信）

派遣了 4 位独立审查者（架构集成 / 正确性与测试 / 数据利用 / 安全与北极星对齐），给足自由度、客观批判。**四人独立收敛于同一核心判断，与我自查一致**：

> Phase 0–6 是一个**测试良好、但完全仿真自洽的参考实现栈**，没有接入任何 live 运行路径，提交标题用"complete / closure"**过度宣称**了。

### 5.0 实质强化(第二轮,commit aa6ef3d)——把"仿真单薄"补成"数据驱动+鲁棒"

针对审查者"控制器与数据脱节、仿真过易"的核心批评,做了三项实质强化(非表面):

**Phase 6 / 战斗——让策展数据真正驱动决策**:
- `ReactiveCombatController` 新增**弱点/反应感知的轮换选人**:对后台技能就绪角色按"与当前 aura 触发元素反应"+"命中怪物 DB 已知弱点"打分选人;无数据时退化为原行为(严格改进)。
- `combat_world` 建模弱点(命中弱点 1.5× 伤害),弱点透传进 view。**恢复的 208 怪物弱点现在真正改变战斗**。行为差异测试证明数据 load-bearing(无弱点数据选 index 1,有弱点数据翻转到 index 2)。
- **真实资产战斗 0.75 → 0.90**(真实队伍 vs 真实怪物弱点)。

**Phase 5 / 任务图校验**:
- `MissionGraph.validate()`:检测悬空依赖(原会 mid-walk KeyError)与依赖环(原会静默 stall);`next_runnable` 现 KeyError-safe;`run()` 先校验、失败即给诊断。4 个新测试。

**Phase 4 / 解谜系统性偏差鲁棒性**(真实 VLM 失败模式):
- 发现真实失败:恒定垂直测量偏差使误差梯度环收敛到"测量为零但真实偏移 bias"的点,永不能解(bias≥2 时 **0/20**)。根因是控制器卡在 verify 死循环("测量说在容差内"但 sim 真值未确认)。
- 修复:统计"未确认 verify"+停滞,回退到由**真值 verify 驱动**的物理就近网格搜索(不信有偏测量)。**垂直偏差 0/20 → 20/20**(bias 2-4 全过);零偏差回归 0.94 → **0.98**。

### 5.1 已核验并修复的有效发现(第一轮)

| 发现 | 来源 | 核验 | 处置 |
|---|---|---|---|
| **`genshin_monsters.yaml` 解析失败丢掉 208→0 全部怪物**（ScannerError 中断整文件，非丢 1 行） | 数据审查 P0 | 已核验：文件 208 个 monster_id，16 行 `name_en: X: Y` 未加引号冒号 | **已修**：精确引号那 16 行，恢复全部 208 怪物 |
| **学习闭环 write-only**：`learning_bridge` 存了 `failure_pattern` fact，但全项目无任何读取者，自改进回路未闭合 | 数据 P0 / 架构 P1 | 已核验：grep 读取者为零 | **已修**：新增 `control/recovery_strategies.KnowledgeAwareRecovery`，恢复时查询知识库并按学到的 suggested_fix 选机动；测试证明写入→读取→行为变化 |
| **puzzle escalate 永久锁存**：一旦 stall，`_best_error_mag` 不重置，之后每帧 escalate 直到超时 | 正确性 P2 | 已核验：恒定误差输入序列确为 act×6→escalate×∞ | **已修**：escalate 时重置 stall 计数，使条件改善后可恢复迭代 |

### 5.2 已核验但未在本轮处置的发现（需 live 集成战役，见 §6）

这些是真实的，但**修复属于"真实游戏集成"阶段**，不在本轮"离线可建"范畴：

- **新导航/任务栈未接 live**（架构 P0）：`pose_navigation`/`navigation_coordinator`/`mission/` 仅被 `harness/sim/*` 与测试引用；live 仍跑旧的 `navigation_runtime`（经 `brainstem_navigator`）与 `MissionGraphV4`/`mainline_runner`。`attach_pose_estimation` 全仓库仅被 1 个测试调用，从未进 `live_factory` 或任何 capsule install()。
- **新控制器未实现 `domain_protocols`**（架构 P0）：`CombatView/InteractionView/PuzzleView` 与 `CombatPlannerProtocol/NavigatorProtocol/DialogHandlerProtocol` 类型不兼容，无适配层，真实胶囊无法直接喂。
- **`DualModelCoordinator`（M3 感知 + GLM-5.2 推理）未接 live**（安全审查 P1）：仅 `model_team.py` + 测试引用；从未用真实 API key 验证。
- **战斗弱点未驱动反应瞄准**（数据 P1）：`GenshinCombatPlanner` 有能力，但 live 调用方传假 enemy_id（`world_boss`/`commission_enemy`），胶囊 provider 是返回 `["LMB","E","Q"]` 的硬编码 stub。
- **世界图 edges/routes 未进寻路**（数据 P0）：live `RouteSelector` 跑 demo 数据（3 航点），非真实 230+ 航点。
- **技能 YAML 未进 runtime**（数据 P1）：`GenshinSkillLoader` 无 live 引用者；HSR 数据大部分未加载。

### 5.3 安全结论（审查 4）
**新代码安全洁净**：所有新控制器是纯决策策略（`decide(view)→action`），不触 OS 输入、不发网络、只用 `time.perf_counter()`——正因为没进执行平面，所以不可能违反 InputLease/deadman/时钟规则。LLM 网络路径（截图上传）受显式 key + `LLMRequestGuard` 限流 + 默认 mock 保护，符合 dry-run 默认姿态。GLM-5.2 经核验为真实（2026-06-13 发布，端点匹配）。

**一处预存（非本轮）InputLease 旁路**：`interaction/ui_flow_engine.py:525` `backend._user32.SetCursorPos(...)` 在 backend 缺 `move_cursor` 时直接 ctypes 伸入。属快照提交的旧代码，不是本轮回归，已登记待修。

### 5.4 指标诚实度（审查 2）
审查者独立复测了各批次率，与我引用值基本一致（微小差异源于种子/规模）。**关键诚实点**：测试断言门槛远低于宣传值（战斗 `>=0.55` vs 0.92、解谜 `>=0.7` vs 0.94）——测试证明"能跑通"，不等于"达到宣传率"。复测实测值：nav 0.95、combat 0.956、puzzle 0.925、commission 1.00、chapter 0.95、asset-combat 0.75。引用时应附实测值。

### 5.5 关于"过度宣称"
审查 4 指出：内部 `STATUS.md`/`state.yaml` 本来诚实（标 Phase 6 "blocked on real game"），但**提交标题**（`Phase 5 complete`、`Phase 6 … closure`）与 ROADMAP 的真实 exit gate（真实章节通关）不符。我不会重写已推送的历史（破坏性、违反安全规则），但本文件与 STATUS.md 已据实修正为"离线参考实现，未接 live"。后续提交将用"offline reference / sim-only"措辞。

---

## 6. 与北极星的诚实差距

（原 §6 内容保留并强化）北极星：无需训练、自主通关原神主线。当前诚实差距，按优先级（这些就是真实游戏集成阶段的任务清单）：

1. **Live 接线（最高）**：pose 处理器进 `live_factory`/capsule install；导航协调器接 `brainstem_navigator`（或合并旧 `navigation_runtime`）；`mission/` 并入或复用 `planning/mainline/`。
2. **协议合规 + 适配层**：让参考控制器实现/适配 `domain_protocols`，真实胶囊可喂数据。
3. **真实标定**：minimap 光流符号/尺度、相机伺服增益——必须在真实游戏标定。
4. **真实视觉闭环**：解谜/场景 `propose` 步接真实 `VisionLLMProvider`（MiniMax-M3）。
5. **双模型接线**：`DualModelCoordinator` 接 live 感知→规划节点，并用 key 验真实 API。
6. **战斗弱点驱动**：传真实 monster_id（从感知）进 `GenshinCombatPlanner`，胶囊 provider 委托给它。
7. **学习读侧 live 化**：`KnowledgeAwareRecovery` 已证明闭环可行，需接 live 恢复路径。
8. **修预存 InputLease 旁路**：`ui_flow_engine.py:525`。

**结论（诚实）**：本轮把"可离线建的部分 + 可复用范式 + 真实数据底座（208 怪物/110 角色/36 队伍/230 航点已可加载）+ 闭环学习（读侧已通）"打牢了。从仿真到真实通关是一场需要真实游戏在场的集成战役；提交标题此前的"complete/closure"措辞过度，已在本文件据实修正。

---

## 7. 提交与可追溯性

本阶段提交（分支 `codex/pre-realworld-closure`，全部已推送）：
- `676503a` Phase 4 start: puzzle controller
- `ac9ba4c` Phase 5 complete: claim-gated mission orchestration
- `95cd9ba` fix: Phase 4/5 review findings（P0 死循环 + P1 回滚/阻断）
- `95cd9ba`(cont) Phase 6: trial-and-error→learning closure + real-asset integration

工作区干净，117 个本轮测试全绿。
