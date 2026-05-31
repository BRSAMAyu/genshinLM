# Agent B Round 2 深度验证报告

## 验证结果

### P1问题验证

#### 问题1: task_spec_builder 硬编码
- **验证结论**: 确认
- **具体位置**: `D:\Aurora\vision_agent_kernel_v0_5\planning\task_spec_builder.py` 第16-21行
- **影响范围**:
  - 所有 MissionNode 的 skill_name 使用硬编码版本字符串: `acquire_monster_a_v1`, `safe_combat_playbook_v1`
  - playbook 参数硬编码为 `"safe_combat_v1"`
  - 无法针对不同任务类型选择不同版本的技能实现
  - 新增技能版本需要修改此文件
- **修复建议**:
  ```python
  # 在 TaskSpecBuilder.__init__ 中添加版本映射配置
  def __init__(self, route_selector: RouteSelector | None = None,
               skill_versions: dict[str, str] | None = None) -> None:
      self._routes = route_selector or RouteSelector()
      self._skill_versions = skill_versions or {
          "acquire": "acquire_monster_a_v1",
          "combat": "safe_combat_playbook_v1",
          "playbook": "safe_combat_v1",
      }
  
  # 在 build 方法中引用配置
  MissionNode("acquire_target", "acquire_target",
              self._skill_versions["acquire"], "target_visible", failure)
  ```

#### 问题2: quest_skill_adapter time.sleep
- **验证结论**: 确认
- **具体位置**: `D:\Aurora\vision_agent_kernel_v0_5\planning\quest_skill_adapter.py` 第170-174行
- **影响范围**:
  - `_chunked_sleep` 方法使用 `time.sleep(chunk)` 其中 `chunk=0.05` (50ms)
  - 在 `drive_dialog` 中每步调用 `_advance_dialog` + `_chunked_sleep` 累计约 380ms 阻塞
  - 在 `skip_cutscene` 中持续循环调用 `_chunked_sleep`
  - 对于实时性要求高的游戏控制场景，存在累积延迟风险
- **修复建议**:
  ```python
  # 方案1: 使用 StateBus 中断机制替代轮询
  def _wait_for_screen_change(self, target_screens: set[str],
                               timeout_sec: float = 5.0) -> bool:
      deadline = time.perf_counter() + timeout_sec
      while time.perf_counter() < deadline:
          obs = self._bus.latest_observation.get()
          if obs is not None:
              state = getattr(obs, "ui_state", None)
              if state is not None:
                  screen = getattr(state, "state", "unknown")
                  if screen in target_screens:
                      return True
          # 发布检查请求而非 sleep
          self._bus.publish_interrupt(Interrupt(...))
          # 让出控制权给事件循环
          await asyncio.sleep(0.05)  # 非阻塞等待
      return False
  ```

## 深入分析

### 1. camera_servo.py FOV 参数分析
- **发现**: `CameraModel` 默认 `horizontal_fov_deg=90.0`
- **问题**: 原神默认 FOV 通常为 75-80 度，90度过宽会导致:
  - 像素到角度转换的数学误差增大
  - `pixel_to_yaw_pitch_error_deg` 计算不准确
  - 相机 PID 控制响应偏慢
- **建议**: 添加 FOV 自动校准或从配置文件读取

### 2. progress_supervisor.py EWMA 窗口分析
- **发现**: 配置参数使用合理的默认值
  - `ewma_alpha=0.3`: 合理的历史平滑系数
  - `slope_window_sec=2.0`: 足够覆盖帧间波动
  - `visibility_window_sec=1.0`: 合理的可见性统计窗口
- **潜在问题**:
  - `stale_penalty=8.0` 和 `no_task_progress=30.0` 的惩罚力度较强
  - `target_lost_after_ms=3000.0` 对高速战斗场景可能过长
- **建议**: 这些阈值应该可配置而非硬编码

### 3. recovery_policy.py 恢复策略分析
- **发现**: 严重硬编码问题
  - 第52行: `if progress.frustration >= 80.0` (escalate 阈值)
  - 第116行: `if progress.frustration >= 30.0` (local reroute)
  - 第128行: `if progress.frustration >= 10.0` (micro recovery)
  - 第67行: `stuck_by_slope` 斜率阈值 `> 5.0`
- **问题**:
  - 无法针对不同游戏场景调整恢复策略
  - 硬编码的斜率阈值缺乏数学依据
- **建议**:
  ```python
  @dataclass(frozen=True, slots=True)
  class RecoveryPolicyConfig:
      escalate_threshold: float = 80.0
      local_reroute_threshold: float = 30.0
      micro_recovery_threshold: float = 10.0
      stuck_slope_threshold: float = 5.0
      stuck_progress_threshold: float = 0.01
  ```

### 4. ultralytics_tracker.py 额外发现
- **发现**: 速度估计使用简单差分
  - `_velocity` 方法直接用当前位置减上一位置除以 dt
  - 单帧速度估计噪声大
- **建议**: 考虑使用类似 progress_supervisor 的 EWMA 平滑

## 问题卡

| ID | 严重性 | 模块 | 问题 | 状态 |
|----|--------|------|------|------|
| B2-P1-01 | P1 | task_spec_builder | skill 版本硬编码，无法扩展 | 待修复 |
| B2-P1-02 | P1 | quest_skill_adapter | 使用 time.sleep 阻塞等待 | 待修复 |
| B2-P2-01 | P2 | camera_model | 默认 FOV 90 度对原神偏高 | 建议优化 |
| B2-P2-02 | P2 | recovery_policy | 恢复阈值硬编码，无法配置 | 建议优化 |
| B2-P3-01 | P3 | ultralytics_tracker | 速度估计未使用 EWMA 平滑 | 建议改进 |

## 修复优先级

1. **P1-01 (高)**: task_spec_builder 硬编码 - 影响系统可扩展性
2. **P1-02 (高)**: quest_skill_adapter time.sleep - 影响实时性
3. **P2-02 (中)**: recovery_policy 阈值硬编码 - 影响调优灵活性
4. **P2-01 (中)**: FOV 默认值优化 - 影响控制精度
5. **P3-01 (低)**: 速度估计优化 - 边缘优化