# Genshin 错误恢复架构文档

> Sparkle Vision Agent Kernel v0.5 — 统一错误恢复基础设施
> 版本: 1.0 | 日期: 2026-05-30 | 状态: 核心实现完成

---

## 文档目的

本文档定义 Sparkle Agent 在原神中长时间自主运行（15分钟至数小时）所需的统一错误恢复架构。覆盖跨场景的错误级联处理和全局恢复状态机设计，是自主运行的最关键基础设施。

**与现有代码的集成关系:**
- `control/sentinel/recovery_recipe.py` — 恢复配方基类
- `control/sentinel/sentinel_runtime.py` — 看门狗运行时
- `control/sentinel/recipes.py` — 8 个内置恢复配方
- `control/recovery_policy.py` — 挫折感驱动恢复策略
- `control/progress_supervisor.py` — 进度监督与中断生成
- `execution/crash_recovery.py` — 崩溃恢复与会话状态管理
- `core/events.py` — 中断事件定义
- `core/state_bus.py` — 状态总线
- `control/sentinel/somatic_state.py` — 体感状态快照

---

## 第一章：错误分类体系

### 1.1 按来源分类

```
错误来源分类树:
├── 感知错误 (Perception Errors)
│   ├── 检测器失效: YOLO 置信度 < 0.3
│   ├── 跟踪器发散: BoT-SORT track_id 跳变
│   ├── OCR 误识别: 文字提取置信度 < 0.5
│   ├── VLM 超时: 模型响应 > 5s
│   ├── 屏幕分类错误: state 置信度 < 0.6
│   └── 深度估计漂移: depth 偏差 > 30%
│
├── 导航错误 (Navigation Errors)
│   ├── 卡地形: obstacle_pressure > 0.7 且 slope ≈ 0
│   ├── 目标消失: target_track.state == LOST > 3s
│   ├── 路径规划失败: 无法到达目标区域
│   ├── 传送失效: teleport 操作无响应
│   └── 地图锚点丢失: waypoint 无法定位
│
├── 战斗错误 (Combat Errors)
│   ├── 角色死亡: hp_ratio == 0 for all characters
│   ├── 队伍全灭: 复活后立即再次死亡
│   ├── 连击中断: combo 未触发机制
│   ├── 元素反应错误: elemental reaction 顺序错误
│   ├── Boss 机制未识别: 新机制响应失败
│   └── 树脂耗尽: condensed_resin == 0 during domain
│
├── UI 错误 (UI Errors)
│   ├── 按钮未找到: button ROI 置信度 < 0.4
│   ├── 未知弹窗: screen_state == unknown
│   ├── 界面层级混乱: menu depth 不匹配
│   ├── 输入无响应: input_response_timeout > 5s
│   ├── 弹窗阻塞: blocking_notification detected
│   └── 加载卡死: loading_screen timeout > 60s
│
├── 输入错误 (Input Errors)
│   ├── 焦点丢失: target_window focus == False
│   ├── InputLease 过期: expires_at <= now
│   ├── 死锁检测: 线程无心跳 > heartbeat_timeout
│   ├── 输入队列满: command_queue == Full
│   └── 物理按键异常: key state 与预期不符
│
├── 系统错误 (System Errors)
│   ├── 游戏进程崩溃: process_alive == False
│   ├── GPU 驱动失败: graphics_crash detected
│   ├── 网络断开: network_disconnect > 30s
│   ├── 内存溢出: mem_usage > 90%
│   └── 版本更新弹窗: patch_notice detected
│
└── 环境错误 (Environment Errors)
    ├── 体力耗尽: stamina_ratio < 0.05
    ├── 环境伤害: hazard_level == DANGER/LETHAL
    ├── 溺水/窒息: oxygen_ratio < 0.15
    ├── 地形突变: region 切换时位置不一致
    └── 天气影响: storm/rain visibility < 0.4
```

### 1.2 按严重性分级

| 级别 | 优先级 | 名称 | 特征 | 响应要求 |
|------|--------|------|------|----------|
| **CRITICAL (P0)** | 0 | 紧急停止 | 必须立即 release_all | 触发 EMERGENCY_STOPPED 模式 |
| **SEVERE (P1)** | 10 | 严重错误 | 可能导致会话终止 | 触发看门狗 + 中断升级 |
| **MODERATE (P2)** | 20-30 | 中等错误 | 单次恢复可解决 | 执行恢复配方 |
| **MINOR (P3)** | 40-100 | 轻微错误 | 自行修复或忽略 | 微调策略或记录 |

```python
# Interrupt 严重性与优先级映射 (core/events.py)
@dataclass(order=True, slots=True)
class Interrupt:
    priority: int        # 0=P0_EMERGENCY, 10=P1_WATCHDOG, 20=P2_HUMAN_OVERRIDE, 30=P3_ACTION_BLOCK, 40=P4_RECOVERY, 50=P5_TRACKING, 100=P6_IDLE
    code: str            # 错误码
    recoverable: bool    # 是否可恢复
    requires_input_release: bool  # 是否需要释放输入

# P0 紧急中断示例
Interrupt(
    priority=0,
    code="FOCUS_LOST",
    source="InputWorker",
    requires_input_release=True
)

# P2 中断示例
Interrupt(
    priority=20,
    code="TARGET_LOST",
    source="progress_supervisor",
    payload={"missing_duration_ms": track.missing_duration_ms}
)
```

### 1.3 按传播性分类

| 类型 | 定义 | 级联风险 | 阻断策略 |
|------|------|----------|----------|
| **单点错误** | 仅影响当前操作，不传播 | 低 | 局部恢复配方 |
| **级联错误** | 错误触发后续错误 | 中 | 在第二节点阻断 |
| **系统性错误** | 根本性问题影响所有操作 | 高 | 全面状态重置 |

### 1.4 量化指标

```python
# 感知错误量化 (perception/genshin_screen_classifier.py)
class GenshinScreenClassifier:
    STATE_CONFIDENCE_MIN = 0.6      # 屏幕状态分类最低置信度
    OCR_CONFIDENCE_MIN = 0.5        # OCR 文字识别最低置信度
    DETECTION_CONFIDENCE_MIN = 0.3  # 目标检测最低置信度

# 进度错误量化 (control/progress_supervisor.py)
class ProgressSupervisorConfig:
    stale_penalty: float = 8.0           # 陈旧帧惩罚
    low_visibility_penalty: float = 5.0   # 低可见度惩罚
    flat_progress_penalty: float = 2.0     # 平坦进度惩罚
    oscillation_penalty: float = 4.0       # 振荡惩罚
    escalate: float = 80.0                 # 升级阈值
    target_lost_after_ms: float = 3000.0   # 目标丢失超时

# 恢复策略量化 (control/recovery_policy.py)
class RecoveryPolicy:
    # 挫折感阈值
    ESCALATE_THRESHOLD = 80.0         # 升级到中断
    STUCK_BY_SLOPE_THRESHOLD = 5.0    # 挫折斜率阈值
    FLAT_SLOPE_EPSILON = 0.02         # 平坦进度容忍
```

---

## 第二章：全局恢复状态机

### 2.1 状态机定义

```
全局恢复状态机:

    ┌─────────────┐
    │   NORMAL   │◄──────────────────────────────────────────┐
    │  (正常执行) │                                           │
    └──────┬──────┘                                           │
           │ 异常检测 (frustration >= 10 或 interrupt)         │
           ▼                                                 │
    ┌─────────────┐                                          │
    │ ANOMALY     │──────────────────────────────────────────┤
    │  (异常检测) │                                           │
    └──────┬──────┘                                           │
           │ 诊断完成                                         │
           ▼                                                 │
    ┌─────────────┐                                          │
    │ DIAGNOSE    │──────────────────────────────────────────┤
    │  (诊断分析) │                                           │
    └──────┬──────┘                                           │
           │ 策略选择                                         │
           ▼                                                 │
    ┌─────────────┐                                          │
    │ PLAN        │──────────────────────────────────────────┤
    │  (策略规划) │                                           │
    └──────┬──────┘                                          │
           │ 恢复执行                                         │
           ▼                                                 │
    ┌─────────────┐                                          │
    │ RECOVER    │──────────────────────────────────────────┤
    │  (恢复执行) │                                           │
    └──────┬──────┘                                          │
           │ 验证成功?                                        │
     ┌─────┴─────┐                                           │
     │           │                                           │
    Yes          No                                          │
     │           │                                           │
     ▼           ▼                                           │
┌────────┐  ┌────────────┐                                    │
│NORMAL  │  │ ESCALATE  │───────────────────────────────────┘
└────────┘  │  (升级)   │
            └────────────┘
```

### 2.2 状态转移规则

```python
# 状态转移表
STATE_TRANSITIONS = {
    ("NORMAL", "anomaly_detected"): "ANOMALY",
    ("NORMAL", "interrupt_received"): "ANOMALY",
    ("ANOMALY", "diagnosis_complete"): "DIAGNOSE",
    ("DIAGNOSE", "strategy_selected"): "PLAN",
    ("PLAN", "recovery_executed"): "RECOVER",
    ("RECOVER", "verification_success"): "NORMAL",
    ("RECOVER", "verification_failed"): "ESCALATE",
    ("RECOVER", "budget_exhausted"): "ESCALATE",
    ("ESCALATE", "manual_intervention"): "NORMAL",
    ("ESCALATE", "session_terminated"): None,  # 终止会话
}

# ModeArbiter 集成 (core/mode_arbiter.py)
TERMINAL_MODES = frozenset({COMPLETE, FAILED, EMERGENCY_STOPPED})

class ModeArbiter:
    P0_EMERGENCY = 0
    P1_WATCHDOG = 10
    P2_HUMAN_OVERRIDE = 20
    P3_ACTION_BLOCK_EXCLUSIVE = 30
    P4_RECOVERY = 40
    P5_TRACKING = 50
    P6_IDLE = 100

    # RECOVERING 模式可被 P0-P3 中断
    def _can_preempt_locked(self, request: ModeRequest) -> bool:
        if self._current_mode == EMERGENCY_STOPPED:
            return request.requested_mode == EMERGENCY_STOPPED
        if self._current_mode in TERMINAL_MODES:
            return request.priority > P0_EMERGENCY
        return request.priority < self._active_request.priority
```

### 2.3 异常检测条件

| 检测类型 | 阈值参数 | 计算方式 | 触发条件 |
|----------|----------|----------|----------|
| **进度停滞** | `slope_2s <= 0.02` | 滑动窗口斜率 | 持续 2 秒以上 |
| **挫折感升级** | `frustration >= 80` | EWMA + 惩罚累积 | 立即触发 |
| **目标丢失** | `missing_duration_ms >= 3000` | track.missing_duration | 3 秒以上 |
| **死锁检测** | `heartbeat_gap > 30s` | 时间戳差值 | 无心跳超30秒 |
| **输入无响应** | `response_timeout > 5s` | 时间戳差值 | 5 秒无响应 |
| **状态卡死** | `state_change_gap > 30s` | 时间戳差值 | 30 秒无变化 |
| **黑屏超时** | `loading_gap > 10s` | 时间戳差值 | 加载超 10 秒 |

```python
# CrashDetector (execution/crash_recovery.py)
class CrashDetector:
    STUCK_THRESHOLD_SEC = 30.0        # 状态卡死阈值
    BLACK_SCREEN_THRESHOLD_SEC = 10.0  # 黑屏阈值
    NO_INPUT_RESPONSE_SEC = 5.0        # 输入无响应阈值

    def detect(self, current_state: str, last_state_change: float, ...) -> CrashIndicator | None:
        # 进程终止检测
        if not process_alive:
            return CrashIndicator(severity="critical", confidence=1.0)
        # 状态卡死检测
        if now - last_state_change > self.STUCK_THRESHOLD_SEC:
            return CrashIndicator(severity="high", confidence=min(1.0, gap / 60.0))
```

### 2.4 诊断流程树

```
诊断流程树 (Decision Tree):

root: 异常触发
├─── interrupt.code == "FOCUS_LOST"
│    └── → P0 紧急停止 → release_all → 等待焦点恢复
│
├─── interrupt.code == "TARGET_LOST"
│    ├─── missing_duration < 3s → 继续跟踪
│    └─── missing_duration >= 3s → TARGET_LOST_RECOVERY
│
├─── interrupt.code == "NO_TASK_PROGRESS"
│    ├─── frustration < 30 → MICRO_RECOVERY (相机微调)
│    ├─── frustration < 80 → LOCAL_REROUTE (局部重路由)
│    └─── frustration >= 80 → ESCALATE → ModeArbiter
│
├─── screen_state == "unknown"
│    └── → UILostRecovery (ESC × 2 + 等待 HUD)
│
├─── is_stuck == True
│    └── → StuckRecovery (跳跃→横移→攀爬取消)
│
├─── is_healthy() == False
│    └── → CombatDefeatRecovery (复活对话框)
│
├─── team_state.hp_ratio < 0.2
│    └── → LowHealthRecovery (使用食物)
│
└─── model_provider_failed == True
     └── → ModelProviderFailureRecovery (等待 5s 重试)
```

### 2.5 恢复验证机制

```python
# RecoveryRecipe.verify_restabilized (control/sentinel/recovery_recipe.py)
class RecoveryRecipe:
    def verify_restabilized(
        self,
        perception: Any = None,      # 感知层检查
        claim_runtime: Any = None,   # 声明运行时验证
    ) -> bool:
        """验证恢复后系统是否稳定"""
        return False  # 子类覆盖

# 示例: UILostRecovery 验证
class UILostRecovery(RecoveryRecipe):
    def verify_restabilized(self, perception=None, claim_runtime=None) -> bool:
        # 验证屏幕状态已恢复到已知状态
        return True  # 简化版本，实际应检查 screen_state

# SomaticState 健康检查 (control/sentinel/somatic_state.py)
@dataclass(frozen=True, slots=True)
class SomaticState:
    def is_healthy(self) -> bool:
        """检查队伍是否有存活角色"""
        if not self.team_state.hp_ratios:
            return True  # 未知 = 假设健康
        return any(hp > 0.0 for hp in self.team_ratios)

    def is_safe_screen(self) -> bool:
        """检查当前界面是否安全"""
        return self.last_safe_screen_state in (
            "world_viewport", "dialogue", "map", "character_menu",
            "inventory", "quest_log", "settings",
        )
```

### 2.6 失败升级路径

```python
# 升级策略 (control/sentinel/recipes.py)
RecoveryPolicy = Literal["abort", "replan", "ask_user", "escalate"]

# 各配方的失败策略
UILostRecovery.failure_policy = "ask_user"           # 需用户介入
StuckRecovery.failure_policy = "replan"              # 重新规划路径
TargetLostRecovery.failure_policy = "replan"         # 重新获取目标
LoadingTimeoutRecovery.failure_policy = "ask_user"  # 需用户确认
CombatDefeatRecovery.failure_policy = "replan"      # 重新制定战斗策略
LowHealthRecovery.failure_policy = "replan"         # 调整策略或撤退
DriftRecovery.failure_policy = "replan"             # 重新定位
ModelProviderFailureRecovery.failure_policy = "ask_user"  # 需用户确认

# 全局预算耗尽处理 (control/sentinel/sentinel_runtime.py)
class SentinelRuntime:
    max_global_budget: int = 10  # 全局最大干预次数

    def intervene(self, snapshot: SomaticState) -> SentinelEvent | None:
        if self._global_budget_used >= self._max_global_budget:
            # 全局预算耗尽，返回 BUDGET_EXHAUSTED 事件
            return SentinelEvent(
                event_id=uuid.uuid4().hex[:12],
                recipe_id="BUDGET_EXHAUSTED",
                snapshot=snapshot,
                result=RecoveryResult("BUDGET_EXHAUSTED", "budget_exhausted"),
                budget_used=self._global_budget_used,
            )
```

---

## 第三章：场景级恢复模板

### 3.1 战斗恢复模板

| 场景 | 触发条件 | 恢复序列 | 验证方式 |
|------|----------|----------|----------|
| **单角色死亡** | `hp_ratio == 0` for 1 char | 复活→食物→换人 | 确认 HP > 0 |
| **团灭** | `all(hp == 0)` | 复活→传送→重置 | 确认世界界面 |
| **战斗超时** | `combat_duration > threshold` | 撤退→重试/放弃 | 确认位置安全 |
| **连续失败** | `fail_count >= 3` in session | 策略重评→换队/降级 | 确认队伍状态 |

```python
# CombatDefeatRecovery (control/sentinel/recipes.py)
class CombatDefeatRecovery(RecoveryRecipe):
    recipe_id = "COMBAT_DEFEAT_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return not snapshot.is_healthy()  # 有角色死亡

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "wait_screen", "params": {"screen": "defeat_dialog", "timeout_ms": 2000}},
            {"action": "click_at", "params": {"target": "revive_button"}},
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 8000}},
        ]
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
            claim_data={"recovery_type": "combat_defeat", "actions": actions},
        )

# LowHealthRecovery (control/sentinel/recipes.py)
class LowHealthRecovery(RecoveryRecipe):
    recipe_id = "LOW_HEALTH_RECOVERY"
    max_budget = 3

    def check_precondition(self, snapshot: SomaticState) -> bool:
        if not snapshot.team_state.hp_ratios:
            return False
        active_hp = snapshot.team_state.hp_ratios[0]
        return active_hp < 0.2

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "press_key", "params": {"key": "z"}},  # 使用快捷食物
            {"action": "wait_ms", "params": {"ms": 500}},
        ]
        return RecoveryResult(
            self.recipe_id, "success", actions_taken=len(actions),
            new_screen_state="world_viewport",
        )
```

### 3.2 导航恢复模板

| 场景 | 触发条件 | 恢复序列 | 验证方式 |
|------|----------|----------|----------|
| **卡地形** | `obstacle_pressure > 0.7` | 跳跃→横移→传送 | 确认位置变化 |
| **目标消失** | `track.state == LOST > 3s` | 旋转→锁定→重定位 | 确认新目标 |
| **路径失败** | `path_distance > max` | 重规划→传送 | 确认到达 |
| **连续失败** | `stuck_count >= 3` | 方向交替→重置 | 确认脱离 |

```python
# StuckRecovery (control/sentinel/recipes.py)
class StuckRecovery(RecoveryRecipe):
    recipe_id = "STUCK_RECOVERY"
    max_budget = 3

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_stuck

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            # Phase 1: Jump-Forward
            {"action": "press_key", "params": {"key": "space"}},
            {"action": "hold_key", "params": {"key": "w", "duration_ms": 400}},
            # Phase 2: Strafe-Right
            {"action": "hold_key", "params": {"key": "d", "duration_ms": 500}},
            # Phase 3: Climb-Cancel (Space+X)
            {"action": "press_key", "params": {"key": "space"}},
            {"action": "press_key", "params": {"key": "x"}},
            # Phase 4: Final forward
            {"action": "hold_key", "params": {"key": "w", "duration_ms": 600}},
        ]
        return RecoveryResult(...)

# TargetLostRecovery (control/sentinel/recipes.py)
class TargetLostRecovery(RecoveryRecipe):
    recipe_id = "TARGET_LOST_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_target_lost

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "mouse_move", "params": {"dx": 300, "dy": 0}},
            {"action": "press_key", "params": {"key": "tab"}},  # 锁定
        ]
        return RecoveryResult(...)

# RecoveryPolicy (control/recovery_policy.py)
class RecoveryPolicy:
    def decide(self, progress: ProgressState) -> RecoveryDecision:
        # 挫折感驱动决策
        if progress.frustration >= 80.0:
            return RecoveryDecision(action="ESCALATE", ...)
        if is_stuck_by_slope or is_stuck_by_level:
            # 动态弧线绕行
            return RecoveryDecision(action="SMOOTH_BYPASS", ...)
        if progress.frustration >= 30.0:
            return RecoveryDecision(action="LOCAL_REROUTE", ...)
        if progress.frustration >= 10.0:
            return RecoveryDecision(action="MICRO_RECOVERY", ...)
        return RecoveryDecision(action="continue", ...)
```

### 3.3 UI 恢复模板

| 场景 | 触发条件 | 恢复序列 | 验证方式 |
|------|----------|----------|----------|
| **按钮未找到** | `button_conf < 0.4` | ESC×2→重试 | 确认界面 |
| **未知弹窗** | `state == unknown` | ESC→等待→诊断 | 确认状态 |
| **界面混乱** | `menu_depth mismatch` | 返回→重置 | 确认层级 |
| **加载卡死** | `loading > 60s` | 等待→重连 | 确认完成 |
| **弹窗阻塞** | `blocking_notification` | ESC→点击 | 确认关闭 |

```python
# UILostRecovery (control/sentinel/recipes.py)
class UILostRecovery(RecoveryRecipe):
    recipe_id = "UI_LOST_RECOVERY"
    max_budget = 2

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.last_safe_screen_state == "unknown"

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "press_key", "params": {"key": "escape"}},
            {"action": "wait_ms", "params": {"ms": 300}},
            {"action": "press_key", "params": {"key": "escape"}},
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 3000}},
        ]
        return RecoveryResult(...)

# LoadingTimeoutRecovery (control/sentinel/recipes.py)
class LoadingTimeoutRecovery(RecoveryRecipe):
    recipe_id = "LOADING_TIMEOUT_RECOVERY"
    max_budget = 1

    def check_precondition(self, snapshot: SomaticState) -> bool:
        return snapshot.is_loading

    def execute_recovery(self, executor: Any = None) -> RecoveryResult:
        actions = [
            {"action": "wait_screen", "params": {"screen": "world_viewport", "timeout_ms": 10000}},
        ]
        return RecoveryResult(...)

# NotificationHandler (execution/notification_handler.py)
class NotificationHandler:
    def handle_notification(self, frame=None) -> bool:
        self._backend.key_press("escape")
        _chunked_sleep(0.3)
        self._backend.mouse_click(0.1, 0.1)
        return True
```

### 3.4 对话恢复模板

| 场景 | 触发条件 | 恢复序列 | 验证方式 |
|------|----------|----------|----------|
| **选项未出现** | `dialog_option_missing` | 等待→跳过→跳过 | 确认继续 |
| **对话中断** | `dialog_interrupt` | ESC→重试 | 确认对话 |
| **过场卡住** | `cutscene_stuck` | ESC→等待→跳过 | 确认跳过 |

### 3.5 探索/解谜恢复模板

| 场景 | 触发条件 | 恢复序列 | 验证方式 |
|------|----------|----------|----------|
| **步骤失败** | `puzzle_step_failed` | 重置→尝试备用 | 确认状态 |
| **连续失败** | `puzzle_fail_count >= 3` | 放弃→记录→跳过 | 确认跳过 |
| **采集物消失** | `collectible_missing` | 刷新→重找 | 确认新位置 |

---

## 第四章：错误级联与传播控制

### 4.1 级联链阻断策略

```
级联链阻断模型:

Level 1 (源头阻断):
├── 挫折感斜率 > 5.0 且 进度平坦 → SMOOTH_BYPASS
├── 目标丢失 > 3s → TARGET_LOST_RECOVERY
└── 屏幕状态异常 → UILostRecovery

Level 2 (中间节点阻断):
├── 恢复失败重试 >= 2 次 → 升级策略
├── 连续同类型错误 >= 3 次 → 重新规划
└── 预算耗尽 → 人工介入请求

Level 3 (全局阻断):
├── 全局干预预算 >= 10 次 → 会话评估
├── 模式变为 FAILED/EMERGENCY_STOPPED → 终止流程
└── 连续 5 次恢复失败 → 任务放弃

# 阻断决策点 (SentinelRuntime)
class SentinelRuntime:
    def intervene(self, snapshot: SomaticState) -> SentinelEvent | None:
        # 预算检查
        if self._global_budget_used >= self._max_global_budget:
            return SentinelEvent(recipe_id="BUDGET_EXHAUSTED", ...)
        # 各配方预算检查
        used = self._recipe_budget_used.get(recipe.recipe_id, 0)
        if used >= recipe.max_budget:
            return None  # 跳过，不干预
```

### 4.2 错误上下文保存与恢复

```python
# CrashCheckpoint (execution/crash_recovery.py)
@dataclass(slots=True)
class CrashCheckpoint:
    """恢复检查点状态"""
    timestamp: float = 0.0
    quest_id: str = ""
    quest_phase: str = ""
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    character_states: dict[str, int] = {}
    inventory_snapshot: dict[str, int] = {}
    resin_state: int = 0
    mora_state: int = 0
    last_screen_state: str = ""
    pending_resin_tasks: list[str] = []

# SomaticState (control/sentinel/somatic_state.py)
@dataclass(frozen=True, slots=True)
class SomaticState:
    """Agent 的体感状态快照"""
    active_quest_id: str = ""
    last_verified_checkpoint: str = ""
    last_safe_screen_state: str = "world_viewport"
    last_known_position: PositionEstimate | None = None
    team_state: TeamState = field(default_factory=TeamState)
    resource_state: ResourceState = field(default_factory=ResourceState)
    active_mission_node: str = ""
    claim_graph_version: int = 0
    frame_id: int = 0
    timestamp: float = 0.0
    is_stuck: bool = False
    is_target_lost: bool = False
    is_loading: bool = False
    is_drifting: bool = False
    model_provider_failed: bool = False

    def evolve(self, **overrides: Any) -> SomaticState:
        """创建更新后的快照"""
        return replace(self, **overrides)

# SessionStateManager (execution/crash_recovery.py)
class SessionStateManager:
    def save_checkpoint(
        self,
        quest_id: str,
        quest_phase: str,
        location: tuple[float, float, float],
        character_states: dict[str, int],
        inventory: dict[str, int],
        resin: int,
        mora: int,
        screen_state: str,
    ) -> None:
        """保存恢复检查点"""

    def auto_checkpoint(self, ...) -> bool:
        """自动定期保存检查点"""
        if elapsed >= checkpoint_interval_sec:
            self.save_checkpoint(...)
            return True
        return False
```

### 4.3 错误记忆与预防

```python
# 错误模式识别表
ERROR_PATTERN_TABLE = {
    "combat_fail_repeated": {
        "pattern": "combat_status == DEFEATED 出现 3 次",
        "root_cause": "队伍战力不足 / 策略错误",
        "prevention": "降低难度或更换队伍配置"
    },
    "navigation_stuck_loop": {
        "pattern": "is_stuck == True 连续出现",
        "root_cause": "地形设计绕过 / 坐标计算错误",
        "prevention": "记录障碍物位置，下次绕行"
    },
    "ui_timeout_loop": {
        "pattern": "button not found 连续 2 次",
        "root_cause": "界面时序变化 / 检测器失效",
        "prevention": "增加等待时间或使用备用检测"
    }
}

# SentinelEvent 历史记录 (control/sentinel/sentinel_runtime.py)
@dataclass(frozen=True, slots=True)
class SentinelEvent:
    event_id: str
    recipe_id: str
    snapshot: SomaticState
    result: RecoveryResult | None
    timestamp: float = 0.0
    budget_used: int = 0

class SentinelRuntime:
    @property
    def interventions(self) -> list[SentinelEvent]:
        """返回所有干预历史"""
        return list(self._history)

    def get_error_patterns(self) -> dict[str, int]:
        """统计错误模式出现频率"""
        patterns = {}
        for event in self._history:
            patterns[event.recipe_id] = patterns.get(event.recipe_id, 0) + 1
        return patterns
```

---

## 第五章：8 个具体级联案例

### 5.1 案例 1: Boss 团灭级联

```
触发事件: Boss 战斗团灭
├── E1: 角色 HP 全部归零 → CombatDefeatRecovery 触发
├── E2: 复活后无食物 → LowHealthRecovery 触发
│    └── 食物栏为空 → 紧急传送至神像
├── E3: 传送后偏离原目标 → DriftRecovery 触发
├── E4: 重新导航失败 → StuckRecovery 连续触发
└── E5: 预算耗尽 → 会话评估

检测点:
- E1: team_state.hp_ratios 检测 (每帧)
- E2: food_count <= 0 检测
- E3: is_drifting 检测
- E4: is_stuck 检测 (max_budget=3)

阻断策略: 在 E2 检测到食物耗尽时，提前触发传送而非继续战斗

恢复:
1. 检测团灭 → 点击复活
2. 检测食物耗尽 → 传送神像
3. 恢复 HP → 重试或放弃

预防:
- 战前检查食物数量
- 预留紧急传送锚点
- 记录连续失败次数，超阈值降级难度
```

### 5.2 案例 2: UI 超时级联

```
触发事件: 按钮点击后无响应 > 5s
├── E1: UI 超时 → UILostRecovery 触发
├── E2: ESC 按下后出现未知弹窗 → 再次 ESC
├── E3: 感知失焦 (focus_lost) → P0 中断
├── E4: 误操作 (在错误界面) → 需要重新导航
└── E5: 状态不同步 → 需要状态重置

检测点:
- E1: input_response_timeout > 5s
- E2: screen_state == unknown
- E3: focus_lost interrupt 发布
- E4: current_screen != expected_screen
- E5: observation 与预期不符

阻断策略: E1 阶段使用双 ESC + 等待，而非立即重试

恢复:
1. ESC×2 清除弹窗
2. 等待 HUD 出现 (3s timeout)
3. 验证屏幕状态
4. 重新导航至目标

预防:
- 关键操作前验证 UI 状态
- 使用 wait_screen 而非固定等待
- 增加 UI 超时预警
```

### 5.3 案例 3: 卡墙级联

```
触发事件: 移动时卡入地形
├── E1: obstacle_pressure > 0.7 → 障碍检测
├── E2: 前进指令重复执行 → 原地踏步
├── E3: frustration 上升 → RecoveryPolicy 决策
├── E4: 跳跃尝试 → 仍卡住
├── E5: 横移尝试 → 陷入更深
└── E6: 地形穿模 → 强制传送

检测点:
- E1: obstacle_field.sectors 检测
- E2: position_delta ≈ 0 持续 2s
- E3: progress.frustration >= 10
- E4: is_stuck == True
- E5: stuck_count 递增
- E6: camera angle 异常 / clip 检测

阻断策略: E3 阶段即触发 SMOOTH_BYPASS，而非等待卡死

恢复:
1. 阶段 1: 后退脱离碰撞体
2. 阶段 2: 侧向弧线绕行
3. 阶段 3: 攀爬取消脱离
4. 阶段 4: 传送至最近锚点

预防:
- 定期更新障碍地图
- 检测到压力时提前绕行
- 记录卡墙位置，下次避开
```

### 5.4 案例 4: 网络波动级联

```
触发事件: 网络断开 > 30s
├── E1: loading_screen 持续 → 等待
├── E2: 加载超时 > 60s → LoadingTimeoutRecovery
├── E3: 游戏进程断开 → CrashDetector 检测
├── E4: 状态不同步 → 会话状态丢失
├── E5: 重连后操作冲突 → 需要状态恢复
└── E6: 连续错误操作 → 级联失败

检测点:
- E1: loading_screen state 持续
- E2: state_change_gap > 30s (CrashDetector)
- E3: process_alive == False
- E4: checkpoint 数据陈旧
- E5: last_action 与服务器状态不符
- E6: fail_count 递增

阻断策略: E3 检测到进程断开时立即保存检查点

恢复:
1. DETECT: 崩溃检测
2. ASSESS: 评估损失
3. LAUNCH: 重启游戏
4. RECONNECT: 重连服务器
5. RESTORE: 从检查点恢复状态
6. RESUME: 恢复任务执行

预防:
- 定期自动保存检查点 (每 60s)
- 网络质量监测
- 关键操作前暂停
```

### 5.5 案例 5: 感知偏差级联

```
触发事件: 目标检测置信度 < 0.3
├── E1: YOLO 检测失败 → 使用备用检测
├── E2: 目标 ID 跳变 → BoT-SORT 重新关联
├── E3: 错误决策 (基于错误目标) → 雪崩式失败
├── E4: 战斗失败 → 团灭风险
└── E5: 修复后仍失败 → 任务放弃

检测点:
- E1: detection_confidence < 0.3
- E2: track_id 跳变或 state == LOST
- E3: decision 与实际目标不符
- E4: combat_result == DEFEATED
- E5: consecutive_fail >= 3

阻断策略: E1 阶段立即触发感知增强，而非继续执行

恢复:
1. 降低动作速度
2. 增加确认步骤
3. 使用 OCR/模板匹配备用方案
4. 暂停 LLM 决策，回退到规则引擎

预防:
- 多源感知融合 (YOLO + OCR + 模板)
- 关键决策前双重确认
- 降低感知阈值预警
```

### 5.6 案例 6: 版本更新弹窗级联

```
触发事件: 版本更新通知弹窗出现
├── E1: 未知 UI 元素 → UILostRecovery
├── E2: 弹窗阻塞操作 → NotificationHandler
├── E3: UI 层级混乱 → 多次 ESC 无效
├── E4: 错误理解状态 → 误操作
└── E5: 全部功能失效 → 需要重启

检测点:
- E1: screen_state == unknown
- E2: blocking_notification detected
- E3: ESC 次数 > 3 且状态未变
- E4: action 与 expected_state 不匹配
- E5: 多个 recovery 连续失败

阻断策略: E1 阶段即识别为更新弹窗，而非未知界面

恢复:
1. 识别为 patch_notice 类型
2. 查找并点击"确定"按钮
3. 等待下载/安装
4. 重启游戏
5. 恢复检查点

预防:
- 维护版本更新弹窗模板库
- 关键操作前检查 patch_notice
- 更新后重新校准感知器
```

### 5.7 案例 7: 死亡循环级联

```
触发事件: 同一战斗反复失败 > 3 次
├── E1: 战斗失败 → 复活
├── E2: 再次失败 → 复活 + 使用食物
├── E3: 食物耗尽 → 传送神像
├── E4: 再次挑战 → 又失败
├── E5: 树脂耗尽 → 无法继续
├── E6: 连续失败 → 任务放弃评估
└── E7: 会话终止 → 通知用户

检测点:
- E1: combat_result == DEFEATED
- E2: fail_count 递增
- E3: food_count == 0
- E4: resin_state == 0 (如果是树脂任务)
- E5: consecutive_fail >= 3
- E6: 全局预算接近耗尽
- E7: 人工确认放弃

阻断策略: E5 检测到连续失败即触发策略重评，而非继续重试

恢复:
1. 分析失败原因 (战力/策略/运气)
2. 调整队伍配置
3. 降低挑战难度
4. 或记录并跳过该任务
5. 通知用户决策

预防:
- 战前战力评估
- 失败次数阈值保护
- 自动降级机制
```

### 5.8 案例 8: 任务条件变更级联

```
触发事件: 游戏更新后任务目标变更
├── E1: 完成任务条件后未触发 → 超时
├── E2: 基于旧信息重试 → 失败
├── E3: 状态停滞 → stagnation 检测
├── E4: 尝试其他方法 → 又失败
├── E5: 意识到变更 → 死循环退出
└── E6: 浪费大量时间 → 任务效率下降

检测点:
- E1: completion_condition_met 但 state 未变
- E2: same_action repeated > threshold
- E3: progress_slope ≈ 0
- E4: multiple recovery attempts
- E5: external_info mismatch
- E6: session_time > expected

阻断策略: E2 检测到重复动作时查询外部信息

恢复:
1. 检测到停滞
2. 查询任务目标状态
3. 更新本地任务知识库
4. 重新规划执行路径
5. 继续执行

预防:
- 定期查询服务器任务状态
- 关键节点前验证任务条件
- 任务目标变化检测
```

---

## 第六章：恢复策略决策树

### 6.1 决策树输入

```
输入维度:
├── 错误类型 (Error Type)
├── 严重性级别 (Severity Level)
├── 当前场景 (Scene Context)
├── 历史统计 (Error History)
│    ├── 同类型错误连续次数
│    ├── 总干预预算消耗
│    └── 各配方使用次数
└── 资源状态 (Resource State)
     ├── 食物数量
     ├── 树脂状态
     └── 角色 HP
```

### 6.2 决策矩阵

| 错误类型 | 严重性 | 场景 | 历史 | 资源 | 最优策略 |
|----------|--------|------|------|------|----------|
| TARGET_LOST | P2 | 战斗 | 首次 | - | TARGET_LOST_RECOVERY |
| TARGET_LOST | P2 | 战斗 | 连续2次 | - | 重新锁定+等待 |
| TARGET_LOST | P1 | 导航 | 首次 | - | STUCK_RECOVERY |
| TARGET_LOST | P1 | 导航 | 连续3次 | - | DRIFT_RECOVERY |
| NO_TASK_PROGRESS | P2 | - | frustration<30 | - | MICRO_RECOVERY |
| NO_TASK_PROGRESS | P2 | - | frustration>=30 | - | LOCAL_REROUTE |
| NO_TASK_PROGRESS | P1 | - | frustration>=80 | - | ESCALATE→ModeArbiter |
| SCREEN_UNKNOWN | P2 | - | 首次 | - | UILostRecovery |
| SCREEN_UNKNOWN | P2 | - | 连续2次 | - | ESC×3+人工介入 |
| COMBAT_DEFEAT | P2 | Boss | 首次 | 食物>0 | CombatDefeatRecovery |
| COMBAT_DEFEAT | P2 | Boss | 首次 | 食物=0 | CombatDefeatRecovery+传送 |
| COMBAT_DEFEAT | P1 | Boss | 连续3次 | - | 策略重评+换队 |
| HP_CRITICAL | P2 | - | 首次 | 食物>0 | LowHealthRecovery |
| HP_CRITICAL | P1 | - | 首次 | 食物=0 | 紧急传送神像 |
| LOADING_STUCK | P2 | - | 首次 | - | LoadingTimeoutRecovery |
| LOADING_STUCK | P1 | - | 连续2次 | - | 崩溃恢复流程 |
| FOCUS_LOST | P0 | - | - | - | P0紧急停止+release_all |
| PROCESS_CRASH | P0 | - | - | - | 崩溃恢复+游戏重启 |
| NETWORK_DISCONNECT | P1 | - | <30s | - | 等待重连 |
| NETWORK_DISCONNECT | P0 | - | >=30s | - | 崩溃恢复流程 |

### 6.3 策略选择伪代码

```python
def select_recovery_strategy(
    error_type: str,
    severity: int,
    scene: str,
    history: ErrorHistory,
    resources: ResourceState,
) -> tuple[str, RecoveryRecipe]:
    """决策树主函数"""

    # P0 紧急处理
    if severity == 0:
        return ("EMERGENCY_STOP", None)

    # 预算检查
    if history.global_budget_remaining <= 0:
        return ("BUDGET_EXHAUSTED", None)

    # 错误类型分支
    if error_type == "FOCUS_LOST":
        return ("RELEASE_ALL", None)

    if error_type == "TARGET_LOST":
        if scene == "combat":
            return ("TARGET_LOST_RECOVERY", TargetLostRecovery())
        else:
            return ("STUCK_RECOVERY", StuckRecovery())

    if error_type == "NO_TASK_PROGRESS":
        if resources.frustration >= 80:
            return ("ESCALATE", None)
        elif resources.frustration >= 30:
            return ("LOCAL_REROUTE", None)
        else:
            return ("MICRO_RECOVERY", None)

    if error_type == "SCREEN_UNKNOWN":
        if history.ui_recovery_count < 2:
            return ("UI_LOST_RECOVERY", UILostRecovery())
        else:
            return ("ASK_USER", None)

    if error_type == "COMBAT_DEFEAT":
        if resources.food_count > 0:
            return ("COMBAT_DEFEAT_RECOVERY", CombatDefeatRecovery())
        else:
            return ("COMBAT_DEFEAT_RECOVERY", CombatDefeatRecovery())

    if error_type == "HP_CRITICAL":
        if resources.food_count > 0:
            return ("LOW_HEALTH_RECOVERY", LowHealthRecovery())
        else:
            return ("TELEPORT_STATUE", None)

    if error_type == "LOADING_STUCK":
        if history.loading_timeout_count < 1:
            return ("LOADING_TIMEOUT_RECOVERY", LoadingTimeoutRecovery())
        else:
            return ("CRASH_RECOVERY", None)

    # 默认
    return ("UNKNOWN_ERROR", None)
```

---

## 第七章：与 Sparkle 五平面架构集成

### 7.1 Perception 平面：异常检测

```
Perception 平面职责:
├── 屏幕状态分类 → 检测 unknown/loading/blocking_popup
├── 目标检测 → 检测 target_conf < 0.3
├── 跟踪器监控 → 检测 track_id 跳变
├── 障碍物检测 → 检测 obstacle_pressure > 0.7
└── 生命值/体力检测 → 检测 HP < 0.2 / stamina < 0.05
```

**关键组件:**
```python
# GenshinScreenClassifier (perception/genshin_screen_classifier.py)
class GenshinScreenClassifier:
    def classify(self, frame) -> UIStateEstimate:
        """检测屏幕状态，识别异常界面"""
        state = ...
        if state.confidence < 0.6:
            return UIStateEstimate(state="unknown", ...)
        return state

# RecoveryDetector (perception/recovery_detector.py)
class RecoveryDetector:
    def detect(self, frame, frame_id) -> RecoveryDetection:
        """检测 HP 恢复状态"""
        ...

# SomaticStateSupervisor (control/sentinel/somatic_state_supervisor.py)
class SomaticStateSupervisor:
    def check_frame(self, frame, frame_id) -> SomaticState:
        """分析帧，检测异常状态"""
        stamina_ratio = self._detect_stamina_bar(frame)
        health_ratio = self._detect_health_bar(frame)
        hazard_level, hazard_type = self._detect_hazards(frame)
        ...

# ProgressSupervisor (control/progress_supervisor.py)
class ProgressSupervisor:
    def update(self, observation: Observation) -> ProgressState:
        """更新进度状态，生成中断"""
        slope = self._window_slope(...)
        frustration = self._update_frustration(...)
        active_interrupt = self._active_interrupt(...)
        ...
```

### 7.2 Control 平面：策略调整

```
Control 平面职责:
├── RecoveryPolicy → 根据 frustration 决策
├── ObstaclePolicy → 障碍物绕行
├── SomaticStateSupervisor → 体力/HP 拦截
└── CameraServo → 视觉反馈调整
```

**关键组件:**
```python
# RecoveryPolicy (control/recovery_policy.py)
class RecoveryPolicy:
    def decide(self, progress: ProgressState) -> RecoveryDecision:
        """基于进度状态决策恢复动作"""
        if progress.frustration >= 80.0:
            return RecoveryDecision(action="ESCALATE", ...)
        if is_stuck_by_slope:
            return RecoveryDecision(action="SMOOTH_BYPASS", ...)
        ...

# ObstaclePolicy (control/obstacle_policy.py)
class ObstaclePolicy:
    def decide(self, obstacle_field, progress) -> ObstacleDecision:
        """障碍物绕行决策"""
        if front >= self._front_threshold:
            move_right = choose_side()
            return ObstacleDecision(action="LOCAL_REROUTE", ...)

# SomaticStateSupervisor (control/sentinel/somatic_state_supervisor.py)
class SomaticStateSupervisor:
    def monitor_and_intercept(self, backend, frame, frame_id) -> tuple:
        """监控体力/HP，拦截危险动作"""
        state = self.check_frame(frame, frame_id)
        if state.stamina_zone == StaminaZone.CRITICAL:
            self._halt_all_movement(backend)
            ...
```

### 7.3 Execution 平面：输入安全

```
Execution 平面职责:
├── InputWorker → 输入执行 + Deadman Switch
├── InputLease → 租约管理
├── LoadingWaiter → 加载等待
├── NotificationHandler → 弹窗处理
└── CrashRecovery → 崩溃恢复
```

**关键组件:**
```python
# InputWorker (execution/input_worker.py)
class InputWorker:
    def _run_focus_check(self) -> None:
        """焦点丢失 → 立即 release_all"""
        if not focused:
            cleared = self._lease_store.clear()
            self._backend.release_all(reason="focus_lost")
            self._state_bus.publish_interrupt(Interrupt(priority=0, ...))

    def _run_deadman_check(self) -> None:
        """租约过期 → 释放按键"""
        expired = self._lease_store.expire_due(now)
        for key in expired.keys_to_release:
            self._backend.key_up(key, reason="deadman_expired")

    def _handle_interrupt(self, interrupt: Interrupt) -> None:
        """高优先级中断 → release_all"""
        if interrupt.priority == 0 or interrupt.requires_input_release:
            self._lease_store.clear()
            self._backend.release_all(...)

# LoadingWaiter (execution/loading_waiter.py)
class LoadingWaiter:
    def wait_for_load_complete(self, frame_source, shutdown_event) -> bool:
        """等待加载完成，超时触发恢复"""

# CrashRecoveryOrchestrator (execution/crash_recovery.py)
class CrashRecoveryOrchestrator:
    RecoveryPhase = Enum("DETECT", "ASSESS", "LAUNCH", "RECONNECT", "RESTORE", "RESUME")
```

### 7.4 Orchestration 平面：场景切换

```
Orchestration 平面职责:
├── Orchestrator → 状态机驱动
├── InterruptHandler → 中断处理
├── TaskSpec → 任务规格
└── RecoveryRecipe → 恢复配方注册
```

**关键组件:**
```python
# Orchestrator (orchestration/orchestrator.py)
class Orchestrator:
    RECOVER = "RECOVER"

    def run_once(self) -> StateTransition:
        """处理中断 + 执行技能"""
        interrupt = self._state_bus.next_interrupt(timeout=0.0)
        if interrupt is not None:
            transition = self._graph.next_for_interrupt(self._state, interrupt)
            self._apply_transition(transition)
            return transition
        ...

# InterruptHandler (orchestration/interrupt_handler.py)
class InterruptHandler:
    def handle(self, interrupt: Interrupt) -> RecoveryRecipe | None:
        """根据中断选择恢复配方"""

# SentinelRuntime (control/sentinel/sentinel_runtime.py)
class SentinelRuntime:
    def intervene(self, snapshot: SomaticState) -> SentinelEvent | None:
        """检测异常 + 执行恢复"""
        recipe = self.detect_anomaly(snapshot)
        if recipe is None:
            return None
        result = recipe.execute_recovery()
        ...
```

### 7.5 Telemetry 平面：错误记录

```
Telemetry 平面职责:
├── JSONL 日志 → 错误事件记录
├── 视频录制 → 问题复盘
├── 错误统计 → 模式识别
└── 性能监控 → 瓶颈发现
```

**关键组件:**
```python
# StateBus (core/state_bus.py)
class StateBus:
    observation_ring: RingBuffer[Observation]  # 300帧历史
    progress_ring: RingBuffer[ProgressState]    # 300帧进度
    event_queue: PriorityEventQueue[Interrupt]   # 中断队列

    def publish_interrupt(self, interrupt: Interrupt) -> bool:
        """发布中断事件"""
        return self.event_queue.put(interrupt, priority=interrupt.priority)

# SentinelRuntime (control/sentinel/sentinel_runtime.py)
class SentinelRuntime:
    @property
    def interventions(self) -> list[SentinelEvent]:
        """返回干预历史"""
        return list(self._history)

    def get_error_patterns(self) -> dict[str, int]:
        """统计错误模式"""

# Verifier (execution/verifier_base.py)
class Verifier:
    def verify(self, context: VerifierContext) -> VerifierResult:
        """验证结果记录"""
```

---

## 附录 A：错误码速查表

| 错误码 | 名称 | 严重性 | 恢复配方 | 说明 |
|--------|------|--------|----------|------|
| FOCUS_LOST | 焦点丢失 | P0 | 无 (紧急停止) | 游戏窗口失去焦点 |
| PROCESS_CRASH | 进程崩溃 | P0 | CrashRecovery | 游戏进程终止 |
| GRAPHICS_CRASH | 图形崩溃 | P0 | CrashRecovery | GPU 驱动失败 |
| NETWORK_DISCONNECT | 网络断开 | P0 | CrashRecovery | 服务器连接断开 |
| TARGET_LOST | 目标丢失 | P2 | TARGET_LOST_RECOVERY | 跟踪目标消失 |
| NO_TASK_PROGRESS | 无任务进度 | P1 | ESCALATE | 进度停滞 |
| SCREEN_UNKNOWN | 屏幕未知 | P2 | UI_LOST_RECOVERY | 无法识别界面 |
| COMBAT_DEFEAT | 战斗失败 | P2 | COMBAT_DEFEAT_RECOVERY | 角色死亡 |
| HP_CRITICAL | HP 危急 | P2 | LOW_HEALTH_RECOVERY | HP 过低 |
| LOADING_STUCK | 加载卡死 | P2 | LOADING_TIMEOUT_RECOVERY | 加载超时 |
| OBSTACLE_BLOCKED | 障碍阻挡 | P2 | STUCK_RECOVERY | 卡在地形 |
| DRIFT_DETECTED | 位置偏离 | P2 | DRIFT_RECOVERY | 偏离预期位置 |
| MODEL_PROVIDER_FAIL | 模型失败 | P2 | MODEL_PROVIDER_FAILURE_RECOVERY | LLM 调用失败 |
| INPUT_RESPONSE_TIMEOUT | 输入超时 | P2 | UI_LOST_RECOVERY | 无输入响应 |
| BUDGET_EXHAUSTED | 预算耗尽 | P1 | 无 (升级) | 恢复预算用尽 |

---

## 附录 B：超时阈值参考表

| 类型 | 参数名 | 默认值 | 说明 |
|------|--------|--------|------|
| **崩溃检测** | STUCK_THRESHOLD_SEC | 30.0s | 状态无变化阈值 |
| **崩溃检测** | BLACK_SCREEN_THRESHOLD_SEC | 10.0s | 黑屏超时 |
| **崩溃检测** | NO_INPUT_RESPONSE_SEC | 5.0s | 输入无响应 |
| **进度监督** | target_lost_after_ms | 3000ms | 目标丢失超时 |
| **进度监督** | interrupt_cooldown_sec | 0.5s | 中断冷却时间 |
| **恢复策略** | stale_penalty_threshold | 0 | 陈旧帧惩罚 |
| **加载等待** | max_wait | 60.0s | 加载最大等待 |
| **会话管理** | checkpoint_interval_sec | 60.0s | 检查点保存间隔 |
| **崩溃恢复** | RESTART_TIME_SEC | 60.0s | 游戏重启时间 |
| **崩溃恢复** | RECONNECT_TIME_SEC | 30.0s | 重连时间 |
| **崩溃恢复** | RESTORE_TIME_SEC | 15.0s | 状态恢复时间 |
| **崩溃恢复** | max_wait_sec | 180.0s | 最大恢复等待 |

---

## 附录 C：恢复耗时预算表

| 恢复类型 | 预计耗时 | 最大预算 | 失败策略 |
|----------|----------|----------|----------|
| MICRO_RECOVERY | 0.5-1s | 无限制 | 局部重试 |
| LOCAL_REROUTE | 1-3s | 无限制 | 升级到 SMOOTH_BYPASS |
| SMOOTH_BYPASS | 2-5s | 无限制 | 升级到 STUCK_RECOVERY |
| UI_LOST_RECOVERY | 2-5s | 2次 | 人工介入 |
| STUCK_RECOVERY | 3-8s | 3次 | 重新规划 |
| TARGET_LOST_RECOVERY | 2-5s | 2次 | 重新规划 |
| COMBAT_DEFEAT_RECOVERY | 5-10s | 2次 | 策略重评 |
| LOW_HEALTH_RECOVERY | 1-2s | 3次 | 传送神像 |
| DRIFT_RECOVERY | 15-20s | 2次 | 重新规划 |
| LOADING_TIMEOUT_RECOVERY | 10-15s | 1次 | 崩溃恢复 |
| MODEL_PROVIDER_FAILURE_RECOVERY | 5-10s | 2次 | 人工介入 |
| **全局预算** | - | **10次** | 会话评估 |

---

## 文档变更历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| 1.0 | 2026-05-30 | 初始版本，集成现有代码 |

---

*本文档为 Sparkle Vision Agent Kernel v0.5 的核心基础设施文档，与代码库同步维护。*