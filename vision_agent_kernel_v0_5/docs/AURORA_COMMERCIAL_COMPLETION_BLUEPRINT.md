# Aurora 商业完成度与内容体系蓝图

本文档面向后续 Coding Agent、产品设计、Capsule 开发者和测试负责人。目标不是再写一份抽象愿景，而是把 Aurora 从“架构组件已经很多”推进为“可以被用户理解、安装、校准、使用、复盘、扩展和商业推广”的完整产品。

核心判断：

- Aurora 的壁垒不应是“让大模型直接操控键鼠”，而是“用可验证的本地运行时、可校准的 UI/视觉锚点、可复用的 Skill/Capsule 内容和可审计的任务闭环，降低大模型负担”。
- 当前项目已经有较强的底座：五平面架构、InputLease 安全执行、Claim-Centric Runtime、Declarative Verifier、MissionGraph、Capsule、HSR/Genshin 数据包、Local VLM/OCR 接口、AuroraBench、BossBench、DecisionMemory 等。
- 当前项目尚未达到商业可用：内容资产不够成体系，真实任务闭环还需要用 Profile、Skill、Verifier、Benchmark 绑定；无录制泛化 Agent 只能作为受监督兜底，不能作为 unattended 主路径；用户和开发者体验仍需产品化。

## 1. 产品北极星

Aurora 应定义为：

> Local-first, verifier-first visual agent runtime for safe, replayable, extensible desktop and game workflows.

中文表述：

> 一个本地优先、证据优先、可校准、可复盘、可扩展的视觉 Agent 运行时。它通过 Capsule 装载具体游戏/桌面应用，通过 Skill 表达可验证能力，通过 ClaimGraph 和 Verifier 证明每一步真实发生，通过 InputLease 和安全窗口保证物理操作可控。

### 1.1 不做什么

- 不做反作弊绕过、内存读取、进程注入、驱动级输入。
- 不承诺“任意游戏零配置全自动通关”。
- 不把 VLM/LLM 的单次判断当作事实源。
- 不把未验证的鼠标轨迹当成稳定 Skill。
- 不在没有授权窗口、Profile Preflight、InputLease、ReleaseAll 兜底的情况下运行 unattended 自动化。

### 1.2 要做到什么

商业推广时必须能讲清楚四类价值：

1. **用户价值**：用户不用理解底层脚本，只需安装 Capsule、完成校准、选择任务，系统能可靠执行日常、UI、采集、对话、奖励领取、部分战斗/跑图，并在不确定时诚实停下或请求确认。
2. **开发者价值**：开发者不用改 core，只需写 Capsule Manifest、UIAnchor、VerifierRecipe、Skill YAML、Knowledge Pack 和 Benchmark，即可扩展一个新游戏或新流程。
3. **技术壁垒**：Claim-Centric Runtime、Verifier-first 证据闭环、InputLease 安全租约、Reflex/Controller 快慢脑分离、Skill/Failure 飞轮、Capsule 资产体系。
4. **商业资产**：官方 Capsule、Skill Packs、Knowledge Packs、Benchmark Packs、Persona Packs、教学模板、失败案例库和创作者工作台。

## 2. 目标用户与核心需求

### 2.1 普通用户

需求：

- 希望用自然语言或图形界面安排任务，例如“今天把日常奖励领完”“去合成指定材料”“跑一条采集路线”。
- 希望系统少打扰，但关键风险要提示。
- 希望本地运行、成本可控、隐私可控。
- 希望失败时不是一堆 traceback，而是看得懂的原因、截图、建议和一键修复入口。

必须交付：

- 一键启动面板。
- Capsule 安装与健康检查。
- 图形化校准向导。
- 任务模板库。
- 运行进度面板。
- 安全停止按钮。
- 失败报告与复盘包。
- 本地模型/OCR 健康检查。

### 2.2 高级用户与创作者

需求：

- 能录制、编辑、验证、发布 Skill。
- 能为新游戏/新 UI 创建 Capsule。
- 能校准和调试 UIAnchor、OCR、模板和 Verifier。
- 能用 Benchmark 证明自己的 Skill 真的稳定。

必须交付：

- Capsule DevKit。
- Skill Studio。
- Verifier Studio。
- UIAnchor Inspector。
- Mission Composer。
- Knowledge Pack Editor。
- Benchmark Runner 与报告。
- 发布前质量门禁。

### 2.3 研究与工程团队

需求：

- 可复现、可测量、可审计。
- 能比较不同模型、OCR、Verifier、Skill 版本的真实效果。
- 能定位长程任务失败点，而不是只看最终失败。

必须交付：

- ClaimGraph trace。
- EvidenceGraph frame refs。
- RunJournal。
- ReliabilityStore。
- DelayedAudit。
- AuroraBench v2。
- Long-run endurance。
- 模型路由与成本/延迟报告。

## 3. 当前能力盘点

### 3.1 已具备的底座

当前代码和文档已经显示出以下基础能力：

- **五平面架构**：Perception、Control、Execution、Orchestration、Telemetry，外加 Product Shell。
- **安全执行**：InputLease、Deadman、Focus Guard、SafeWindow、release_all。
- **Claim 主链路**：StateDeltaClaim、ObservationClaim、ClaimGraphWorker、ClaimAdjudicator、ReliabilityStore、DelayedAudit。
- **声明式验证基础**：VerifierCompiler、DeclarativeVerifierEngine、ClaimRecipe、source family、risk budget。
- **泛化感知与任务脑雏形**：ScreenStateClaim、ActionAffordance、HierarchicalPlanner、MissionGraph v3、AutonomousTaskBrain。
- **持久记忆**：DecisionMemory、RunSummary、Reliability statistics。
- **Capsule 架构**：Genshin、HSR、desktop_ui、demo_arpg，ProviderRegistry，Capsule Manifest。
- **OCR 与 VLM 管线**：PaddleOCR/GLM-OCR 分层思路，OpenAI-compatible local VLM/LM Studio 接口。
- **内容资产雏形**：Genshin/HSR 角色、资源、任务、boss、skill、patch、benchmark 报告。
- **验证体系**：pytest、compileall、core boundary scan、AuroraBench、BossBench。

### 3.2 尚未达到商业完成度的部分

必须承认以下事实：

- **无录制泛化 Agent 还不能作为主力无人值守能力**。它可以做 supervised fallback、低风险探索、候选 UIElement 提议，但不能替代 Capsule/Skill/Verifier 主路径。
- **内容资产缺乏产品组织**。已有 YAML、patch、bench 报告很多，但用户不知道哪些是官方稳定流程、哪些是实验数据、哪些适合真机。
- **真实 Profile 绑定流程仍需产品化**。商业用户不能接受手工改 YAML、猜 ROI、看日志定位 OCR。
- **Skill 录制到语义 Skill 的闭环仍需强化**。录制原始轨迹只是素材，必须蒸馏为 semantic action + anchor + verifier + fallback。
- **Verifier 的可编辑和可理解体验不足**。开发者需要声明式模板和可视化调试，不应每次写 Python。
- **长程任务的完成度仍取决于任务内容库**。Planner 不能凭空理解每个游戏任务，它需要 Capsule plan templates、knowledge pack、mission graph examples。
- **真机前安全边界必须更明确**。所有商业 demo 应先落在 dry-run/testbed/授权窗口，真实客户端测试必须走用户确认与安全守卫。

## 4. 商业产品分层

Aurora 不应只按代码模块解释，而应按用户和开发者可理解的服务协议解释。

```text
L8 Product Experience
  用户任务、伴游角色、GUI、创作者工作台、反馈包

L7 Capsule Domain
  游戏/应用特调包：UIAnchor、OCR词典、知识库、Skill、Verifier、Benchmark

L6 Mission Planner
  用户目标 -> MissionGraph DAG -> 可替代路径 -> checkpoint

L5 Skill Contract
  可验证能力：precondition、semantic action、claim、verifier、fallback、risk

L4 Semantic Controller
  UI、导航、战斗、系统动作控制器

L3 Claim And Verifier Truth Plane
  StateDeltaClaim、ObservationClaim、ClaimAdjudicator、DelayedAudit、Reliability

L2 Observation OS
  Frame、OCR、UIElement、ScreenState、Object、Danger、Quest、Navigation signal

L1 Physical Safety And Motor
  SafeWindow、InputLease、MousePath、Keyboard、ReleaseAll、Reflex

L0 Runtime Health And Telemetry
  队列、线程、内存、帧延迟、模型延迟、异常、benchmark、run journal
```

每层必须提供稳定交付物：

| 层 | 稳定交付物 | 上层不应知道 | 失败出口 |
|---|---|---|---|
| L1 | PhysicalActionReceipt | OS 输入细节 | release_all + interrupt |
| L2 | ObservationGraph | OCR/OpenCV/VLM 实现细节 | stale/low_quality observation |
| L3 | AdjudicationEvent | 单个 verifier 内部算法 | uncertain/rejected/error |
| L4 | ControllerResult | 鼠标轨迹和按键时序 | bounded retry/safe abort |
| L5 | SkillResult with Claims | 低层坐标和帧处理 | local fallback/escalate |
| L6 | MissionNode state | 单步输入细节 | replan around/ask/abort |
| L7 | Capsule health | core 实现 | profile repair/dev diagnostics |
| L8 | 用户可懂状态 | 栈内细节 | supervised recovery |

## 5. 内容体系：从框架到产品的关键

商业完成度不是“有框架”，而是“有足够好的内容”。Aurora 需要把内容分成七类资产。

### 5.1 Official Capsule Packs

每个官方 Capsule 必须包含：

- `capsule.yaml`
- `resources/ui_anchors.yaml`
- `resources/screen_regions.yaml`
- `resources/ocr_dictionary.yaml`
- `resources/task_patterns.yaml`
- `resources/mission_templates.yaml`
- `resources/verifier_recipes.yaml`
- `skills/*.yaml`
- `benchmarks/*.yaml`
- `docs/user_guide.md`
- `docs/developer_notes.md`
- `profile_checklist.yaml`

首批官方 Capsule：

1. **Desktop UI Capsule**：用于证明通用 UI 操作，覆盖文件、浏览器、设置页、表单、列表、弹窗。
2. **HSR Capsule**：UI-first 标杆，覆盖菜单、任务追踪、对话、奖励领取、合成、自动战斗入口、战斗后领奖。
3. **Genshin Capsule**：Hard embodied 标杆，分阶段覆盖 UI/传送/背包/合成/采集/跑图/战斗。
4. **Demo ARPG Capsule**：授权 testbed，用于战斗、导航、反射和长程 benchmark。

### 5.2 Skill Packs

Skill Pack 不应只是轨迹库，而是可验证能力库。

每个 Skill 必须有：

- skill_id
- capsule_id
- capability tags
- input_claims
- produced_claims
- semantic_actions
- ui_anchors
- verifier_recipe
- fallback_policy
- cleanup
- risk_level
- profile_compatibility
- benchmark_stats
- reliability_summary
- version

首批 Skill Pack：

| Pack | 面向用户价值 | 必须覆盖 |
|---|---|---|
| UI Basics | 通用菜单跳转 | open_menu、confirm、back、select_list_item、click_text |
| HSR Daily | 崩铁日常 | task menu、claim reward、auto-battle toggle、dialog continue |
| Genshin UI | 原神 UI | map、teleport、inventory、craft、use item、confirm/back |
| Genshin Collection | 采集 | teleport to route、navigate segment、interact、verify pickup |
| Genshin Survival | 生存 | low_hp detect、shield/heal/food_ui、safe abort |
| Combat Testbed | 战斗测试 | danger detect、dodge reflex、resume checkpoint、target reacquire |

### 5.3 Knowledge Packs

Knowledge Pack 解决“Planner 不知道游戏内容”的问题。

必须包含：

- item dictionary
- quest/task names and aliases
- UI text aliases across languages
- map anchors and route segments
- NPC dictionary
- enemy/boss profiles
- team/role profiles
- crafting/material recipes
- failure signatures
- known UI drift notes

这些内容要可版本化、可审计、可由社区贡献，但官方版本必须通过 Benchmark。

### 5.4 Verifier Recipe Library

把常见验证模式做成可复用 recipe：

- screen_state_transition
- screen_state_stable
- anchor_exists
- anchor_disappeared
- text_match
- regex_match
- numeric_delta
- inventory_delta
- progress_threshold
- danger_score_below
- hp_delta
- target_lost_or_reacquired
- reward_claimed
- dialog_advanced
- loading_finished
- route_segment_arrived

每个 recipe 必须声明：

- source_families
- required families
- optional families
- family_correlations
- stabilization_window_ms
- audit strategy
- default risk thresholds
- fallback if unverifiable

### 5.5 Persona Packs

用户提到“以用户喜欢的口吻复刻角色”。这应作为产品体验层，但不能污染执行事实。

Persona Pack 只负责：

- 任务确认话术
- 运行中状态播报
- 失败解释
- 需要用户确认时的提示
- 成功总结
- 语音/TTS 风格

Persona Pack 不能：

- 改写 Claim 状态。
- 绕过风险门禁。
- 自行决定物理操作。
- 把不确定说成成功。

### 5.6 Benchmark Packs

每个公开能力必须有 benchmark case。

Benchmark Pack 包含：

- scenario seed
- testbed frames or synthetic state
- mission graph
- expected claim chain
- expected audit result
- failure injection
- metrics thresholds

公开 demo 没有 benchmark，不允许进入商业宣传页。

### 5.7 Learning And Repair Packs

失败不是日志垃圾，而是产品资产。

每次失败应产出：

- failure_signature
- run summary
- evidence refs
- claim graph slice
- failed verifier votes
- controller receipts
- recovery attempts
- suggested fix
- 是否可转化为 regression benchmark
- 是否可转化为 new UIAnchor / verifier recipe / skill patch

## 6. 泛化能力的真实定位

### 6.1 四级自主能力

商业表达必须诚实分级：

| 等级 | 名称 | 能力 | 是否可 unattended |
|---|---|---|---|
| G0 | Manual Assist | 用户手动，系统观察/记录/提示 | 否 |
| G1 | Supervised Visual Agent | VLM/OCR 提议候选动作，用户确认 | 否 |
| G2 | Capsule Guided Automation | 已校准 anchor + verifier + skill | 低/中风险可 |
| G3 | Mission Automation | MissionGraph 串联多个 Skill，支持恢复 | 已验证任务可 |
| G4 | Adaptive Agent | 从失败和审计中改进，自动生成修复候选 | 仅在 testbed 或低风险 |

当前应主推 G2-G3。G1 是兜底。G4 是研发卖点，不应包装成已完全成熟。

### 6.2 无人工录制的边界

无人工录制可以做到：

- 识别 screen state。
- 提议 UI 元素。
- 解释任务目标。
- 选择已有 Skill。
- 在低风险 UI 中尝试 supervised 操作。
- 生成新 Skill 草稿。

无人工录制暂不应承诺：

- 任意游戏全自动长期运行。
- 高难 Boss 自主通关。
- 新 UI 无校准稳定点击。
- 新任务无知识库长程拆解。

因此产品主路径是：

```text
Capsule 内容 + 校准 Profile + Skill/Verifier + Mission Template
优先于
VLM 兜底探索
```

## 7. 用户体验主流程

### 7.1 首次启动

流程：

1. 选择语言和运行模式。
2. 阅读安全边界。
3. 选择本地模型/OCR 模式。
4. 安装官方 Capsule。
5. 选择授权窗口或 testbed。
6. 运行环境健康检查。
7. 进入 Capsule 校准。
8. 运行 60 秒 dry-run demo。
9. 生成首份可读报告。

体验要求：

- 不要求用户打开命令行。
- 所有失败都给出“原因 + 下一步”。
- 模型不可用时仍能用规则/OCR/手动校准继续。
- 真机前必须清晰标注“受监督模式”和“无人值守模式”的区别。

### 7.2 Capsule 校准向导

必须做成低摩擦流程：

```text
load capsule anchors
-> capture authorized window
-> auto-detect candidates
-> show overlay boxes
-> user confirm/adjust
-> save normalized profile
-> capture template crops
-> OCR text snapshot
-> run anchor validation
-> run safety preflight
-> mark ready
```

校准向导页面：

- 左侧：当前需要校准的锚点列表。
- 中间：授权窗口截图和可拖拽框。
- 右侧：检测来源、置信度、OCR 结果、模板匹配预览、历史漂移。
- 底部：重新截图、自动检测、确认此锚点、跳过、进入受监督模式。

关键原则：

- 坐标保存为窗口归一化坐标。
- 同时保存模板裁剪图、OCR 文本、relative layout rule。
- Profile 绑定 capsule version、game version hint、分辨率、缩放、语言、窗口模式。
- 每次运行前抽检关键 anchor。
- 抽检失败时阻止 unattended，只允许校准或 supervised fallback。

### 7.3 任务执行面板

用户需要看到：

- 当前 Mission。
- 当前节点。
- 当前屏幕状态。
- 最近一次动作。
- Claim 状态。
- Verifier 证据。
- 风险等级。
- 预计下一步。
- 是否需要用户确认。
- 一键暂停/停止。

不要只显示日志。日志是开发者材料，用户需要进度和解释。

### 7.4 失败复盘体验

失败卡片必须包含：

- 用户可懂原因：例如“任务按钮没有被可靠识别”。
- 技术原因：anchor low confidence / verifier conflict / claim rejected。
- 截图证据。
- 可选操作：重新校准、重试节点、切换受监督、生成报告、提交 bug。
- 是否已生成 regression case。

## 8. 开发者体验主流程

### 8.1 创建新 Capsule

命令或 GUI：

```text
Create Capsule
-> choose type: UI-first / 3D embodied / mixed
-> generate manifest
-> define screen states
-> define anchors
-> define claim recipes
-> define starter skills
-> define mission templates
-> run capsule lint
-> run synthetic benchmark
```

必须提供模板：

- `capsules/templates/ui_first`
- `capsules/templates/embodied_3d`
- `capsules/templates/desktop_app`
- `capsules/templates/combat_testbed`

### 8.2 Skill Studio

Skill Studio 工作流：

```text
record raw trace
-> segment by UI/state/action boundaries
-> infer semantic actions
-> bind UIAnchors
-> declare input/produced claims
-> attach verifier recipes
-> dry-run replay
-> inject failure cases
-> benchmark
-> approve version
```

关键设计：

- 原始鼠标轨迹只能是 fallback 素材。
- 主执行路径必须是 semantic action。
- 高风险 Skill 缺 verifier 不允许保存为 stable。
- Skill 发布时必须有 `benchmark_stats`。

### 8.3 Verifier Studio

目标是让开发者少写 Python。

界面能力：

- 从截图选择 ROI。
- 选择 recipe 类型。
- 预览 OCR/template/detector 结果。
- 配置 source family。
- 配置 required/optional families。
- 配置 family correlation。
- 配置 stabilization window。
- 配置 risk thresholds。
- 用历史 frame 批量测试。

导出：

- `verifier_recipes.yaml`
- test fixtures
- benchmark scenario

### 8.4 Mission Composer

用于把 Skill 串成可替代 DAG。

功能：

- 拖拽节点。
- 声明 dependencies。
- 声明 alternatives。
- 声明 risk_level。
- 声明 checkpoint。
- 声明 terminal claim。
- 自动检查缺失 verifier、循环依赖、不可恢复节点。

输出：

- `mission_templates.yaml`
- dry-run benchmark

## 9. 模型与 OCR 产品策略

### 9.1 本地优先，端云混合

模型路由原则：

1. 低延迟、低成本、高频任务优先本地。
2. OCR 优先轻量本地，复杂文本或低置信度时再走高精度模型。
3. VLM 只能产出候选 UIElement、screen state proposal、reasoning hint，不直接产出物理坐标执行。
4. 云端模型适合低频复杂解释、失败总结、策略生成，不适合高频画面理解。

### 9.2 OCR 分层

建议三层：

| 层 | 模型 | 用途 | 触发 |
|---|---|---|---|
| O1 | PaddleOCR 或等价轻量 OCR | 高频 UI 文本、按钮、列表 | 默认 |
| O2 | GLM-OCR 或高精度 OCR | 低置信度、复杂字体、长文本 | O1 不确定 |
| O3 | VLM OCR/理解 | 文字与语义强绑定，例如任务描述、复杂截图 | O1/O2 冲突或需要解释 |

需要记录指标：

- latency p50/p95
- recognition confidence
- correction rate
- cost per 1000 calls
- language coverage
- failure examples

### 9.3 Local VLM

用户侧已验证 LM Studio 可跑本地模型，因此产品应支持 OpenAI-compatible endpoint。

必须实现：

- Endpoint URL 配置。
- Model name 配置。
- Text smoke test。
- Image smoke test。
- JSON mode smoke test。
- Timeout 和降级。
- GPU/CPU latency 展示。
- E4B/E2B 或同系列模型对比报告入口。

不要把具体模型名写死到业务逻辑。模型能力通过 `ModelCapabilityProfile` 描述：

- supports_image
- supports_json
- max_image_size
- avg_latency_ms
- reliability_score
- recommended_use

## 10. HSR 商业化内容路线

HSR 是 UI-first 标杆，适合最先做真实可用体验。

### 10.1 首批任务

按商业价值排序：

1. 打开菜单并识别当前状态。
2. 进入任务/指南/奖励页面。
3. 领取可领取奖励。
4. 对话继续与确认。
5. 合成/材料页面跳转。
6. 自动战斗开关识别。
7. 战斗后奖励领取。
8. 日常流程模板。

### 10.2 必备资产

- menu anchors
- quest anchors
- reward anchors
- dialog anchors
- battle result anchors
- confirm/back anchors
- OCR dictionary for common buttons
- screen state classifier
- reward claimed verifier
- delayed audit strategy

### 10.3 HSR 上线门槛

- 至少 10 个 UI flow benchmark。
- 至少 2 种分辨率 Profile。
- 每个 flow 有 terminal claim。
- 低置信度 anchor 不自动点击。
- Auto-battle 只做 UI 状态控制，不做商业客户端绕过。

## 11. Genshin 商业化内容路线

Genshin 是最高难标杆，但不应一开始把高难 Boss 当上线门槛。

### 11.1 阶段路线

1. **Genshin UI R1**：地图、传送、背包、确认、返回、合成、使用。
2. **Collection R1**：采集提示识别、交互、toast/OCR、路线段 testbed。
3. **Navigation R1**：短段路线、heading servo、progress monitor、stuck recovery 上限。
4. **Combat R1**：testbed danger reflex、target reacquire、resume checkpoint。
5. **Boss R1**：synthetic BossBench 稳定后再绑定真实 Boss profile。

### 11.2 必备资产

- world map anchors
- teleport confirmation anchors
- inventory anchors
- item use anchors
- collection prompt anchors
- route segments
- local recovery playlist
- danger signal recipes
- boss profiles
- team role profiles
- survival policies

### 11.3 Genshin 上线门槛

- UI/传送/采集先于战斗。
- 所有移动 lease 有 timeout。
- stuck recovery 有次数上限。
- 采集成功必须有多信号 claim。
- 战斗成功不能只看单帧状态。
- Boss demo 必须标注 testbed/supervised/experimental 等级。

## 12. 长程任务与记忆系统

### 12.1 任务事实源

LLM 上下文不是事实源。事实源是：

- MissionGraph。
- ClaimGraph。
- EvidenceGraph。
- RunJournal。
- Checkpoints。
- ReliabilityStore。
- DecisionMemory。
- Capsule Knowledge。

### 12.2 DecisionMemory 应提炼什么

不要让 LLM 读一千条日志。EpisodeAnalyzer 应输出：

- last_successful_approach
- repeated_failure_pattern
- blocked_path
- reliable_skill_under_context
- unreliable_skill_under_context
- suggested_next_action
- do_not_repeat
- confidence and support count

### 12.3 长程运行门槛

必须实现和测试：

- checkpoint resume。
- profile revalidation。
- window revalidation。
- capsule version revalidation。
- skill version revalidation。
- context compaction validation。
- audit pending queue recovery。
- release_all on abort。
- memory growth bound。

## 13. Verifier 与 Claim 的商业可靠性策略

### 13.1 不追求“单个 Verifier 永远正确”

商业系统要承认：

- Verifier 会 false positive。
- Verifier 会 false negative。
- OCR 会漏检。
- VLM 会幻觉。
- UI 会漂移。
- 游戏状态会延迟。

因此最终事实由 ClaimAdjudicator 裁决，而不是单个 Verifier。

### 13.2 三类可靠度

- VerifierReliability：某个证人是否可靠。
- RecipeReliability：某个证据组合是否可靠。
- SkillClaimReliability：某个 Skill 在某个上下文里是否可靠。

执行信任建议：

```text
execution_trust = min(
  verifier_reliability,
  recipe_reliability,
  skill_claim_reliability,
  context_match_score
)
```

MVP 可先完整使用 VerifierReliability + SkillClaimReliability，RecipeReliability 做可选增强，但 schema 必须预留。

### 13.3 不确定状态必须有出口

UncertaintyPolicy 必须明确：

1. resample。
2. alternate verifier。
3. low-risk probe。
4. local recovery。
5. human confirm。
6. safe abort。

禁止：

- 无限等待。
- 把 uncertain 当 success。
- 让 LLM 在所有候选都低置信度时“硬选一个”。

## 14. 商业质量指标

### 14.1 核心成功指标

- verified_task_completion_rate
- false_accept_rate proxy / delayed audit mismatch rate
- false_reject_rate proxy
- manual_intervention_count
- mean_time_to_recover
- uncertain_state_count
- claim_verified_rate
- claim_audited_rate
- anchor_resolution_rate
- OCR latency p95
- VLM latency p95
- release_all_success_rate
- safety_violation_count
- memory_growth_mb_per_hour

### 14.2 内容资产指标

- official capsule count
- stable skill count
- benchmark-backed skill percentage
- verifier recipe coverage
- profile compatibility count
- supported screen resolutions
- known UI drift cases
- regression case count
- community contribution acceptance rate

### 14.3 商业发布指标

公开宣传的每个功能必须标注：

- 支持 Capsule。
- 支持任务。
- 自动化等级 G0-G4。
- 是否需要用户监督。
- benchmark success rate。
- 已测分辨率/语言。
- 失败时是否可恢复。

## 15. 实施阶段

### Phase A：真实主链路收口

目标：所有公开流程都走 Claim 主路径。

任务：

- UI action -> InputLease -> PhysicalActionReceipt -> ObservationClaim -> ClaimAdjudicator。
- 旧 `VerifierResult(ok=True)` 只能作为 ObservationClaim。
- Terminal MissionNode 必须有 verified/audited Claim。
- StateBus 发布 claim_event 和 claim_graph_state。
- ClaimGraph snapshot 可视化。

验收：

- 一个 HSR UI testbed flow 完整产生 claim chain。
- 一个 Genshin collection testbed flow 完整产生 claim chain。
- 没有 claim evidence 的 terminal success 失败。

### Phase B：产品化校准与 UI 操作

目标：让用户可以优雅绑定真机 Profile。

任务：

- Calibration Wizard 2.0。
- UIAnchor Inspector。
- Profile preflight。
- OCR preview。
- Template crop preview。
- Anchor drift detection。
- Supervised fallback。

验收：

- HSR/Genshin 各至少 12 个关键 anchor。
- 至少两种分辨率模拟或 testbed 校验。
- Profile 缺失时拒绝 unattended。

### Phase C：Skill Studio 与内容工厂

目标：让 Skill 从宏变成可验证资产。

任务：

- Recording pipeline。
- Segmenter。
- Semantic action inference。
- Claim binding。
- Verifier recipe binding。
- Dry-run replay。
- Skill versioning。
- Benchmark generation。

验收：

- 录制一个 UI Skill，换分辨率后通过 anchor 执行。
- Skill 缺 verifier 时不能标 stable。
- Skill 发布生成 benchmark case。

### Phase D：Verifier Studio 与 Recipe Library

目标：降低 Capsule 开发门槛。

任务：

- Declarative Verifier editor。
- Recipe templates。
- Frame fixture runner。
- Source family preview。
- Correlation config。
- Stabilization window config。

验收：

- 开发者无需写 Python 创建 reward_claimed、dialog_advanced、inventory_delta verifier。
- Recipe 可批量跑历史 frame。

### Phase E：Local Model Center

目标：本地 OCR/VLM 真正可用。

任务：

- PaddleOCR provider health。
- GLM-OCR provider health。
- OpenAI-compatible local VLM health。
- Model capability profile。
- OCR/VLM routing dashboard。
- Cost/latency report。

验收：

- 本地 OCR 不可用时有明确降级。
- VLM 不可用时 fallback visual agent 自动转 human confirm。
- 本地模型 JSON/image smoke bench 通过。

### Phase F：HSR Official Capsule

目标：交付第一个商业上最可能稳定的游戏 Capsule。

任务：

- HSR UI anchors。
- HSR screen states。
- HSR reward/daily mission templates。
- HSR auto-battle state checks。
- HSR delayed audit。
- HSR user guide。

验收：

- 至少 10 条 UI-first benchmark flow。
- 低风险日常 flow 达到可监督稳定运行。
- 失败报告可读。

### Phase G：Genshin Official Capsule

目标：逐步打通最难场景。

任务：

- UI R1。
- Collection R1。
- Navigation R1。
- Combat testbed R1。
- BossBench synthetic R1。

验收：

- 传送 -> 短导航 -> 采集 -> 验证 testbed 可跑。
- 移动失败安全 abort。
- Boss 仅作为 testbed/supervised 展示，未达指标不宣传真实胜率。

### Phase H：Open Beta 质量门禁

目标：可对外测试。

任务：

- Installer。
- First-run flow。
- Feedback package。
- Benchmark dashboard。
- Privacy/export settings。
- Crash recovery。
- Release notes。

验收：

- 新用户 15 分钟内完成 demo。
- 每个公开 demo 有 benchmark。
- safety_violation_count = 0。
- 所有失败可以生成反馈包。

## 16. Coding Agent 执行规则

后续 Coding Agent 必须遵守：

1. 不得把游戏特定逻辑写入 core。
2. 不得用旧布尔 success 作为 terminal success。
3. 不得让 VLM 直接输出物理坐标执行。
4. 不得绕过 InputLease、SafeWindow、release_all。
5. 不得新增无 Benchmark 的 public demo。
6. 不得新增无 Profile Preflight 的 unattended flow。
7. 每个新 Skill 必须有 failure path。
8. 每个新 Verifier 必须说明 source family 和 risk ceiling。
9. 每个新 Capsule 必须有 user guide 和 developer notes。
10. 每个真实能力宣称必须有 dry-run/testbed 或授权窗口证据。

## 17. 最小商业可发布版本

MCPV，Minimum Commercially Promotable Version，应包含：

- 桌面 GUI 可启动。
- 本地模型/OCR 健康检查。
- Capsule 安装和校准。
- HSR UI-first 官方 flow。
- Genshin UI/collection testbed flow。
- Skill Studio 最小版。
- Verifier Studio 最小版。
- Mission Composer 最小版。
- AuroraBench v2 dashboard。
- 失败反馈包。
- 用户指南。
- 开发者指南。
- 明确安全边界。

不要求：

- 任意游戏零配置。
- 高难 Boss 真实无人通关。
- 全自动从零生成 Capsule。
- 完整社区市场。

## 18. 给后续执行者的优先级

如果资源有限，按以下顺序推进：

1. **Profile 和 UIAnchor 校准体验**：没有它，真机不可用。
2. **Claim 主链路贯通**：没有它，成功不可证明。
3. **HSR UI-first 官方内容**：最快形成用户可感知价值。
4. **Skill Studio 最小闭环**：没有内容生产工具，项目无法扩张。
5. **Verifier Studio 最小闭环**：没有验证生产工具，稳定性无法扩张。
6. **Genshin UI/Collection**：比战斗更早产生真实价值。
7. **Navigation/Combat/Boss**：作为最高难壁垒持续打磨。
8. **Local Model Center**：降低长期成本，增强本地体验。
9. **Open Beta 包装**：在证据足够后再扩大。

## 19. 结论

Aurora 的商业机会不是“又一个自动点击器”，而是一个有治理能力的视觉 Agent OS：

- 它用 Capsule 解决泛化与特调的矛盾。
- 它用 Skill Contract 让动作可迁移。
- 它用 UIAnchor 和 Calibration 让点击可靠。
- 它用 ObservationGraph 和 Verifier 让视觉可落地。
- 它用 ClaimGraph 让事实可审计。
- 它用 Reliability 和 DelayedAudit 让系统知道自己是否可靠。
- 它用 Benchmarks 把宣传变成可复现证据。
- 它用 Persona 和 GUI 把复杂工程变成用户能理解的体验。

接下来的关键不是继续堆抽象，而是围绕 HSR 和 Genshin 两条官方内容线，建设足够强的 Profile、Skill、Verifier、Mission、Benchmark 和用户工作流。只有当用户能稳定完成真实任务、开发者能低摩擦扩展内容、系统能诚实报告边界时，Aurora 才真正具备商业推广的完成度。
