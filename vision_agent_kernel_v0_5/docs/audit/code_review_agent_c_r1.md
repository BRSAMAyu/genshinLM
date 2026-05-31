# Agent C Round 1 审查报告

## 审查文件清单
| 文件/目录 | 覆盖 | 质量 | 正确性 | 完整性 | 问题数 |
|-----------|------|------|--------|--------|--------|
| tests/test_state_bus.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_mode_arbiter.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_interrupt_priority.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_input_lease.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_watchdog.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_telemetry_logger.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_perception_pipeline.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_progress_supervisor.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_visual_trigger_detector.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_visual_action_block.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_chaos_recovery.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_runtime_health.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_orchestrator.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_obstacle_policy.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_app_service_controller.py | ⚠️ | ✅ | ✅ | ✅ | 1 |
| tests/test_viewport.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_camera_model.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_camera_servo.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_yolo_detector.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_danger_detector.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_reflex_scheduler.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_composed_verifier.py | ✅ | ⚠️ | ✅ | ✅ | 2 |
| tests/test_evidence_graph.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_strict_evidence_mode.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_bagel_arbiter.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_bagel_evidence_matrix.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_bagel_fig_schema.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_bagel_safe_revision.py | ✅ | ✅ | ✅ | ✅ | 0 |
| tests/test_pre_realworld_closure.py | ✅ | ✅ | ✅ | ✅ | 0 |
| scripts/run_kernel.py | ✅ | ✅ | ✅ | ✅ | 0 |
| scripts/run_final_demo.py | ✅ | ✅ | ✅ | ⚠️ | 1 |
| scripts/run_testbed.py | ✅ | ✅ | ⚠️ | ✅ | 1 |
| configs/*.yaml | ⚠️ | N/A | N/A | ⚠️ | 2 |
| bagel/runtime.py | ✅ | ✅ | ✅ | ✅ | 0 |
| bagel/arbiter.py | ✅ | ✅ | ✅ | ✅ | 0 |
| bagel/evidence_matrix.py | ✅ | ✅ | ✅ | ✅ | 0 |
| bagel/safe_revision.py | ✅ | ✅ | ✅ | ✅ | 0 |
| bagel/fig_schema.py | ✅ | ✅ | ✅ | ✅ | 0 |
| bagel/feedback_shift.py | ✅ | ✅ | ✅ | ✅ | 0 |
| bagel/metrics.py | ✅ | ✅ | ✅ | ✅ | 0 |

## 问题清单

### [ISSUE-C001] tests/test_app_service_controller.py:40
**严重性**: P2
**类别**: 覆盖

问题描述: `active_interrupt` 返回的是原始字典格式而非 dataclass，但测试代码访问 `["code"]` 采用了字典语法。这是隐式依赖接口实现细节。

**证据**
```python
assert stopped.active_interrupt["code"] == "EMERGENCY_STOP"  # 行40
```

修复建议: 测试应验证 `active_interrupt.code` 属性访问（如果 dataclass），或统一接口返回类型文档。

---

### [ISSUE-C002] tests/test_composed_verifier.py:18
**严重性**: P2
**类别**: 质量

问题描述: `SimpleMockVerifier.verify` 方法签名使用 `dict[str, Any]` 但缺少 `from __future__ import annotations` 或类型导入，`Any` 未导入。

**证据**
```python
def verify(self, context: VerifierContext | dict[str, Any]) -> VerifierResult:
    # ...
```
文件中第4-8行没有 `from typing import Any`。

修复建议: 在文件顶部添加 `from typing import Any` 导入。

---

### [ISSUE-C003] tests/test_composed_verifier.py:84
**严重性**: P1
**类别**: 正确性

问题描述: VOTE 验证器的置信度计算假设所有子验证器都通过，但代码实际取通过验证器的平均值。测试断言 `0.85` 而实际可能是 `(0.9 + 0.8) / 2 = 0.85`。

**证据**
```python
# v1=0.9 (ok), v2=0.8 (ok), v3=0.2 (fail)
# k=2 需要2个通过
assert pytest.approx(res_vote_ok.confidence) == 0.85  # (0.9 + 0.8) / 2
```

这与代码实现一致，但 `composed_type` 字段名应为小写 `vote`。

修复建议: 确认 VOTE 验证器实现返回的 `evidence["composed_type"]` 确实是 `"VOTE"`（大写），而非 `"vote"`（小写）。

---

### [ISSUE-C004] scripts/run_final_demo.py:28
**严重性**: P2
**类别**: 完整

问题描述: 当 `--record-video` 被指定时，代码仅打印警告但不执行任何操作。缺少视频录制实现，用户无法获得预期功能。

**证据**
```python
if args.record_video:
    print("[final_demo] warning: video recording backend is optional and not configured; continuing", flush=True)
```

修复建议:
1. 移除 `--record-video` 选项或实现该功能
2. 若视频录制是计划功能，添加 TODO 注释和占位符
3. 或改为 `--record-video-dir` 接收路径并记录实现状态

---

### [ISSUE-C005] scripts/run_testbed.py
**严重性**: P2
**类别**: 正确性

问题描述: `run_testbed.py` 仅导入并调用 `testbed.pseudo3d_scene.main()`，没有传递命令行参数给 `main()` 函数。

**证据**
```python
if __name__ == "__main__":
    raise SystemExit(main())  # 未传递 sys.argv
```

在 `run_final_demo.py` 中调用 `run_testbed.py` 时传入的参数（`--title`, `--auto-chaos` 等）无法被处理。

修复建议: 修改 `main()` 函数签名接收 `argv` 参数，或使用 `main(sys.argv[1:])` 方式。

---

### [ISSUE-C006] configs/default.yaml, control.yaml, perception.yaml, input.yaml, telemetry.yaml, testbed.yaml
**严重性**: P1
**类别**: 完整

问题描述: 6个配置文件（`default.yaml`, `control.yaml`, `perception.yaml`, `input.yaml`, `telemetry.yaml`, `testbed.yaml`）为空文件（0字节），没有任何配置内容。

**证据**
```bash
ls -la configs/
# -rw-r--r-- 1 ...    0 ... control.yaml
# -rw-r--r-- 1 ...    0 ... default.yaml
# -rw-r--r-- 1 ...    0 ... input.yaml
# -rw-r--r-- 1 ...    0 ... perception.yaml
# -rw-r--r-- 1 ...    0 ... telemetry.yaml
# -rw-r--r-- 1 ...    0 ... testbed.yaml
```

修复建议:
1. 如果这些配置应由代码动态生成，删除空占位符文件
2. 如果需要配置模板，添加最小有效 YAML 内容
3. 在 `CLAUDE.md` 中记录哪些配置文件是必需的

---

### [ISSUE-C007] configs/genshin_model.yaml (非空配置)
**严重性**: P2
**类别**: 完整

问题描述: `genshin_model.yaml` 配置完整，但缺少 `detector` 和 `camera` 相关的游戏特定配置段落。

**证据**
```yaml
detector: {}
# 缺少 genshin 特定的 detector 配置（如 class_ids, ROI）
camera:
  # 缺少 genshin 视角敏感度参数
```

修复建议: 为 `genshin_model.yaml` 添加游戏特定参数，如：
- `detector.class_ids`（角色、敌人、NPC 等）
- `camera.sensitivity_yaw/pitch`（原神默认视角灵敏度）
- `danger.rois`（特定危险区域坐标）

---

### [ISSUE-C008] tests/test_composed_verifier.py:101-105
**严重性**: P2
**类别**: 正确性

问题描述: `VoteVerifier` 测试用例 `k=2` 但只传入 1 个验证器。这个断言应该失败（k 不能超过 verifier 数量）。

**证据**
```python
with pytest.raises(ValueError, match="cannot exceed"):
    VoteVerifier([v1], k=2)
```

修复建议: 测试逻辑正确，但需要确认错误消息格式与 `match` 正则匹配。

---

### [ISSUE-C009] tests/test_app_service_controller.py:32-41
**严重性**: P2
**类别**: 覆盖

问题描述: `test_agent_controller_emergency_stop_releases_input` 测试没有启动 controller 就调用 `emergency_stop()`，可能测试路径不完整。

**证据**
```python
def test_agent_controller_emergency_stop_releases_input() -> None:
    controller = AgentController()
    stopped = controller.emergency_stop()  # 未调用 start()
```

修复建议: 添加调用 `controller.start()` 后再 `emergency_stop()` 的测试用例，确保实际紧急停止流程被覆盖。

---

## 审查摘要

### 测试覆盖总结
- **核心模块** (StateBus, ModeArbiter, Interrupt, InputLease, Watchdog): 覆盖完整
- **感知平面** (Pipeline, VisualTrigger, Viewport, CameraModel): 覆盖完整
- **控制平面** (CameraServo, ProgressSupervisor, ObstaclePolicy): 覆盖完整
- **执行平面** (VisualActionBlock, Orchestrator, ComposedVerifier): 覆盖较好，有类型问题
- **证据系统** (EvidenceGraph, StrictMode): 覆盖完整
- **BAGEL 信念系统**: 覆盖完整（Arbiter, EvidenceMatrix, FIG, SafeRevision）

### 测试质量总结
- **可重复性**: 大部分测试无随机性，使用固定输入
- **隔离性**: 使用 ThreadPoolExecutor 的并发测试有正确的同步机制
- **断言清晰度**: 大部分断言准确，少数依赖实现细节

### BAGEL 系统评估
- **信念更新逻辑**: EvidenceMatrix 的非对称评分公式正确实现了 "one core contradiction veto" 规则
- **状态机转换**: Arbiter 完整覆盖 confirmed/suspect/falsified 状态
- **元学习机制**: SafeRevision 正确实现级联风险评估和 stale marking 策略
- **证据矩阵**: 线程安全实现，使用 `threading.Lock` 保护

### 配置完整性
- 6个配置文件为空，缺少默认配置内容
- `demo_task.yaml` 和 `model.yaml` 有实际内容
- `genshin_model.yaml` 存在但缺少游戏特定参数

### 建议修复优先级
1. **P0/P1**: 空配置文件清理 (ISSUE-C006)
2. **P1**: `test_composed_verifier.py` 类型导入 (ISSUE-C002)
3. **P2**: 视频录制占位符 (ISSUE-C004)、测试用例覆盖 (ISSUE-C001, ISSUE-C009)