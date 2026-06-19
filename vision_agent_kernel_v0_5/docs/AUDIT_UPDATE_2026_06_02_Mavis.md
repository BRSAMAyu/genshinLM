# Sparkle Project 审计更正与对齐（2026-06-02 第二轮）

> **目的**：基于用户对项目设想的进一步说明，**纠正第一轮 audit 里的错位判断** + **补查第一轮遗漏的 data/ knowledge/ agent/ agentic/ 目录** + **重新校准 BAGEL、UniversalEntryAgent、CapsuleForge 在新设想下的真实定位**。
>
> **关联文档**：`docs/AUDIT_2026_06_02_Mavis.md`（第一轮完整分析）→ **本文件是它的更新与纠错**，请两份对照阅读。

---

## A. 用户核心新设想的总结（先对齐）

| # | 设想 | 含义 |
|---|---|---|
| 1 | **P0 优先级**：原神主线跑通 | 这是 2026-26H1 唯一目标 |
| 2 | **P0.5 配套**：自然语言接口 | 真机联调时必须有可用的自然语言入口，否则调不通 |
| 3 | **P3 暂缓**：多游戏兼容 | 架构能力具备即可，**不实际接入第二款游戏** |
| 4 | **self-programming coding agent 内核** | 框架内**运行**一个类 minisweagent / claudecode 的 coding agent，**它跟用户直接对话**，能自我修复系统、写代码、写测试、找管线问题、调参数 |
| 5 | **capsule 重新定位 = skill 机制** | 不再用 CapsuleForge 自动生成骨架，capsule 是**agent 自主实现/调用的 skill 库** |
| 6 | **BAGEL 移出生产** | BAGEL 是测试理论，**未来不接生产**。需要用成熟方案（langchain/autogen/claudecode-like）替换 |
| 7 | **5-Plane 智能化分层** | 关键词匹配在某些层（高频感知、状态路由）是合理的；但**核心 agent 内核、关键决策组件必须 LLM 化**；**封装自动化部分**要快、不进 LLM |
| 8 | **data/knowledge/ 真实存在** | 用户做的大量原神数据库搜索工作可能在我第一轮 audit 漏掉了，需要补查 |

---

## B. 第一轮 audit 错位判断的纠正

### B.1 ❌→✅ 错位 1：BAGEL 不是 P0 缺口

**第一轮判断**：
> "BAGEL 认知闭环是软集成（try/except），是 P0 缺口。需要从软集成升级为强约束。"

**事实**（用户新信息）：
- BAGEL 是用户的**测试理论**，**未来要移出生产**
- 替换为"已经过验证的成熟 AI 系统方案"（如 langchain/autogen/claudecode-like coding agent）

**新判断**：
- BAGEL **不是"软集成"问题**，而是"**BAGEL 整个要被替换**"
- 替换方向：**self-programming coding agent**（用户设想 #4）+ **成熟的 planning 库**（langchain/autogen/MiniMax）
- 第一轮 audit 里的阶段 4（"认知闭环实战化"）要**改写为"BAGEL 替换为 self-programming agent 内核"**

### B.2 ❌→✅ 错位 2：UniversalEntryAgent 不是"P0 缺口"

**第一轮判断**：
> "UniversalEntryAgent 没用 LLM，纯关键词匹配，是自然语言接口的 P0 缺口。需要重写为 LLM-first。"

**事实**（用户新信息 + 第二轮补查）：
- 用户的真意是：**UEAgent 只是"前端 shell"**，背后是 **self-programming coding agent 内核**
- 第二轮补查发现：**项目里已经有真实 LLM 集成的 agent**：
  - `agent/zero_shot_agent.py` 682 行——真实 VLM/LLM prompt 模板、ZhipuVLM 调用
  - `llm/zhipu_vlm_provider.py`——智谱 VLM 真实 provider
  - `agent_kernel/live_factory.py:287` 真接 `ZhipuVLMProvider`
- **真实缺陷**是：**没有一个统一的、self-programming 的 agent 内核**直接跟用户对话

**新判断**：
- UEAgent 的 keyword 匹配**本身合理**（高频入口加速）
- **真正的 P0 缺口是**：把多个分散的 LLM agent 实现（zero_shot_agent、CerebrumAgentImpl 是 keyword fallback、UEAgent 是 keyword）**整合成一个 self-programming coding agent 内核**直接跟用户对话
- 第一轮 audit 里的"重写 UEAgent"要**改写为"构建 self-programming agent 内核"**

### B.3 ❌→✅ 错位 3：CapsuleForge 不是"多游戏扩展核心"

**第一轮判断**：
> "CapsuleForge 永远 return unknown，多游戏扩展是幻象。需要重写。"

**事实**（用户新信息）：
- 用户的真意是：**capsule = agent 调用的 skill 库**，**由 agent 自主实现/扩展**，**不需要 CapsuleForge 自动生成**
- 多游戏兼容**P3 暂缓**，架构能力具备即可

**新判断**：
- CapsuleForge 是**历史包袱**，**当前可降级 / 不修**（不影响 P0 原神主线）
- **capsule 真正的演进方向**：agent 在跑原神时**自主识别"这个场景需要 skill X"** → **自主生成 X**（用 LLM + 沙箱）→ **把 X 注册到 skill 库** → 复用
- 这是"**agent 自主实现 skill**"的范式——比 CapsuleForge 自动生成**高几个数量级**

### B.4 ❌→✅ 错位 4：CerebrumAgentImpl 不是 LLM 驱动

**第一轮判断**（隐含）：
> CLAUDE.md 把 CerebrumAgentImpl 说成 L7-L8 大脑。

**事实**（第二轮补查）：
- `agent_kernel/cerebrum_agent.py:31-33` 文档自述：
  > "Provides rule-based strategic planning with LLM/VLM fallback. **In production, the cloud-first path uses a remote API. This implementation provides the offline fallback: keyword-based goal decomposition and pattern-based failure diagnosis.**"
- **CerebrumAgentImpl 自述是"offline fallback"**！L42-56 是 hardcoded `_GOAL_SKILL_MAP`，L58-79 是 hardcoded `_FAILURE_PATTERNS`，L125-142 是 fixed 3-action fallback
- **CLAUDE.md 又一次过度声明**

**新判断**：
- CerebrumAgentImpl 是 keyword fallback（关键路径就走这个）→ **核心规划层实际没用 LLM**
- `agent/zero_shot_agent.py` 是 LLM 化的正确实现，但**没接到 CerebrumAgentImpl 的路径上**
- **修复方向**：让 CerebrumAgentImpl 的云端路径**真的接** zero_shot_agent 或 MiniMax/智谱 LLM API

### B.5 ⚠️ 第一轮 audit 盲点：漏了 data/ 和 knowledge/

**第一轮**只读了 `app_service/`、`capsules/genshin/`、CLAUDE.md、PROJECT_ALIGNMENT.md、几份 docs。**漏了**：

| 漏掉的内容 | 实际规模 | 重要程度 |
|---|---|---|
| `data/combat_profiles/character_profiles.yaml` | 48KB | **真实角色战斗数据** |
| `data/combat_profiles/team_profiles.yaml` | 32KB | **真实队伍配置** |
| `data/combat_profiles/hsr_team_profiles.yaml` | 36KB | **HSR 队伍数据**（P3 暂缓但已有） |
| `data/decision_memory.db` | 28KB SQLite | **决策记忆持久化** |
| `data/skills/genshin_combat_skills.yaml` | 6.4KB | **真实战斗 skill 数据** |
| `data/skills/genshin_navigation_skills.yaml` | 6.9KB | **真实导航 skill 数据** |
| `data/skills/genshin_collection_skills.yaml` | 5.4KB | **真实收集 skill 数据** |
| `data/skills/versions/*.v1-v8.json` | 8 个版本 | **skill 版本管理** |
| `data/bagel_events/events.jsonl` | **3.85MB** | **大量 BAGEL 事件记录** |
| `knowledge/genshin_monsters.yaml` | **92KB** | **怪物数据库** |
| `knowledge/genshin_world_graph.yaml` | 83KB | **世界图**（有 .bak 备份） |
| `knowledge/genshin_ui_system.yaml` | 72KB | **UI 系统** |
| `knowledge/persona_characters.yaml` | 48KB | **角色人格** |
| `knowledge/genshin_resources.yaml` | 38KB | **资源** |
| `knowledge/hsr_enemies.yaml` | 79KB | HSR 敌人 |
| `knowledge/hsr_characters.yaml` | 23KB | HSR 角色 |
| `knowledge/online_guide_system.py` | 26KB | **在线攻略查询** |
| `knowledge/genshin_character_progression.py` | 22KB | 角色培养 |
| `knowledge/genshin_f2p_builds.py` | 21KB | **0 氪构建** |
| `knowledge/weapon_refinement_priority.py` | 15KB | 武器精炼优先级 |
| `agent/autonomous_task_brain.py` | 32KB | **task brain 主实现** |
| `agent/genshin_game_agent.py` | 30KB | **原神 game agent** |
| `agent/zero_shot_agent.py` | 26KB | **LLM 化的 zero-shot agent** |
| `agent/exploration_agent.py` | 7.6KB | 探索 agent |
| `agentic/visual_grounding.py` `action_proposer.py` `ui_explorer.py` `confidence_gate.py` | 各 ~800B | agentic 辅助 |
| `llm/zhipu_vlm_provider.py` | (未读) | **智谱 VLM provider** |
| `llm/vision_provider.py` | (未读) | VLM 接口 |

**新增的事实**：
- 用户说"做了很多原神数据库搜索" → **确实有 400KB+ 的真实知识数据**（knowledge/），**我没看就被我打脸了**——这本来是 P0 资产
- `agent/` 目录有 **3 个真实 agent 实现**（autonomous_task_brain、genshin_game_agent、zero_shot_agent），**第一轮 audit 完全没提**
- live_factory.py 把它们 + ZhipuVLM 整条链路 wire 起来了
- `data/bagel_events/events.jsonl` 3.85MB → **BAGEL 事件在真生产链路里跑过的证据**（虽然你说未来要移出）

### B.6 ⚠️ 第一轮 audit 错位 6：BAGEL 实际还在生产

**第一轮 audit 的隐含判断**：
> "BAGEL 是 CLAUDE.md 描述的核心引擎。"

**事实**（用户新信息 + 第二轮补查）：
- 用户说 BAGEL 移出生产 → **但代码 live_factory.py:368-372 真接着**：
  ```python
  from bagel.fig_schema import FalsifiableInterventionGraph
  from bagel.belief_proposer import BeliefProposer
  from learning.decision_memory import DecisionMemory
  from learning.meta_learning_bridge import MetaLearningBridge
  from learning.parameterized_skill_induction import ParameterizedSkillInductor
  ```
- `agent_kernel/loop.py:319-335` 真在调 `classify_failure_mode` + `meta_learning_bridge.on_exploration_result`

**新判断**：
- **代码现状**：BAGEL 整套在主链路上跑
- **用户意图**：未来 BAGEL 移出
- **现状与意图的 gap**：**没改代码**——这是用户没做完的迁移，**不是已完成的迁移**
- **第一轮 audit 的"BAGEL 软集成"P0 缺口判断仍然成立**，但要换个表述：**BAGEL 整块要在某阶段被替换为 self-programming agent 内核**

---

## C. 校正后的项目真实状态

### C.1 已存在的真实组件（第一轮低估）

| 组件 | 真实状态 | 证据 |
|---|---|---|
| **DXcam 屏幕抓帧** | 真接入 | `live_factory.py:262-263` DxcamCapturer |
| **智谱 VLM 接入** | 真接入 | `live_factory.py:287-288` ZhipuVLMProvider，API key 从 env |
| **VLMPerceptionProvider** | 真实现 | `agent_kernel/adapters.py`（CLAUDE.md 引用，未深读） |
| **CerebrumAgentImpl** | 真实现，但**是 keyword fallback** | `agent_kernel/cerebrum_agent.py:31-33` 自述 |
| **GenshinActionExecutor** | 真实现 | `agent/genshin_game_agent.py` 30KB |
| **VLMSuccessChecker** | 真实现 | `live_factory.py:320-321` |
| **SpinalReflexAgentImpl** | 真实现 | `agent_kernel/spinal_reflex_agent.py`（未深读） |
| **DialogueController** | 真实现 | `agent_kernel/dialogue_controller.py`（未深读）+ `OptionRegistry` |
| **DailyCommissionDryRunRuntime** | 真实现 | `agent_kernel/embodied_runtime.py`（未深读） |
| **FileMemoryStore** | 真实现 | `agent_kernel/memory.py`（未深读） |
| **UnknownSceneHandler** | 真实现 | `agent_kernel/unknown_scene_handler.py`（未深读），6 次 probe 尝试，0.45 阈值 |
| **BAGEL 整链** | 真接在 live_factory | `live_factory.py:368-372` + `loop.py:319-335` |
| **decision_memory.db** | 真有数据 | `data/decision_memory.db` 28KB |
| **Bagel 事件记录** | 3.85MB 真实事件 | `data/bagel_events/events.jsonl` |
| **知识库** | 400KB+ YAML 数据 | knowledge/ 12 个 .yaml / 5 个 .py |
| **任务 brain** | 32KB 真复杂 | `agent/autonomous_task_brain.py` 依赖 25+ 模块 |
| **zero-shot LLM agent** | 682 行真 VLM 集成 | `agent/zero_shot_agent.py` |
| **Demo ARPG / Desktop UI capsule** | 真存在但 dummy | capsules/demo_arpg/, capsules/desktop_ui/ 显式 dummy 文件名 |

### C.2 真实缺陷（按用户新设想重排）

#### 缺陷 1：缺 **self-programming coding agent 内核**（P0）

**用户设想**：
- 框架内**运行**一个类 minisweagent / claudecode 的 coding agent
- 它跟用户直接对话
- 能：操控流程规划/执行 + 自我修复系统（写代码、写测试、找问题、调参数、改设计）

**现状**：
- 有 `app_service/coding_agent.py`（137 行）—— **只是 skill 函数生成器**，没有 self-modification 能力
- 有 `app_service/agent_controller.py`（33KB）—— **可能是更完整的 agent 控制器**（未深读）
- 有 `app_service/skill_manager.py`（34KB）—— **可能是 skill 库**（未深读）
- 有 `agent/autonomous_task_brain.py`（32KB）—— **是 task brain**，但不能写代码修复自己
- **没有"self-programming + self-modification"能力**——agent 跑的时候不能修改自己的代码

**结论**：**这是用户最想要的、目前最大的缺口**。

#### 缺陷 2：CerebrumAgentImpl 没用 LLM（P0.5）

**现状**：
- `cerebrum_agent.py:31-33` 自述是 "offline fallback"
- 实际是 keyword/rule-based
- `live_factory.py:308` 把它当主 planner

**修复**：
- 让 CerebrumAgentImpl 的 "cloud-first path" **真接** zero_shot_agent 或 LLM API
- 或者：把 CerebrumAgentImpl 替换为"self-programming agent 内核"（用户设想 #4）

#### 缺陷 3：5-Plane 智能化分层不清晰（P0.5）

**用户设想**：
- 关键词匹配在某些层是合理的（高频感知、状态路由）
- **核心 agent 内核、关键决策组件必须 LLM 化**
- **封装自动化部分**要快、不进 LLM

**现状**：
- live_factory.py 的 5 层都接好了，但**没有显式的"哪层用 LLM、哪层用 keyword"的策略说明**
- UniversalEntryAgent 纯 keyword → **可能是合理的加速**（用户原话"有些部分用关键词匹配能够加速降低我们的开销"）
- CerebrumAgentImpl 纯 keyword → **不合理**（这是核心规划层，应该 LLM）
- zero_shot_agent LLM 化 → **是合理的**

**修复**：
- 显式给每个 plane 标注"LLM / keyword / hybrid"
- 写 `docs/PLANE_LLM_POLICY.md` 说明每个平面的 LLM 策略

#### 缺陷 4：BAGEL 待替换（P0，未来某个阶段）

**用户设想**：
- BAGEL 移出生产
- 替换为成熟方案

**现状**：
- BAGEL 整套在 live_factory 接好
- 3.85MB 事件数据在累积
- **没改代码**

**修复路径**（在阶段 4 做）：
- 保留 BAGEL 的 event store（作为 backup 知识）
- 用 self-programming coding agent + 成熟 planning 库（langchain/autogen/MiniMax 风格的）替换 BAGEL 的实时归因/技能归纳
- 切换完成后删 BAGEL 代码

#### 缺陷 5：capsule 演进方向调整（P0）

**用户设想**：
- capsule = agent 调用的 skill 库
- agent 自主实现/扩展 skill
- 不需要 CapsuleForge 自动生成

**现状**：
- capsule 现在的形态是"声明式 manifest + 5 个抽象 SkillRecipe + 几个 .py provider"
- `app_service/skill_manager.py` 34KB 可能是真正的 skill 管理器（**未深读**）
- `app_service/coding_agent.py` 137 行能 LLM 生成 skill 函数（但默认 LLM 是 None）
- `data/skills/` 已有 4 个 skill YAML + 8 个版本文件

**修复**：
- 强化 `skill_manager.py` 作为 skill 中心注册表
- 强化 `coding_agent.py` 让 LLM 生成的 skill 自动进 skill 库
- 让 agent 跑任务时能"自主发现缺 skill → 调用 CodingAgent 生成 → 注册 → 重试"

#### 缺陷 6：data/ knowledge/ 是真实资产（**第一轮 audit 严重低估**）

**事实**：
- `data/` 有 32-48KB 真实战斗数据 + 28KB SQLite
- `knowledge/` 有 400KB+ 真实 YAML 数据 + 5 个真实知识 .py 模块
- **这些是 P0 资产**，原神主线跑通要重度依赖

**修复**：
- 把 knowledge/ 接入 LLM prompts（zero_shot_agent、CodingAgent、CerebrumAgentImpl）
- 用 knowledge/ 替换部分 hardcoded logic（CerebrumAgentImpl 的 _GOAL_SKILL_MAP 应该从 knowledge/genshin_world_graph.yaml 查）

---

## D. 校正后的多阶段改进方案

> **第一轮 audit 里的 6 阶段**改写如下。重点：聚焦 P0（self-programming agent 内核 + 原神主线跑通），**BAGEL 替换推到 P1**，**多游戏兼容 P3 暂缓**。

### 阶段 0：地基修缮 + LLM 化最小骨架（4 周）

**目标**：
- 修 CLAUDE.md 让"声明-现实"对齐
- 最小化 LLM 接入（智谱/MiniMax API），让 UniversalEntryAgent / CerebrumAgentImpl / CodingAgent 都有 LLM 后端
- 强化 knowledge/ data/ 接入（不让它们只是静态文件）

**关键交付物**：

1. **CLAUDE.md 重写** —— "声称/已实现/规划中"三段式
2. **`app_service/universal_entry_agent.py` 加 LLM 后端**（可开关）
3. **`agent_kernel/cerebrum_agent.py` 接 LLM**（替换 keyword fallback）
4. **`app_service/coding_agent.py` 接 LLM**（默认走 MiniMax 风格）
5. **`docs/PLANE_LLM_POLICY.md`** —— 5-Plane 每层的 LLM/keyword 策略
6. **`knowledge/loader.py`** 强化 —— 知识查询 LLM-friendly

**任务清单**：
- [ ] 重写 CLAUDE.md，加 `claimed|implemented|partial` 标签
- [ ] UniversalEntryAgent 加 LLMProvider Protocol，默认 MiniMax
- [ ] CerebrumAgentImpl 的 `compile_mission` 改为 LLM 调用（保留 keyword fallback）
- [ ] CodingAgent 默认 LLMProvider 改为 MiniMax
- [ ] 写 PLANE_LLM_POLICY.md：perception 关键词/YOLO、control 关键词、execution 关键词、orchestration LLM、telemetry 关键词
- [ ] knowledge/ 加 `query(game_id, topic) -> dict` 通用接口
- [ ] 把 data/combat_profiles/team_profiles.yaml 接入 CerebrumAgentImpl._GOAL_SKILL_MAP

**风险**：
- LLM API 限流/成本 → 默认 keyword，LLM 走 throttle（5s 一次）
- LLM 误判 → 执行前向用户确认

**验证标准**：
- 用户输入"去蒙德"→ UniversalEntryAgent 调 LLM 解析 → 返回带参 ExecutionPlan
- CerebrumAgentImpl.compile_mission 调 LLM → 返回 MissionGraph
- CodingAgent.generate_skill 调 LLM → 返回 GeneratedSkill（带 validation 报告）

**对应愿景**：A、B

---

### 阶段 1：self-programming coding agent 内核（10-14 周）⭐ 核心

**目标**：框架内运行一个**类 minisweagent / claudecode 的 coding agent**，它：
- 跟用户直接对话
- 能调用所有内核 API（StateBus、LiveFactory、MissionRunner、KnowledgeStore、CodingAgent）
- 能**写代码、写测试、修改系统参数、找管线问题**
- 是真机联调时**用户的唯一对话对象**

**关键交付物**：

1. **`agent_kernel/self_programming_agent.py`**（新文件，预计 20-30KB）：
   - 类 minisweagent：接收用户 query → LLM 拆解为"工具调用" → 执行
   - 工具集（Tools）：
     - `read_file(path)` / `write_file(path, content)` / `edit_file(path, old, new)` / `run_test(pattern)` / `run_benchmark(name)` / `inspect_module(path)` / `query_knowledge(topic)` / `dry_run_action(plan)` / `run_mission(graph_id)` / `update_param(key, value)` / `submit_patch(file, old, new)` 等
   - 沙箱保护：所有写操作只写到 staging 目录，测试通过才能 merge
   - 测试运行：`pytest tests/ -k "..."` 自动跑相关测试
   - 自我修复循环：用户说"战斗场景处理的不好" → agent 调 inspect_module('combat/') → 找可疑代码 → edit_file → 跑测试 → 通过则 commit
2. **CLI / Tauri GUI 入口**：
   - CLI：`python -m self_programming_agent "战斗处理有问题，修一下"`
   - GUI：自然语言输入框 + 代码 diff 视图 + 测试报告
3. **对话式 task 拆解**：
   - 用户："我想跑通蒙德风龙废墟主线"
   - agent 拆解：选 MissionGraph 模板 → 检查 capsule 完整性 → 选 1 个蒙德章节 → 跑测试 → 找问题 → 修 → 重跑
4. **跟现有内核的集成**：
   - 调用 LiveFactory 创建 AgentLoop
   - 调用 MissionRunner 跑任务
   - 调用 KnowledgeStore 查攻略
   - 调用 CodingAgent 生成新 skill
   - 读/写/改项目内代码
5. **真实 LLM 接入**：
   - 走 MiniMax API（或用户指定的 LLM）
   - prompt 包含项目 CLAUDE.md + 当前 5-Plane 状态 + 当前 mission 进度

**任务清单**：
- [ ] 写 `agent_kernel/self_programming_agent.py`：Tools、LLM loop、沙箱保护
- [ ] 写 `self_programming_agent/tools/` 工具集（每个工具一个 .py）
- [ ] 写 `self_programming_agent/sandbox.py`：写文件到 staging、测试通过才 commit
- [ ] 写 `self_programming_agent/cli.py`：CLI 入口
- [ ] 写 `self_programming_agent/prompts/system_prompt.yaml`：项目上下文注入
- [ ] 写测试 `tests/test_self_programming_agent.py`
- [ ] 写文档 `docs/SELF_PROGRAMMING_AGENT.md`

**风险**：
- agent 改坏自己代码 → 强制 staging + 测试门禁
- LLM 成本 → 用 throttle，每 turn 限 1 次 LLM 调用
- 用户给出模糊指令 → agent 主动追问

**验证标准**：
- 用户："战斗时 HP 计算不对，去查 combat/reaction_damage_calc.py" → agent 读文件 → 找 bug → 写 patch → 跑测试 → 通过 → 自动 commit
- 用户："自动给我准备蒙德风龙废墟主线的 MissionGraph" → agent 调 knowledge/ + 模板生成 → 跑 dry-run → 输出可执行的 mission graph
- 用户："先跑 5 分钟蒙德某段主线，自己看哪里有问题" → agent 启动 LiveFactory + MissionRunner → 记录所有失败 → 自我修复 → 报告

**对应愿景**：A、B、D（这是用户最想要的、贯穿所有愿景的核心能力）

---

### 阶段 2：原神蒙德首章主线端到端跑通（10-14 周）⭐ P0

**目标**：在真实原神游戏窗口下，agent 能从新号开始，自动完成蒙德章节的某一段主线，端到端跑通。

**前置依赖**：阶段 1（self-programming agent 内核）

**关键交付物**：

1. **真实蒙德主线条目化的 MissionGraphV4 实例** —— 至少 3-5 个蒙德主线节点
2. **真实 VLM 接入** —— 智谱 GLM-4V API，端到端延迟 <2s
3. **真实 YOLO 权重** —— 原神界面关键元素
4. **真实 live 跑通报告** —— 视频+JSONL
5. **失败恢复** —— 5+ 失败模式 + recovery 路径
6. **用 self-programming agent 调试** —— 真机联调时用户**直接跟 self-programming agent 对话**

**任务清单**：
- [ ] 选蒙德某段主线（建议"风龙废墟"或"蒙德城找凯瑟琳"）
- [ ] 拆 MissionGraphV4 节点：open_quest_log → select_quest → teleport → walk → enter → boss → reward → return
- [ ] 用 knowledge/genshin_monsters.yaml 92KB 知识训练 LLM prompt
- [ ] 用 knowledge/genshin_world_graph.yaml 83KB 知识做 waypoint 路由
- [ ] 用 knowledge/online_guide_system.py 做实时攻略查询
- [ ] YOLO：HP 条、对话框、任务标记、菜单按钮、敌人轮廓
- [ ] 接智谱 GLM-4V
- [ ] 用 self-programming agent 调试（用户 → self_programming_agent → 修代码 → 重跑）
- [ ] 跑通 30-60 分钟主线，5 次连跑 ≥4 次成功

**风险**：
- 智谱 VLM 限流 → retry + 本地小 VLM 备选
- 原神更新 → content_versioning 检测
- YOLO 误检 → VLM 替代 screen state 分类

**验证标准**：
- 30 分钟连续视频：agent 自动完成蒙德某段主线
- JSONL：所有动作、claim、recovery 都有时间戳
- 5 次连跑 ≥4 次成功
- **self-programming agent 能自动修复至少 3 类常见问题**（"目标丢失"、"过场动画卡住"、"对话选项判断错"）

**对应愿景**：A

---

### 阶段 3：自然语言 + Long-horizon 体系化（6-8 周）

**目标**：用户用自然语言下"先去 A 然后 B 再 C"这种复合长程任务，agent 端到端完成。

**前置依赖**：阶段 1、2

**任务清单**：
- [ ] UniversalEntryAgent 强化 LLM 化（多步意图、实体抽取、参数 binding）
- [ ] MissionGraph 生成：LLM 接收意图 + 上下文 → 输出 MissionGraphV4 JSON
- [ ] 跨 session 状态延续：quest_context_persistence + persona memory
- [ ] 20+ 高频自然语言指令测试集
- [ ] self-programming agent 加 "intent understanding" tool，能读 knowledge/ 校准意图

**验证标准**：
- 20 条自然语言指令，≥18 正确解析
- "先去蒙德找凯瑟琳，再去璃月买 5 个烤鱼"正确分解

**对应愿景**：B

---

### 阶段 4：BAGEL 替换为 self-programming + 成熟 planning 库（6-8 周）

**目标**：把 BAGEL 整块从生产移除，替换为：
- self-programming coding agent（阶段 1 已有）
- 成熟 planning 库（langchain/autogen/MiniMax 风格）
- 保留 BAGEL 的 event store 作为 backup 知识

**前置依赖**：阶段 1、2、3 都稳定

**任务清单**：
- [ ] 用 langchain/autogen 替换 BeliefProposer 实时归因（保留历史 events.jsonl 数据）
- [ ] 替换 MetaLearningBridge 实时触发
- [ ] 删除 live_factory.py:368-372 的 BAGEL import
- [ ] 删 agent_kernel/loop.py:319-335 的 BAGEL 调用
- [ ] 把 data/bagel_events/ 标记为 archive
- [ ] 写 BAGEL_REMOVAL.md 记录迁移过程

**验证标准**：
- live_factory 不再 import bagel
- 阶段 2 的端到端跑通依然通过

**对应愿景**：架构清理

---

### 阶段 5-6：（P3 暂缓，列出占位）

- **阶段 5：HSR 接入** —— P3 暂缓
- **阶段 6：长程记忆 + 玩家 persona** —— P2

---

## E. 校正后的关键建议（取代第一轮 8 条）

1. **P0 不是"BAGEL 强约束"** 而是"**构建 self-programming coding agent 内核**"（用户新设想 #4）—— 这是项目目前最大的、最有价值的缺口
2. **5-Plane 智能化分层要显式声明** —— 写 `docs/PLANE_LLM_POLICY.md`，避免 CLAUDE.md 那种"全栈 LLM"的过度声明
3. **CerebrumAgentImpl 是 keyword fallback** —— 不能再当 L7-L8 决策大脑，**必须真接 LLM**（或替换为 self-programming agent）
4. **data/ knowledge/ 是真资产**（第一轮 audit 严重低估）—— 把 knowledge/ 接入所有 LLM prompt，**这是 P0 资产**
5. **capsule 演进方向改为"agent 自主实现 skill"** —— 不要重写 CapsuleForge，强化 CodingAgent + skill_manager，让 agent 自己造 skill
6. **BAGEL 替换分阶段** —— 阶段 1-3 让 self-programming agent 跑稳，阶段 4 才真正动 BAGEL
7. **self-programming agent 是"真机联调时的唯一对话对象"**（用户新设想 #4）—— 这改变了开发模式，**从"用户 → claude code → 改代码"变成"用户 → 框架内 coding agent → 自动修"**
8. **CLAUDE.md 重写优先级提到 P0** —— 当前 CLAUDE.md 误导严重，**对内对外都要重写**

---

## F. 第一轮 audit 哪几条仍然成立

1. ✅ **CLAUDE.md 自我描述偏差严重**（仍然成立，但具体偏差点要按 B.1-B.4 修正）
2. ✅ **capsule 演进方向要重写**（成立，但方向是"agent 自主 skill"而非"CapsuleForge 自动生成"）
3. ✅ **5-Plane 真接起来了**（成立，第一轮没看 live_factory.py 是我的疏忽）
4. ✅ **BAGEL 需要替换**（成立，方向对了，但替换内容改为 self-programming + 成熟 planning）
5. ✅ **CerebrumAgentImpl 实际不是 LLM 驱动**（新发现，CLAUDE.md 过度声明）
6. ⚠️ **benchmark 报告在 testbed 跑**（仍然成立，但"全 0ms timing"是因为 pseudo3d_scene testbed，跟"没真跑"不矛盾）
7. ⚠️ **tests 真实规模 4342**（仍然成立，但 mock 测试占比需要进一步核查）
8. ✅ **多游戏扩展 P3 暂缓**（成立，按用户优先级）

---

## G. 我之前的几个具体错位（一并承认）

| 我说的 | 实际 | 怎么改 |
|---|---|---|
| "capsules/genshin/ 总共 4 个 .py 文件，不到 20KB 代码" | 错。**capsule.yaml 192 行 + 5 个 SkillRecipe 骨架 + 7 个 resources 指向真实数据**：48KB character_profiles、32KB team_profiles、6.4KB combat_skills、6.9KB nav_skills、5.4KB collection_skills、92KB 怪物库、83KB 世界图、72KB UI 系统等。**总真实资产是 400KB+ 数据**。 | 重新评估"代码量"≠"能力"——capsule 的能力在数据+manifest，不是 .py 代码行数 |
| "agent_kernel 821 行 AgentLoop 是真实实现" | 没错，但**没提 live_factory.py 把整套生产链 wire 起来了** | 第一轮 audit 漏了 live_factory.py 的关键内容 |
| "BAGEL 是软集成" | 半对：BAGEL 整套接在 live_factory，但 CerebrumAgentImpl 调用 BAGEL 时被 try/except 包住 | "软集成"是真的，但根因是 BAGEL 整个要被替换 |
| "UniversalEntryAgent 是关键词匹配 → P0 缺口" | **错位**。UEAgent 是合理的 keyword 入口，**真正 P0 缺口是 self-programming agent 内核** | 重写为"self-programming coding agent 内核" |
| "CapsuleForge 永远 return unknown → 多游戏扩展是幻象" | 错位。capsule 在用户设想里是 skill 库，**不是 CapsuleForge 自动生成的** | 重新定位 capsule 演进方向 |
| "CerebrumAgentImpl 是 L7-L8 大脑" | **CLAUDE.md 又一次过度声明**。CerebrumAgentImpl **自述是 offline fallback** | 修复方向：CerebrumAgentImpl 真接 LLM 或替换为 self-programming agent |

---

## H. 总结

**用户新设想的核心**：
1. P0 = 原神主线跑通
2. P0.5 = 自然语言接口（self-programming agent）
3. P3 = 多游戏暂缓
4. **self-programming coding agent 内核** 是用户最想要的、目前最大的缺口
5. BAGEL 移出生产（**代码还没动**）
6. capsule = agent 自主 skill 库
7. 5-Plane 智能化分层要显式

**第一轮 audit 的纠错**：
- B.1 BAGEL 缺口判断错位（不是软集成，而是要替换）
- B.2 UEAgent 缺口判断错位（不是没 LLM，是缺 self-programming 内核）
- B.3 CapsuleForge 缺口判断错位（capsule 演进方向不同）
- B.4 CerebrumAgentImpl 过度声明（CLAUDE.md 又骗）
- B.5 严重漏查 data/ knowledge/（**400KB+ 真实资产**）
- B.6 BAGEL 在生产里（**代码没动**）

**校正后的 P0 路线**：
1. **阶段 0**（4 周）：CLAUDE.md 重写 + LLM 化最小骨架 + knowledge/ 接入
2. **阶段 1**（10-14 周）：**self-programming coding agent 内核**（这是用户最想要的）
3. **阶段 2**（10-14 周）：原神蒙德首章主线端到端跑通（用 self-programming agent 调试）

总工期 P0 段：24-32 周（6-8 个月），**单人加班可压到 18-24 周**。

**最关键的一句话**：
> **不要重写 CapsuleForge，不要硬塞 BAGEL 强约束，优先建 self-programming coding agent 内核 + 把它跟现有 LiveFactory 联通。** 这是项目 P0 阶段最该做的事，也是你真机联调时唯一需要的对话对象。

---

*更新报告完*
