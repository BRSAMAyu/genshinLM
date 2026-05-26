# Aurora 自主 Skill 进化与长程通关执行方案

本文档是 Aurora 下一阶段的核心执行方案。它不以商业包装为中心，而以最终效果和研究贡献为中心：让 Aurora 在真实复杂 3D 场景中，逐步实现从“人类辅助配置 Skill”到“系统自主探索、生成 Skill、复用 Skill、修复 Skill、长期推进任务”的能力。

最终目标可以用一句话概括：

> 用户从原神初始登场开始，只下达“持续推进剧情”这样的高层目标。系统能够在安全边界内理解当前状态、规划长期目标、首次慢速探索未知操作、沉淀可复用 Skill、在后续任务中快速调用 Skill，并通过战斗、剧情、采集、养成、任务追踪、队伍配置、奖励领取等连续闭环，持续推进主线。

这不是一个普通自动化脚本目标，而是一个研究级目标。若要达到顶会论文标准，Aurora 必须证明：

1. 不依赖任务专用微调数据，也能通过多模态基础模型、可验证运行时和自生成 Skill 在复杂环境中提升任务完成率。
2. 不让 LLM 直接承担高频控制，而是通过 Skill 抽象、Claim 验证、快慢脑分工和本地控制器降低大模型负担。
3. 系统能够从失败与成功中沉淀新的可执行能力，并形成跨任务、跨会话、跨场景的复用。
4. 在原神这类开放 3D 游戏中，相比纯 computer-use agent、纯脚本、纯录制宏、纯端到端 VLA，有更高的可解释性、可恢复性和可扩展性。

## 1. 当前问题的本质

当前 Aurora 已经拥有大量底层组件：五平面架构、InputLease、ClaimGraph、Verifier、Capsule、MissionGraph、Skill、OCR/VLM、BossBench、DecisionMemory 等。但它还没有达到愿景中的最终效果，原因不是某个模块缺失，而是“主闭环”还没有被系统性打通。

### 1.1 当前系统主要短板

1. **启动与使用体验差**  
   用户不知道怎么启动、怎么配置、怎么绑定窗口、怎么开始任务。浏览器页面和配置项缺少明确引导。

2. **Skill 体系还偏静态**  
   有 Skill 定义、Skill 管理和部分录制/修复能力，但还没有形成“首次探索 -> 成功轨迹 -> 语义抽象 -> verifier 绑定 -> dry-run -> promotion -> 复用”的完整自生成闭环。

3. **Planner 还不够长程**  
   当前任务图可以表达 DAG，但距离“持续推进主线”还缺少 quest-level 状态机、长期目标栈、子目标发现、失败后改路、任务上下文压缩和战略记忆。

4. **泛化 Agent 仍然只是兜底**  
   VLM/LLM 可以看图和提出候选操作，但还没有被约束成“慢速探索器 + Skill 生成器”。如果直接让它长期接管鼠标键盘，会不稳定。

5. **内容资产和能力发现未统一**  
   数据包、知识库、BossProfile、UIAnchor、Skill、Verifier、Benchmark 分散存在，但系统还不能像操作系统一样自动检索“当前场景有什么可用能力、哪个能力最可靠、缺什么能力需要探索生成”。

6. **战斗和长程移动仍是最高风险点**  
   原神战斗、Boss、开放世界导航不是 UI 点击问题。必须依赖快控制、反射、局部策略、战前慢思考和失败学习，不能靠 LLM 每帧推理。

7. **研究指标尚未闭合**  
   顶会级系统必须有清晰指标：首次解题时间、Skill 生成成功率、复用收益、长期任务完成率、失败恢复率、人工介入下降曲线、跨任务迁移能力。

## 2. 核心研究命题

Aurora 下一阶段应围绕一个明确研究命题：

> Can a verifier-first visual agent runtime autonomously convert slow multimodal reasoning into reusable hierarchical skills, enabling long-horizon completion in complex 3D game environments without task-specific fine-tuning?

中文：

> 一个证据优先的视觉 Agent 运行时，能否不依赖任务专用微调，通过慢速多模态推理自动生成可验证的分层 Skill，并在复杂 3D 游戏中完成长程任务？

### 2.1 论文级贡献点

1. **Hierarchical Skill Induction**  
   把首次慢速探索成功的过程自动蒸馏为多层 Skill，而不是保存成鼠标宏。

2. **Claim-Gated Skill Promotion**  
   Skill 不是生成后立即可信，而是必须通过 ClaimGraph、Verifier、DelayedAudit、ReliabilityGate 才能晋升。

3. **Slow-to-Fast Control Transfer**  
   第一次用 LLM/VLM 慢思考解决，后续由本地 Skill/Controller 快速执行。

4. **Embodied Long-Horizon Mission OS**  
   用 MissionGraph、WorldState、QuestState、SkillLibrary 和 FailureMemory 支撑数小时长程任务。

5. **Verifier-First Self-Improvement Loop**  
   自我进化不是“LLM 自我反思说自己变强”，而是基于 evidence、benchmark、成功率和失败签名的可测量改进。

6. **No Fine-Tuning, No Task-Specific Training Data**  
   不训练专用模型，用基础模型、OCR、局部视觉算法、符号记忆和 Skill 编译达成效果。

## 3. 总体架构：从 Computer Use 到自主 Skill OS

Aurora 必须从“能操作电脑”升级为“能把操作电脑的经验沉淀成可复用技能的系统”。

```text
User Goal
-> Long-Horizon Mission OS
-> Goal Stack / Quest State / World State
-> Skill Retrieval and Applicability Gate
-> If skill exists: execute fast skill
-> If no skill exists: slow exploration agent
-> Trace recording
-> Semantic segmentation
-> Skill induction
-> Claim / Verifier binding
-> Dry-run and testbed validation
-> Reliability promotion
-> Skill library update
-> Mission resumes with new skill
```

### 3.1 快慢脑关系

| 模块 | 速度 | 职责 | 不能做 |
|---|---:|---|---|
| Reflex / Motor | 10-60Hz | 闪避、释放按键、短期方向修正 | 长程规划 |
| Controller | 5-30Hz | UI 点击、导航段、战斗执行 | 解释复杂目标 |
| Skill Runtime | 事件驱动 | 调用语义动作、维护 checkpoint | 毫秒级视觉判断 |
| Mission Planner | 低频 | 分解目标、选择 Skill、重规划 | 直接输出坐标 |
| Slow Exploration Agent | 很低频 | 在无 Skill 时逐步试探和解释 | 长期无人值守 |
| Reflection / Skill Inducer | 离线/后台 | 总结成功轨迹、生成 Skill | 实时接管控制 |

关键规则：

- 战斗中 LLM 不参与毫秒级控制。
- 过剧情、UI、任务追踪、升级、合成等可以慢思考。
- 未知操作第一次允许慢，但成功后必须沉淀为 Skill。
- Skill 是否使用，比 Skill 本身更重要，因此必须有 Applicability Gate。

## 4. Skill 的分层定义

Skill 不能只是一段录制宏。必须分成多个抽象层级。

### 4.1 Skill Level 0：Motor Primitive

最底层动作：

- key_down/key_up
- click
- drag
- mouse_move
- wait_state
- release_all

来源：

- Runtime 内置。

特点：

- 只能被 Controller 调用。
- 必须有 InputLease。
- 不对用户直接暴露。

### 4.2 Skill Level 1：Grounded Interaction Skill

基于 UIAnchor 或输入映射的操作：

- click_anchor("quest_menu")
- click_text("继续")
- select_list_item("主线任务")
- open_map()
- confirm_dialog()

来源：

- Capsule anchor + declarative verifier。

特点：

- 可跨分辨率。
- 必须有 anchor resolution confidence。
- 失败时进入校准/重扫/用户确认。

### 4.3 Skill Level 2：Controller Skill

局部连续控制：

- navigate_to_marker()
- follow_route_segment()
- collect_visible_item()
- dodge_incoming_attack()
- execute_basic_rotation()

来源：

- Controller + Perception + Claim。

特点：

- 高频或中频。
- 有局部恢复。
- 不调用 LLM。

### 4.4 Skill Level 3：Task Skill

完成一个短任务：

- track_current_quest()
- teleport_to_nearest_anchor()
- collect_material_at_known_spot()
- clear_small_combat_encounter()
- claim_daily_reward()
- upgrade_character_once()

来源：

- 人类设计、录制蒸馏、自动探索后编译。

特点：

- 有 preconditions。
- 有 produced_claims。
- 有 fallback。
- 可 benchmark。

### 4.5 Skill Level 4：Strategic Skill

类似攻略策略：

- 推进某个任务链。
- 打某类 Boss 的策略。
- 培养某角色到可用水平。
- 缺材料时决定采集/合成/兑换路线。

来源：

- LLM 总结、Knowledge Pack、成功 Episode。

特点：

- 不直接执行按键。
- 输出 MissionGraph 或 Skill 序列。
- 必须可解释。

### 4.6 Skill Level 5：Meta Skill

让系统自己变强的技能：

- 学会一个新 UI 页面。
- 学会一种新 Boss 机制。
- 学会一类任务流程。
- 从失败中生成修复候选。

来源：

- Skill Induction Engine。

特点：

- 这是论文级核心。
- 输出新的 lower-level skill 或 verifier。

## 5. 自主 Skill 生成飞轮

### 5.1 完整链路

```text
Unknown Situation
-> Slow Exploration
-> Candidate Actions
-> Safe Probe
-> Observation / Claim
-> Success or Failure
-> Trace Store
-> Segmenter
-> Semantic Skill Inducer
-> Anchor Binder
-> Verifier Synthesizer
-> Dry-run Replay
-> Failure Injection
-> Reliability Gate
-> Skill Library Promotion
-> Future Fast Execution
```

### 5.2 新增核心模块

#### ExplorationAgent

职责：

- 在没有可用 Skill 时，用 VLM/OCR/LLM 低频探索。
- 只能输出 CandidateAction，不直接绕过风险门禁。
- 每次动作前说明 expected_state_delta。
- 每步都触发 ObservationClaim。

输入：

- current ObservationGraph。
- available ActionAffordances。
- current goal。
- risk policy。
- previous failed probes。

输出：

- candidate semantic action。
- rationale。
- expected claim。
- risk estimate。

#### TraceRecorder

职责：

- 记录首次探索过程的完整轨迹。

必须记录：

- frames。
- OCR blocks。
- UI elements。
- input receipts。
- action proposals。
- actual actions。
- claims。
- verifier votes。
- failures。
- user interventions。

#### EpisodeSegmenter

职责：

- 把长轨迹切分成可复用段。

切分边界：

- screen_state transition。
- quest_state transition。
- claim verified。
- UI page changed。
- combat started/ended。
- failure/recovery。
- user intervention。

#### SemanticSkillInducer

职责：

- 把 trace segment 转成 Skill Draft。

它不能保存原始轨迹作为主路径，而要提炼：

- semantic actions。
- required anchors。
- preconditions。
- produced claims。
- verifier recipes。
- fallbacks。
- cleanup。
- risk level。

#### AnchorBinder

职责：

- 将“点击了某个位置”绑定为：
  - OCR text。
  - UIAnchor。
  - template crop。
  - relative layout。
  - screen_state。

如果无法绑定，Skill 只能是 experimental，不能 stable。

#### VerifierSynthesizer

职责：

- 根据 produced_claims 自动推荐 verifier bundle。
- 如果 claim_type 已有 recipe，使用 recipe。
- 如果没有 recipe，让 LLM/VLM 提出 verifier draft，但必须进入 human/developer review。

#### SkillEvaluator

职责：

- replay。
- dry-run。
- testbed。
- failure injection。
- multi-resolution simulation。
- reliability computation。

#### PromotionGate

Skill 晋升规则：

| 状态 | 条件 |
|---|---|
| raw_trace | 只记录，不能复用 |
| draft | 有 semantic actions，但 verifier 不完整 |
| experimental | 可 supervised 执行，有基础 claims |
| candidate | 通过 dry-run，低风险可自动 |
| stable | 通过 benchmark，有可靠度统计 |
| trusted | 多上下文、多次审计稳定 |

## 6. Skill 选择比 Skill 生成更重要

系统必须知道什么时候用哪个 Skill。

### 6.1 Skill Applicability Gate

输入：

- current_goal。
- current_screen_state。
- current_world_state。
- quest_state。
- team_state。
- inventory_state。
- active_capsule。
- profile_state。
- available_skills。
- reliability_stats。
- risk_policy。

输出：

- ranked candidate skills。
- reason。
- required preconditions。
- missing preconditions。
- risk。
- expected claims。

建议评分：

```text
skill_score =
  0.25 * goal_match
+ 0.20 * precondition_satisfaction
+ 0.20 * context_reliability
+ 0.15 * verifier_coverage
+ 0.10 * expected_utility
+ 0.10 * recency_success
- 0.20 * risk_penalty
- 0.15 * uncertainty_penalty
- 0.10 * cost_penalty
```

硬规则：

- precondition 不满足，不执行。
- profile 不匹配，不 unattended。
- terminal verifier 缺失，不 stable。
- 所有候选低于阈值，不能让 LLM 硬选，必须探索/询问/abort。

### 6.2 Skill Retrieval

检索维度：

- capability tags。
- screen_state。
- quest_state。
- semantic goal embedding。
- produced_claims。
- input_claims。
- historical success contexts。
- failure signatures。

需要新增：

- `SkillIndex`
- `SkillEmbeddingStore`
- `SkillContextMatcher`
- `SkillApplicabilityExplainer`

## 7. 长程通关系统

“持续推进剧情”不是单个任务，而是一个长期操作系统。

### 7.1 Long-Horizon Mission OS

新增模块：

- `GoalStack`
- `QuestStateTracker`
- `WorldStateStore`
- `ProgressionManager`
- `PrerequisiteResolver`
- `ResourcePlanner`
- `TrainingPlanner`
- `ExplorationScheduler`
- `MainlineMissionRunner`

### 7.2 状态模型

必须维护：

```text
PlayerProfile
  adventure_rank
  unlocked_regions
  unlocked_systems
  party
  character_levels
  weapons
  artifacts
  talents
  inventory_summary
  resin_state
  currency_state

QuestState
  active_quest
  quest_objective_text
  tracked_target
  completed_steps
  blocked_steps
  npc_targets
  map_targets

WorldState
  current_region
  current_position_estimate
  current_screen_state
  nearest_waypoints
  known_unlocked_waypoints
  known_blocked_routes

CapabilityState
  available_skills
  missing_skills
  reliable_skills
  experimental_skills
  known_failure_modes
```

### 7.3 主线推进循环

```text
observe current state
-> infer active quest objective
-> check if objective can be solved by existing skills
-> if yes: compile MissionGraph
-> execute with Claim gates
-> if no: enter ExplorationAgent
-> if exploration succeeds: induce skill
-> if blocked by power/resource: invoke ResourcePlanner
-> if blocked by combat: invoke CombatPreparationPlanner
-> checkpoint
-> continue
```

### 7.4 任务类型拆解

原神主线可拆成常见任务类型：

- dialog progression。
- follow NPC。
- go to marker。
- open menu / tutorial page。
- unlock waypoint。
- enter domain。
- solve simple puzzle。
- collect item。
- defeat enemies。
- boss fight。
- upgrade character。
- craft material。
- claim reward。
- team setup。

每种任务类型都要有：

- detector。
- skill candidates。
- fallback exploration policy。
- verifier recipes。
- failure modes。
- benchmark scenario。

## 8. 从初始登场到主线通关的课程体系

不要一开始就要求通关全部主线。必须设计 curriculum。

### Stage 0：启动和绑定

目标：

- 用户能一键启动。
- 绑定窗口。
- 绑定键位。
- 校准 UI。
- 运行 test action。

验收：

- 新用户 10 分钟内知道怎么开始。
- 有明确“下一步”按钮。
- 不需要看 README 才能启动。

### Stage 1：剧情与对话

目标：

- 能识别对话框。
- 能点击继续。
- 能选择选项。
- 能检测剧情推进。
- 能记录新 UI 操作并生成 Skill。

验收：

- 30 分钟剧情推进 testbed。
- 遇到新按钮能 supervised 探索并沉淀 anchor。

### Stage 2：任务追踪与地图

目标：

- 打开任务列表。
- 追踪任务。
- 打开地图。
- 找目标区域。
- 传送到 waypoint。

验收：

- 能从 quest objective 到地图行动。
- 失败能解释是“无法识别目标”还是“未解锁传送点”。

### Stage 3：短距离导航

目标：

- 从传送点到任务 marker。
- Heading servo。
- progress monitor。
- stuck recovery。

验收：

- 多段路线 testbed。
- 跑偏不会无限 W。
- 卡住能安全恢复或 abort。

### Stage 4：基础战斗

目标：

- 识别进入战斗。
- 锁定目标。
- 使用基础 rotation。
- danger reflex。
- 验证战斗结束。

验收：

- 小怪战斗 testbed clear rate。
- target lost 能 reacquire。
- 低血不会继续贪刀。

### Stage 5：采集与养成

目标：

- 识别采集提示。
- 交互采集。
- 验证获得。
- 打开角色/武器/天赋页面。
- 升级/突破/合成。

验收：

- 从缺材料到采集/合成的闭环。
- 资源不足能切换 plan。

### Stage 6：Boss 与复杂战斗

目标：

- Boss phase。
- telegraph detection。
- survival runtime。
- team adapter。
- failed fight learning。

验收：

- Synthetic BossBench。
- 真实 Boss 先 supervised。
- 多次失败后生成策略变化，而不是重复同一打法。

### Stage 7：长期主线推进

目标：

- 多小时运行。
- checkpoint/resume。
- context compaction。
- autonomous skill generation。
- 用户介入逐步减少。

验收：

- 从初始区域持续推进多个主线节点。
- 记录所有新技能生成和复用收益。

## 9. 战斗系统：最高难试金石

战斗必须单独成体系。

### 9.1 战斗快慢分工

战前慢思考：

- 分析队伍。
- 分析 Boss。
- 选择角色站位。
- 生成 playbook。
- 设定 survival policy。

战中快控制：

- rotation。
- cooldown。
- target tracking。
- danger detection。
- dodge/shield/heal。
- target reacquire。

战后慢反思：

- 为什么失败。
- 哪个 phase 失败。
- 是否伤害不足。
- 是否生存不足。
- 是否需要升级角色。
- 是否生成新 combat skill。

### 9.2 Boss 学习闭环

```text
fight attempt
-> phase trace
-> danger missed?
-> death cause?
-> damage window missed?
-> team resource issue?
-> strategy revision
-> playbook patch
-> BossBench replay
-> next attempt
```

### 9.3 战斗 Skill 层级

- micro：dodge, shield, iframe, switch。
- combo：E/Q/attack sequence。
- phase tactic：shield phase / burst window / retreat。
- fight strategy：team plan / resource plan / survival plan。

### 9.4 战斗验收指标

- survival_rate。
- boss_clear_rate。
- death_count。
- danger_false_negative_rate。
- reflex_latency_p95。
- resume_success_rate。
- target_reacquire_success_rate。
- heal_success_rate。
- repeated_failure_diversity：失败后策略是否真的变化。

## 10. 多模态模型管线预留

系统必须支持未来更强原生多模态模型。

### 10.1 Provider 抽象

```text
MultimodalProvider
  describe_screen(image, context)
  locate_ui_element(image, query)
  propose_action(observation, goal)
  explain_failure(trace)
  summarize_episode(trace)
  generate_skill_draft(trace)
```

### 10.2 模型层级

| 类型 | 用途 |
|---|---|
| Local OCR | 高频文字识别 |
| High-Accuracy OCR | 低置信度文本补偿 |
| Local VLM | 高频/中频截图理解和候选动作 |
| Cloud VLM | 低频复杂理解、失败解释、长程规划 |
| Text LLM | 任务拆解、策略、Skill 草稿、文档总结 |

### 10.3 未来模型适配

必须预留：

- Qwen native multimodal。
- Gemini/Flash multimodal。
- Gemma/Gemma-family local VLM。
- GLM-OCR / GLM-V。
- OpenAI-compatible endpoint。
- MCP image tools as fallback。

模型不能写死。每个模型用 `ModelCapabilityProfile` 描述：

- image_understanding。
- OCR。
- JSON reliability。
- latency。
- cost。
- context size。
- local/cloud。
- recommended roles。

## 11. 用户体验必须重做

如果用户不知道怎么启动，再强的架构也没价值。

### 11.1 一键启动

必须提供：

- `Start Aurora` 桌面入口。
- 自动检查后端。
- 自动打开 GUI。
- 显示系统状态。
- 提示下一步。

用户不应需要知道：

- FastAPI 端口。
- 前端 dev server。
- Python venv。
- 配置文件位置。

### 11.2 First Run Wizard

步骤：

1. 选择用途：Testbed / Desktop / HSR / Genshin。
2. 检查安全边界。
3. 检查模型/OCR。
4. 绑定窗口。
5. 绑定键位。
6. 校准 UI。
7. 运行安全测试。
8. 运行第一个 demo。
9. 生成报告。

### 11.3 Cockpit

主界面必须显示：

- 目标。
- 当前任务。
- 当前状态。
- 可用技能。
- 缺失技能。
- 正在探索的技能。
- 最近 Claim。
- 风险等级。
- 用户需要做什么。
- 一键暂停/停止。

### 11.4 新手引导

每个模式必须有“我该怎么做”的说明：

- Testbed：用于验证系统。
- Supervised：系统提议，用户确认。
- Assisted Auto：低风险自动，高风险确认。
- Unattended：仅 benchmark-backed stable flow。

## 12. 顶会论文实验设计

### 12.1 Baselines

必须比较：

- Pure VLM computer-use agent。
- Scripted macro。
- Human-authored Skill only。
- Aurora without Claim gate。
- Aurora without skill induction。
- Aurora full system。

### 12.2 Tasks

任务集：

- UI navigation。
- dialog progression。
- quest tracking。
- collection route。
- basic combat。
- boss testbed。
- long-horizon multi-step mission。
- unseen UI task。
- repeated task after first success。

### 12.3 Metrics

核心指标：

- first_attempt_success。
- time_to_first_success。
- skill_induction_success_rate。
- replay_success_rate。
- reuse_speedup。
- human_interventions。
- long_horizon_completion。
- false_success_rate。
- recovery_success_rate。
- capability_growth_over_time。

论文必须证明：

```text
After first successful slow exploration,
Aurora can produce a reusable skill whose later execution is faster,
more reliable, and less token-expensive than repeated VLM control.
```

### 12.4 Ablations

消融：

- no verifier。
- no delayed audit。
- no skill induction。
- no decision memory。
- no controller/reflex。
- no local OCR。
- no capsule knowledge。

## 13. 实施计划

### Phase 0：可启动性和体验救火

目标：

- 用户能启动、知道下一步、能进入 testbed。

任务：

- 单入口 launcher。
- First Run Wizard。
- Backend health page。
- Model/OCR health page。
- Window binding page。
- Key binding page。
- Safe action test。

验收：

- 新用户不看文档，10 分钟内跑通 testbed demo。

### Phase 1：Skill Evolution Core

目标：

- 系统能从一次探索生成 Skill Draft。

任务：

- TraceRecorder。
- EpisodeSegmenter。
- SemanticSkillInducer。
- AnchorBinder。
- VerifierSynthesizer。
- PromotionGate。

验收：

- 未知 UI 操作首次 supervised 成功后，生成可 dry-run 的 Skill Draft。

### Phase 2：Skill Applicability and Retrieval

目标：

- 系统知道什么时候用哪个 Skill。

任务：

- SkillIndex。
- context matcher。
- applicability scorer。
- reliability gate。
- explanation。

验收：

- 同一目标下可解释选择 Skill。
- 不满足 precondition 时拒绝执行。

### Phase 3：Long-Horizon Mission OS

目标：

- 从单任务升级到持续推进。

任务：

- GoalStack。
- QuestStateTracker。
- WorldStateStore。
- PrerequisiteResolver。
- ResourcePlanner。
- MainlineMissionRunner。

验收：

- 能在 testbed 中连续完成 5 个异构任务节点。

### Phase 4：ExplorationAgent

目标：

- 没有 Skill 时能慢速探索。

任务：

- candidate action generation。
- safe probe policy。
- VLM/OCR action affordance。
- uncertainty exits。
- exploration budget。

验收：

- 未知页面能找到按钮、执行、验证、沉淀。
- 探索超预算时安全停止。

### Phase 5：Genshin Story Curriculum

目标：

- 建立原神主线课程。

任务：

- dialog progression。
- quest tracking。
- map/teleport。
- short navigation。
- basic combat。
- collection。
- upgrade。

验收：

- testbed + supervised real profile 分阶段通过。

### Phase 6：Combat Self-Improvement

目标：

- 战斗失败后能产生策略变化。

任务：

- fight trace。
- death cause classifier。
- phase failure analyzer。
- playbook patcher。
- team/resource planner。

验收：

- 同一 Boss testbed 多次失败后，策略不是重复执行旧 rotation。

### Phase 7：Knowledge Acquisition

目标：

- 系统能补充背景知识。

任务：

- quest text extraction。
- UI tutorial extraction。
- user-provided guide ingestion。
- web/document retrieval interface。
- knowledge claim validation。

验收：

- 新任务文本能进入 MissionGraph，不只是截图描述。

### Phase 8：Paper Benchmark Suite

目标：

- 为顶会论文准备实验。

任务：

- task suite。
- baselines。
- metrics。
- ablations。
- report generator。
- reproducible seeds。

验收：

- 一条命令生成论文实验表格。

## 14. 工程落地文件建议

新增目录：

```text
agent/exploration/
  exploration_agent.py
  action_proposal.py
  safe_probe_policy.py

learning/skill_induction/
  trace_recorder.py
  episode_segmenter.py
  semantic_skill_inducer.py
  anchor_binder.py
  verifier_synthesizer.py
  promotion_gate.py

planning/long_horizon/
  goal_stack.py
  quest_state_tracker.py
  world_state_store.py
  progression_manager.py
  prerequisite_resolver.py
  mainline_runner.py

skills/runtime/
  skill_index.py
  applicability_gate.py
  skill_context_matcher.py
  skill_promotion_state.py

ui/onboarding/
  first_run_wizard.py
  health_check_service.py
  profile_binding_flow.py

benchmarks/research_suite/
  baselines/
  tasks/
  ablations/
  report.py
```

## 15. 最终验收标准

### 15.1 近期验收

- 用户可一键启动。
- Testbed demo 可跑。
- 未知 UI 操作可 supervised 探索并生成 Skill Draft。
- Skill Draft 可被 dry-run。
- Skill 可通过 Claim gate 晋升。
- MissionGraph 可调用新生成 Skill。

### 15.2 中期验收

- HSR UI-first 日常流程可稳定执行。
- Genshin UI/剧情/传送/短导航/采集可持续推进。
- 未知页面可探索并沉淀。
- 用户介入次数随重复运行下降。

### 15.3 长期验收

- 从原神初始阶段开始，系统能在用户监督逐步减少的情况下持续推进主线。
- 遇到新机制时，系统先慢速探索，成功后沉淀 Skill。
- 遇到打不过的战斗时，系统能分析原因、调整策略、补资源、再次尝试。
- Skill library 随运行增长，任务完成率随时间提升。
- 论文实验能证明 Aurora full system 优于纯 VLM、纯宏、纯人工 Skill、无 Claim 版本。

## 16. 最关键的原则

1. **最终效果优先**  
   架构只为完成任务服务。任何不能提升真实任务完成率、恢复率、复用率、用户理解度的抽象都应被砍掉。

2. **首次可以慢，复用必须快**  
   允许第一次用很多 token 和时间推理，但成功后必须生成可复用 Skill。

3. **Skill 必须可验证**  
   没有 Claim/Verifier 的 Skill 只能是草稿，不能作为长期自动化资产。

4. **LLM 是策略与抽象器，不是实时控制器**  
   高频控制必须交给本地算法和 Controller。

5. **失败必须变成资产**  
   每次失败都要进入 FailureMemory、Benchmark 或 Skill 修复候选。

6. **系统必须知道自己不会什么**  
   不确定时要探索、询问、降级或停止，而不是假装成功。

7. **用户体验是研究系统的一部分**  
   如果用户无法启动和绑定，系统永远无法获得真实数据和真实验证。

## 17. 结论

Aurora 真正要挑战的不是“自动点击游戏”，而是“在复杂 3D 世界中，把慢速多模态推理转化为可验证、可复用、可进化的技能体系”。这条路线比端到端训练更工程化，也更适合当前没有大规模训练数据的条件。

要达到你提出的目标，下一阶段必须死磕三条主线：

1. **用户能用**：启动、绑定、校准、运行、理解失败。
2. **系统能学**：未知任务慢速探索，成功后自动生成 Skill，并通过验证晋升。
3. **任务能长**：Mission OS 能持续推进剧情、处理资源、战斗、养成、失败和恢复。

如果这三条主线打通，Aurora 才真正具备顶会论文级别的技术命题，也才有机会在原神、崩铁乃至更复杂 3D 游戏中证明：不依赖专用训练数据，也能通过系统工程和自生成 Skill 实现高完成度的长程智能体。
