# Agent A Round 2: 跨平面调用链验证

## 2.1 StateBus 纪律审查

### execution/ -> control/: 无违规

### control/ -> execution/: 4 处违规
| 文件 | 行号 | import | 评估 |
|------|------|--------|------|
| controller_protocol.py | 6-7 | PhysicalActionReceipt, SemanticAction | 部分合理，应通过 core/types.py 中转 |
| sentinel/somatic_state_supervisor.py | 337 | InputWorker | **严重违规** — 创建新 StateBus+InputWorker |
| sentinel/notification_handler.py | 9 | SafeWindowInputBackend | TYPE_CHECKING，可接受 |

### control/ -> interaction/: 2 处严重违规
| 文件 | 行号 | import |
|------|------|--------|
| sentinel/somatic_state_supervisor.py | 335-336 | ui_flows.get_flow, UIFlowExecutor |

### execution/ -> perception/: 5 处违规
| 文件 | import |
|------|--------|
| declarative_verifier.py | ObservationGraph |
| observation_verifiers.py | ObservationGraph |
| ui_action_executor.py | ObservationGraph |
| loading_waiter.py | GenshinScreenClassifier |
| ui_flow_skill_adapter.py | OcrPurpose |

### execution/ -> planning/: 3 处违规
| 文件 | import |
|------|--------|
| execution_runtime.py | ScreenStateClaimBuilder |
| closed_loop_runner.py | ScreenStateClaimBuilder |
| daily_loop_executor.py | DailySchedule, ActionRecommendation |

### execution/ -> interaction/: 6+ 处 (灰色地带)
UIFlowSkillAdapter 本身是 execution-interaction 桥接层，但 mouse_motor.py -> ui_anchor, ui_action_executor.py -> ui_anchor 等共享类型应提取到 core/types.py

### core/state_bus.py 反向依赖
- `from planning.screen_state_claim import ScreenStateClaim` (line 11, **顶层硬导入**)
- core 不应反向依赖 planning，造成循环依赖风险

## 2.2 ExecutionRuntime 调用链

### submit() 完整链
1. ContractValidator.validate()
2. _build_lease() -> InputLease (key_states, mouse_delta, actions)
3. InputWorker.submit_lease() (队列满则丢弃)
4. _wait_for_execution() (轮询 active_keys, 5s超时)
5. _verify() -> PhysicalReceipt (verified/failed)

### PhysicalReceipt 生命周期 Gap
- `pending`, `submitted`, `lease_accepted`, `focus_ok` 四个状态从未被赋值
- 文档描述的渐进式状态机未实现
- 5s 超时仍返回 `status="executed"`，语义歧义

### VerifierContext.state 始终为空 {}
- 验证器无法访问状态机上下文
- post_action_frame 默认 None 无保护

## 2.3 InputWorker 边界条件

### 队列满行为
- 普通命令: 丢弃
- 关键命令: 驱逐一个 lease 命令，重试入队

### Gap: lease 被驱逐后 InputLeaseStore 条目残留
- 被驱逐的 lease 仍在 Store 中注册，deadman check 前被视为"活跃"

### 线程异常 release_all
- BaseException 捕获 -> key_up + release_all
- finally 块再次 release_all（冗余但安全）
- **Gap**: 若 backend 不可用，级联异常无更外层保护

### Focus check 竞态
- `_focus_lost_published` 无线程安全保护
- check 和 release 间 TOCTOU 窗口
- 无 "focus recovered" 事件

## 2.4 CrashRecovery 衔接

### crash 检测 (4 种信号)
- process_terminated, stuck_state(30s), black_screen_timeout(10s), no_input_response(5s)

### Gap: 完全隔离
- CrashDetector.detect() **无调用者**
- CrashRecoveryOrchestrator 不持有 StateBus 引用
- 恢复流程纯时间驱动空转，无实际动作
- 与 MainlineRunner/MainlineLiveBridge 无集成

## 2.5 Sentinel 与 MainlineRunner 衔接

### 两个同名 SomaticState 类
1. `somatic_state.py` 的 SomaticState: quest_id, team_state, is_stuck 等
2. `somatic_state_supervisor.py` 的 SomaticState: stamina_ratio, health_ratio, hazard_level 等
- 字段不兼容，无法互转

### SentinelRuntime 恢复通道断路
- `recipe.execute_recovery()` 未传入 executor (StateBus)
- 所有恢复配方的 `_publish()` 因 executor=None 短路
- 配方返回 "success" 但无物理动作执行

### SentinelRuntime 与 MainlineRunner 无直接连接
- SentinelRuntime 是纯计算组件（无 I/O）
- 依赖外部编排层调用 update_snapshot() 和 intervene()

## Gap 汇总

### Critical (4)
1. SomaticStateSupervisor 紧急治疗绕过 StateBus (新 InputWorker+StateBus)
2. SentinelRuntime 恢复动作发布通道断路 (executor=None)
3. CrashRecovery 完全隔离于 StateBus，无实际恢复动作
4. core/state_bus.py 反向依赖 planning 层 (硬导入)

### High (5)
5. 两个同名 SomaticState 类字段不兼容
6. PhysicalReceipt 中间状态从未使用
7. 超时等待返回 status="executed"
8. InputWorker focus check 竞态条件
9. Lease 被驱逐后 InputLeaseStore 条目残留

### Medium (9)
10. VerifierContext.state 始终为空
11. post_action_frame 默认 None 无保护
12. CrashDetector.detect() 无调用者
13. 仅含 DOWN key 的 lease 被 deadman 监督
14. execution/ 大量跨平面直接导入 (15+处)
15. controller_protocol.py 导入 execution/perception 类型
16. agent_kernel 直接依赖 control/execution 具体类
17. claim_adapter.py 导入 runtime 私有函数
18. InputWorker 异常后双重 release_all
