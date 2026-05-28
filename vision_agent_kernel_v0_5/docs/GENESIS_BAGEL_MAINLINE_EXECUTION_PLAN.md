# Genesis BAGEL Mainline Autonomy Execution Plan

> 目标：把 Aurora / GenesisAgent 从“有很多强模块的视觉自动化内核”推进到“能在实机前把长程主线自主能力做到理论与工程上尽可能封顶”的系统。
> 方法：以任务事实链为主轴，以 BAGEL 的可证伪信念归因为失败恢复与自我修正内核，以 Claim Runtime 为事实裁判，以分层 Skill OS 为执行资产，以沙盒/回放/授权测试环境为实机前验证边界。

本文档是给 coding agent 执行的工程方案，不是愿景白皮书。所有条目都应能落成文件、接口、测试、基准或验收报告。

---

## 0. 不可谈判边界

### 0.1 目标能力和执行边界分离

项目的能力目标可以按“自主推进原神主线”定义，因为它足够复杂：开放世界、剧情对话、导航、战斗、养成、资源约束、长程恢复。
但仓库实现必须遵守现有 `SAFETY.md`：

- 不新增线上游戏自动化。
- 不新增真实商业客户端进程绑定。
- 不新增内存读取、注入、反作弊绕过、驱动级或硬件级输入。
- 不允许 LLM 输出原始键鼠命令。
- 所有可执行链路默认 `dry-run`。
- 真实输入只能通过授权 testbed / pseudo3d / QA safe-window，并且要有确认、焦点校验、`InputLease` 和 emergency stop。

因此，coding agent 的实现目标是：

```text
能力上对齐 Genshin-like mainline autonomy
工程上先落在 self-built testbed / replay / synthetic state / authorized safe-window
领域知识放在 Capsule
真实客户端适配不进入默认仓库主路径
```

这不是保守退让，而是为了避免把架构污染成一次性脚本。实机前所有能靠思考解决的问题，都必须先在安全、可复现、可审计环境里解决。

### 0.2 成功定义

不能再用“测试数量通过”证明接近愿景。合格进展必须同时满足：

- `VCR`: Verified Completion Rate，有 Claim / BAGEL 证据链支持的真实完成率。
- `HIC`: Human Intervention Count，人类介入次数下降。
- `RSR`: Recovery Success Rate，死亡、卡墙、UI 迷路、目标丢失后的恢复率。
- `SRR`: Skill Reuse Rate，慢探索后沉淀 Skill 并复用的比例。
- `CTR`: Token Cost Reduction，重复任务中 VLM/LLM 调用成本下降。
- `FSR`: False Success Rate，假阳性完成率必须被压低。
- `CCR`: Cascade Containment Rate，错误信念修正时不破坏无关下游的比例。

---

## 1. 当前系统判断

Aurora 不是从零开始。当前仓库已经具备这些地基：

- `runtime.claim_runtime`: `StateDeltaClaim`, `ObservationClaim`, `ClaimGraph`, `ClaimProducingExecutor`, `CapabilityReliabilityGate`。
- `runtime.claim_worker`: 单写者 ClaimGraph worker。
- `runtime.claim_adjudicator`: rule-based adjudication 和 evidence vote。
- `planning.mission_graph_v3`: hierarchical MissionGraph。
- `planning.quest_tracker`: 初版 QuestStateTracker。
- `planning.applicability_gate`: SkillApplicabilityGate。
- `agent.autonomous_task_brain`: Claim-gated strategic loop 雏形。
- `agent.exploration_agent`: 慢探索候选动作雏形。
- `learning.skill_induction_gate`: trace -> anchor-bound skill 的早期雏形。
- `reliability.reliability_store`: 条件可靠度地基。
- `control.*`, `combat.*`: 导航、进度、战斗、生存、恢复等局部控制器雏形。
- `benchmarks.*`: AuroraBench、boss gauntlet、long-horizon testbed 的基础。

关键短板不是“没有模块”，而是这些模块还没有形成主线能力闭环：

1. `QuestStateTracker` 仍是文本 regex 级别，不能维护主线事实链。
2. Claim 能证明状态变化，但还不能归因“哪一个信念导致失败”。
3. MissionGraph 还缺少可执行契约、证据、失败预算、stale propagation 的统一格式。
4. Skill induction 还只是从短 trace 生成 catalog entry，缺少可证伪 verifier、promotion ladder、failure injection。
5. ApplicabilityGate 有初步评分，但没有完整上下文向量、Wilson 下界、漂移、任务阶段、Capsule 维度。
6. Recovery 还不是一套可组合的 Sentinel protocol。
7. 长程运行缺少 `MainlineRunner`、checkpoint/resume、上下文压缩和课程基准。
8. 战斗和导航缺少“先务实闭环，后 V-NavMesh 增强”的工程阶梯。
9. 缺少 BAGEL 的双账本、FIG、Evidence Matrix、Popper Probe、Safe Revision。

---

## 2. 总体架构：Genesis Mainline OS + BAGEL Runtime

最终系统分为 9 个平面，每个平面只通过结构化事件或不可变快照通信。

```text
User Goal
  -> Mainline Mission OS
  -> Quest Fact Chain
  -> Claim-Gated MissionGraph
  -> Skill Applicability Gate
  -> Skill Runtime / Local Controllers
  -> Claim Runtime
  -> BAGEL Attribution Runtime
  -> Reliability / Decision Memory
  -> Benchmark Curriculum
```

### 2.1 Mainline Mission OS

负责长程主线推进。它不点击、不导航、不做事实裁判，只做：

- 维护 `GoalStack`。
- 读取 `ActiveQuestContext`。
- 选择或生成 `MissionGraph`。
- 调用 Skill / Exploration / Recovery。
- 管理 checkpoint 和 resume。
- 控制预算和风险。

目标文件：

- 新增 `planning/mainline/active_quest_context.py`
- 新增 `planning/mainline/mainline_runner.py`
- 新增 `planning/mainline/progression_manager.py`
- 新增 `planning/mainline/prerequisite_resolver.py`
- 新增 `planning/mainline/resource_planner.py`
- 新增 `tests/test_mainline_runner.py`

### 2.2 Quest Fact Chain

主线推进不是“当前屏幕像什么”，而是一条可追溯事实链：

```text
Quest objective text
  + dialogue facts
  + map marker facts
  + screen state facts
  + inventory/team facts
  + completed claims
  + blocked claims
  -> ActiveQuestContext
```

`ActiveQuestContext` 最小字段：

```python
@dataclass(frozen=True)
class ActiveQuestContext:
    quest_id: str
    quest_title: str
    objective_text: str
    objective_type: str  # dialog | go_to_marker | combat | collect | domain | upgrade | unknown
    evidence_refs: tuple[str, ...]
    last_dialogue_turns: tuple[DialogueTurn, ...]
    map_marker: MapMarker | None
    screen_state: str
    known_blockers: tuple[QuestBlocker, ...]
    confidence: float  # system-computed
    version: int
```

任务：

- 把 `planning.quest_tracker.QuestStateTracker` 升级为 `QuestStateTrackerV2`。
- 输入从 `ScreenStateClaim` 扩展为 `ObservationGraph`、OCR block、dialogue transcript、map marker、ClaimGraph summary。
- 输出不再只是 `QuestState`，而是 `ActiveQuestContext`。
- 每次 context 变化必须产生 `quest_context_changed` 事件和 `StateDeltaClaim`。

验收：

- `tests/test_quest_state_tracker_v2.py`
- 能区分 objective changed、dialogue advanced、map marker lost、blocked by prerequisite。
- objective 没变但屏幕变了时，不误判任务完成。
- OCR 缺失时可以保持上一版 context，但标记 `confidence_decay`。

### 2.3 Claim-Gated MissionGraph v4

MissionGraph 节点必须从“执行步骤”升级为“事实契约”。

节点 schema：

```yaml
node_id: talk_to_npc
node_type: dialog
risk_level: medium
skill_candidates:
  - proc_dialogue_advance
input_claims:
  - claim_type: screen_state_match
    target: world_or_dialogue
    required_status: verified
output_claims:
  - claim_type: quest_objective_changed
    target: active_quest.objective_text
    verifier_recipe: quest_objective_delta.default
fallbacks:
  - recovery_recipe: UI_LOST_RECOVERY
  - replan_policy: resample_then_explore
budgets:
  max_retries: 2
  max_uncertain: 1
  max_duration_sec: 90
bagel:
  required_belief_commits:
    - target_object: "quest objective"
      causal_role: "objective_type_hypothesis"
```

目标文件：

- 新增 `planning/mainline/mission_graph_v4.py`
- 新增 `planning/mainline/mission_graph_validator_v4.py`
- 新增 `runtime/claim_schema.py` 扩展或 v2 schema。
- 新增 `tests/test_mission_graph_v4_contract.py`

验收：

- 节点没有 output claim 不可作为 terminal。
- 风险高但没有 fallback 不通过 validator。
- LLM/Planner 生成 graph 后必须经 validator 才能执行。
- Graph 可导出为 deterministic JSON，用于 replay 和 audit。

---

## 3. BAGEL Runtime 落地

BAGEL 是这次计划中最关键的理论升级。Claim Runtime 解决“世界是否如声称那样变化”，BAGEL 解决“失败应归因到哪个可干预信念，以及如何安全修正”。

### 3.1 BAGEL 与 Claim 的关系

```text
ClaimGraph:
  world/task state truth ledger
  证明或反驳状态变化

FIG:
  belief-action-feedback-probe attribution graph
  归因失败、生成探针、修正信念、标记 stale
```

Claim 是事实裁判。Belief 是可证伪、可干预的行为控制变量。
两者不能混用：

- `StateDeltaClaim`: “任务目标文本从 A 变成 B”。
- `BeliefNode`: “当前 objective_type 是 dialog，所以应执行 dialogue loop”。

### 3.2 新增 BAGEL 包

目标目录：

```text
bagel/
  __init__.py
  fig_schema.py
  event_store.py
  executor_ledger.py
  critic_ledger.py
  shadow_graph.py
  evidence_matrix.py
  arbiter.py
  probe_policy.py
  safe_revision.py
  counterfactual_priming.py
  runtime.py
```

测试：

```text
tests/test_bagel_fig_schema.py
tests/test_bagel_event_store.py
tests/test_bagel_evidence_matrix.py
tests/test_bagel_arbiter.py
tests/test_bagel_safe_revision.py
tests/test_bagel_runtime_integration.py
```

### 3.3 FIG schema

`fig_schema.py` 必须定义：

- `BeliefNode`
- `ActionNode`
- `FeedbackNode`
- `ProbeNode`
- `TypedEdge`
- `BeliefLifecycleState`
- `BeliefIdentity`
- `FalsifiableInterventionGraph`

关键约束：

- BeliefCommit 必须发生在 ActionProposal 之前。
- `NominalBelief` 前向只要求 action relevance、falsifiability、intervenability-by-design。
- `AttributedBelief` 后向才要求 feedback coupling。
- Belief identity 使用两阶段：
  - provisional: intent/action anchor。
  - confirmed: materialized fingerprint。
- Action materialization 后，如果 fingerprint mismatch，不能直接高置信归因。

验收：

- 事后补 belief 的事件必须被拒绝或标记 `posthoc_invalid`。
- 没有 falsification condition 的 belief 不可驱动中高风险 action。
- identity mismatch 会触发 audit required。

### 3.4 不可变事件流

`event_store.py` 实现 JSONL 或 SQLite WAL 之一。MVP 先用 JSONL，接口不要绑定实现。

事件类型：

```text
BeliefCommitted
ActionProposed
ActionMaterialized
ActionExecuted
FeedbackReceived
AuditStarted
AuditCompleted
ProbeGenerated
ProbeExecuted
ArbiterUpdated
BeliefRevised
BeliefRetired
BeliefStaled
SubgraphCondensed
```

硬性要求：

- append-only。
- 每个事件有 `graph_version`, `trace_id`, `timestamp`, `snapshot_id`。
- 写入失败不能继续外部 action。
- 能从 event stream 重建 FIG。

### 3.5 Shadow Fingerprint Graph

Critic 不读 Executor 长篇叙事，只读投影图：

```text
atomic claim
belief identity
supported action fingerprint
screen/action anchor
claim evidence summary
feedback signal quality
dependency edges
omitted-belief anchors
```

目标：

- 防止 Critic 被 Executor 自我辩护污染。
- 让多 Auditor 分歧能映射到 Evidence Matrix。

### 3.6 Evidence Matrix

`evidence_matrix.py` 实现 BAGEL v1.1 的非对称因果激活：

```python
M_ij in {+1, 0, -1, NaN}
C_i = max_j(w_j * I[M_ij == +1])
S_i = sum_j(w_j * I[M_ij == -1])
R_i = sum_j(w_j * I[M_ij != 0])
score_i = C_i + alpha * R_i / (epsilon + S_i)
```

约束：

- 无关通过信号必须记 `0`，不能记 `-1`。
- environment_error / insufficient_signal 记 `NaN`，不参与归因。
- high-quality core probe 的 contradiction 应具备近似一票否决权。

测试：

- 一个核心失败信号不能被 100 个无关通过信号淹没。
- 相关存活信号可以降低排序，但不能消除强证伪。
- 多 auditor 高冲突时不能平均成中性结论。

### 3.7 Popper Probe

`probe_policy.py` 只生成“证伪候选信念”的探针，不生成“证明自己正确”的探针。

在 GUI / game-like 环境中，Probe 可以是：

- 重新 OCR 指定 ROI。
- 打开任务面板核对 active quest。
- 打开地图核对 marker 是否存在。
- 等待 N 帧验证 screen state 是否稳定。
- 在 testbed 中执行小型 state mutation。
- replay 上做 viewpoint / resolution / OCR-noise perturbation。

探针执行前必须通过 sanity：

- 只测试声明 invariant。
- 有明确失败判据。
- 不产生不可逆外部动作。
- 能区分至少两个候选 belief。
- 超时和噪声风险已声明。

### 3.8 Safe Revision

`safe_revision.py` 实现：

```python
Affected(b_i) = all downstream actions reachable from b_i
CascadeRisk = affected_ratio * coupling * (1 - verification_coverage)
SafeRevision = CascadeRisk < kappa and Impact < K
```

Revision protocol：

```text
if SafeRevision:
  revise belief
  regenerate affected local actions
  run targeted probes
else:
  mark downstream nodes stale
  estimate expanded revision cost
  JIT regenerate stale actions before execution
```

验收：

- hub belief 被证伪时，不允许静默继续下游旧 action。
- 低影响 belief 修正只重生成局部节点。
- 高影响 belief 触发 lazy stale marking，而不是全局重写。

---

## 4. Screen State Tree 2.0

SC-UPG 必须从概念落地为强类型屏幕状态树。

目标文件：

```text
perception/screen_state_tree.py
perception/screen_state_compiler.py
perception/ui_semantic_roles.py
planning/action_mask.py
tests/test_screen_state_tree.py
tests/test_action_mask.py
```

### 4.1 ScreenStateTree schema

```python
@dataclass(frozen=True)
class ScreenStateTree:
    frame_id: int
    game_id: str
    screen_state: str
    page_id: str
    confidence: float
    elements: tuple[UIElementNode, ...]
    text_blocks: tuple[TextBlock, ...]
    regions: tuple[RegionNode, ...]
    active_modal: ModalState | None
    focus_target: str | None
    evidence_refs: tuple[str, ...]
```

`UIElementNode` 必须有：

- `element_id`
- `semantic_role`
- `text`
- `bbox_norm`
- `anchor_candidates`
- `clickable`
- `enabled`
- `confidence`
- `source`: OCR / detector / VLM / template / fused

### 4.2 Action Mask

LLM/Explorer 只能从 mask 里选动作：

```text
WorldViewport:
  observe, open_menu, open_map, interact_prompt, heading_servo, safe_pause

Dialogue:
  advance_dialogue, select_dialogue_option, back, observe

Map:
  select_marker, teleport, back, observe

CharacterMenu:
  select_tab, select_character, upgrade, equip, back, observe

Unknown:
  observe, back, ask_user, safe_probe
```

验收：

- 在 UI 页面中不允许 `release_skill`、`wasd_move`。
- 在 unknown 页面中不允许点击任意坐标。
- VLM 输出不在 mask 内时被拒绝，并生成 BAGEL Feedback。

---

## 5. Skill OS 重构

Skill 不是宏。Skill 是带前置条件、动作体、产出 Claim、Verifier、Fallback、Reliability、BAGEL belief template 的可执行资产。

### 5.1 目录规划

```text
skills/
  __init__.py
  schema.py
  registry.py
  index.py
  applicability.py
  promotion.py
  runtime.py
  verifier_binding.py
  serialization.py
learning/skill_induction/
  trace_recorder.py
  episode_segmenter.py
  semantic_skill_inducer.py
  anchor_binder.py
  verifier_synthesizer.py
  failure_injector.py
  promotion_gate.py
```

现有 `planning.skill_capability_catalog`, `learning.skill_induction_gate`, `recording.semantic_distiller`, `learning.evolution_engine` 可以逐步迁移，不要大爆炸替换。

### 5.2 Skill schema

```yaml
skill_id: proc_dialogue_advance
version: 1
capsule_id: core
kind: procedure
risk_level: low

applicability:
  screen_states: [dialogue]
  required_anchors: [dialogue_continue]
  required_claims:
    - screen_state_match: dialogue

belief_templates:
  - target_object: dialogue_overlay
    causal_role: ui_affordance_hypothesis
    falsification_condition: "dialogue_continue anchor absent for 3 stable frames"

steps:
  - action: click_anchor
    target: dialogue_continue
    wait_until: dialogue_text_changed

produced_claims:
  - claim_type: dialogue_advanced
    target: active_dialogue.turn_index
    claim_role: dependency
    verifier_recipe: dialogue_delta.default

fallbacks:
  - UI_LOST_RECOVERY
  - resample_then_back

promotion:
  min_replays: 3
  min_wilson_lower_bound: 0.70
  required_profiles: [default_1920x1080]
```

### 5.3 Induction pipeline

```text
TraceRecorder
  -> EpisodeSegmenter
  -> SemanticSkillInducer
  -> AnchorBinder
  -> VerifierSynthesizer
  -> FailureInjector
  -> PromotionGate
  -> SkillRegistry
```

硬规则：

- 坐标-only trace 只能作为 raw trace，不可晋升。
- 没有 produced claim 的 Skill 不能进 candidate。
- 没有 verifier 的 terminal skill 不能 unattended。
- 新 Skill 的 prior 只可排序，不可进入安全门。

### 5.4 Promotion ladder

```text
raw_trace
  -> draft
  -> experimental
  -> candidate
  -> stable
  -> trusted
```

每级含义：

- `raw_trace`: 只保存，不执行。
- `draft`: 有 semantic action，但 verifier 不完整。
- `experimental`: supervised 可执行。
- `candidate`: dry-run/testbed 通过，低风险可自动。
- `stable`: 多次审计通过。
- `trusted`: 多上下文、多 profile、漂移测试通过。

---

## 6. Recovery Recipes 与 Sentinel Protocol

恢复机制必须从局部 fallback 升级为常驻哨兵。

目标文件：

```text
control/sentinel/
  __init__.py
  sentinel_runtime.py
  recovery_recipe.py
  recipe_registry.py
  recipes.py
  somatic_state.py
tests/test_sentinel_recovery.py
tests/test_somatic_state.py
```

### 6.1 SomaticState

```python
@dataclass(frozen=True)
class SomaticState:
    active_quest_id: str
    last_verified_checkpoint: str
    last_safe_screen_state: str
    last_known_position: PositionEstimate | None
    last_map_anchor: str | None
    team_state: TeamState
    resource_state: ResourceState
    active_mission_node: str
    claim_graph_version: int
```

### 6.2 Recovery recipes

必须先在 testbed / synthetic 环境实现：

- `UI_LOST_RECOVERY`
- `STUCK_RECOVERY`
- `TARGET_LOST_RECOVERY`
- `LOADING_TIMEOUT_RECOVERY`
- `COMBAT_DEFEAT_RECOVERY`
- `LOW_HEALTH_RECOVERY`
- `QUEST_TARGET_MISSING_RECOVERY`
- `DRIFT_RECOVERY`
- `MODEL_PROVIDER_FAILURE_RECOVERY`

每个 recipe 必须有：

```python
check_precondition(snapshot) -> bool
execute_recovery(executor) -> RecoveryResult
verify_restabilized(perception, claim_runtime) -> StateDeltaClaim
failure_policy -> abort | replan | ask_user | escalate
```

验收：

- Sentinel 可以抢占普通 MissionRunner。
- 抢占时释放所有 input lease。
- 恢复结束必须写入 Claim 和 BAGEL Feedback。
- 恢复失败不允许无限循环，必须有 budget。

---

## 7. 导航路线：务实三段式优先，V-NavMesh 后置增强

在主线闭环跑通前，不要把 3D SLAM 当第一优先级。

### 7.1 MVP 导航链

```text
Map / quest marker recognition
  -> select nearest unlocked waypoint
  -> teleport / load verification
  -> heading servo toward marker
  -> progress supervisor
  -> stuck recovery
  -> arrival claim
```

目标文件：

```text
navigation/mainline_navigation.py
control/heading_servo.py
control/route_progress.py
execution/navigation_verifier.py
tests/test_mainline_navigation.py
```

### 7.2 V-NavMesh 作为增强层

只有当以下条件满足后再做 V-NavMesh：

- Quest fact chain 已跑通。
- 短距离 heading servo 有可测基线。
- Stuck recovery 有统计。
- Benchmark 能复现卡墙/断崖/高度差失败。

V-NavMesh 第一版不追求完整 3D 重建，只做 `local affordance map`：

- walkable
- blocked
- climb-like
- drop-risk
- water-like
- obstacle-unknown

验收：

- 在 pseudo3d_scene 中减少 stuck rate。
- 不要求实机三维精确地图。

---

## 8. 战斗路线：生存优先于输出

战斗系统的第一目标不是打得快，而是不死锁、不重复同一错误。

目标文件：

```text
combat/mainline_combat.py
combat/fight_trace.py
combat/death_cause_classifier.py
combat/playbook_patcher.py
combat/combat_preparation_planner.py
tests/test_combat_failure_learning.py
```

### 8.1 战斗闭环

```text
combat_started claim
  -> load playbook
  -> reflex runtime owns survival
  -> cooldown/rotation runtime owns damage
  -> danger verifier emits P0 interrupts
  -> combat_end claim or defeat claim
  -> BAGEL attribution on defeat
  -> playbook patch or resource plan
```

### 8.2 战斗失败归因 Belief 类型

- `team_power_insufficient`
- `wrong_element_strategy`
- `danger_telegraph_missed`
- `target_tracking_lost`
- `rotation_timing_bad`
- `healing_policy_too_late`
- `boss_phase_misclassified`
- `arena_navigation_failed`

每次失败必须至少生成：

- `FeedbackNode`: 死亡/低血/超时/目标未清除。
- `BeliefNode`: 候选失败信念。
- `ProbeNode`: testbed/replay 可执行验证。
- `Revision`: playbook patch 或 resource plan。

验收：

- 同一 boss testbed 连续失败三次后，不能重复同一 playbook。
- 修正必须可解释为某个 belief 被证伪或降权。

---

## 9. Capsule 边界与知识系统

通用内核不得硬编码 Genshin。所有领域知识进入 Capsule。

目标目录：

```text
capsules/genshin_like/
  capsule.yaml
  quest_vocabulary.yaml
  ui_anchors.yaml
  screen_states.yaml
  mission_templates/
  verifier_recipes/
  skills/
  combat_profiles/
  benchmark_tasks/
```

注意：默认仓库可以保留 `genshin` 作为数据命名历史，但新增能力应倾向 `genshin_like` 或 `mainline_arpg` testbed capsule，避免把默认执行链指向真实商业客户端。

Capsule API：

```python
class MainlineCapsuleProvider(Protocol):
    def parse_quest_text(...)
    def classify_objective(...)
    def provide_mission_templates(...)
    def provide_ui_anchors(...)
    def provide_verifier_recipes(...)
    def provide_recovery_recipes(...)
    def provide_benchmark_tasks(...)
```

验收：

- Core 不 import `capsules.genshin_like`。
- Capsule boundary test 检查通用层无 game-specific imports。
- 替换 capsule 后 MainlineRunner 仍可跑 synthetic curriculum。

---

## 10. Benchmark Curriculum

必须把能力拆成课程，不再用大而空的“通关”判断。

目标目录：

```text
benchmarks/mainline_curriculum/
  tasks/
  runners/
  metrics.py
  report.py
  baselines/
  ablations/
```

### 10.1 课程

```text
C0_bootstrap_startup
C1_dialogue_progression
C2_quest_tracking
C3_map_teleport
C4_short_navigation
C5_interaction_collect
C6_basic_combat
C7_recovery_gauntlet
C8_skill_induction_unknown_ui
C9_multi_node_mainline
C10_boss_failure_revision
C11_long_horizon_2h_resume
```

### 10.2 Baselines

- pure VLM computer-use。
- scripted macro。
- human-authored skills only。
- no Claim gate。
- no BAGEL attribution。
- no Skill induction。
- no Recovery Sentinel。
- full system。

### 10.3 报告字段

```json
{
  "task_id": "...",
  "variant": "full_system",
  "tsr": 0.0,
  "vcr": 0.0,
  "hic": 0,
  "rsr": 0.0,
  "srr": 0.0,
  "ctr": 0.0,
  "fsr": 0.0,
  "ccr": 0.0,
  "time_to_success_sec": 0.0,
  "token_cost": 0,
  "claim_count": 0,
  "bagel_revisions": 0
}
```

验收：

- 一条命令跑 synthetic curriculum。
- 一条命令生成 Markdown + JSON 报告。
- 报告能指出最低分能力瓶颈。

---

## 11. UX / Cockpit

复杂系统如果不能被操作，就无法获取真实数据。

目标：

- 用户知道当前处于 dry-run/testbed/supervised/authorized safe-window 哪个模式。
- 用户看得到目标、任务、Claim、Belief、Skill、Recovery、风险。
- 用户能一键暂停、停止、导出 evidence bundle。

目标文件：

```text
app_service/mainline_api.py
app_service/bagel_api.py
desktop/src/views/MainlineCockpit.tsx
desktop/src/views/BagelInspector.tsx
desktop/src/views/SkillPromotionPanel.tsx
desktop/src/views/BenchmarkDashboard.tsx
```

最小 API：

- `GET /mainline/state`
- `POST /mainline/start`
- `POST /mainline/pause`
- `POST /mainline/stop`
- `GET /mainline/claims`
- `GET /bagel/fig`
- `GET /bagel/beliefs`
- `GET /skills/promotion`
- `POST /benchmarks/mainline/run`

验收：

- Cockpit 能显示当前 `ActiveQuestContext`。
- 能显示 ClaimGraph 最新状态。
- 能显示 BAGEL suspect beliefs。
- 能显示为什么某个 Skill 被允许/拒绝。

---

## 12. 分阶段执行包

下面是 coding agent 可直接拆分执行的任务包。每个任务包必须独立测试，禁止跨阶段大爆炸。

### P0: 边界与文档固化

目标：

- 把本方案作为主执行契约。
- 增加安全边界测试，防止再引入真实客户端绑定。

任务：

- 新增本文件。
- 新增或扩展 `tests/test_safety_boundaries.py`。
- 检查 `YuanShen.exe`, `GenshinImpact.exe`, `mhyprot2.sys`, `SendInput` 等字符串不得出现在新执行路径。
- README / docs 中明确默认只支持 dry-run/testbed/authorized safe-window。

验收：

```powershell
python -m pytest tests/test_safety_boundaries.py -q
python .\scripts\check_core_boundaries.py --root .
```

### P1: BAGEL MVP

目标：

- 完成 FIG、事件流、Evidence Matrix、Arbiter、Safe Revision。

任务文件：

- `bagel/fig_schema.py`
- `bagel/event_store.py`
- `bagel/evidence_matrix.py`
- `bagel/arbiter.py`
- `bagel/safe_revision.py`
- `tests/test_bagel_*.py`

验收：

- Belief pre-commit 顺序被强制。
- 非对称 evidence scoring 通过。
- conflict 触发 tie-breaker probe request。
- safe revision 和 stale marking 通过。

### P2: Quest Fact Chain

目标：

- `QuestStateTrackerV2` 输出 `ActiveQuestContext`。

任务文件：

- `planning/mainline/active_quest_context.py`
- `planning/mainline/quest_state_tracker_v2.py`
- `tests/test_quest_state_tracker_v2.py`

验收：

- OCR/VLM/ClaimGraph summary 能融合。
- context versioning 正确。
- objective change 生成 StateDeltaClaim。
- confidence decay 可测。

### P3: ScreenStateTree + ActionMask

目标：

- VLM/Explorer 被限制在符号动作空间。

任务文件：

- `perception/screen_state_tree.py`
- `perception/screen_state_compiler.py`
- `planning/action_mask.py`
- `tests/test_screen_state_tree.py`
- `tests/test_action_mask.py`

验收：

- UI 页面不允许 WASD / combat action。
- unknown 页面只允许 observe/back/ask/safe_probe。
- raw coordinate action 被拒绝。

### P4: MissionGraph v4

目标：

- 每个节点都是 claim contract。

任务文件：

- `planning/mainline/mission_graph_v4.py`
- `planning/mainline/mission_graph_validator_v4.py`
- `tests/test_mission_graph_v4_contract.py`

验收：

- terminal node 无 output claim 不通过。
- 无 fallback 的 high risk node 不通过。
- graph 可 deterministic serialize。

### P5: Skill OS MVP

目标：

- 从现有 SkillCatalog 迁移到 schema 化 Skill OS。

任务文件：

- `skills/schema.py`
- `skills/registry.py`
- `skills/index.py`
- `skills/applicability.py`
- `skills/promotion.py`
- `tests/test_skill_os_schema.py`
- `tests/test_skill_applicability_v2.py`

验收：

- 新 Skill schema 可读写。
- zero-sample prior 不进入安全 gate。
- 不满足 precondition 时拒绝执行。
- Skill 拒绝原因可解释。

### P6: Skill Induction v2

目标：

- 首次 supervised exploration 成功后生成 verifier-bound Skill Draft。

任务文件：

- `learning/skill_induction/trace_recorder.py`
- `learning/skill_induction/episode_segmenter.py`
- `learning/skill_induction/semantic_skill_inducer.py`
- `learning/skill_induction/anchor_binder.py`
- `learning/skill_induction/verifier_synthesizer.py`
- `learning/skill_induction/failure_injector.py`
- `learning/skill_induction/promotion_gate.py`
- `tests/test_skill_induction_v2.py`

验收：

- 坐标-only trace 不晋升。
- anchor-bound trace 生成 draft。
- draft 有 produced_claims 和 verifier recipe。
- failure injection 能发现至少一个不稳定条件。

### P7: Sentinel Recovery

目标：

- 恢复成为常驻协议，不是 ad-hoc fallback。

任务文件：

- `control/sentinel/*`
- `tests/test_sentinel_recovery.py`

验收：

- sentinel 抢占会 release all input。
- recovery 有 budget。
- recovery 结果进入 ClaimGraph 和 BAGEL Feedback。

### P8: Mainline Runner

目标：

- 在 testbed 中连续完成多节点主线闭环。

任务文件：

- `planning/mainline/mainline_runner.py`
- `planning/mainline/progression_manager.py`
- `planning/mainline/prerequisite_resolver.py`
- `tests/test_mainline_runner.py`

验收：

- 能执行：observe -> quest context -> graph -> skill -> claim -> next context。
- 5 个异构 synthetic nodes 连续跑通。
- 中途失败能进入 recovery 或 BAGEL revision。

### P9: Benchmark Curriculum

目标：

- 用可重复课程评估系统进步。

任务文件：

- `benchmarks/mainline_curriculum/*`
- `tests/test_mainline_curriculum.py`

验收：

- 一条命令生成 JSON report。
- full system 与 no-bagel / no-skill-induction 至少在 synthetic task 上可比较。

### P10: Cockpit

目标：

- 操作者能看懂系统正在做什么。

任务文件：

- `app_service/mainline_api.py`
- `app_service/bagel_api.py`
- `desktop/src/views/*`

验收：

- 页面显示 ActiveQuestContext、Claim、Belief、Skill gate reason、Recovery 状态。
- 不提供绕过安全门的按钮。

---

## 13. Mainline Minimum Closed Loop 重新定义

实机前最小闭环必须在 testbed/replay 中先达成：

```text
1. World/Testbed state stabilized
2. ScreenStateTree compiled
3. ActiveQuestContext updated
4. MissionGraph v4 generated and validated
5. Skill selected by ApplicabilityGate
6. BeliefCommit before action
7. Action executed via dry-run/testbed InputLease
8. ObservationClaim emitted
9. StateDeltaClaim adjudicated verified
10. BAGEL event stream receives feedback
11. Quest context version advances
12. Skill reliability updated
13. Benchmark metrics updated
```

硬性标准：

- 无 raw coordinate action。
- 无 action without belief pre-commit。
- 无 node complete without terminal claim。
- 无 failure without BAGEL attribution cycle。
- 无 recovery without budget and claim.
- 无 unattended execution for zero-sample skill。

---

## 14. 验证命令

每个阶段局部测试通过后，跑仓库级验证：

```powershell
python -m pytest tests -q
python -m compileall . -q
python .\scripts\check_core_boundaries.py --root .
python .\scripts\run_aurorabench.py --suite all --mode dry-run --output-dir .\runs\aurorabench_mainline
```

如果新增 frontend cockpit：

```powershell
cd desktop
npm test
npm run build
```

如果 build/test 依赖当前机器缺失，coding agent 必须记录：

- 缺失命令。
- 错误输出。
- 可替代验证。
- 未验证风险。

---

## 15. 最终验收门槛

### 15.1 实机前能力封顶门槛

在不接触真实商业客户端的前提下，必须达到：

- C0-C9 curriculum 全部可跑。
- `MainlineRunner` 连续 30 个 synthetic/replay mission nodes 不死锁。
- `False Success Rate` 低于 2%。
- `Recovery Success Rate` 高于 85%。
- 首次探索成功后，重复任务 token 成本下降至少 60%。
- BAGEL 能在故意注入的错误 belief 上完成归因、probe、revision、stale marking。
- 高风险节点无法绕过人类确认或 testbed gate。

### 15.2 进入 supervised profile 的门槛

只有满足以下条件，才允许考虑授权 supervised profile：

- 所有默认路径仍为 dry-run。
- Profile 明确标注为 authorized/supervised。
- 所有动作经过 `InputLease`。
- 所有窗口有 focus check。
- F9 / Ctrl+C / stop API 都能 release all。
- 每个 Skill 有 promotion state 和 risk level。
- Cockpit 显示即将执行的 action 和 claim。

### 15.3 不接受的“完成”

以下都不能算完成：

- 只新增文档，无测试。
- 只跑单元测试，不跑 boundary check。
- LLM 直接点击坐标。
- Skill 只有宏，没有 verifier。
- MissionGraph 只有步骤，没有 output claim。
- 失败只重试，没有 BAGEL attribution。
- Recovery 无限循环。
- 把真实商业客户端绑定进默认路径。

---

## 16. 架构判断

这条路线的核心选择是：

```text
任务事实链优先于 3D SLAM
BAGEL 归因优先于盲目 retry
Skill OS 优先于鼠标宏
Claim verification 优先于模型自信
Sentinel recovery 优先于临场乱想
Benchmark curriculum 优先于测试数量
Capsule boundary 优先于游戏特调污染
```

如果这些工程契约全部落地，Aurora 才会真正具备“通往原神主线自主推进”的底层能力：不是靠一次脚本跑通，而是靠可验证事实链、可证伪信念修正、可复用 Skill、可恢复长程执行和可量化课程评估逐步逼近最终愿景。
