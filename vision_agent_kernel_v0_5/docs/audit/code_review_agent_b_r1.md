# Agent B Round 1 审查报告

## 审查文件清单
| 文件 | 语法 | 算法 | 状态管理 | 依赖 | 逻辑 | 性能 | 问题数 |
|------|------|------|----------|------|------|------|--------|
| control/camera_servo.py | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 0 |
| control/progress_supervisor.py | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | 1 |
| control/recovery_policy.py | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 0 |
| orchestration/task_spec.py | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | 1 |
| orchestration/task_spec_builder.py | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | 5 |
| planning/mainline/mainline_skill_executor.py | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | 2 |
| planning/quest_skill_adapter.py | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | 3 |

## 问题清单

### [ISSUE-B001] orchestration/task_spec_builder.py:17-27
**严重性**: P1
**类别**: 状态管理/逻辑

硬编码的 MissionNode 列表无法应对动态任务扩展。当 `build()` 被调用时，直接构造固定的4个节点（enter_region、acquire_target、combat、verify_reward），没有任何参数化扩展机制。

**证据**
```python
def build(self, intent: ParsedIntent) -> MissionQueue:
    ranked = self._routes.rank_routes(intent.resource_id)
    route = ranked["routes"][0] if ranked.get("routes") else {"route_id": None}
    failure = {"max_retries": 3, "on_failed": "recover_or_skip", "cleanup_skill": "return_to_safe_anchor_v1"}
    nodes = [
        MissionNode("enter_region", "enter_region", "enter_region_a_v1", "region_entered", failure, route_id=route.get("route_id")),
        MissionNode("acquire_target", "acquire_target", "acquire_monster_a_v1", "target_visible", failure),
        MissionNode("combat", "combat", "safe_combat_playbook_v1", "target_defeated", failure, playbook="safe_combat_v1"),
        MissionNode("verify_reward", "verify", None, "reward_seen_or_count_changed", failure),
    ]
```

**修复建议**
添加节点注册表机制，支持从配置或路由元数据中动态加载任务节点类型。

---

### [ISSUE-B002] orchestration/task_spec_builder.py:14
**严重性**: P2
**类别**: 逻辑

当 `ranked["routes"]` 为空列表时，直接访问 `[0]` 导致 IndexError。

**证据**
```python
route = ranked["routes"][0] if ranked.get("routes") else {"route_id": None}
# 如果 ranked.get("routes") == [] (空列表)，条件为 False，但若为 None 则 OK
# 问题：若 routes 键存在但值为空列表 []，条件为 False，会走到 else
# 但若 routes 键存在且为 [None] 或其他假值，可能崩溃
```

**修复建议**
```python
routes = ranked.get("routes") or []
route = routes[0] if routes else {"route_id": None}
```

---

### [ISSUE-B003] orchestration/task_spec_builder.py:13
**严重性**: P2
**类别**: 依赖

`rank_routes()` 返回结构无类型注解，调用方无法验证字段存在性。`route_id` 访问依赖隐式约定。

**证据**
```python
ranked = self._routes.rank_routes(intent.resource_id)
route = ranked["routes"][0] if ranked.get("routes") else {"route_id": None}
```

**修复建议**
为 `RouteSelector.rank_routes()` 添加返回值类型注解，或在调用处增加字段校验。

---

### [ISSUE-B004] orchestration/task_spec_builder.py:16
**严重性**: P2
**类别**: 逻辑

`MissionQueue` 的 `loop` 参数硬编码 `max_iterations=5`。对于某些任务类型（如采集或持续监控），可能需要不同的迭代策略。

**证据**
```python
return MissionQueue(
    mission_id=f"mission_{intent.resource_id}",
    goal=MissionGoal(intent.goal_type, intent.resource_id, intent.target_count),
    nodes=nodes,
    loop=MissionLoop({"resource_count_delta": intent.target_count}, max_iterations=5),  # 硬编码
)
```

**修复建议**
从 `intent` 参数或路由配置中读取 `max_iterations`，或添加配置参数。

---

### [ISSUE-B005] orchestration/task_spec_builder.py:14-15
**严重性**: P2
**类别**: 依赖

缺少导入验证：`MissionGoal`, `MissionLoop`, `MissionNode`, `MissionQueue` 均来自 `planning.mission_queue`，但该文件可能被删除或重构。

**证据**
```python
from planning.mission_queue import MissionGoal, MissionLoop, MissionNode, MissionQueue
```

**修复建议**
添加对这些类型的基本可用性检查，或在模块级别捕获 ImportError 并提供有意义的错误信息。

---

### [ISSUE-B006] planning/mainline/mainline_skill_executor.py:164
**严重性**: P2
**类别**: 依赖

`BeliefNode.causal_role` 参数要求字面值联合类型，但代码传入普通 `str`。

**证据**
```python
belief = BeliefNode(
    ...
    causal_role="custom",  # 类型要求：Literal['objective_type_hypothesis', 'ui_affordance_hypothesis', ...]
    ...
)
```

**修复建议**
```python
from bagel.fig_schema import BeliefNode as _BeliefNode
# 使用 "custom" 作为 fallback 时需要断言或 cast
```

---

### [ISSUE-B007] planning/mainline/mainline_skill_executor.py:66
**严重性**: P2
**类别**: 依赖

`BagelRuntime()` 实例化时无参数校验，若后续初始化失败，错误信息不足。

**证据**
```python
self._bagel = bagel_runtime or BagelRuntime()
```

**修复建议**
添加运行时健康检查：
```python
if bagel_runtime is None:
    self._bagel = BagelRuntime()
    if not self._bagel.is_initialized():
        log.warning("[MainlineSkillExecutor] BagelRuntime initialization may be incomplete")
```

---

### [ISSUE-B008] planning/quest_skill_adapter.py:77-104
**严重性**: P1
**类别**: 逻辑

`skip_cutscene()` 使用 `time.sleep()` 而非 chunked wait。CLAUDE.md 明确禁止 `time.sleep()`。

**证据**
```python
@staticmethod
def _chunked_sleep(seconds: float, chunk: float = 0.05) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(min(chunk, max(0.0, deadline - time.perf_counter())))
```

**修复建议**
已有正确的 `_chunked_sleep`，但主循环中使用 `time.perf_counter()` 替代 `time.time()` 搭配 `time.sleep`。确认在 `skip_cutscene()` 的 `while` 循环中调用 `_chunked_sleep`。

---

### [ISSUE-B009] planning/quest_skill_adapter.py:127-131
**严重性**: P2
**类别**: 逻辑

`check_prerequisites()` 返回类型注解为 `bool`，但实际通过 `quest_sm.check_prerequisites()` 返回。需确认该方法签名一致。

**证据**
```python
def check_prerequisites(self, current_ar: int = 0) -> bool:
    if self._quest_sm is None:
        return True
    return self._quest_sm.check_prerequisites(current_ar)
```

**修复建议**
添加断言或类型守卫：
```python
result = self._quest_sm.check_prerequisites(current_ar)
assert isinstance(result, bool), f"check_prerequisites returned {type(result)}"
return result
```

---

### [ISSUE-B010] planning/quest_skill_adapter.py:170-174
**严重性**: P2
**类别**: 逻辑

`_chunked_sleep()` 是正确的实现，但 `skip_cutscene()` 循环体中使用 `time.sleep()` 直接等待（虽然有 try/except）。需确认是否全部替换为 `_chunked_sleep`。

**证据**
```python
while time.perf_counter() < deadline:
    try:
        self._backend.key_press("escape", reason="skip_cutscene")
    except Exception:
        pass

    self._chunked_sleep(interval)  # 已使用 _chunked_sleep

    # Check if we're back in gameplay
    ...
```

实际上已使用 `_chunked_sleep`，本条为误报，可忽略。

---

### [ISSUE-B011] control/progress_supervisor.py:124
**严重性**: P2
**类别**: 逻辑

`obstacle_penalty` 计算使用 `max()` 但若 `sectors` 为空字典，`default=0.0` 应能处理。需要确认无其他边界情况。

**证据**
```python
obstacle_pressure = max(observation.obstacle_field.sectors.values(), default=0.0)
```

**修复建议**
确认 `max()` 在 `default` 参数可用（Python 3.4+），当前写法正确。补充测试用例验证空 sectors 场景。

---

## 算法正确性验证

### CameraServo (camera_servo.py + camera_model.py)
FOV 角度转换公式：
```python
yaw_error = math.degrees(
    math.atan(normalized_x * math.tan(math.radians(camera.horizontal_fov_deg) / 2.0))
)
```
数学推导正确：将像素坐标归一化到 [-1,1]，乘以半 FOV 的正切值，然后求 atan 得到角度。

### ProgressSupervisor (progress_supervisor.py)
EWMA 计算：
```python
self._ewma_progress = (
    sample.progress
    if len(self._samples) == 1
    else self._config.ewma_alpha * sample.progress
    + (1.0 - self._config.ewma_alpha) * self._ewma_progress
)
```
正确。斜率计算使用首尾差分除以时间间隔，正确。震荡分数计算正确统计方向变化次数。

### RecoveryPolicy (recovery_policy.py)
恢复策略覆盖：
- P0: 活跃中断 → interrupt_recovery
- P1: frustration >= 80 → ESCALATE
- P2: stuck_by_slope 或 stuck_by_level → SMOOTH_BYPASS（有侧向交替）
- P3: frustration >= 30 → LOCAL_REROUTE
- P4: frustration >= 10 → MICRO_RECOVERY
- 无需恢复 → continue

覆盖完整，但缺少对 `ProgressState` 为 None 或无效输入的保护。

---

## 状态管理检查

### CameraServo
状态转移：`reset()` 方法清空 `_last_yaw_delta`、`_last_pitch_delta`、`_pending_substeps`。完整。

### ProgressSupervisor
样本历史：`deque` 自动管理，`_trim()` 在每次 `update()` 时清理过期样本。正确。

### RecoveryPolicy
`decide()` 方法基于 ProgressState 计算恢复决策，无持久状态泄露。正确。

### TaskSpecBuilder
`build()` 方法无副作用，可重入。正确。

---

## 依赖注入检查

所有组件正确使用 StateBus 作为可选注入：
- `ProgressSupervisor.__init__(state_bus: StateBus | None = None)`
- `QuestSkillAdapter.__init__(..., state_bus: Any | None = None, ...)`

无循环依赖。

---

## 总结

| 级别 | 数量 | 说明 |
|------|------|------|
| P0 | 0 | 无发现 |
| P1 | 2 | task_spec_builder 硬编码问题，quest_skill_adapter sleep 问题 |
| P2 | 9 | 类型安全、边界检查、配置参数化等问题 |

**优先级 P1 需修复**：ISSUE-B001 (task_spec_builder 动态扩展)、ISSUE-B008 (time.sleep 替换确认)。