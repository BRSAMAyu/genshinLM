# Aurora 分层运行时计划 — 批判性分析报告

**审查范围**: `docs/AURORA_LAYERED_RUNTIME_AND_LOCAL_VLM_EXECUTION_PLAN.md`
**审查结论**: 方向正确，架构合理，但存在 14 处需要修复的逻辑缺陷、4 处架构裂缝、3 处严重安全盲区，以及 2 处必须先于实现澄清的概念性问题。

---

## 一、整体评价

**优点（事实性确认）**：
- L0-L9 分层边界清晰，与现有 `InputLease`、`ObservationGraph`、`Capsule` 实现在逻辑上一致。
- 硬性边界（第 6 节）定义正确：禁止内存读取、禁止直接键鼠输出、禁止在 core 里写游戏逻辑。
- 本地 VLM 设计正确：OpenAI-compatible 不绑定具体型号，E2B/E4B 任务级路由思路合理。
- 失败定位按层级分类的设计符合系统工程原则。

**核心问题**：这份文档是**工程规格说明**，不是**实施计划**。Phase 1 写了 5 个组件名但没有说哪些是全新的、哪些是演进现有代码的、它们的接口边界在哪里、它们之间的依赖关系是什么。这会导致 coding agent 产生大量返工。

---

## 二、逐层批判分析

### L0 Physical Safety — 基础正确，执行有误

**正确之处**：`InputLease` + `PhysicalActionReceipt` 架构是对的。action family label 扩展合理。

**缺陷 1（逻辑错误）**：文档说"所有上层 Controller 只能拿到 receipt，不能直接调用 OS 输入"，但没有说明若 Controller 错误地直接调用了 OS 输入，**谁来检测和拒绝**。这缺少一个 enforcement layer — 要么在 `InputWorker` 入口做 audit trail，要么让 receipt 成为唯一的 release 凭证，否则这条规则形同虚设。

**缺陷 2（遗漏）**：`deadman switch` 触发后的状态没有定义。`release_all` 后系统进入什么状态？Mission 是否自动 abort？还是进入 `idle` 等待重试？文档没有说明。如果停在"部分输入已释放但任务未确认终止"的状态，下次 resume 可能产生双重执行。

**缺陷 3（边界案例）**：`InputLease` 过期时的处理是"优先释放"，但没有定义**竞态条件**：当 lease 刚过期、上层 Controller 仍在执行 `execute` 时，物理输入是否应该等待 Controller 完成当前 action 队列？或者立即中断？立即中断可能导致 UI 停在半空（点击了确认但未等结果），这是比"没执行"更危险的错误状态。

---

### L1 Motor Layer — 完整性不足

**缺陷 4（关键遗漏）**：`MousePathPolicy` 引入了 4 种策略（straight/bezier/jitter_bounded/instant），但没有定义**选择规则**。哪个 Controller 用哪种策略？`ui_click` 用 instant 还是 bezier？`movement` 用 straight 还是 jitter_bounded？在实际场景中，错误的选择会导致：点击落点偏移（instant 跳变过大）、移动被人脸识别为外挂（straight 线不自然）、bezier 在边界处过界（path 超出了 safe window ROI）。这个决策逻辑必须在实现前写清楚，否则每个 Controller 都会各自造轮子。

**缺陷 5（依赖缺失）**：`MousePathPolicy` 的输入依赖 `CoordinateMapper` 的输出，但文档没有定义 `CoordinateMapper` 的坐标系映射表（window-normalized → screen px 的转换规则）。对多窗口游戏（如 HSR 全屏 + 桌面分屏）或 DPI 缩放场景，如果没有显式的坐标校准步骤，点击落点会系统性偏斜。

**验收条件不足**："同一 normalized point 在 1280x720、1920x1080、2560x1440 能映射到正确区域"这个验收没有考虑：
- fractional scale（如 125% / 150% DPI）
- 游戏内部分辨率 vs 系统分辨率不匹配（如游戏 1280x720 但系统 2560x1440）
- 窗口被其他窗口部分遮挡的情况

---

### L2 Universal Desktop Tree — 依赖关系不清晰

**缺陷 6（核心依赖缺失）**：`DesktopTree` 的构建依赖 LLM（或 VLM）来生成节点，但 LLM 的输出格式没有 schema 约束。文档说"VLM 只在置信度低时补全"，但：
- "置信度低"由谁判定？`ObservationGraph`？还是 Controller 自己的置信度？
- 如果 VLM 不在本地（LM Studio 关闭），降级路径是什么？文档说"兜底 Visual Agent 只能产出候选节点"，但没说如果 VLM 不可用时谁来生成这些候选节点。
- 候选节点如何映射到物理动作执行？`UIController.can_handle` 接收的是 `SemanticAction`，但 `DesktopTree` 节点是 OCR/template 检测结果，两者之间没有显式转换路径。

**缺陷 7（循环依赖）**：`ObservationBuilder` 输出 `DesktopTree` 派生摘要，但 `DesktopTree` 的节点 source 包含 `vlm`。如果本地 VLM 不可用导致节点缺失，`ObservationBuilder` 的输出质量下降；质量下降导致 Controller 的 `can_handle` 判定错误；判定错误导致 Controller 拒绝处理；然后系统降级到 LLM replan。这形成了一个**降级循环**：系统依赖 VLM 的存在来生成输入，但 VLM 的不可用导致系统需要更频繁地调用 VLM（因为其他路径都失败了）。

---

### L3 Perception — 观察质量报告不够

**缺陷 8（观察质量报告的使用路径缺失）**：`ObservationQualityReport` 定义了 4 种不良情况（stale frame、missing OCR、conflicting screen_state、low evidence coverage），但没有定义**如何使用这个报告**：
- 报告分数低到什么程度才触发降级？阈值是多少？
- 降级后走哪条路径？是 LLM retry、refresh observation、还是 abort mission？
- 如果同一帧连续 N 次都是低质量，说明摄像头/屏幕捕获本身有问题，这时候系统的应对是什么？

此外，`screen_state` conflict 的仲裁规则没有定义。如果 `OCR` 说"这是 dialog"，但 `HSRScreenClassifier` 说"这是 combat"，系统应该相信谁？这两个来源之间没有优先级说明。

---

### L4 Controller — 接口设计有逻辑错误

**缺陷 9（Protocol 设计错误）**：

```python
class Controller(Protocol):
    controller_id: str
    def can_handle(action: SemanticAction, ctx: ControllerContext) -> bool: ...
    def execute(action: SemanticAction, ctx: ControllerContext) -> ControllerResult: ...
```

这个 interface 的问题是：如果 `can_handle` 返回 `False`，上层（ControllerRouter）应该选谁？文档没有定义 ControllerRouter 的逻辑。这意味着有两种可能的实现：
1. `can_handle=False` 意味着这个 Controller 跳过，继续选下一个
2. `can_handle=False` 意味着**没有** Controller 能处理，需要上报

这两种实现的语义完全不同。如果按第 1 种实现，当所有 Controller 都返回 `False` 时，任务就没人处理了。如果按第 2 种实现，系统会进入 LLM replan 路径。这必须在文档里写清楚，不能留给 coding agent 揣测。

**缺陷 10（ControllerResult 的 evidence_refs 类型不明确）**：`ControllerResult` 的 `evidence_refs: list[str]` 没有定义格式。是 evidence graph 的 node ID？是截图文件路径？是 timestamp+region 描述？如果 coding agent 按不同理解实现，这会导致 Verifier 无法解析 evidence_refs，整个验证链断裂。

---

### L5 Skill — 版本兼容性没有说明

**缺陷 11（Skill 版本兼容性）**：

```text
skill_id
version
```

文档说了 `version` 字段，但没有定义：
- 同一 capsule 能否同时注册同一 skill 的多个版本？
- 不同 capsule 之间 skill 版本冲突时（capsule A 依赖 v3，capsule B 依赖 v2）如何处理？
- Skill 在旧版本运行失败后，能否自动降级到同一 skill 的更早版本？还是必须上报用户？

此外，"Skill failure 自动生成 repair session 和 regression case"这个描述过于模糊。repair session 的输入是什么？是 failure signature？是 failed semantic action？是 recorder trace？这些必须先定义，否则 coding agent 会造出一个无法实际使用的 repair 系统。

---

### L6 Capsule — lifecycle uninstall 不完整

**缺陷 12（uninstall 遗漏）**：文档列出了 6 项完整的 uninstall 内容，但没有包含：
- `controller_bindings` 的卸载（Phase 4 会新增 Controller）
- Capsule 专属的 `ObservationGraph` namespace 清理
- Capsule 专属的 `StateBus` slot 清理
- Benchmark 中 Capsule 专属测试用例的卸载

如果不清理这些，系统会在卸载后留下 dangling reference，导致下次安装同 capsule 时命名冲突。

---

### L7 Mission Graph — 检查点语义不明确

**缺陷 13（检查点内容模糊）**：

```text
- 每个 MissionNode 成功后写 checkpoint。
- 每 N 分钟进入 periodic safe point。
```

"写 checkpoint"没有定义 checkpoint 包含什么。至少应该包括：
- 当前 MissionNode 和其状态
- 所有 active slot 的最新值
- 已完成的 evidence graph 摘要
- 当前的 LLM context summary（不是完整 context，是投影后的摘要）

如果没有这些字段定义，coding agent 会实现出一个只保存"我做到了第几步"的粗糙检查点，resume 时无法 revalidate 状态，导致 mission 从错误的上下文重启。

---

### L8 Persona — 表达层与控制层隔离不彻底

**缺陷 14（潜在绕过）**：文档说"Persona 不允许说'已完成'除非 verifier ok"，但没有说明 enforcement 机制——如果某次调用中 Persona 代码被绕过（在紧急情况下开发者直接调用 `companion_message()` 跳过了 verifier 检查），系统无法检测。更根本的问题是：如果 `CompanionMessage` 和 `TechnicalTrace` 是并行输出的，Companion layer 的延迟会不会阻塞 TechnicalTrace 的输出？这两者的优先级没有定义。

---

## 三、架构裂缝（跨层问题）

### 裂缝 1：Context 压缩的正确性验证

`runtime/context_compactor.py` 的存在说明系统有上下文压缩能力，但文档没有定义：**压缩后的 context projection 如何被验证是正确且完整的**？特别是：
- 如果压缩算法错误地删除了关键信息（比如某个 rare edge case 的处理规则），系统在没有报错的情况下会静默失败
- LLM 在压缩后的 context 下做决策，但如果决策依赖于被压缩掉的隐式信息，LLM 会产生幻觉决策
- "上下文压缩后，Agent 不能依赖自由文本记忆断言历史事实"这一条在实现上如何强制？

这个问题在 Mission DAG 的重规划场景下尤其严重：`LLM replan` 的输入是压缩后的 projection，但如果压缩丢失了导致失败的关键信息，replan 只是在错误的基础上迭代。

### 裂缝 2：Local VLM 与云端 LLM 的决策边界没有量化

文档说"简单 UI 用 E2B，复杂 screen/frame 用 E4B，长程规划用云端"，但没有定义"简单"和"复杂"的分界线。这会导致 coding agent 按自己的理解实现路由策略，结果可能在实际运行时：
- 简单 UI 也用 E4B（因为定义宽松），导致本地 GPU 负载过高、延迟反而大于云端
- 复杂 failure explanation 用了 E2B（因为没有明确要求），导致准确性不足，产生错误的修复建议

### 裂缝 3：Long-Running Session 的状态一致性

Phase 5 提到"每个修复都有 before/after 指标"，但没有定义**这些指标存储在哪里、生命周期是多久、是否跨 session 持久化**。如果 failure 发生在第 3 天的长 session 中，修复记录能否在第 4 天被引用？Skill version 能否跨 session 演进？如果这些没有定义，Phase 5 的"failure-to-repair 全链路"实际上只对单次 session 有效，无法积累系统性知识。

---

## 四、必须先澄清的概念性问题

### CP-1：Human-in-the-loop 的位置

文档将"用户确认"作为 fallback ladder 的倒数第二步，但全文没有说清楚：
- **日常任务**（如采集、导航、每日委托）是否需要每次都用户确认？还是只有"风险操作"才需要？
- "风险操作"的定义是什么？谁定义这个阈值？
- 如果用户长时间不响应（如 30 分钟没有操作），系统应该做什么？是保持 MissionNode 状态等待？还是超时 abort？
- 首次 onboarding 的 Calibration Wizard 是完全自动的还是有用户参与的？参与的程度是多少？

没有这些定义，Phase 2 的 Desktop UI 实现会产生大量歧义，coding agent 不得不做大量假设。

### CP-2：Skill 与 Controller 的边界

文档出现了两种能力节点：`SemanticAction` 和 `Controller`。但没有说清楚它们的关系：

```
Skill -> SemanticAction -> Controller
Skill -> SemanticAction -> (no Controller, direct execution?)
```

两种可能：
1. Skill 是"能力声明"，Controller 是"执行引擎"，SemanticAction 是两者的连接协议
2. Skill 本身包含 Controller 的能力，不需要单独调用

如果按第 1 种理解，那么 Skill 只是一个配置文件，Controller 是实际执行者。这样设计是合理的。
但如果按第 2 种理解，那么 Controller 就变成了 Skill 的子模块，Controller protocol 就多余了。

这必须先澄清，因为 Phase 4 的 Controller 完善（DialogueController、CraftingController 等）直接依赖于这个边界定义。

---

## 五、严重安全盲区

### SB-1：VLM 注入攻击面

文档描述了本地 VLM 接入，但没有考虑：**如果本地 VLM 被污染或返回恶意响应，系统如何防御？**

具体场景：
- Skill 录制中 VLM 生成的 semantic action draft 被注入恶意指令
- DesktopTree 节点被 VLM 注入不可见坐标（如点击一个正常按钮实际上会在另一区域执行操作）
- failure explanation 由 VLM 生成时，如果 VLM 被攻陷，可能返回"一切正常"来掩盖真实错误

文档的硬性边界（不直接调用 OS 输入）对 LLM/VLM 输出同样适用，但当前只在第 5 节说了"所有输出必须通过 validator"，没有针对 VLM 输出的专门验证步骤。

### SB-2：Controller 结果的不可验证性

如果 `ControllerResult.failure_code` 是 Controller 自己填写的（不是系统判定的），那么 Controller 可以"隐瞒失败"。比如：
- `UIController` 说"点击成功"但实际上按钮没有变化（click no effect）
- `NavigationController` 说"路径有效"但实际上目标是不可达的

文档提到 "Controller 失败必须返回 failure_code，不能抛出裸异常给上层"，但没有说 failure_code 的正确性由谁验证。

### SB-3：Benchmark 污染

文档的验收标准包含：

```bash
rg "\b(genshin|hsr|honkai|star_rail)\b|崩坏|星穹" core --glob "*.py"
```

但这个检测只针对字面上的游戏名。如果 core 中存在间接依赖（如 `from game_impl import *`，`import *.characters`，动态 `__import__`），这个正则检测会失效。真正的无污染验证需要静态分析工具，而不是 grep。

---

## 六、实施优先级建议

### 必须先于 Phase 1 实现的内容（否则必然返工）

1. **定义 ControllerRouter 的选择逻辑**（缺陷 9 的修复）
2. **定义 checkpoint 的 schema**（缺陷 13 的修复）
3. **定义 action family label → MousePathPolicy 映射规则**（缺陷 4 的修复）
4. **澄清 CP-1 和 CP-2**（Human confirmation 位置、Skill/Controller 边界）

### 可以后置但必须记录的设计决策

5. VLM 输出 schema（JSON schema 用于约束 LLM 的 UI grounding 输出）
6. benchmark 的失败标准（什么情况下 AuroraBench 应该拒绝通过）
7. Skill version 跨 session 的持久化策略

### 文档改进建议

- 每层增加"依赖其他层的哪些组件"和"被其他层依赖的哪些接口"两个子节
- Phase 1 的每个组件增加"新建 vs 演进现有代码"的明确标注
- 增加"不可实现的边界案例"子节，明确说明哪些场景当前架构无法处理

---

## 七、最终评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构方向 | 9/10 | 分层清晰，与现有实现一致 |
| 完整性 | 6/10 | 有 14 处关键逻辑缺失 |
| 可实施性 | 5/10 | Phase 1 定义模糊，必然返工 |
| 安全性 | 5/10 | 3 处严重盲区，VLM 注入面尤其危险 |
| 可验证性 | 6/10 | benchmark 设计合理但验收条件不完整 |
| 可维护性 | 7/10 | 文档结构好，但关键设计决策分散 |

**综合结论**：这份文档作为 **架构设计说明** 是优秀的，可以作为长期演进的技术路线图。但作为 **coding agent 的实施指引** 是不充分的——Phase 1 必须先完成上文"必须先于实现"列出的 4 项内容，否则 coding agent 会在 Controller 接口、checkpoint schema 和路由逻辑上产生不可兼容的分歧。