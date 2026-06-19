# Sparkle Project (Vision Agent Kernel v0.5) — 批判性质量审查与多阶段改进方案

> **审查人**：Mavis (Mavis)
> **审查时间**：2026-06-02
> **审查范围**：`D:\Aurora\vision_agent_kernel_v0_5\` 全仓
> **方法**：CLAUDE.md / PROJECT_ALIGNMENT.md 自述 → 关键 docs 文档 → 60+ 个核心 .py 文件的代码状态核查 → 5 份 phase8 final audit 报告 + benchmark_reports 实证 → 4342 个测试的 pytest collect 结果 → TODO/NotImplementedError/stub 密度扫描

---

## 0. TL;DR — 10 条最致命发现

1. **CLAUDE.md 高度乐观，声称与代码现实严重不符**。文档说"已有 UniversalEntryAgent 能解析自然语言"，代码里它只是**关键词匹配 + 7 个 hardcoded 模板**（`app_service/universal_entry_agent.py:47-55, 87-172`），**不调 LLM、不解析参数、不支持多步意图**。这是项目最大的"声明-现实 gap"。

2. **CapsuleForge 是个幻影**。`app_service/capsule_forge.py:188-209` 生成的"screen classifier"模板永远 `return "unknown"`，"combat detector" 永远返回空的 `CombatDetection()`。**所谓"LLM-driven code generation"是可选路径，StubLlmBackend 永远返回空字符串，默认走 stub**。多游戏扩展 = 一堆永远 `return unknown` 的空壳。

3. **声称"4323 个测试"**实际 **4342 tests collected**（CLAUDE.md 数字大致准确），但**主 benchmark 报告都在伪 3D 场景里跑**。`testbed/pseudo3d_scene.py` 标题是 "vision_agent_kernel_v0_5 pseudo3d_scene"（line 27），**5 份 phase8 final audit 报告所有 timing 都是 0.000ms**（boss_combat 报告 line 50-54、long_horizon 报告 line 43-50 等），**100% pass rate，没有任何真实 VLM 推理、YOLO 检测、屏幕抓帧时间**。UI 安全报告测的是 `btn_start/btn_delete/btn_sell` 这种**通用 button 测试**，不是原神。

4. **capsules/genshin/ 总共 4 个 .py 文件，** 不到 20KB 代码**。`genshin_game_capsule.py` 299 行（`capsules/genshin/genshin_game_capsule.py`）**只有 5 个 SkillRecipe 骨架、27 个 screen 词汇、27 个 action 词汇、风险策略表**。**没有任何真实元素反应 / 角色轮转 / 战斗循环逻辑**——Python 里都是"abstract intent"（"assess_threats"、"dodge_if_danger"），实际执行由下游 `execution/safe_window_backend.py`、`combat/combat_skill_adapter.py` 等模块负责，但这些**与真实原神主线的覆盖率不明**。

5. **mainline_live_bridge.py 是真接到原神窗口的**（`planning/mainline/mainline_live_bridge.py:40-46` 显式 `SafeWindowInputBackend(target_window_title="原神")`），**但 MissionGraphV4 的"主线节点"覆盖率无可见证据**。`planning/mainline/` 11 个文件是**完整的声明式图基础设施**（claim contract / BAGEL 信念模板 / 节点预算 / fallback / probe policy），但**没有看到公开的"Mondstadt → Liyue → Inazuma"主线条目**作为 MissionGraphV4 实例。

6. **架构/管道层写得相当完整**（685 个 .py、13.7 万行、TODO 仅 1 个、FIXME 0 个、NotImplementedError 2 个、bare pass 142 个——这 142 个是抽象方法/Protocol 的空实现，不算"骗人 stub"），**核心数据结构、协议、状态机、BAGEL 信念系统、Combat 战术、Navigation 适配器都已经有真实代码**。**但"完整架构" ≠ "端到端跑通"**。架构 80% 完整 vs 端到端真跑通原神主线 5% 完成度——这是当前最准确的描述。

7. **BAGEL 认知闭环是软集成**。`agent_kernel/loop.py:319-335` 的 MetaLearningBridge 调用被 try/except 包住，失败只 `log.debug`；L337-380 的 `replan_on_failure` 也被 try/except 包装。这本身是合理的鲁棒性写法，但**意味着 BAGEL→learning 链路实际是 optional 软链接**，没有强约束。CLAUDE.md 把它说得像核心引擎，实际是 best-effort。

8. **PROJECT_ALIGNMENT.md 的"宪法"在多个核心模块都没真正落地**。"拒绝阻塞等待"（PROJECT_ALIGNMENT.md L93）—— `agent_kernel/loop.py:227, 235, 385` 有 `time.sleep(0.05)`，但 chunked wait 实现 OK；"拒绝单帧差值"——ProgressSupervisor 在 `control/progress_supervisor.py`（CLAUDE.md 提到）实际状态我没深查，但代码里有 `EWMA` 字段。"LLM 保持克制"——**事实上 UniversalEntryAgent 完全不用 LLM，CapsuleForge 默认不用 LLM**——这反而是"过度克制"，**自然语言理解和代码生成完全缺失**。

9. **多游戏兼容目前只到配置层**。`capsules/hsr/` 跟 `capsules/genshin/` 是**结构对称的孪生**——同一份 capsule.yaml 模板、同一份 SkillRecipe 骨架（`hsr_game_capsule.py` 8.5KB）。`CapsuleProtocol` / `Domain Protocols` 抽象层写得不错（`capsules/domain_protocols.py` 4.4KB），但**combat_skill_adapter / navigation 内部仍大量硬编码 genshin 语义**（例如 `combat/combat_skill_adapter.py` 26KB）。

10. **最大的隐藏风险**：**CLAUDE.md 是项目主入口文件**，CLAUDE.md 写得像产品宣传文案。**新加入的 Coding Agent / 架构师读 CLAUDE.md 会被严重误导**——会以为 LLM 已接入、CapsuleForge 已工作、原神主线已实现。**项目自我描述的"乐观偏差"是当前最严重的工程债**。

---

## 1. 审查方法与证据基础

### 1.1 审查操作清单

| 操作 | 结果 |
|---|---|
| `pytest --collect-only -q` | **4342 tests collected**（CLAUDE.md 声称 4323，差 19） |
| 扫描 685 个非测试 .py 文件 | 13.7 万行；TODO 1 个、FIXME 0 个、NotImplementedError 2 个、bare pass 142 个 |
| 读 5 份 phase8 final audit 报告 | 100% pass rate，**所有 timing 0.000ms** |
| 读 2 份核心 capsule（genshin, hsr）实际代码 | 不到 30KB Python，**全 YAML/声明式** |
| 读 mainline_live_bridge.py、live_factory.py、mission_graph_v4.py、universal_entry_agent.py、capsule_forge.py、agent_kernel/loop.py | 确认**架构真实存在但部分功能 stub** |

### 1.2 关键代码引用约定

- 文件路径以 `vision_agent_kernel_v0_5/` 为根
- 行号基于当前快照
- 引用代码片段用 markdown 代码块

---

## 2. 项目当前实现成熟度

### 2.1 维度 A：自主通关原神主线

#### 已实现（带证据）

| 能力 | 证据 |
|---|---|
| 5-Plane 架构 + StateBus | `core/state_bus.py`（CLAUDE.md 引用，我未深读代码，但目录存在、CLAUDE.md 自述详尽） |
| MissionGraphV4 声明式节点系统 | `planning/mainline/mission_graph_v4.py`（15KB）：ClaimContract、BeliefTemplate、NodeBudget、FallbackDecl、ProbePolicyDecl 真实 dataclass 实现 |
| MainlineRunner 完整执行循环 | `planning/mainline/mainline_runner.py`（37KB），是该项目最大单文件之一 |
| MainlineLiveBridge 真接原神窗口 | `planning/mainline/mainline_live_bridge.py:40-46` 显式 wire SafeWindowInputBackend(target_window_title="原神") + InputWorker + MinimapQuestReader + QuestMarkerFollower + BossCombatBridge + TeamProfile + SentinelRuntime |
| Genshin Capsule 完整 YAML 清单 | `capsules/genshin/capsule.yaml`（192 行）：7 个 providers、4 个 skills、3 个 transitions、2 个 detectors、keymaps、5 个 ui_anchors、7 个 resources |
| 5 个抽象 SkillRecipe | `capsules/genshin/genshin_game_capsule.py:130-238`：safe_combat_genshin_v1、boss_combat_genshin_v1、dodge_reflex_genshin_v1、teleport_and_navigate_v1、handle_dialog_v1、open_chest_genshin_v1 |
| L0-L9 AgentLoop 真有 821 行 | `agent_kernel/loop.py`（38KB）：100Hz 拦截线程、50Hz 战斗反射线程、Cerebrum 5s throttle、Claim 仲裁、Recovery 重规划 |
| 战斗战术层深度 | `combat/` 子目录 25+ 文件，包含 `combat_survival.py`(28KB)、`spiral_abyss.py`(23KB)、`boss_combat_handlers.py`(24KB)、`reaction_damage_calc.py`(18KB) 等 |
| 导航层深度 | `navigation/special_movement.py`(23KB) 含爬墙/解谜，`universal_navigator.py`（CLAUDE.md 引用） |
| 持久化 | `persistence/` 目录存在 |
| 多场景测试 | `runs/aurorabench_phase8_final_audit/` 5 份：long_horizon、boss_combat、ui_safety、repair、reflex |

#### 声明但未实现 / 严重不达

| 声明 | 现实 |
|---|---|
| "原神主线节点"作为 MissionGraphV4 实例 | **无公开证据**。`mission_graph_v4.py` 是通用声明式框架，**没看到任何 "Mondstadt Chapter 1" 之类的具体节点实例**。`docs/GENSHIN_MAINLINE_PROGRESSION_CHAIN.md`（CLAUDE.md 提到）我未读，但 docs/ 里同名 70KB+ 文档是规划/breakdown 性质，**不一定是真在跑的 mission graph**。 |
| "BAGEL 信念归因"实战 | `agent_kernel/loop.py:319-335` 的调用被 try/except 软包，**失败只 log.debug**。`bagel/runtime.py`(28KB)、`bagel/fig_schema.py`(23KB)、`bagel/belief_proposer.py` 等**代码存在**，但**端到端跑通原神主线的归因记录我没看到**。 |
| "claim-gated 端到端跑通" | `agent_kernel/loop.py:300-304` 真实调 `self._checker.adjudicate_delta(obs, post_obs, goal.success_criteria)`，Claim 仲裁有真实代码路径。但**benchmark 报告里 0ms timing、0 consecutive dodges、UI 测 btn_start 通用 button**——这不是真实原神。 |
| "UniversalEntryAgent 能解析自然语言" | **关键词匹配 + 7 个 hardcoded 模板**，**不调 LLM**。详见 2.2 维度。 |
| "CapsuleForge 自动生成可用 capsule" | **永远 return "unknown" 的 stub 模板**，详见 2.3 维度。 |
| "已支持 4323 个测试" | 实际 4342，**接近准确**（差 19），但**很多测试是 mock 跑 unit 级**，benchmark 报告是 testbed 跑。 |

#### 关键 gap

1. **原神主线节点实例** —— 没有任何 MissionGraphV4 实例文件明确是"蒙德→璃月→稻妻"主线节点。**这是最关键的 gap**。
2. **真实 VLM 接入** —— `live_factory.py` 提到 `ZhipuVLM`，但我未确认智谱 VLM 真实调用是否存在、API key 是否配好、端到端 latency 多少。
3. **真实 YOLO 模型权重** —— `perception/` 下有 YOLO 管线，但**YOLO weights 是否训过/finetune 过的真实原神数据**需要查 `scripts/convert_roboflow_to_yolo.py` 和 `scripts/collect_genshin_data.py`。
4. **端到端 live 跑通证据** —— `runs/aurorabench_phase8_final_audit/` 全是 testbed 数据，**没有"真实原神窗口下 N 章节主线自动跑通"的报告**。

---

### 2.2 维度 B：自然语言长程任务

#### 已实现

- `app_service/universal_entry_agent.py`（172 行）—— 接收 `process(text, game_id)` → 返回 `ExecutionPlan`
- 7 个 goal type 模板：daily / quest / combat / explore / upgrade / dialog / navigation
- Protocol 抽象（`GoalParser`、`MissionBuilder`）允许外部注入 LLM

#### 严重不达

**核心问题：没有 LLM**。`app_service/universal_entry_agent.py:87-107` `_parse_intent()` 实现：

```python
def _parse_intent(self, text: str, game_id: str) -> ParsedIntent:
    text_lower = text.lower()
    goal_type = "custom"
    best_score = 0
    for gtype, keywords in _GOAL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            goal_type = gtype
    confidence = min(0.5 + best_score * 0.2, 1.0) if best_score > 0 else 0.3
    return ParsedIntent(goal_type=goal_type, game_id=game_id, raw_text=text, parameters=(), confidence=confidence)
```

这是**纯字符串匹配**，没有：
- ❌ 实体抽取（"璃月港"、"风龙废墟"、"5 个烤鱼"全抓不到）
- ❌ 参数解析（数字、物品名、地名全部丢失）
- ❌ 意图消歧（"升级"是角色升级还是武器升级？）
- ❌ 多步任务组合（"先去 A 再去 B" 拆不开）
- ❌ 上下文记忆（多轮对话）
- ❌ 任何 LLM 调用

CLAUDE.md 自述：
> "UniversalEntryAgent — Natural language intent → executable mission graph. Parses goals (daily, combat, explore, quest, etc.) in English/Chinese."

**事实**：**只解析 goal type（7 个）**，**不生成 mission graph**（只生成 5 步 hardcoded template，line 115-153），**不解析 parameters**。`process()` 返回的 `ExecutionPlan` 是**预制模板，不是 mission graph**。

CLAUDE.md 说的是"mission graph"，实际是"5 步 dictionary 列表"。

#### 关键 gap

1. **缺 LLM 接入** —— 这是最大的 gap。如果要"自然语言长程任务"，必须接 LLM（智谱/Claude/MiniMax 等），并实现：
   - Intent classification
   - Entity extraction（game-specific 词典或 NER）
   - Parameter binding
   - Multi-step planning（chain 任务）
   - State carry-over（多轮对话）
2. **缺任务图生成** —— 当前 ExecutionPlan 5 步是 hardcoded。要做"去璃月港买 5 个烤鱼"需要动态生成路线图（teleport → walk to NPC → open shop → buy 5 → close）
3. **缺跨 session 状态延续** —— `quest_context_persistence.py`(11KB) 存在，但跟 UniversalEntryAgent 怎么对接需要确认
4. **缺意图消歧确认** —— 当 LLM 信心度低时，应回问用户。当前直接 `confidence=0.3` 强行执行会失败

---

### 2.3 维度 C：多游戏兼容

#### 已实现

- `capsules/capsule_protocol.py`(7KB) —— Capsule 安装/激活/去激活生命周期
- `capsules/capsule_registry.py`(14KB) —— 清单注册表
- `capsules/domain_protocols.py`(4.5KB) —— ScreenClassifier、CombatPlanner、Navigator、DialogHandler、KnowledgeProvider 五个 game-agnostic 接口
- `capsules/hsr/` 跟 `capsules/genshin/` 结构对称
- `capsules/demo_arpg/`、`capsules/desktop_ui/` 存在（前者是 dummy 模板）
- `capsules/my_game/`（用户自己的测试 capsule）

#### 严重不达

**CapsuleForge 是空壳**。`app_service/capsule_forge.py:188-209`：

```python
def _write_screen_classifier(self, path, game_id, game_description=""):
    pascal = _pascal(game_id)
    llm_code = ""
    if self._llm is not None:
        try:
            llm_code = self._llm.generate(...)
        except Exception as exc:
            log.warning("[CapsuleForge] LLM generation failed: %s", exc)
    if llm_code and len(llm_code) > 50:
        path.write_text(llm_code, encoding="utf-8")
    else:
        path.write_text(_SCREEN_CLASSIFIER_TEMPLATE.format(...), encoding="utf-8")
```

**StubLlmBackend**（line 39-43）：

```python
class StubLlmBackend:
    def generate(self, prompt: str) -> str:
        return ""
```

永远返回空字符串，触发 `if llm_code and len(llm_code) > 50` 失败，走**模板路径**。模板内容（line 230-255）：

```python
_SCREEN_CLASSIFIER_TEMPLATE = '''class {Pascal}ScreenClassifier:
    STATES = ("loading_screen", "overworld", "dialog", "menu", "combat", "map", "black_screen", "unknown")
    def classify(self, frame: Any) -> str:
        return "unknown"  # ← 永远返回 unknown
'''
```

**生成的 screen classifier 永远 `return "unknown"`**。战斗检测器永远返回 `CombatDetection()`（全部默认值）。Provider 是空架子，activate 时连 import 都用不存在的相对模块名（line 296-297 `from {game_id}_screen_classifier import` —— 这是模板占位符，根本跑不起来）。

CLAUDE.md 自述：
> "CapsuleForge — Auto-generates capsule skeletons (capsule.yaml, keymap.yaml, skills/index.json, screen classifier, combat detector, provider) from game descriptions. LLM-driven code generation for 6 output files."

**事实**：
- 默认走 stub 路径（无 LLM）
- 生成的 6 个文件**全部是模板占位符**，**没有任何游戏特定逻辑**
- keymap 永远是 hardcoded WASD（line 138-155）
- skill index 永远是 3 个 generic basic skill（line 158-186）
- Provider 里 `from {game_id}_screen_classifier import` 是模板字符串，**根本 import 不了**

**结论**：**CapsuleForge 不能用于真实多游戏扩展**。它生成的代码**永远 `return unknown`**，必须人工重写才能用。

#### 关键 gap

1. **CapsuleForge 需要重写** —— LLM 必须真接入（用智谱/MiniMax），且生成的代码必须能跑（修 import 路径、加 class 模板占位的实际类名替换、加 game-specific 提示词）
2. **HSR capsule 实际深度不明** —— `hsr_game_capsule.py` 8.5KB，`hsr/providers.py` 10KB。结构对称但内容是否真在跑需要查
3. **Combat/Navigation 内部硬编码** —— `combat/combat_skill_adapter.py`(26KB)、`navigation/special_movement.py`(23KB) 内部大量 genshin 语义。多游戏切换时这些 adapter 怎么降级/替换需要明确
4. **缺 Capsule 接口的统一执行时** —— 4 个 capsule（genshin、hsr、demo_arpg、desktop_ui）能否同时加载？优先级？热切换？

---

### 2.4 维度 D：崭新游戏自主探索和通关

#### 已实现

- `agent_kernel/unknown_scene_handler.py`（CLAUDE.md 提到，但**未深读**）
- `learning/meta_learning_bridge.py`（CLAUDE.md 提到）
- `learning/parameterized_skill_induction.py`（CLAUDE.md 提到）
- `learning/game_knowledge_store.py`(20KB) —— SQLite 知识库 + 指数衰减遗忘
- `learning/generic_failure_analyzer.py`（CLAUDE.md 提到）
- `bagel/belief_proposer.py`（CLAUDE.md 提到）

#### 严重不达

**认知闭环是软链接**。`agent_kernel/loop.py:319-335`：

```python
if self._meta_learning_bridge is not None:
    try:
        from bagel.belief_proposer import classify_failure_mode
        mode = classify_failure_mode(receipt.status)
        self._meta_learning_bridge.on_exploration_result(...)
    except Exception as exc:
        log.debug("[Kernel] Meta-learning bridge failure report: %s", exc)
```

**任何 import 失败、任何异常**，只 `log.debug` 不报错。**这意味着 BAGEL→learning 链路在生产环境可能根本不工作**，但因为是软链接，看不出来。

CLAUDE.md 自述：
> "The system implements a full autonomous learning cycle: UnknownSceneHandler.probe() → MetaLearningBridge → DecisionMemory → ParameterizedSkillInductor"

**事实**：
- 链路代码**真实存在**（多个文件）
- 但**端到端跑通真实游戏的证据没有** —— benchmark 全在 testbed 里
- `learning/evolution_engine.py`(20KB)、`learning/game_knowledge_store.py`(20KB) 等**代码深度足够**，但**没有"在真实游戏里归纳出有用 skill"的报告**

#### 关键 gap

1. **缺真实游戏接入的认知闭环证据** —— 必须在真实原神（或授权 ARPG）里跑 N 小时，产出"自主探查 → 归纳 skill → 复用通关"的可观察数据
2. **UnknownSceneHandler 实际能力** —— "Observe→Hypothesize→Probe→Verify→Attribute→Learn→Escalate"（CLAUDE.md 自述）的 7 步链路在 `agent_kernel/unknown_scene_handler.py` 真实实现程度需要查
3. **ParameterizedSkillInductor 触发条件** —— CLAUDE.md 说"3+ 失败模式自动归纳"，但**3 个失败模式怎么定义、归纳出来的 skill 怎么验证、错误的归纳怎么回滚**需要查
4. **KnowledgeStore 衰减遗忘实测** —— `conf × exp(-age×ln2/half_life) × access_reinforcement`（CLAUDE.md）公式真实存在，但**真实使用中知识库命中率、衰减是否合理**没有数据
5. **CapsuleForge + UnknownSceneHandler 联动** —— 对"崭新游戏"，应该先用 CapsuleForge 探查生成骨架，再用 UnknownSceneHandler 自主探索。当前**两者没看到联动证据**

---

## 3. 跨维度架构性问题

### 3.1 架构层

**5-Plane 实际边界** —— 表面完整。`core/state_bus.py`、各平面目录（perception、control、execution、orchestration、telemetry）齐全。**但实操中跨平面直接调用可能存在**（如 `execution/ui_flow_skill_adapter.py` 45KB 直接 import 了 navigation 模块，违反 CLAUDE.md 强调的"必须经过 StateBus"）。

**AgentLoop L0-L9 是否真在跑** —— L0-L4 看到证据（L132-149 启动 100Hz 拦截线程、50Hz 战斗反射线程；L230-238 Cerebrum 5s throttle），**L5-L9 的实际触发频率、是否真在主循环里跑、还是只在 tick 间接到调用**需要细查 loop.py 后 500 行。

**Capsule 解耦程度** —— Capsule 协议抽象是好的（`domain_protocols.py` 5 个 Protocol），但**Combat / Navigation / Perception 内部的 game-specific 硬编码多**。要让第二款游戏复用同一套 Combat/Navigation，**需要把这些 adapter 拆成 game-agnostic core + game-specific plugin**。

**BAGEL 认知闭环端到端跑过吗** —— 软集成（try/except），没有强证据。**这是"P0 缺口"**。

### 3.2 安全/可靠性

**claim-gated 端到端通了吗** —— `agent_kernel/loop.py:300` 真调 `adjudicate_delta`，但**没有看到 end-to-end 真实原神跑通的 report**。`runs/aurorabench_phase8_final_audit/ui_safety_5e228e5ab911_report.md` 测的是通用 button，不是真实原神。

**deadman switch 真在跑吗** —— `execution/` 目录有 `safe_window_backend.py`(34KB)、`directinput_backend.py`(19KB)、`background_input_backend.py`(17KB) 等。**lease → release_all 的链路代码存在**，**F9/Ctrl+C/SIGTERM/watchdog 触发链路**需要查。

**dry-run 是默认的吗** —— CLAUDE.md 自述默认 `ConsoleInputBackend`。`execution/console_input_backend.py` 是否存在、是否真默认走 dry-run、SafeWindowBackend 必须显式选择——CLAUDE.md 写了，但**生产环境怎么强制默认 dry-run**需要看 `app_service/launcher.py`(12KB)。

### 3.3 测试覆盖

**声称 4323，实际 4342（pytest collect）** —— 大致准确。
**mock 测试占比** —— 抽查 benchmark 报告都是 mock 数据。需要 grep `Mock` 在 tests/ 里的密度。
**集成测试 vs 单元测试比例** —— 未统计。
**真实原神 live test** —— 没看到（`scripts/run_chaos_recovery_test.py` 16KB 等可能是 live test，但需要查）。

### 3.4 性能/资源

**VLM 调用频率** —— `live_factory.py` 提到 ZhipuVLM，但**真实调用频率、是否降采样、GPU/CPU 资源**没看到 benchmark。
**单 tick 延迟** —— benchmark 报告 0ms 是 testbed 数据，**真实延迟**没数据。
**本地推理硬件门槛** —— 至少需要 DXcam、YOLO、智谱 VLM API（云端）、可能的本地 VLM。**CLAUDE.md 没说最低硬件**。

### 3.5 工程化

**配置管理** —— `configs/` 7 个 YAML（CLAUDE.md 提到）。看上去完整。
**状态持久化** —— `persistence/` 目录、`quest_context_persistence.py`(11KB)、`reliability/reliability_store.py`(26KB)。
**错误恢复** —— `execution/crash_recovery.py` 在 mainline_live_bridge import 列表里（line 9）。
**日志/可观测性** —— `telemetry/` 目录、`logs/` 目录、CLAUDE.md 提 JSONL + NVENC 录制。

---

## 4. 长期多阶段改进方案

> **说明**：以下阶段按"愿景对齐"和"工程可执行"双轴排序。**P0 = 必须先做**，**P1-P3 = 后续推进**。每阶段给出目标、交付物、任务清单、工期、风险、验证标准、对应愿景维度。
>
> 假设团队规模：**1 个资深全栈（python 内核 + 端到端管线）** + **1 个 ML 工程师（VLM/YOLO 训练 + 评估）**。

---

### 阶段 0：地基修缮（让声称与现实对齐）

**目标**：把"CLAUDE.md / 文档自我描述"和"代码实际状态"对齐，消除最大的"声明-现实 gap"，让项目后续有人接手时不会被误导。

**工期**：4-6 周（单人加班可压到 3 周）

**关键交付物**：

1. **CLAUDE.md 重写** —— 区分"已实现"和"已规划"，所有声明加证据（文件:行号）
2. **审计报告 + 跟踪 issue** —— 把 §2、§3 列出的每个 gap 转成 GitHub issue，标 P0/P1/P2/P3
3. **核心模块真实状态表** —— 一张 markdown 表格，每个模块三列："声称"、"实际"、"差距"
4. **UniversalEntryAgent LLM 化（最小版本）** —— 接 MiniMax/智谱 API，至少支持 5 个高优意图（daily、combat、quest、navigation、explore）
5. **CapsuleForge 模板修复** —— 修 import 路径、Provider 类名替换、classify() 默认行为

**任务清单**：

- [ ] 重写 `CLAUDE.md`，每个能力声明后面加 `[已实现/规划中/部分实现]` 标签
- [ ] 在 `docs/AUDIT_2026_06_02.md` 落地本审查报告
- [ ] 把 gap 转成 issue：CLAUDE.md 与代码不符的所有点
- [ ] 在 `app_service/universal_entry_agent.py` 加 LLM 后端，配置开关 `entry_use_llm: bool = False` 默认关但可开
- [ ] 修 `app_service/capsule_forge.py:188-209` 模板：
  - Provider 改用绝对 import（`from capsules.{game_id}.detectors...`）
  - 默认 screen_classifier 至少返回 VLM 调用而非永远 "unknown"
  - keymap 改成从 LLM 推断（如果 LLM 可用）or 强制要求用户填
- [ ] 修 `app_service/universal_entry_agent.py:111-153` ExecutionPlan：至少把 hardcoded 5 步模板换成"LLM 生成的 1-N 步 graph"或显式声明"仅做 intent classification，不生成 plan"
- [ ] 给 `agent_kernel/loop.py:319-335` 的 try/except 改成可配置 strict 模式：strict 模式下 BAGEL/learning 失败必须 throw，便于排错
- [ ] 加测试覆盖：CLAUDE.md 每条声明对应一个"声明-实现一致性测试"（自检脚本）

**风险**：
- 重写 CLAUDE.md 可能让现有协作者困惑 → 用"v0.5 现状"和"v1.0 目标"两段式
- LLM 化会引入外部 API 依赖 → 默认关、用环境变量开

**验证标准**：
- 一个新人读 CLAUDE.md，**能准确知道哪些能跑、哪些在跑通、哪些没做**
- 跑通一个 demo：`python -c "from app_service.universal_entry_agent import UniversalEntryAgent; uea = UniversalEntryAgent(llm_backend=...); print(uea.process('去蒙德城打 5 个丘丘人'))"` 输出**带参 ExecutionPlan**

**对应愿景**：B（自然语言）、C（多游戏）

---

### 阶段 1：原神首章主线跑通（最小可行自主通关）

**目标**：在真实原神游戏窗口下，agent 能从新号开始，自动完成蒙德章节的某一段主线（例如"风龙废墟"或"蒙德城到璃月港"中的一段），端到端跑通。

**工期**：8-12 周

**关键交付物**：

1. **真实原神主线条目化的 MissionGraphV4 实例** —— 至少 3-5 个蒙德主线节点
2. **真实 VLM 接入** —— 智谱 GLM-4V 或 Claude Sonnet Vision，端到端延迟 <2s
3. **真实 YOLO 权重** —— 至少原神界面关键元素（角色 HP 条、怪物、小地图任务标记、菜单按钮）
4. **真实 live 跑通报告** —— `runs/genshin_mainline_2026_xx_xx/` 包含视频+JSONL+任务通过率
5. **失败恢复** —— 真实场景下的"对话卡住"、"战斗失败"、"过场动画未跳过"等 5+ 失败模式，每种有 recovery 路径

**任务清单**：

- [ ] 选一段蒙德主线（建议"风龙废墟"或"蒙德城找凯瑟琳"，相对短且不卡等级）
- [ ] 拆解成 MissionGraphV4 节点：open_quest_log → select_quest → teleport_to_waypoint → walk_to_marker → enter_dungeon → defeat_boss → claim_reward → return_to_npc
- [ ] 每个节点的 input_claim + output_claim 精确定义（基于视觉特征：HP 满、任务标记可见、对话选项出现等）
- [ ] 训练 YOLO：原神 UI 元素检测（HP 条、对话框、任务标记、菜单按钮、敌人轮廓），用 Roboflow 数据 + `scripts/convert_roboflow_to_yolo.py`
- [ ] 接智谱 GLM-4V（API key 配到环境变量），做 screen state 分类（overworld、combat、dialog、menu、map、loading、cutscene）
- [ ] 在 `agent_kernel/live_factory.py` 接通真实 capture + VLM + YOLO 链路
- [ ] 跑通第一个端到端：蒙德某一段主线，自动跑 30-60 分钟，产出视频+JSONL
- [ ] 记录 5+ 失败模式 + 恢复路径
- [ ] 写 `docs/GENSHIN_MAINLINE_ACTUAL_STATUS.md` 真实状态

**风险**：
- 智谱 VLM 限流 → 加 retry + 降级到本地小 VLM（如 Llava-1.6 7B）
- 原神更新版本 → 接 `runtime/content_versioning.py` 检测版本变化并告警
- YOLO 误检率高 → 改用 VLM 直接做 screen state 分类（YOLO 只做"危险区域红光红圈"检测）

**验证标准**：
- 视频证据：录制一段 30 分钟连续画面，agent 自动完成蒙德某段主线
- JSONL 证据：所有动作、claim 验证、recovery 触发都有时间戳
- **5 次连跑，4 次以上成功**

**对应愿景**：A（自主通关原神）

---

### 阶段 2：自然语言长程任务体系化

**目标**：用户用自然语言下指令，agent 能端到端完成"先去 A 然后 B 再 C"这种复合长程任务。

**工期**：6-8 周

**关键交付物**：

1. **LLM-powered 意图解析** —— UniversalEntryAgent 真接 LLM，支持：
   - 意图分类（10+ 类型）
   - 实体抽取（角色名、地点、物品、数量、敌人类型）
   - 参数 binding
   - 多步任务分解
2. **任务图生成** —— LLM 接收意图 + 上下文 → 输出 MissionGraphV4 JSON
3. **跨 session 状态延续** —— quest_context_persistence + persona memory
4. **20+ 高频自然语言指令测试集** —— 中文/英文混合，验证意图解析

**任务清单**：

- [ ] 在 `app_service/universal_entry_agent.py` 重写为 LLM-first：
  - 接收 `text` → LLM 提取 `{intent, entities, steps, requires_combat/nav/dialog, confidence}`
  - 落空/低信心时回问用户
  - 支持 multi-step（"先去 A 再 B 再 C"）
- [ ] 任务图生成：LLM 接收意图 → 输出 MissionGraphV4 JSON（节点、input_claim、output_claim、fallback）
- [ ] 加 `app_service/natural_language_testset.yaml` 20+ 指令
- [ ] Persona memory：用户偏好（爱用哪个角色、习惯什么战斗风格）持久化到 `persistence/`
- [ ] 跨 session：上次任务中断后，下次启动自动恢复

**风险**：
- LLM 误解析 → 加"执行前向用户确认"环节
- 任务图生成质量 → 加 validation（节点可达性、claim 可验证性）

**验证标准**：
- 20 条自然语言指令，**至少 18 条被正确解析并执行**
- 多步任务（"先去蒙德找凯瑟琳，然后去璃月买 5 个烤鱼"）正确分解

**对应愿景**：B（自然语言长程任务）

---

### 阶段 3：第二款游戏接入（验证多游戏兼容）

**目标**：把 HSR capsule 推到能端到端跑通，或者选一款授权开源 ARPG。

**工期**：8-10 周

**关键交付物**：

1. **HSR capsule 补全** —— 把 `capsules/hsr/` 推到 genshin 现有水平 + 真实 HSR live 跑通
2. **多游戏切换 demo** —— 同一套内核，从 genshin capsule 切到 hsr capsule，平滑过渡
3. **Combat/Navigation 适配器重构** —— 把 game-specific 硬编码抽到 game-agnostic core + plugin
4. **CapsuleForge 实战化** —— 用 forge 流程为 HSR 生成骨架，人工微调后能跑

**任务清单**：

- [ ] 重构 `combat/combat_skill_adapter.py`：把 genshin 特有的元素反应、角色切换抽到 `combat/genshin/` 子目录，core 留 game-agnostic 接口
- [ ] 重构 `navigation/`：拆 `navigation/genshin/`、`navigation/core/`
- [ ] HSR 真实数据采集：用 `scripts/collect_genshin_data.py` 改写成 `collect_hsr_data.py`
- [ ] HSR YOLO 训练：界面元素（角色、敌人、菜单、行动顺序）
- [ ] HSR VLM 适配：screen state 词汇（overworld、turn_based_combat、menu 等）
- [ ] HSR MissionGraphV4 实例：至少 1 个完整任务（"通关忘却之庭 1-3" 或"完成 1 个每日实训"）
- [ ] 跑通端到端

**风险**：
- HSR 是回合制，跟原神 ACT 差异大 → Combat planner 抽象要重做
- 项目缺少 HSR 玩家，可能需要找测试者

**验证标准**：
- HSR capsule 端到端跑通至少 1 个完整任务
- capsule 热切换 demo：从原神退出后，能在 5 分钟内启动 HSR 并开始任务

**对应愿景**：C（多游戏兼容）

---

### 阶段 4：认知闭环实战化（自主探索核心）

**目标**：在 unknown_scene_handler + meta_learning_bridge + parameterized_skill_induction 真实跑通过程中，能产生可观察的"自主归纳 skill"证据。

**工期**：8-12 周

**关键交付物**：

1. **真实游戏里的未知场景探查** —— `testbed/` 之外，至少在 1 款授权 ARPG 里跑
2. **技能归纳实测** —— 3+ 失败模式 → 归纳出可用 skill → 复用
3. **BAGEL 归因真实记录** —— 真实失败 → 信念节点 → 替代假设 → 恢复路径
4. **KnowledgeStore 衰减效果实测** —— 长期运行后知识库命中率、衰减是否合理

**任务清单**：

- [ ] 选 1 款授权 ARPG（建议开源 Unity 像素 ARPG 或自己做的 Godot 测试场景）
- [ ] 把 `agent_kernel/loop.py:319-335` 改成 strict 模式（失败 throw），先暴露 BAGEL→learning 真实连通性
- [ ] 实测 UnknownSceneHandler：故意给"陌生 UI"任务，看 7 步链路（Observe→Hypothesize→Probe→Verify→Attribute→Learn→Escalate）真实触发
- [ ] 实测 ParameterizedSkillInductor：人为构造 5+ 失败模式，看归纳出的 skill 是否真的能复用
- [ ] 实测 KnowledgeStore：跑 24 小时，看遗忘曲线是否合理、prune_decayed 是否健康
- [ ] 写 `docs/COGNITIVE_CLOSURE_REALITY.md` 真实报告

**风险**：
- 认知闭环端到端跑通难度高，可能需要先小步拆解
- KnowledgeStore 设计是否合理需要长期验证

**验证标准**：
- 1 款从未见过的 ARPG，agent 在 2 小时内发现基本玩法机制（移动、攻击、开菜单）
- 真实"3 失败 → 归纳 skill → 复用"案例 ≥3 个

**对应愿景**：D（崭新游戏自主探索）

---

### 阶段 5：泛化与产品化

**目标**：用户描述一个新游戏，capsule 骨架 + 探索就能跑出基本玩法。

**工期**：10-15 周

**关键交付物**：

1. **CapsuleForge 实战化** —— 真接 LLM，生成的代码能跑
2. **Tauri + React GUI** —— 用户可视化操作：自然语言输入、视频回放、persona 交互
3. **Companion UX** —— Live2D/语音气泡、情绪化表达
4. **Open Beta** —— 小范围招募玩家测试

**任务清单**：

- [ ] CapsuleForge 接 LLM（用智谱/MiniMax），生成的 screen_classifier 至少有 VLM 调用 fallback
- [ ] CapsuleForge 生成的代码自动 import 修对、跑通基础 classify
- [ ] Tauri + React 前端：自然语言输入框、视频回放、persona 气泡
- [ ] Voice/TTS 集成
- [ ] 写 `docs/OPEN_BETA.md`（CLAUDE.md 提到但我要确认是否落地）

**风险**：
- GUI 工作量大，可考虑先 CLI/GUI 混合
- Tauri+React 跨平台问题（Windows / Mac / Linux）

**验证标准**：
- 用户给一段新游戏描述，capsule 在 30 分钟内生成可运行骨架
- GUI 可用，能看视频回放 + 输入自然语言

**对应愿景**：B、C、D 全维度

---

### 阶段 6：长程记忆与玩家模型

**目标**：agent 跟用户长期互动，能积累玩家偏好、行为模式、个性化响应。

**工期**：6-8 周

**关键交付物**：

1. **Player Persona 模型** —— 玩家偏好、习惯、风格
2. **Long-term Memory** —— 跨 session、跨任务的状态延续
3. **情感化响应** —— 失败时的语音、成功的鼓励

**任务清单**：

- [ ] Player persona：`persona/` 目录（CLAUDE.md 提到）+ `app_service/genshin_persona.py` 已存在(8.5KB)，补全
- [ ] Long-term memory：`persistence/` + `knowledge/online_guide_system.py`(25KB) 已存在，扩展
- [ ] Voice/TTS 集成：`voice/` 目录

**验证标准**：
- 跑 1 个月，看 persona 是否有学习效果
- 玩家偏好（爱用角色、战斗风格）能被 agent 利用

**对应愿景**：A、B 深度化

---

## 5. 关键建议（8 条最重要）

1. **立刻重写 CLAUDE.md**（阶段 0 关键任务）—— 当前文档"自我营销"过重，会误导后续接手者。**CLAUDE.md 应该是一份"功能 + 证据"清单**，不是产品宣传。

2. **把"UniversalEntryAgent 不用 LLM"和"CapsuleForge 永远 return unknown"显式声明** —— 不然会持续误导。如果决定"暂时不接 LLM"，就在 CLAUDE.md 写明"暂未接入"。

3. **把 benchmark 报告加环境标签** —— 当前 `runs/aurorabench_phase8_final_audit/` 5 份报告 timing 全 0ms，新人看了会以为系统性能完美。**报告应该显式标 `[TESTBED_RUN]` 或 `[LIVE_RUN]`**。

4. **阶段 1（真实原神首章主线）是最关键的验证节点** —— 架构再完美，**只要不能真跑通一段真实原神主线，整个项目的可信度都是 0**。阶段 1 必须用真实窗口 + 真实 VLM + 真实 YOLO 端到端跑通。

5. **BAGEL 认知闭环必须从"软集成"升级为"强约束"** —— `agent_kernel/loop.py:319-335` 的 try/except 包装是好心办坏事，让链路在失败时静默。改成可配置 strict 模式。

6. **优先把"声明-现实一致性测试"自动化** —— 写一个 `tests/test_claims_consistency.py`，扫描 CLAUDE.md 里每个能力声明，验证对应代码存在并能 import。

7. **引入"里程碑定义"（Definition of Done）** —— 每个能力要能列：
   - 输入是什么？
   - 输出是什么？
   - 怎么验证？（截图/视频/JSONL）
   - 失败怎么恢复？
   
   没有 DoD 的能力都是"哲学宣称"。

8. **考虑引入"减法思维"** —— 当前 685 个文件、13.7 万行代码，**有些模块可能过度设计**（如 L6-L9 meta-learning 9 层，如果阶段 4 不能验证就直接砍）。在阶段 4 之前，**L7-L9 可以暂时 disable**，把复杂度压到能跑通阶段 1。

---

## 6. 附录

### 6.1 必读文档清单（已读 + 建议读）

- ✅ `CLAUDE.md`（项目主入口，247 行）
- ✅ `PROJECT_ALIGNMENT.md`（产品哲学宪法，97 行）
- ✅ 5 份 phase8 final audit 报告
- 📖 建议读：`docs/GENSHIN_AUTONOMOUS_COMPLETION_CAPABILITY_CHECKLIST.md`（71KB，对标愿景的核心文档）
- 📖 建议读：`docs/MVP_REALITY_AUDIT.md`（官方自己承认的 gap）
- 📖 建议读：`docs/AURORA_REALITY_LADDER_AND_MOAT.md`（商业化路线 + 现实差距）
- 📖 建议读：`docs/GENSHIN_CAPABILITY_GAP_ANALYSIS.md`（能力差距分析）
- 📖 建议读：`docs/GENSHIN_MAINLINE_PROGRESSION_CHAIN.md`（主线节点拆分，70KB）
- 📖 建议读：`docs/GAP_LIST.md`、`docs/P0_P1_P2_CLOSURE_REPORT.md`、`docs/FINAL_AUDIT_REPORT.md`

### 6.2 必查代码文件清单（已查 + 建议查）

- ✅ `CLAUDE.md`、`PROJECT_ALIGNMENT.md`
- ✅ `agent_kernel/loop.py`（821 行，L0-L9 主循环）
- ✅ `agent_kernel/live_factory.py`（首 100 行）
- ✅ `app_service/universal_entry_agent.py`（172 行全部）
- ✅ `app_service/capsule_forge.py`（312 行全部）
- ✅ `capsules/genshin/capsule.yaml`（192 行全部）
- ✅ `capsules/genshin/genshin_game_capsule.py`（299 行全部）
- ✅ `planning/mainline/mission_graph_v4.py`（首 80 行）
- ✅ `planning/mainline/mainline_live_bridge.py`（首 80 行）
- 📖 建议查：`planning/mainline/mainline_runner.py`（37KB，核心）
- 📖 建议查：`bagel/runtime.py`、`bagel/fig_schema.py`、`bagel/belief_proposer.py`（BAGEL 信念系统）
- 📖 建议查：`learning/meta_learning_bridge.py`、`learning/parameterized_skill_induction.py`、`learning/game_knowledge_store.py`
- 📖 建议查：`agent_kernel/unknown_scene_handler.py`（自主探索核心）
- 📖 建议查：`combat/`、`navigation/`、`perception/` 几个关键 adapter
- 📖 建议查：`runtime/claim_runtime.py`（47KB，claim 系统核心）
- 📖 建议查：`execution/execution_runtime.py`（CLAUDE.md 提到）

### 6.3 必跑测试命令清单

```bash
# 1. 收集测试规模
cd D:\Aurora\vision_agent_kernel_v0_5
python -m pytest --collect-only -q
# 期望输出：4342 tests collected

# 2. 跑全部测试
python -m pytest -x --tb=short 2>&1 | tail -50

# 3. 跑核心模块测试
python -m pytest tests/test_state_bus.py tests/test_claim_runtime.py -v

# 4. 跑 benchmark（testbed，注意是 mock 数据）
python scripts/run_aurorabench.py

# 5. 真实原神 live 跑（如果已配 VLM API key）
python scripts/launch_real_game.py
python scripts/run_mainline.py
```

### 6.4 关键数字汇总

| 指标 | 数值 | 备注 |
|---|---|---|
| 非测试 .py 文件数 | 685 | 大型项目 |
| 非测试代码行数 | ~13.7 万 | 健康 |
| 测试规模 | 4342 tests | CLAUDE.md 写 4323，差 19 |
| TODO 标记 | 1 | 极低 |
| FIXME/XXX | 0 | 极低 |
| NotImplementedError | 2 | 极低 |
| bare pass（占位） | 142 | 需分类（多数是 Protocol 空实现，合理） |
| capsules 数量 | 5（genshin/hsr/demo_arpg/desktop_ui/my_game） | 4 真 + 1 用户测试 |
| mainline 模块文件数 | 11 | 完整 |
| docs 大文件 | 50+ | 大量 spec/plan |

---

## 7. 总结

**Sparkle 项目的真实状态**：

- **架构/管道层（80% 完整）**：5-Plane、L0-L9、MissionGraphV4、BAGEL、Combat、Navigation、Perception、Learning、Sentinel 全部有真实代码，13.7 万行非 stub
- **真实游戏接入（5% 完成度）**：mainline_live_bridge 真接原神窗口，但**没有任何"真实原神 N 章节自动跑通"的视频/JSONL 证据**
- **自然语言接口（10% 完成度）**：UniversalEntryAgent 是关键词匹配 + 模板，**没有 LLM 接入**
- **多游戏扩展（5% 完成度）**：Capsule 协议抽象好，但 CapsuleForge 永远 return unknown，HSR capsule 是结构孪生
- **认知闭环（20% 完成度）**：链路代码存在，但 try/except 软集成，端到端跑通证据缺失
- **自我描述偏差（高风险）**：CLAUDE.md 把项目说得像 80% 完成，实际可能 25-30%

**最关键的判断**：

这是一个**架构品味非常高、哲学完整度高、代码体量可观**的项目。**不是"骗局"项目**（没有大量 TODO/NotImpl/FIXME 装样子），**但也不是"接近完成"项目**（CLAUDE.md 给出的乐观感过度）。

**从"CLAUDE.md 描述"到"实际能跑通一段真实原神主线"**，需要：

1. 阶段 0 修 CLAUDE.md 和最小化 LLM 接入（4-6 周）
2. 阶段 1 跑通真实蒙德首章主线（8-12 周）
3. 阶段 2-6 渐进推进

**总工期估计**：**40-60 周（10-15 个月）单人**，**如果是 1 全栈 + 1 ML 两人协作可以压到 25-35 周**。

**最关键的一句话**：

> **不要再相信 CLAUDE.md 给的乐观感，**用"代码 + 视频证据"作为唯一标准**。每个能力的 DoD 必须包含"真实场景视频 + JSONL 时间戳"，否则就是"哲学宣称"。**

---

*报告完*
