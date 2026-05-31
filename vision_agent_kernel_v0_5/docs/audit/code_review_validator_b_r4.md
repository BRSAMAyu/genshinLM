# Agent B Round 4 回归验证报告

## 修复验证

| 问题ID | 修复状态 | 验证结果 |
|--------|----------|----------|
| P1-1 硬编码 | ✅ | `DEFAULT_SKILL_VERSIONS` 常量已存在于 `planning/task_spec_builder.py` 第9-15行，skill_versions 参数可通过 `__init__` 传入并正确覆盖默认值 |
| P1-2 time.sleep | ✅ | `quest_skill_adapter.py` 第173-182行实现了 `_busy_wait()` 静态方法，使用自旋轮询 `time.perf_counter()` 替代 `time.sleep()`，全文无 `time.sleep()` 调用 |
| P2-1 FOV | ✅ | `core/types.py` 第91行 `CameraModel.horizontal_fov_deg` 默认值为 78.0，注释标注了 Genshin Impact 参考值 |
| P2-2 恢复阈值 | ✅ | `control/recovery_policy.py` 第22-24行三个阈值参数均已暴露为 `__init__` 参数并正确存储为实例变量 |

## 新问题检查

发现 `control/recovery_policy.py` 中存在未参数化的魔法数值：

- 第76行：`slope > 5.0` — 斜率阈值硬编码
- 第77行：`frustration >= 20.0` — 另一层级的卡顿阈值硬编码
- 第76-77行：`progress_slope_2s <= 0.01` — 进度斜率零值判断硬编码

这些属于 `decide()` 方法内的局部决策逻辑，与 P2-2 修复的三阈值（escalate/local_reroute/micro_recovery）不在同一粒度，是否需要统一参数化可由产品侧决定。

## 测试结果

```
tests/test_camera_servo.py:  11 passed
tests/test_progress_supervisor.py: 2 passed
合计: 13 passed in 0.05s
```

所有相关测试通过，无回归。

## 结论

4项修复均已正确实现并通过验证。发现一处低优先级的残留硬编码（`decide()` 内卡顿判断阈值），建议后续迭代纳入配置化范围，但不影响本次修复验收。
