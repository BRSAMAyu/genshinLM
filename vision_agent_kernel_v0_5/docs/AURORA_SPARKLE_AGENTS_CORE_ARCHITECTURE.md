# Sparkle Agent Kernel: L0-L9 多层神经运行时架构 (ADR)

> **文档定位**: 本文档是 `SPARKLE_AGENT_KERNEL_DESIGN.md` 的运行时分层 ADR（Architecture Decision Record）。
> 它细化了 L0-L9 控制分层的实现方案，但不替代总纲。
>
> **约束修正**: 云端大脑为 cloud-first 而非 cloud-required。系统必须在网络不可用时退化为本地小脑 + 离线 fallback。
>
> **战略目标**：建立一套完全解耦的、”大脑-小脑-脑干-脊髓-神经”多层神经元架构，打通 **”信息抽取-推理-动作-反馈”** 闭环，支撑以原神主线自主通关（包含复杂 3D 寻路、野外战斗、UI 动态变化、突发谜题）为核心试炼场的通用游戏 AI 框架。
>
> **设计哲学**：
> 1. **脑脑分工，彻底解决 GPU 瓶颈**：大脑慢思考（LLM/VLM）全云端托管，脊髓快反射（YOLO 战斗）本地超轻量运行。
> 2. **拒绝 if-else 规则地狱，拥抱“知识压缩（Skill）”**：Skill 并非死宏，而是包含动态 Fallback 与 VLM 推理补偿的意图流。
> 3. **人机始终在环，交互伴侣化**：内置自然语言交互伴侣（Companion Agent），用悬浮窗热注入（Runtime Overrides）代替硬编码调参和修改源码，结算时交互式写入 YAML 实现自愈进化。

---

## 一、 核心痛点与解决路径 (v1.1 实战对齐)

### 1.1 算力分治：全云端策略大脑 vs 本地轻量神经
* **解决路径**：**大脑层（Cerebrum）100% 托管给云端多模态大模型**。所有涉及高层视觉理解（如解密谜题分析）、任务长程规划（Mission Graph 生成）以及连续失败时的灾难性重规划，均通过 API 异步发送至云端（如 Gemini 3.5）。本地仅保留极轻量的小脑（OCR、UI树）、脑干（PID导航）与脊髓（YOLO战斗），彻底释放本地 GPU 压力，确保游戏画面丝滑。

### 1.2 行为压缩：声明式 YAML 胶囊与插件化 Python 适配器
* **解决路径**：**游戏与内核 100% 解耦的胶囊（Capsule）机制**。胶囊结构包括两部分：声明式 YAML（定义 UI 状态、按键映射、路网与连招）与插件化 Python 适配器（负责定制化的 PuzzleSolver 扩展），内核保持 100% 游戏无关。

### 1.3 联调革命：悬浮伴侣窗热注入与交互式沉淀
* **解决路径**：**伴侣对话 Agent（Companion Agent）与运行时参数热注入（Runtime Overrides）**。
  - 伴侣作为桌面悬浮窗存在。当遇到卡点（如 OCR 置信度低）时，伴侣展示对话，用户可输入自然语言（如“将领取选项的置信度阈值调低到 0.2 并强行点击”）。
  - 伴侣解析指令，在**共享内存状态总线**中热注入覆盖参数，控制器无重启瞬间生效。
  - **交互式会话沉淀 (Interactive Evolution)**：在结算时，伴侣主动询问用户：“刚才的热修复成功解决了卡点，是否将其永久写入当前胶囊的 YAML 规则库？”，确认后自动写入更新。

---

## 二、 专项技术栈与链路细节硬化 (v1.1 深度共识)

### 2.1 小脑树解析：模板锚点定位与相对几何聚类的聚合
为了在大脑层（Cerebrum）提供最易读、最便利的文本输入信息，并确保在游戏版本 UI 微调时具有极致的鲁棒性，小脑的 `DesktopTree` 动态 UI 树采用**模板定位与空间几何位置聚类的聚合路线**：
1. **模板锚点匹配 (Template Anchor)**：在胶囊中定义核心 UI 界面边界的特征模板图（如：大面板背景边框、关闭按钮、背包图标）。运行时使用超快速的 OpenCV 匹配（或 YOLO 边界框分类）确定大容器面板的具体坐标与边界框 (ROI)。
2. **局部限制性 OCR**：只在大容器面板的坐标范围内（ROI）启动本地轻量 OCR 引擎扫描，屏蔽游戏 3D 大世界背景中的杂乱文字干扰。
3. **相对几何位置聚类 (Geometric Clustering)**：对 ROI 内提取出的所有文字框进行空间排布聚类（根据水平相近性、垂直对齐度以及 parent-child 相对缩进关系）。自动将空间对齐的节点聚类为更高级的逻辑单元（例如：自动将“标题文本”、“说明正文”与“确认按钮”归拢并聚类为一个高级的 `ModalDialog` 节点）。
4. **模型易读序列化**：构建好具有清晰层级的 `DesktopTree` 后，以极简的结构化 XML 或 JSON（包含层级节点 id、label 与归一化位置）输出给云端 API。这极大地减小了 Token 消耗，使云端大脑能轻易定位节点。

### 2.2 周围神经层：主动让权与即时挂起 (Human-first Intercept)
当物理用户插手游戏操控时，系统必须提供绝对的主动避让与权属转让：
1. **物理干预持续监测**：外周神经层（L0）在后台以 100Hz 频率实时监测 Windows 底层物理外设的真实变化：
   - 物理鼠标偏离当前 Agent 轨迹的位移差超出微小安全阈值（如 > 10 像素）。
   - 物理键盘检测到任何非系统注入的物理按键触发。
   - 游戏窗口失去焦点 (Focus Lost)。
2. **瞬间释放与挂起 (Interrupt & Clear)**：一旦触发干预，`InputLeaseManager` 强行收回当前活跃的租约（Lease），向物理驱动层下发 `release_all()` 指令瞬间清空所有持续的长按状态，彻底消除物理粘滞。
3. **伴侣状态转接**：暂停 Agent 自主决策循环。伴侣悬浮窗瞬间切换至“用户手动干预中”的静止防打扰状态，气泡框温柔提示：“旅行者，检测到你在亲自操作，我已乖乖停下，需要我重新接管时随时叫我哦！”，彻底杜绝“人机争抢”的负向体验。

### 2.3 对话快进策略：智能对齐快进与分支拦截 (Intelligent Dialogue Skipping)
主线剧情跳过不再采用盲目的按键连点，而采用**智能对齐与拦截机制**：
1. **智能对齐快进**：脑干对话控制器（DialogueController）结合小脑的 UI 状态判定，检测到处于剧情对话状态时，开启一个受控快进线程，以 3-5Hz（约每 200-300ms 一次）的合理频率模拟 Space/F/左键，既满足极速跳过，又完全避免了极高频盲点导致连点失效或驱动卡死。
2. **分支选项拦截**：一旦小脑监测到屏幕上弹出了多分支选择框，**对话快进线程瞬间挂起**。小脑利用 `DesktopTree` 极速定位所有选项的文字文本。
3. **选项判定决策**：首先与胶囊中预设的最佳选项映射库（YAML）进行比对；若选项完全属于未知内容，则向云端托管大脑发出异步多模态解析（VLM/LLM），判定最优剧情选项，点击选定目标项后，重新恢复对话快进。
4. **CG 与黑屏避让**：在剧情黑屏加载、转场或进入过场动画（CG）时，自动暂停物理快进，防止画面丢失和操作溢出，确保剧情过渡绝对安全。

---

## 三、 多层神经元运行时架构 (Neurological Architecture)

本框架的多层神经元运行边界定义如下：

* **L7-L8 大脑 (Cerebrum / Brain) | 0.1Hz - 0.2Hz (延迟 2000ms - 5000ms)**
  - 职责：多模态解密分析、终极目标编译、重规划、伴侣自然语言转换。
  - 运行介质：云端 API。
* **L5-L6 小脑 (Cerebellum) | 2Hz - 5Hz (延迟 200ms - 500ms)**
  - 职责：构建 `DesktopTree`（模板锚点定位 + 相对几何聚类）、OCR 动态比对、全局路径编译、热注入配置拦截、交互式 YAML 写回。
  - 运行介质：本地 OCR 引擎 + 共享内存总线。
* **L3-L4 脑干 (Brainstem) | 10Hz - 20Hz (延迟 50ms - 100ms)**
  - 职责：3D 寻路 PID 导航控制、智能快进对话与分支拦截、卡死状态自动判定与脱卡、采集对齐。
  - 运行介质：本地确定性导航控制算法。
* **L1-L2 脊髓 (Spinal Cord) | 50Hz (延迟 10ms - 20ms)**
  - 职责：实时战斗反射、危险预警检测、HP 紧急药剂抬升、切人时机控制、队伍连招状态机（Combat Combo State Machine）。
  - 运行介质：本地超轻量级 YOLO 目标检测引擎 + 队伍状态机。
* **L0 物理神经与安全层 (Motor Nerves) | 100Hz (延迟 < 5ms)**
  - 职责：窗口焦点绝对劫持、`InputLease` 物理输入释放与用户干预抢占劫持（Human-first Intercept）、死人开关（Deadman switch）、Bezier 鼠标轨迹人类化生成。
  - 运行介质：本地安全物理执行器。

---

## 四、 核心接口与模块衔接设计 (Programmatic Design)

```python
"""
aurora/kernel/neurology/contracts.py
通用多层神经元游戏 Agent 框架协议
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Literal, Any, Sequence, Dict
from uuid import UUID

# ===========================================================================
# L0 - L2: 物理与外周神经元 (Motor & Peripheral Nerves)
# ===========================================================================

@dataclass(frozen=True, slots=True)
class NormalizedCoordinate:
    nx: float  # 0.0 ~ 1.0 (窗口归一化 X)
    ny: float  # 0.0 ~ 1.0 (窗口归一化 Y)

@dataclass(frozen=True, slots=True)
class PhysicalActionReceipt:
    lease_id: UUID
    issued_at: float
    expires_at: float
    action_type: Literal["click", "hover", "key_press", "drag", "scroll"]
    execution_latency_ms: float
    focus_maintained: bool

class InputLeaseManager(Protocol):
    """L0 物理安全层：控制物理键鼠的绝对控制权、安全截断与用户干预强占检测"""
    def acquire_lease(self, owner: str, duration_sec: float, priority: int) -> UUID | None: ...
    def release_lease(self, lease_id: UUID) -> bool: ...
    def verify_window_focus(self) -> bool: ...
    def detect_human_intervention(self) -> bool: ...  # 100Hz 检测物理键鼠位移或按键
    def emergency_release_all(self) -> None: ...  # 释放所有按键锁


# ===========================================================================
# L3: 脊髓与实时反射层 (Spinal Cord & Reflexes)
# ===========================================================================

@dataclass(frozen=True, slots=True)
class ThreatSignal:
    threat_type: Literal["projectile", "telegraph_aoe", "boss_animation_charge", "low_hp"]
    severity: float  # 0.0 ~ 1.0
    direction_degrees: float
    time_to_impact_ms: int

@dataclass(frozen=True, slots=True)
class CombatCommand:
    reflex_action: Literal["dodge", "dash", "cast_skill_e", "cast_burst_q", "combo_normal_attack", "switch_character", "heal_emergency"]
    target_character_index: int = 1
    reason: str = ""

class SpinalReflexAgent(Protocol):
    """L1-L2 脊髓层：50Hz YOLO+Combo 连招状态机战斗引擎"""
    def evaluate_threats(self, latest_frame: Any) -> Sequence[ThreatSignal]: ...
    def tick_combat_reflex(self, threats: Sequence[ThreatSignal], current_combo_step: int) -> CombatCommand | None: ...


# ===========================================================================
# L4 - L5: 脑干与小脑层 (Brainstem & Cerebellum)
# ===========================================================================

@dataclass(frozen=True, slots=True)
class DesktopNode:
    node_id: str
    role: Literal["button", "list_item", "dialog_text", "icon", "slider", "modal"]
    label: str
    bbox: tuple[float, float, float, float]
    confidence: float
    state: Literal["enabled", "disabled", "selected", "hidden"]
    source: Literal["ocr", "template_match", "vlm_grounding", "heuristic"]

@dataclass(frozen=True, slots=True)
class DesktopTree:
    timestamp: float
    screen_state: str
    nodes: tuple[DesktopNode, ...]
    is_modal_active: bool

@dataclass(frozen=True, slots=True)
class RouteSegment:
    segment_id: int
    target_position: tuple[float, float, float]  # 3D 坐标系 (x, y, z)
    movement_type: Literal["run", "glide", "climb", "swim"]
    speed_factor: float = 1.0

class CerebellumController(Protocol):
    """L5-L6 小脑层：构建屏幕 UI 树（模板锚定+几何聚类）与路径编译，处理拦截覆盖"""
    def locate_ui_panel_roi(self, frame: Any, panel_template_id: str) -> tuple[float, float, float, float] | None: ...  # 1. 模板定位
    def parse_desktop_tree(self, frame: Any, active_roi: tuple[float, float, float, float] | None = None) -> DesktopTree: ...  # 2. 局部几何聚类
    def align_ui_anchor(self, tree: DesktopTree, target_label: str, active_overrides: Dict[str, Any]) -> DesktopNode | None: ...
    def compile_route(self, current_pos: tuple[float, float, float], destination: tuple[float, float, float]) -> Sequence[RouteSegment]: ...
    def commit_yaml_patch(self, capsule_id: str, patch_data: Dict[str, Any]) -> bool: ...  # 交互式会话结束沉淀写入


class BrainstemNavigator(Protocol):
    """L3-L4 脑干层：物理 PID 导航与自动脱卡"""
    def update_heading_servo(self, current_yaw: float, target_segment: RouteSegment) -> None: ...
    def detect_stuck_state(self, current_pos: tuple[float, float, float], elapsed_sec: float) -> bool: ...
    def execute_unstuck_routine(self, method: Literal["jump", "dash_back", "teleport_fallback"]) -> None: ...


class DialogueController(Protocol):
    """L3-L4 脑干层：负责智能快进跳过对话与多分支选项拦截判定"""
    def tick_dialogue_skip(self, tree: DesktopTree) -> None: ...  # 3-5Hz 极速对齐跳过
    def is_option_present(self, tree: DesktopTree) -> bool: ...  # 检测分支选择框
    def select_best_option(self, tree: DesktopTree, option_registry: Dict[str, Any]) -> DesktopNode | None: ...  # 选择最优项


# ===========================================================================
# L7 - L8: 大脑与战略决策层 (Cerebrum & Planner)
# ===========================================================================

@dataclass(frozen=True, slots=True)
class AgentGoal:
    goal_id: str
    description: str
    success_criteria: str
    time_limit_sec: float = 1800.0

@dataclass(frozen=True, slots=True)
class MissionNode:
    node_id: str
    skill_intent: str
    preconditions: tuple[str, ...]
    expected_state: str
    risk_level: Literal["low", "medium", "high"]

@dataclass(frozen=True, slots=True)
class MissionGraph:
    graph_id: str
    nodes: tuple[MissionNode, ...]
    edges: tuple[tuple[str, str], ...]
    current_node_index: int = 0

@dataclass(frozen=True, slots=True)
class RepairPatch:
    replan_required: bool
    inject_skills: tuple[str, ...]
    runtime_overrides: dict[str, Any]
    explanation: str

class CerebrumAgent(Protocol):
    """L8 大脑层：云端托管 API 大脑"""
    def compile_mission(self, goal: AgentGoal) -> MissionGraph: ...
    def diagnose_failure(self, failed_node: MissionNode, screenshot: Any, error_trace: str) -> RepairPatch: ...
    def solve_visual_puzzle(self, puzzle_image: Any, scene_description: str) -> tuple[str, ...]: ...


# ===========================================================================
# L9: 伴侣交互总线 (Companion Dialogue Agent)
# ===========================================================================

@dataclass(frozen=True, slots=True)
class UserIntervention:
    text: str
    override_priority: int = 100

@dataclass(frozen=True, slots=True)
class CompanionResponse:
    display_message: str
    technical_action: str
    patch_draft: dict[str, Any] = field(default_factory=dict)

class CompanionAgent(Protocol):
    """L9 交互层：悬浮窗对话伴侣"""
    def handle_user_message(self, message: UserIntervention, current_graph: MissionGraph) -> CompanionResponse: ...
```

---

## 五、 核心闭环：主线任务执行流与热注入过程

我们追踪一段真实主线任务的运行状态，还原热注入与 YAML 沉淀的全过程：

### 5.1 主线任务正常执行与用户抢占拦截
1. **[云端大脑]** 接收到“通关魔神任务：与凯瑟琳交互”的指令，编译生成 MissionGraph。
2. **[小脑与脑干]** 协同执行：小脑编译 3D 导航路线，脑干利用 20Hz PID 控制器物理驱动角色奔向凯瑟琳。
3. **[物理用户瞬间夺权 (Human-first Intercept)]**：角色在奔跑途中，玩家突然发现旁边有个宝箱，手动移动了物理鼠标。**[外周神经层 (L0)]** 瞬间捕获该变化，强行释放全部 Agent 按键租约并下发 `release_all()`，Agent 决策完全挂起。悬浮伴侣窗立刻弹出：*“旅行者，检测到你在亲自操作，我已乖乖停下，需要我重新接管时随时叫我哦！”*。
4. **[任务重新恢复]**：玩家手动捡完宝箱，点击伴侣悬浮窗的“请继续”。Agent 无缝接管，继续跑向凯瑟琳，按下 'F' 进入对话。

### 5.2 智能快进与对话分支拦截
5. **[对话控制器 (L3)]** 检测到进入对话场景，开启 3-5Hz 脉冲模拟点击（Space/F）进行智能快进。突然，界面变暗，凯瑟琳对话框弹出了“【新活动】风花节派遣”和“领取「每日委托」奖励”等多分支选项。
6. 快进点击瞬间暂停。**[小脑]** 立即截取当前画面，通过 OpenCV 模板锚定凯瑟琳对话框 ROI 区域，启动局部 OCR 并通过几何对齐聚类出 `DesktopTree` 选项列表。
7. 对话控制器拿到了这组清爽的 `DesktopTree` 选项文本，与胶囊配置进行匹配。发现“【新活动】风花节派遣”因为新版 UI 活动遮挡了部分字样，导致 OCR 置信度仅为 0.25，比对失败，引发卡点。
8. 系统不关机崩溃，而是将异常上报至 **[伴侣 Agent (L9)]** 并唤醒悬浮伴侣询问用户。
9. 用户输入：“没关系，调低阈值到 0.2 并强行点击第一个选项。”
10. **[伴侣 Agent]** 将 `{"Daily_Commission_Option": {"override_threshold": 0.2, "force_execute": "click"}}` 热注入到共享内存的**状态总线 (StateBus)** 中。
11. **[小脑]** 监测到覆盖项，瞬间以 0.25 的匹配分数成功击中目标并触发物理点击。卡点顺利突破！对话快进恢复！

### 5.3 交互式 YAML 永久沉淀
12. 任务完成，剧情结束退出到大世界。在结算时，伴侣悬浮窗弹出询问：
    > “旅行者，刚才下调置信度的热配置让我们顺利领取了奖励！是否需要我将该修改永久保存到你当前蒙德凯瑟琳的 YAML 规则库中，这样以后就再也不会卡住啦！”
13. 用户点击“确认永久保存”。
14. **[小脑]** 调用 `commit_yaml_patch` 将 `override_threshold: 0.2` 写入本地胶囊的 `resources/ui_anchors.yaml` 中，实现完全受控的“绝不重复犯同样错误”的自愈闭环。

---

*文档版本：通用架构标准规范 v1.1*
*该方案彻底解决了 GPU 负载问题，保障了高频战斗反射与低频战略规划的彻底解耦，并通过伴侣窗大幅降低了系统维护成本。*
