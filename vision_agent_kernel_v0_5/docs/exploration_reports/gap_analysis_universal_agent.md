# 通用游戏 Agent 差距分析：从当前代码库到"说一句'玩 GTA'就能自主游戏"

**日期**: 2026-06-02
**目标**: 用户说 "玩 GTA" → Agent 自主搜索知识 → 创建 capsule → 自动校准 → 探索机制 → 沉淀技能 → 生成适配代码 → 热重载
**当前状态**: 综合评分 6/10，架构骨架完整，关键认知闭环未打通，实现严重偏向原神

---

## 一、架构差距矩阵

| 能力维度 | 需求级别 | 当前状态 | 差距严重度 | 备注 |
|---------|---------|---------|-----------|------|
| **联网搜索与知识获取** | CRITICAL | MOCK | 90% | OnlineGuideSearcher 仅 mock，GuideExtractor 仅中文/原神正则 |
| **内部 Coding Agent** | CRITICAL | NONE | 100% | 无代码生成管线，SandboxValidator 只验证 task spec |
| **增强包自动生成** | CRITICAL | NONE | 100% | 4 个 capsule 全手写，CapsuleManifest YAML 就绪但零自动填充 |
| **热重载/热替换** | HIGH | WEAK | 60% | Pipeline 支持 add/remove post_processor，capsule 有生命周期但无原子替换 |
| **通用感知** | HIGH | LOW | 80% | 70+ 感知文件中 ~65 个原神专用，仅 VLM 和 OCR 是通用的 |
| **通用战斗** | HIGH | LOW | 80% | CombatPlannerProtocol 存在但所有实现都是原神专用 |
| **通用导航** | HIGH | LOW | 80% | NavigatorProtocol 存在但仅 GenshinNavigator + HSRNavigator |
| **安全沙盒** | MEDIUM | STRONG | 20% | 输入安全、InputLease、human-override 完善，缺代码执行沙盒 |
| **元学习闭环** | HIGH | BROKEN | 70% | BAGEL + Learning 系统各自完整但不连接 |
| **Skill 泛化** | HIGH | STUB | 85% | 归纳出的 skill 是固定序列，无参数化/条件分支/循环 |

---

## 二、核心架构洞察

### 洞察 1: 最大差距不是"缺少模块"而是"缺少泛化"

代码库已具备通用游戏 Agent 所需的几乎所有机制：
- Capsule 生命周期（注册/安装/激活/停用/卸载）✅
- Skill 晋升阶梯（raw_trace → trusted 6 级）✅
- Claim 验证系统 ✅
- BAGEL 信念归因 ✅
- 安全探索循环（SPARKLE §11）✅
- 失败修复飞轮（EvolutionEngine）✅

但实现严重偏向原神。差距是"参数化"而非"构建"。

### 洞察 2: CapsuleManifest 是关键设计杠杆

`capsules/capsule_protocol.py` 的 CapsuleManifest 已声明 keymaps、detectors、skills、providers、ui_anchors、transitions、resources。CapsuleForge 只需自动填充这些字段。YAML manifest + 代码生成是正确架构。

### 洞察 3: PerceptionPipeline 已具备热重载接口

`perception/pipeline.py` 有 `add_post_processor()` 和 `remove_post_processor()`。HotReloadManager 只需原子调用这两个方法 + rollback。

### 洞察 4: BAGEL 和 Learning 系统无需修改即可通用

FIG schema（13 种状态，4 种节点，9 种边）、归因循环、Skill 晋升、修复管道、进化引擎全是游戏无关的。

### 洞察 5: ZeroShotAgent 证明闭环可行

`agent/zero_shot_agent.py` 已演示 capture → VLM → LLM → execute 循环。瓶颈是 keymaps 硬编码在第 21-36 行。参数化为从 capsule manifest 加载是最小可行变更。

---

## 三、五大认知鸿沟（与之前评估一致，此处细化到代码级别）

### 鸿沟 1: 信念生成 → 假设驱动探索

**现状**: `agent_kernel/unknown_scene_handler.py:94-118` — 每 affordance 一个假设，无组合推理
**缺失**: `BeliefProposer` 模块 — 分析证伪证据 → 提出 1-3 个结构化替代假设 → 注入 FIG
**影响**: 无法在陌生环境中自主提出并验证假设（如"GTA 可能有通缉系统"）

### 鸿沟 2: 归因 → 学习闭环

**现状**: BAGEL `bagel/runtime.py:55-63` AttributionCycleResult 不流入 DecisionMemory 或 SkillInductionGate
**缺失**: `bagel/runtime.py` → `learning/decision_memory.py` → `learning/skill_induction_gate.py` 的桥接代码
**影响**: 从失败中学习不可能，系统只能证伪信念，不能将归因转化为知识

### 鸿沟 3: Skill 泛化

**现状**: `learning/skill_induction/anchor_binder.py:43-89` 仅提取 timing 参数，固定步骤序列
**缺失**: 多 trace 分析器，从多次成功执行中提取可变部分作为参数
**影响**: 每个归纳出的 skill 只适用于非常具体的场景，不可迁移

### 鸿沟 4: 探索 → 信念 → 技能 全链路

**现状**: UnknownSceneHandler、BAGEL、learning/ 三段完全独立
**缺失**: 探索结果作为信念证据 → 信念修订触发学习 → 学习产生新技能 → 新技能减少探索
**影响**: 系统不会从探索中积累经验

### 鸿沟 5: 长程知识积累

**现状**: DecisionMemory 用 SQLite + LIKE 模糊匹配，无冲突处理
**缺失**: 结构化世界知识图谱 + 增量更新 + 冲突消解 + 遗忘机制
**影响**: 数十小时游戏中无法建立持久世界模型

---

## 四、最小可行架构：4 个新增模块

### 模块 1: WebSearchService (`knowledge/web_search_service.py`)

```python
class WebSearchService:
    """统一联网搜索与结构化知识提取"""

    def search_game_guides(self, query: GameGuideQuery) -> list[GuideSearchResult]: ...
    def search_game_keymaps(self, game_name: str) -> KeymapDiscoveryResult: ...
    def extract_structured_knowledge(self, url: str, game_id: str) -> GameKnowledgePack: ...
```

**复用**: 替换 `knowledge/online_guide_system.py` 的 mock OnlineGuideSearcher
**依赖**: 外部搜索 API（MiniMax MCP / SerpAPI）

### 模块 2: CapsuleForge (`capsules/capsule_forge.py`)

```python
class CapsuleForge:
    """从游戏知识自动生成 capsule 骨架"""

    def forge(self, knowledge: GameKnowledgePack) -> ForgedCapsule: ...
    def generate_manifest(self, knowledge: GameKnowledgePack) -> CapsuleManifest: ...
    def bootstrap_screen_classifier(self, screen_states: list[str]) -> type: ...
```

**复用**: 直接注册到 `capsules/capsule_registry.py`，使用 `capsule_protocol.py` 的 CapsuleManifest
**依赖**: WebSearchService, LLM providers

### 模块 3: CodingAgent (`agent/coding_agent.py`)

```python
class CodingAgent:
    """为缺失能力生成、验证、应用代码补丁"""

    def generate_detector(self, spec: DetectorSpec) -> GeneratedCode: ...
    def generate_skill(self, spec: SkillSpec) -> GeneratedCode: ...
    def generate_provider(self, spec: ProviderSpec) -> GeneratedCode: ...
    def validate_in_sandbox(self, code: GeneratedCode) -> ValidationResult: ...
```

**复用**: 扩展 `llm/sandbox_validator.py`，复用 `learning/evolution_engine.py` 的 `_verify_in_sandbox()`
**依赖**: LLM providers, CodeSandboxExecutor

### 模块 4: HotReloadManager (`runtime/hot_reload_manager.py`)

```python
class HotReloadManager:
    """运行时热替换感知、战斗、导航模块"""

    def reload_post_processor(self, processor_id: str, new: FramePostProcessor) -> bool: ...
    def reload_capsule_provider(self, capsule_id: str, provider_type: str, new: Any) -> bool: ...
    def reload_skill(self, skill_id: str, new_skill_def: SkillDef) -> bool: ...
    def checkpoint_state(self) -> ReloadCheckpoint: ...
    def rollback(self, checkpoint: ReloadCheckpoint) -> bool: ...
```

**复用**: 编排 `perception/pipeline.py` 的 add/remove + `capsules/capsule_registry.py` 的生命周期
**依赖**: PerceptionPipeline, CapsuleRegistry

---

## 五、与现有代码的集成点

### 直接复用（无需修改）

| 模块 | 文件 | 通用性 |
|------|------|--------|
| Capsule Protocol | `capsules/capsule_protocol.py` | 完全通用 |
| Capsule Registry | `capsules/capsule_registry.py` | 完全通用 |
| Domain Protocols (7个) | `capsules/domain_protocols.py` | 完全通用 |
| Provider Registry | `capsules/provider_registry.py` | 完全通用 |
| StateBus | `core/state_bus.py` | 完全通用 |
| Perception Pipeline | `perception/pipeline.py` | 通用，支持动态 add/remove |
| FIG Schema | `bagel/fig_schema.py` | 完全通用 |
| BAGEL Runtime | `bagel/runtime.py` | 完全通用 |
| Skill Schema | `skills/schema.py` | 完全通用 |
| Skill Promotion | `skills/promotion.py` | 完全通用 |
| Hierarchical Planner | `planning/hierarchical_planner.py` | 通用 |
| Autonomous Task Brain | `agent/autonomous_task_brain.py` | 通用 |
| ZeroShotAgent | `agent/zero_shot_agent.py` | 可泛化 |
| EvolutionEngine | `learning/evolution_engine.py` | 完全通用 |
| DecisionMemory | `learning/decision_memory.py` | 完全通用 |
| Claim Runtime | `runtime/claim_runtime.py` | 完全通用 |
| Execution Backends | `execution/safe_window_backend.py` | 完全通用 |
| Knowledge Schema | `knowledge/knowledge_schema.py` | 完全通用 |

### 需要重构

| 模块 | 文件 | 重构内容 |
|------|------|---------|
| AutoCalibrator | `perception/auto_calibrator.py:94-97` | 移除硬编码原神参考点，提取为配置 |
| ZeroShotAgent Keymaps | `agent/zero_shot_agent.py:21-36` | GAME_KEYMAPS 移至 capsule manifest 加载 |
| OnlineGuideSearcher | `knowledge/online_guide_system.py:120-142` | mock → 真实实现 |
| GuideExtractor | `knowledge/online_guide_system.py:194-211` | 中文/原神正则 → 语言/游戏参数化 |
| 30+ 原神检测器 | `perception/genshin_*.py` | 移至 capsule 安装时注册 |

---

## 六、实施路线图

### Phase 1: 基础能力（P0，约 2 周）

1. **WebSearchService** — 接入搜索 API，实现真实搜索
2. **CodeSandboxExecutor** — 带超时和资源限制的独立代码执行
3. **CodingAgent** — LLM 驱动的代码生成 + 验证
4. **CapsuleForge** — 从知识自动生成 capsule 骨架

### Phase 2: 通用感知（P1，约 2 周）

5. **AutoCalibratorV2** — VLM 驱动的 UI 地标发现
6. **GenericScreenClassifier** — VLM 屏幕状态分类
7. **HotReloadManager** — 运行时模块替换
8. **重构 ZeroShotAgent** — keymaps 从 capsule manifest 加载

### Phase 3: 认知闭环（P1，约 2 周）

9. **BeliefProposer** — 假设生成模块
10. **BAGEL → Skill 桥接** — 归因结果流入 SkillInductionGate
11. **Skill 参数化** — 多 trace 分析提取可变参数
12. **DecisionMemory → Planner** — 学习结果注入规划

### Phase 4: 长程成长（P2，约 2 周）

13. **GameKnowledgeStore** — 持久化结构化知识
14. **UniversalEntryAgent** — 用户意图到游戏执行的完整管道
15. **重构原神检测器** — 移至 capsule 安装时注册
16. **通用导航协议** — 多模态路径规划

---

## 七、"玩 GTA" 完整流程模拟

```
用户: "玩 GTA 剧情模式"

Step 1: UniversalEntryAgent 解析意图
  → game_id = "gta5", mode = "story"

Step 2: WebSearchService 搜索
  → "GTA 5 keyboard controls PC"
  → "GTA 5 story mode walkthrough"
  → "GTA 5 combat mechanics guide"
  → 返回 GameKnowledgePack

Step 3: CapsuleForge 生成 capsule
  → capsule.yaml (keymaps, screen_states, capabilities)
  → providers.py (VLM-backed screen classifier)
  → 注册到 CapsuleRegistry

Step 4: 进入游戏
  → AutoCalibratorV2 发现 UI 元素 (小地图、血条、武器轮盘)
  → GenericScreenClassifier 建立屏幕状态映射

Step 5: 零样本探索
  → ZeroShotAgent 使用 capsule keymaps
  → VLM 分析画面 → LLM 决策 → 安全执行
  → 发现机制: 驾驶、射击、掩体、通缉

Step 6: 机制沉淀
  → UnknownSceneHandler 探索未知 → BAGEL 记录信念
  → BeliefProposer 生成假设 → 探测验证
  → SkillInductionGate 从成功 trace 归纳技能

Step 7: 能力增强
  → CodingAgent 发现缺失: "需要 GTA 特殊的驾驶检测器"
  → 生成代码 → CodeSandboxExecutor 验证
  → HotReloadManager 热替换 post_processor

Step 8: 持续成长
  → 探索 → 信念 → 技能 闭环运转
  → DecisionMemory 积累策略经验
  → 长程世界知识逐步建立
```

---

## 八、关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 代码生成质量不稳定 | 生成的检测器/skill 可能不工作 | 沙盒验证 + HotReload rollback + 人工审批 |
| VLM 屏幕分类延迟高 | 实时性不足 | 缓存 + 降级策略 + 先 VLM 后规则 |
| 搜索结果质量参差 | 知识提取不准确 | 多源交叉验证 + BAGEL 证伪 |
| 跨游戏差异太大 | 通用架构无法覆盖 | 游戏类型模板 + coding agent 兜底 |
| 安全边界模糊 | 自动生成的代码可能危险 | 严格沙盒 + 禁止列表 + 用户确认 |

---

## 九、总结

**核心结论**: 代码库的架构设计已为通用游戏 Agent 做好了准备——Capsule 协议、Domain Protocols、BAGEL、Learning Pipeline、Claim Runtime 全是游戏无关的。差距不在"架构"而在"泛化"和"闭环"。

**最小可行闭环** (Phase 1 完成即可演示):
1. WebSearchService 搜索 GTA 知识
2. CapsuleForge 生成最小 capsule (keymaps + screen_states)
3. ZeroShotAgent 用 capsule keymaps 做零样本游戏
4. CodingAgent 生成缺失的检测器
5. HotReloadManager 热加载

**核心突破点**: BeliefProposer + BAGEL→Skill 桥接 + Skill 参数化。这三者打通后，系统从"执行预定义任务的自动化工具"进化为"能自主学习成长的智能体"。
