# Aurora Layered Runtime 与本地多模态模型执行计划

## 0. 目标判断

Aurora 下一阶段的核心不是再堆一个“让大模型直接操控键鼠”的 Agent，而是把复杂任务拆成一套可治理、可验证、可恢复的分层运行时。大模型负责慢思考、长程规划、异常解释、策略选择；实时感知、坐标落点、鼠标轨迹、战斗反射、导航修正、输入释放必须由低延迟本地系统承担。

最终统一链路：

```text
User Goal
-> Persona / Product UX
-> Mission Graph
-> Skill Graph
-> Semantic Action
-> UIAnchor / Navigation / Combat / Desktop Controller
-> InputLease + Safe Window
-> ObservationGraph + EvidenceGraph
-> Verifier
-> Failure / Repair / Benchmark / Memory
```

验收标准不是“能跑 demo”，而是：

- 用户能用直觉方式绑定一个游戏、录制一个 Skill、校准一组页面锚点。
- 开发者能用 Capsule 接入新游戏，不需要改 core。
- 系统能完成跨剧情、NPC、UI、采集、合成、导航、战斗的长程任务。
- 异常发生时能定位层级、局部恢复、升级重规划、沉淀回归测试。
- 本地多模态模型成为可选但重要的低成本视觉理解层，优先支持 LM Studio/OpenAI-compatible API。

> 模型命名说明：用户口中的 Gamma4/Gemma4 需要在实现中做成通用 `local_vlm` 配置，不把具体型号写死。官方可确认的 Google 本地多模态开放模型路线包括 Gemma 3n E2B/E4B；Gemma 3n 官方文档说明其支持视觉、文本、音频输入、32K 上下文、E2B/E4B 有效参数与 MatFormer/PLE 缓存机制。LM Studio 也已有 Gemma 3n E2B 页面并标注 vision supported。后续若用户本地 LM Studio 中是 Gemma4 E4B/E2B，只要暴露 OpenAI-compatible API，Aurora 应直接兼容。

参考：

- Google AI Developers: <https://ai.google.dev/gemma/docs/gemma-3n>
- Hugging Face Gemma 3n E2B: <https://huggingface.co/google/gemma-3n-E2B>
- LM Studio Gemma 3n E2B: <https://lmstudio.ai/models/google/gemma-3n-e2b>

---

## 1. Aurora 分层体系：像 OSI 一样固定边界

### L0 Physical Safety Layer：物理安全与授权窗口

职责：

- 只对授权窗口、测试床、安全沙盒执行输入。
- 所有物理输入必须绑定 `InputLease`、过期时间、owner、priority、release policy。
- focus lost、unauthorized window、lease expired、deadman switch 必须优先于所有上层逻辑。

当前基础：

- `execution/input_lease.py`
- `execution/input_worker.py`
- `execution/safe_window_backend.py`
- `execution/console_backend.py`

下一阶段必须补强：

- `InputLease` 增加动作族标签：`ui_click`、`movement`、`combat_reflex`、`navigation_hold`。
- `InputWorker` 输出统一 `PhysicalActionReceipt`，包含 lease_id、release_at、backend、focus_state、window_id。
- 所有上层 Controller 只能拿到 receipt，不能直接调用 OS 输入。

交付物：

- 新增 `execution/physical_receipt.py`。
- 新增测试：lease 超时、focus lost、unauthorized window、release_all 幂等、长按 W 不可无限持续。

---

### L1 Motor Layer：鼠标、键盘、轨迹与人类化执行

职责：

- 把语义动作变成鼠标路径、点击、滚动、按键、组合键。
- 保证轨迹稳定、速度合理、可回放、可中断。
- 处理最底层的不确定性：窗口缩放、DPI、坐标映射、移动误差、点击无效。

关键设计：

- 鼠标移动必须经过 `MousePathPolicy`：
  - straight：测试用。
  - bezier：默认人类化。
  - jitter_bounded：轻微抖动但不越界。
  - instant：只允许 dry-run。
- 点击执行必须走：

```text
AnchorResolution
-> CoordinateMapper(window-normalized -> screen px)
-> MousePathPolicy
-> InputLease
-> ClickReceipt
-> PostClickVerifier
```

下一阶段实现：

- 新增 `execution/mouse_motor.py`。
- `UIAnchorActionExecutor` 接入 `MousePathPolicy`，dry-run 记录轨迹，live/safe-window 才执行。
- Click receipt 增加 `pre_click_frame_id`、`post_click_frame_id`、`coordinate_space`、`path_points`。

验收：

- 同一 normalized point 在 1280x720、1920x1080、2560x1440 能映射到正确区域。
- 低置信度 anchor 不移动鼠标。
- 点击无变化生成 `ANCHOR_CLICK_NO_EFFECT`。

---

### L2 Universal Desktop Control Tree：通用树形电脑操控

职责：

- 作为兜底的“全息电脑操控”层，把任意屏幕拆成可遍历的 UI 树。
- 不是让模型直接点坐标，而是先生成可解释的候选 UI 元素树。

统一结构：

```text
DesktopTree
  root_window
  screen_state
  panels[]
  lists[]
  buttons[]
  text_blocks[]
  icons[]
  selected_items[]
  modal_dialogs[]
```

每个节点：

```text
node_id
role
text
bbox_norm
confidence
source: ocr/template/detector/vlm/calibrated
state: enabled/disabled/selected/hidden
children[]
evidence_ref
```

当前基础：

- `interaction/ui_anchor.py`
- `interaction/calibration.py`
- `perception/observation_graph.py`
- `execution/ui_action_executor.py`

下一阶段实现：

- 新增 `interaction/desktop_tree.py`。
- `ObservationBuilder` 输出 `DesktopTree` 派生摘要。
- VLM 只在 OCR/template/detector 置信度低时补全树节点，不直接执行。

验收：

- 在 HSR/桌面 UI 测试图中识别按钮、列表、弹窗、返回、确认。
- 树节点冲突时按 `screen_state > OCR exact > template > detector > calibrated > VLM` 排序。
- 兜底 Visual Agent 只能产出候选节点，不直接执行物理输入。

---

### L3 Perception and ObservationGraph：全息观察层

职责：

- 把屏幕、OCR、目标、危险、UI、任务、导航、战斗资源都变成证据图节点。
- 上层不直接读图像 dict，只读 `ObservationGraph` 或 `VerifierContext`。

当前基础：

- `perception/observation_graph.py`
- `execution/observation_verifiers.py`
- `evidence/`

下一阶段补强：

- 将 ObservationGraph 节点稳定分组：
  - UI：`ui_element`、`ocr_block`、`screen_state`
  - Embodied：`target_track`、`navigation_signal`、`landmark_signal`
  - Combat：`danger_signal`、`boss_phase_signal`、`telegraph_signal`、`combat_resource_signal`
  - System：`focus_state`、`window_state`、`profile_state`
- 增加 `ObservationQualityReport`：
  - stale frame
  - missing OCR
  - conflicting screen_state
  - low evidence coverage

验收：

- Verifier 拒绝没有 frame_id/roi_id/confidence 的 terminal success。
- 观察质量低时 Planner 降级为 observe/retry，而不是继续执行。

---

### L4 Controller Layer：UI、导航、战斗、采集的专用控制器

职责：

- 每个高频/复杂场景由专用控制器负责，不让 LLM 处理毫秒级操作。

控制器划分：

```text
UIController:
  click_anchor, click_text, select_list_item, confirm_dialog

NavigationController:
  route_segment, heading_servo, stuck_detector, local_recovery

CombatRuntime:
  boss_phase, danger_reflex, survival_policy, target_reacquire, checkpoint_resume

CollectionController:
  target_prompt, interact, quantity_delta, pickup_verifier

DialogueController:
  npc_detect, option_select, skip/advance, quest_state_verify

CraftingController:
  open_station, select_recipe, adjust_quantity, confirm, verify_inventory_delta
```

下一阶段实现重点：

- 新增 `controllers/` 或按现有目录拆分，统一控制器接口：

```python
class Controller(Protocol):
    controller_id: str
    def can_handle(action: SemanticAction, ctx: ControllerContext) -> bool: ...
    def execute(action: SemanticAction, ctx: ControllerContext) -> ControllerResult: ...
```

- `ControllerResult` 必须包含：
  - status
  - receipts
  - verifier_request
  - evidence_refs
  - recoverable
  - failure_code

验收：

- 同一 `SemanticAction` 只能被一个最高优先级 controller 接管。
- Controller 失败必须返回 failure_code，不能抛出裸异常给上层。

---

### L5 Semantic Action and Skill Contract：语义动作与 Skill

职责：

- Skill 不是鼠标宏，而是可迁移、可验证、可修复的能力契约。
- 原始录制轨迹只作为素材，执行主路径必须使用 semantic action + anchor/verifier。

当前基础：

- `execution/semantic_action.py`
- `recording/semantic_distiller.py`
- `app_service/skill_manager.py`

下一阶段补强：

- Skill v2 固定字段：

```text
skill_id
capsule_id
capabilities_required
capabilities_provided
preconditions
semantic_actions
ui_anchors
controllers
resources
verifiers
failure_modes
fallbacks
cleanup
risk_level
profile_compatibility
benchmark_stats
version
```

- SkillBinder 排序依据：
  - capability match
  - profile compatibility
  - verifier coverage
  - historical success rate
  - risk level
  - required resources ready

验收：

- 缺 verifier 的高风险 Skill 在 strict mode 被拒绝。
- 录制 UI Skill 换分辨率后仍走 anchor，不走 raw xy。
- Skill failure 自动生成 repair session 和 regression case。

---

### L6 Capsule Layer：游戏特调封装

职责：

- Core 只认协议，游戏差异全部进 Capsule。
- Capsule 是“游戏能力包”，包括 UI anchors、OCR/template、地图/任务知识、角色/队伍/Boss 数据、专属 Skill、专属 Verifier、专属 Benchmark。

当前基础：

- `capsules/capsule_protocol.py`
- `capsules/genshin/capsule.yaml`
- `capsules/hsr/capsule.yaml`
- `capsules/provider_registry.py`

下一阶段补强：

- Capsule manifest 增加显式 `controller_bindings`：

```yaml
controller_bindings:
  ui:
    anchors: resources/ui_anchors.yaml
  navigation:
    route_graph: resources/world_graph.yaml
    landmarks: resources/landmarks.yaml
  combat:
    boss_profiles: resources/boss_profiles.yaml
    team_profiles: resources/team_profiles.yaml
  dialogue:
    npc_patterns: resources/dialogue_patterns.yaml
```

- Capsule lifecycle 必须完整 uninstall：
  - subscription
  - slot
  - skill
  - transition
  - provider
  - controller binding

验收：

- install/uninstall/reinstall 不重复注册。
- 添加新游戏只需新 Capsule + tests，不改 core。
- Genshin hard embodied 与 HSR UI-first 共用同一上层协议。

---

### L7 Mission Graph and Planner：长程规划层

职责：

- 把用户目标编译成 Mission DAG，不直接输出坐标或键鼠操作。
- LLM 在这里做慢思考：任务拆解、异常解释、重规划、用户沟通。

当前基础：

- `planning/mission_graph.py`
- `planning/capability_planner.py`
- `planning/capsule_plan_templates.py`
- `runtime/context_compactor.py`
- `runtime/run_state_store.py`

下一阶段补强：

- MissionNode 固定执行协议：

```text
precondition_check
-> observe
-> bind_skill/controller
-> execute semantic action
-> verify
-> checkpoint
-> update summary
```

- 异常策略：

```text
local retry
-> controller fallback
-> skill fallback
-> capsule-specific repair
-> LLM replan
-> user confirmation
-> safe abort
```

- Agent replan 输入必须是：
  - `RunSummary`
  - current `ObservationGraph`
  - active `MissionNode`
  - failure signature
  - allowed next actions

验收：

- 上下文压缩后，Agent 不能依赖自由文本记忆断言历史事实。
- 中途异常能从最近 verified checkpoint 恢复。
- 每个 terminal node 都必须有 verifier 或 human-confirm policy。

---

### L8 Persona and User Interaction：角色化用户交互

职责：

- Agent 对用户的口吻可以复刻用户喜欢的角色，但不能影响安全策略和任务正确性。
- Persona 只改变表达层，不改变底层执行权限。

当前基础：

- `persona/`
- `app_service/*persona*`

下一阶段补强：

- Persona 输出分两层：
  - `CompanionMessage`：给用户看的自然语言。
  - `TechnicalTrace`：给开发者看的执行摘要。
- Persona 不允许说“已完成”除非 verifier ok。
- 异常时 Persona 必须给出：
  - 当前卡在哪一层
  - 是否需要用户确认
  - 下一步系统会自动做什么

验收：

- 同一个 failure，companion mode 与 developer mode 输出不同，但事实一致。
- Persona 不得覆盖 verifier/failure policy。

---

### L9 Product UX and Developer UX：用户与开发者体验

用户侧必须做到：

- 第一次使用：
  - 选择 Capsule
  - 选择窗口
  - 自动识别 UI anchors
  - 用户确认/拖拽校准
  - 运行 anchor validation
  - 进入 dry-run preview
- 录制 Skill：
  - 开始录制
  - 自动切分片段
  - 自动绑定 anchors
  - 生成 semantic draft
  - 用户确认
  - dry-run replay
  - 保存 versioned Skill
- 出错时：
  - 不显示大段 traceback
  - 显示“哪个层级失败、系统尝试了什么、是否需要你确认”

开发者侧必须做到：

- 新游戏接入模板：
  - `capsule.yaml`
  - `resources/ui_anchors.yaml`
  - `resources/screen_states.yaml`
  - `resources/keymap.yaml`
  - `resources/skills.yaml`
  - `tests/test_<capsule>_capsule.py`
- 一条命令跑验证：
  - manifest validation
  - anchor validation
  - dry-run mission
  - capsule boundary check
  - AuroraBench subset

下一阶段实现：

- 新增 `scripts/create_capsule.py`。
- 新增 `scripts/validate_capsule.py`。
- 新增 `docs/CAPSULE_DEVELOPER_GUIDE.md`。
- Desktop UI 增加 Calibration Wizard 页面和 Skill Workshop 页面。

---

## 2. 慢思考与快控制的协同协议

### 什么时候让 LLM 思考

LLM 只在这些场景进入：

- 用户目标解析。
- Mission DAG 编译或重编译。
- 未知 screen_state 的解释。
- 多个候选 Skill/路线/Boss 策略之间的权衡。
- 连续失败后的原因解释。
- Repair session 中从失败轨迹提炼新规则。
- 与用户进行角色化沟通。

LLM 输出限制：

- 只能输出 `MissionNode`、`SemanticAction`、`SkillPatchDraft`、`FailureExplanation`。
- 不得输出 raw coordinates、直接 key press、driver/OS 输入调用。
- 所有输出必须通过 validator。

### 什么时候交给实时系统

实时系统接管：

- 鼠标移动/点击。
- WASD 持续移动。
- Heading servo。
- Stuck recovery。
- 战斗闪避、Boss telegraph response。
- HP emergency survival。
- focus lost、release_all、deadman switch。

### 协同协议

```text
LLM proposes intent
-> Runtime validates allowed action
-> Controller executes bounded action
-> Verifier writes evidence
-> Summary updates LLM context projection
```

若 LLM 输出不可执行：

```text
reject
-> explain schema/risk reason
-> ask LLM for corrected high-level action
-> if repeated: fallback template or user confirmation
```

---

## 3. 本地多模态模型接入方案

### 目标

建立端云混合模型层：

```text
Deterministic algorithms first
-> Local VLM for frequent visual grounding
-> Cloud LLM for difficult reasoning / backup
```

本地模型优先承担：

- 屏幕状态描述。
- UI 树补全。
- OCR/template 冲突仲裁。
- 未知按钮/图标语义识别。
- 失败帧解释。
- Skill 录制后的语义动作草稿。
- Benchmark failure 自动归因。

云端模型承担：

- 长程任务规划。
- 多 Capsule 跨域策略。
- 复杂 repair patch 生成。
- 高质量角色化表达。

### Provider 设计

当前 `LLMProvider` 是文本规划接口。下一阶段新增：

```python
class VisionLLMProvider(Protocol):
    name: str
    def describe_image(self, image: ImageInput, prompt: str) -> VisionResult: ...
    def ground_ui(self, image: ImageInput, query: str) -> UIGroundingResult: ...
    def classify_screen(self, image: ImageInput, candidates: list[str]) -> ScreenStateResult: ...
    def explain_failure_with_image(self, summary: dict, image: ImageInput) -> dict: ...
```

新增通用 provider：

```text
OpenAICompatibleLocalProvider
  base_url: LOCAL_VLM_BASE_URL
  model: LOCAL_VLM_MODEL
  api_key: LOCAL_VLM_API_KEY optional
  supports_images: true/false self-test
  timeout_sec
  max_pixels
  max_calls_per_minute
```

默认 LM Studio 配置：

```env
LOCAL_VLM_PROVIDER=openai_compatible
LOCAL_VLM_BASE_URL=http://127.0.0.1:1234/v1/chat/completions
LOCAL_VLM_MODEL=gemma-3n-e4b 或用户 LM Studio 中的实际 model id
LOCAL_VLM_API_KEY=lm-studio
LOCAL_VLM_TIMEOUT_SEC=20
```

### 用户友好部署路径

优先级 1：用户已有 LM Studio。

- Desktop UI 提供“连接本地模型”按钮。
- 自动探测 `127.0.0.1:1234/v1/models`。
- 展示模型列表，用户选择 E4B/E2B。
- 运行三项自检：
  - text chat
  - image describe
  - UI grounding JSON output

优先级 2：用户已有 Ollama/vLLM/SGLang。

- 只要求 OpenAI-compatible endpoint。
- 不在 Aurora 内管理模型下载。
- 提供配置向导和健康检查。

优先级 3：国内用户下载引导。

- 文档提供两条路径：
  - LM Studio 内搜索并下载。
  - 魔搭/ModelScope 或 Hugging Face 镜像下载后导入本地推理工具。
- Aurora 不强行集成下载器，避免许可证、网络、模型格式和硬件差异带来的维护成本。

### E4B vs E2B 评估

新增 `LocalVlmBench`：

任务集：

- UI button grounding：找按钮、返回、确认、列表项。
- Screen state classification：菜单/背包/地图/对话/战斗/合成。
- Failure frame explanation：点击无效、目标丢失、低血危险、未知弹窗。
- Skill trace distillation：从截图+事件描述生成 semantic action draft。

指标：

```text
latency_p50
latency_p95
json_valid_rate
screen_state_accuracy
ui_grounding_iou
failure_explanation_useful_rate
cost_per_1000_calls
local_memory_gb
fallback_rate_to_cloud
```

决策规则：

- E2B 若 accuracy >= E4B 的 90% 且 latency/memory 明显更优，则默认推荐 E2B。
- E4B 用于复杂 failure explanation 和难 UI。
- 允许任务级路由：简单 UI 用 E2B，复杂 screen/frame 用 E4B，长程规划用云端。

---

## 4. 异常处理与长期运行

异常必须分层定位：

```text
L0 physical: focus lost / lease expired / unauthorized window
L1 motor: click no effect / coordinate mismatch
L2 desktop tree: node missing / conflicting candidates
L3 observation: stale frame / low evidence / unknown screen
L4 controller: stuck / target lost / combo break / NPC option missing
L5 skill: precondition failed / verifier failed
L6 capsule: resource missing / profile mismatch
L7 mission: route invalid / task state changed
L8 persona: user confirmation required
L9 product: onboarding/config incomplete
```

统一恢复阶梯：

```text
retry same action once
-> refresh observation
-> controller local recovery
-> skill fallback
-> capsule template fallback
-> LLM replan
-> user confirmation
-> safe abort with release_all
```

长期运行要求：

- 每个 MissionNode 成功后写 checkpoint。
- 每 N 分钟进入 periodic safe point。
- LLM context 只保留 Hot/Warm 投影；事实源是 EvidenceGraph、RunStateStore、RecordSession、Capsule knowledge。
- 恢复前必须 revalidate：
  - window
  - profile
  - capsule version
  - skill version
  - last verified checkpoint

---

## 5. 分阶段执行计划

### Phase 1：分层协议硬化

实现：

- `PhysicalActionReceipt`
- `ControllerResult`
- `DesktopTree`
- `ObservationQualityReport`
- Controller 通用 Protocol

验收：

- 所有上层执行路径不再直接依赖裸坐标或裸输入。
- 缺 evidence 的 terminal success 被拒绝。

### Phase 2：UI/UX 与开发者体验

实现：

- Calibration Wizard 页面。
- Skill Workshop 页面。
- Capsule scaffolding 脚本。
- Capsule validation 脚本。
- Developer Guide。

验收：

- 新建一个 demo capsule 不需要手写 boilerplate。
- 用户能完成 anchor 校准、dry-run preview、Skill 保存。

### Phase 3：Local VLM Provider

实现：

- `VisionLLMProvider`。
- `OpenAICompatibleLocalProvider`。
- LM Studio health check。
- LocalVlmBench。
- Model routing policy。

验收：

- 本地 LM Studio E4B 能完成 text + image 自检。
- E2B/E4B 能在同一 bench 下输出对比报告。
- 本地 VLM 不可用时自动降级到 deterministic/cloud route。

### Phase 4：复杂任务 Controller 完善

实现：

- DialogueController。
- CraftingController。
- CollectionController。
- NavigationController 与 BossCombatRuntime 接入统一 Controller protocol。

验收：

- HSR UI-heavy daily/material flow 能全程 dry-run。
- Genshin 采集链路能执行：传送、导航、采集、验证。
- BossBench 继续通过。

### Phase 5：Failure-to-Repair 全链路

实现：

- FailureSignature 按层级分类。
- failure -> replay seed -> repair session -> skill/capsule patch -> benchmark regression。
- Persona 用户解释与 Developer trace 双输出。

验收：

- 每个重大失败能复跑。
- 每个修复都有 before/after 指标。
- 用户能选择是否把成功兜底沉淀为 anchor/skill/rule。

---

## 6. 交给 Coding Agent 的实施要求

硬性边界：

- 不实现真实商业客户端自动化。
- 不做内存读取、进程注入、反作弊绕过、驱动级输入。
- 不把游戏专属逻辑写入 core。
- 不让 LLM 输出直接键鼠命令。

每个 PR 必须包含：

- 对应层级说明。
- 新增/修改的 service contract。
- 单元测试。
- 至少一个 integration 或 benchmark 测试。
- Safety boundary 说明。

最低总体验收：

```text
python -m pytest -q
python -m compileall core interaction perception execution planning runtime combat capsules benchmarks app_service tests -q
python scripts/run_aurorabench.py --suite all --mode dry-run --output-dir benchmark_reports/<run>
rg "\b(genshin|hsr|honkai|star_rail)\b|崩坏|星穹" core --glob "*.py"  # must be no matches
```

---

## 7. 批判性结论

Aurora 当前已经有正确方向：Capsule、Skill、UIAnchor、ObservationGraph、EvidenceGraph、InputLease、BossCombatRuntime、Benchmark 都已经成形。但要成为真正有壁垒的平台，下一阶段不能继续只做“功能点”，必须把每一层的服务协议硬化。

真正的创新点是：

- 用系统工程减轻大模型负担。
- 用低层确定性控制解决实时性。
- 用 Observation/Evidence/Verifier 解决幻觉。
- 用 Capsule 解决泛化与特调的矛盾。
- 用 Skill/Record/Repair 解决长期进化。
- 用本地 VLM 解决高频视觉理解成本与延迟。

只有这样，Aurora 才不是“一个会点鼠标的 Agent”，而是一套能治理复杂视觉任务的 Agent Runtime。
