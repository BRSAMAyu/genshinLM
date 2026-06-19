# Sparkle 项目完整 Gap 清单（2026-06-02）

> 方法：6 路并行 agent 逐文件审计，覆盖全部 Python 源文件（685 文件，137K LOC）。
> 已知 6 大关键缺口（前次报告）在文末附录简列，本文主体覆盖**除此之外的全部 gap**。

---

## 一、agent_kernel/ — 神经运行时（18 文件）

### P0 阻断

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AK-1 | loop.py 后台线程竞态 | `loop.py:107-115, 413-470` | StateBus 用了 RLock 但 tick 循环与后台线程之间存在潜在死锁场景，无线程清理保证 |
| AK-2 | cerebrum_agent 自称 "cloud-first" 实际无云端调用 | `cerebrum_agent.py:30-32, 125-143` | 注释声称"云端优先离线回退"，但代码只有 keyword fallback。`solve_visual_puzzle()` 返回硬编码通用动作 |

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AK-3 | unknown_scene_handler 升级后无法真正暂停等用户 | `unknown_scene_handler.py:199-227` | `request_user_help()` 返回 RuntimeOverride 但没有实际暂停机制，也无 companion agent 对接 |
| AK-4 | abyss_chamber_executor 用 tick 计数代替视觉验证 | `abyss_chamber_executor.py:73-85, 139-145` | L81: "placeholder: after enough ticks, assume chamber done"。`_read_stars()` 永远返回 3 |
| AK-5 | cerebellum_controller 多个核心方法返回空值 | `cerebellum_controller.py:46-73` | `parse_desktop_tree()` 返回空 SceneGraph(confidence=0.0)，`commit_yaml_patch()` 只 log 不写文件 |
| AK-6 | brainstem_navigator unstuck 例程是 `pass` | `brainstem_navigator.py:85-95` | jump/dash_back/teleport 全是 `pass` 或只 log warning。`_target_yaw_from_segment()` 返回 0.0 |
| AK-7 | embodied_runtime 接线不完整 | `loop.py:189-228` | 快速路径用硬编码 DailyCommissionDryRunRuntime，`_obs_to_nav_frame()` 大部分占位逻辑 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AK-8 | dialogue_controller VLM delegate 常为 None | `dialogue_controller.py:165-173, 370-390` | `set_vlm_delegate()` 存在但通常未调用，未知对话选项触发 pause 无实际用户交互 |
| AK-9 | cerebrum_agent 失败诊断仅 4 种模式 | `cerebrum_agent.py:58-79, 105-123` | timeout / element_not_found / loading_stuck / combat_death，截图参数被忽略 |
| AK-10 | spinal_reflex_agent 威胁检测仅对 dict frame 工作 | `spinal_reflex_agent.py:53-82` | None 或非 dict frame 返回空列表，阈值全部硬编码 |
| AK-11 | loop.py 元学习桥接失败静默 log | `loop.py:319-335` | BAGEL 分类 + meta_learning_bridge 调用异常时只 debug log，不影响执行流 |

### P3 次要

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AK-12 | loop.py 时间常量全部硬编码 | `loop.py:66, 93, 176, 186, 233, 385, 433, 469` | `time.sleep(0.01/0.02/0.05)` 写死，不是从目标频率计算 |
| AK-13 | adapters.py VLM checker 默认 mock | `adapters.py:260` | `provider: str = "mock"` 应要求显式选择 |
| AK-14 | memory.py 仅关键词匹配，无语义搜索 | `memory.py:40-90` | recall 用简单关键词评分，无 embedding / 时间衰减 / 重要性加权 |

---

## 二、execution/ — 执行层（11 文件）

### P0 阻断

| # | Gap | 文件 | 详情 |
|---|-----|------|------|
| EX-1 | movement_controller.py 完全空文件（0 字节） | `control/movement_controller.py` | 移动控制完全不存在 |
| EX-2 | real_input_backend.py 完全空文件（0 字节） | `execution/real_input_backend.py` | 备选输入后端占位 |

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| EX-3 | BackendFactory 只暴露 3 种后端 | `backend_factory.py:63-86` | console / background / safe_window。directinput 和 flash_focus 存在但未暴露，无插件架构 |
| EX-4 | BackgroundInputBackend 11 个协议方法返回 False | `background_input_backend.py:185-236, 422-478` | mouse_move/click/scroll/drag/type_text/execute_combo 全部 stub。FlashFocusBackend 同样 |
| EX-5 | crash_recovery 恢复仅基于时间 | `crash_recovery.py:150, 398, 409` | 无视觉验证成功、无游戏进程监控集成，auto_checkpoint 返回 False 而非异常 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| EX-6 | execution_runtime 仅 4 个导入者 | `execution_runtime.py` | 主生产流用直接 InputWorker，不经过 ActionContract 管线 |
| EX-7 | computer_use_controller 6+ 方法返回 False | `computer_use_controller.py:73, 80, 93, 99, 113, 121` | 无重试逻辑、VLM 不可用时无回退策略 |

### P3 次要

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| EX-8 | input_worker 静默吞异常 | `input_worker.py:110, 117, 119, 137` | 空 except pass，返回 False 无日志 |
| EX-9 | ui_flow_skill_adapter 多处 False/None | `ui_flow_skill_adapter.py:409-512, 780, 793` | 错误传播断裂 |

---

## 三、core/ — 基础设施

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CO-1 | state_bus 无数据类型校验 | `state_bus.py` | publish() 不验证 payload 类型，slot 写入无 schema 校验 |
| CO-2 | state_bus 无事件持久化/回放 | `state_bus.py` | 纯内存，无 dead letter queue，事件丢失不可恢复 |
| CO-3 | mode_arbiter 无状态转换日志 | `mode_arbiter.py` | 无转换历史追踪，无回调/hooks，FAILED→RUNNING 无防护 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CO-4 | TargetTrack.appearance_signature 始终 None | `types.py:75` | 字段定义但从未写入 |
| CO-5 | Observation.extensions 极少填充 | `types.py:43` | dict 字段但几乎不用 |
| CO-6 | FocusState.window_title/process_name 常为 None | `types.py:16-17` | |
| CO-7 | InputLease.actions 常为空列表 | `types.py:141` | |

---

## 四、control/ — 控制层

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CT-1 | movement_controller.py 空文件（0 字节） | `control/movement_controller.py` | 移动控制不存在 |
| CT-2 | controller_loop 未集成实际控制器 | `controller_loop.py` | 存在但未连接 MovementController |
| CT-3 | controller_verifier 验证逻辑最小 | `controller_verifier.py` | |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CT-4 | sentinel recipes 全用同一个 _verify_screen_stable() | `sentinel/recipes.py:30-55` | 无 recipe 特定验证，工具不可用时 fallback True |
| CT-5 | somatic_state_supervisor 硬编码 HSV/ROI | `somatic_state_supervisor.py:94-112` | 血条/体力条 HSV 范围和 ROI 坐标写死 1920×1080，无自适应校准 |
| CT-6 | SentinelRuntime 未连接 ModeArbiter | 架构级 | sentinel 检测到异常时无法触发模式转换 |

### P3 次要

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CT-7 | 多处 magic number | `somatic_state_supervisor.py` | food_count=5, 阈值常量等 |

---

## 五、app_service/ — 应用服务层（32 文件）

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AS-1 | universal_entry_agent 纯关键词匹配 | `universal_entry_agent.py:87-107` | 无 LLM 语义理解，置信度公式 `0.5 + (关键词数 × 0.2)`，7 个硬编码模板 |
| AS-2 | capsule_forge 默认 StubLlmBackend | `capsule_forge.py:39-43` | LLM None 时返回空字符串，生成模板代码而非真正适配新游戏的逻辑 |
| AS-3 | tool_schema.py FORBIDDEN_TOOLS **从未被调用** | `llm/tool_schema.py:31-32` | `tool_allowed()` 函数定义了安全策略但代码库中无任何地方调用，工具使用无强制约束 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AS-4 | goal_executor 未知目标用固定 3 节点模板 | `goal_executor.py:382-407` | `_build_unknown_goal_graph()` 总是同样结构，不自适应 |
| AS-5 | agent_controller.current_config() 返回固定值 | `agent_controller.py:259-266` | input_backend 永远 "console"，safe_window_required 永远 True |

---

## 六、agent/ — Agent 实现

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AG-1 | zero_shot_agent 无熔断器 | `zero_shot_agent.py:183-212` | API 失败仅简单重试（`time.sleep(0.35*(attempt+1))`），无指数退避、无熔断，最多 30 次迭代 |
| AG-2 | zero_shot_agent VLM/LLM 失败回退到 "unknown"/"wait" | `zero_shot_agent.py:524-573, 575-641` | 异常时 parsed 返回 screen_state="unknown", suggested_action="wait"，无有意义恢复 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| AG-3 | exploration_agent 白名单仅 15 个动作 | `exploration_agent.py:13-29` | 战斗/移动/UI 操纵全在白名单外，探索能力有限 |
| AG-4 | genshin_game_agent 电路断路器最小 | `genshin_game_agent.py` | VLM 故障保护存在但恢复逻辑简单 |

---

## 七、llm/ — LLM 集成层

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| LM-1 | 全部 provider 无熔断器 | `http_provider.py`, `glm_provider.py`, `minimax_provider.py` | 基础重试（1 次），无指数退避、无超时升级、无半开状态 |
| LM-2 | tool_schema FORBIDDEN_TOOLS 未强制执行 | `tool_schema.py:31-32` | 安全策略已定义但未在任何执行路径调用 |

---

## 八、combat/ — 战斗系统

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CB-1 | reflex_evasion 无法达到声称的 50Hz | `reflex_evasion.py:24` | HSV 转换 + 多 mask 操作 + 模板匹配，实际约 20-30Hz |
| CB-2 | live_combat_actuator 6 个异常处理是 `pass` | `live_combat_actuator.py:65, 149, 167, 179, 191, 201` | 紧急治疗/角色切换/技能/爆发/攻击/闪避错误全部静默 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CB-3 | boss_tracker 暴怒检测不完整 | `boss_tracker.py:206` | enrage callback 为 `pass`，无视觉暴怒检测（光环/外观变化） |
| CB-4 | weakpoint_system 伤害值占位 | `weakpoint_system.py:311` | `damage_dealt=200.0 if is_critical else 100.0` 硬编码 |
| CB-5 | boss_mechanic_router fallback 空 | `boss_mechanic_router.py:349` | 默认 boss 处理为空 `pass` |
| CB-6 | 全部检测器用 HSV/边缘检测，无 ML 检测 | `combat/` | 除 YOLO 外全部用简单颜色阈值，无深度学习 |

---

## 九、navigation/ — 导航系统

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| NV-1 | 3D 避障使用 mock 深度图 | `genshin_navigator.py:98-108` | `DepthAnythingEstimator.estimate_depth()` 返回模拟数据（见感知层），避障基于假深度 |
| NV-2 | genshin_dialog_handler 无 OCR | `genshin_dialog_handler.py:107-153` | Canny 边缘检测找选择按钮、阈值化检测文字存在，但不读实际内容 |
| NV-3 | chessboard_solver 棋盘解析未实现 | `chessboard_solver.py:76-94, 92` | "return empty board as placeholder" |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| NV-4 | universal_navigator NullNavigator 全部返回 failed | `universal_navigator.py:24-54` | 无实际回退导航逻辑 |
| NV-5 | quest_marker_follower 依赖小地图颜色检测 | `quest_marker_follower.py:43-118` | 可能受 UI 缩放/分辨率影响，鲁棒性有限 |

---

## 十、perception/ — 感知层（94 文件）

### P0 阻断

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| PC-1 | depth_anything_estimator **完全 mock** | `depth_anything_estimator.py:26-53` | L33: "simulate a depth map"。底部 30%=地面(depth 0.2)，暗中心=障碍物(depth 0.05)，无真正神经网络。导航 3D 避障基于假数据 |
| PC-2 | frame_source.py Win32 截图返回黑帧 | `frame_source.py:64-98` | Win32WindowCapturer 返回安全黑色占位帧，无真正窗口捕获 |

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| PC-3 | generic_screen_classifier 无 VLM 则不可用 | `generic_screen_classifier.py:63-102` | VLM None 时返回 "unknown"，无 CV fallback 分类 |
| PC-4 | auto_calibrator_v2 VLM 集成不完整 | `auto_calibrator_v2.py:62-176` | JSON 解析脆弱（L126-151），无 VLM 时 fallback 到简单启发式 |
| PC-5 | adventure_rank_detector 永远返回 1 | `adventure_rank_detector.py:28, 46, 72` | 三处注释 "Placeholder: returns 1"，无实际 OCR 数字读取 |
| PC-6 | paimon_hint_reader 无 OCR | `paimon_hint_reader.py:133-210` | L133: "OCR placeholder"，L209: "This is a placeholder"，无实际文字提取 |
| PC-7 | timed_chest_detector 定时器硬编码 | `timed_chest_detector.py:101` | `time_remaining = 10.0` 永远 10 秒 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| PC-8 | enkanomiya_daynight_detector placeholder | `enkanomiya_daynight_detector.py:147` | `return True` 硬编码 |
| PC-9 | lava_detector 逃跑方向硬编码 | `lava_detector.py:147-149` | "suggest moving backward"，返回 `(0, 100)` 固定向量 |
| PC-10 | statue_detector fallback 到中心点 | `statue_detector.py:206` | 无真实位置时返回画面中心 |
| PC-11 | dialog_text_capture __eq__ 返回 NotImplemented | `dialog_text_capture.py:183` | 比较逻辑不完整 |

---

## 十一、bagel/ — 信念归因系统

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| BG-1 | belief_proposer 模板驱动，非 LLM | `belief_proposer.py:99-130` | 18 个策略模板跨 6 种失败模式，无法处理未知失败场景 |
| BG-2 | arbiter 无循环依赖处理 | `arbiter.py:143` | belief_depends_on_belief 边可形成循环，振荡阻尼仅计数不追踪具体状态变化 |
| BG-3 | fig_schema "challenged" 状态声明但未使用 | `fig_schema.py` | 11 种生命周期状态中有 "challenged" 但无转换逻辑，僵尸状态累积 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| BG-4 | runtime.py 16 步 API 约 8/16 完整实现 | `runtime.py` | 核心方法可用，高级方法（JIT 重生成、延迟反馈桥）为骨架 |
| BG-5 | evidence_matrix 无空间/时间关联评分 | `evidence_matrix.py:229` | 长归因周期可能丢失相关证据，无审计者可靠性加权 |

---

## 十二、learning/ — 学习系统

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| LR-1 | parameterized_skill_induction 非真正 LCS | `parameterized_skill_induction.py:124-180` | 只检查相邻位置 ±1 匹配，非完整序列对齐，无法检测复杂多动作模式 |
| LR-2 | evolution_engine 无补丁回滚机制 | `evolution_engine.py:360-415` | 补丁经 sandbox 后写入磁盘，但检测到回归时无自动回滚 |
| LR-3 | meta_learning_bridge 归纳阈值硬编码 | `meta_learning_bridge.py` | 3+ 次失败触发，无置信度衰减、无动态阈值 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| LR-4 | decision_memory 缺少高级查询 | `decision_memory.py:132-152` | 无时间范围查询、无 success/failure 过滤、无置信度阈值 |

---

## 十三、planning/ — 规划系统

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| PL-1 | hierarchical_planner JSON 解析脆弱已有回退 | `hierarchical_planner.py:182-192` | strip markdown + find JSON object + raise ValueError，回退到 _fallback_plan()。已实现但有改进空间 |

（注：mainline_runner、mainline_live_bridge、mainline_skill_executor、mission_graph_v4 均为完整实现，无重大 gap。）

---

## 十四、capsules/ — 游戏适配包

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| CP-1 | genshin/providers.py 6/7 是 stub | `genshin/providers.py` | CombatDetector 永远健康、CombatPlanner 硬编码 LMB/E/Q、Navigator 单步 forward、DialogHandler 合成数据、Knowledge 只查 keymap、Verifier 固定 4 个 ID |
| CP-2 | hsr/providers.py 全部 lazy-loading stub | `hsr/providers.py` | 6 个 provider 全部：加载外部模块 → 失败 → 返回 stub fallback。无外部模块则全部退化 |

---

## 十五、data/ + knowledge/ — 数据资产

### P1 关键

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| DA-1 | knowledge/genshin_archon_quests.py 仅序章完整 | `genshin_archon_quests.py:69` | 仅蒙德序章有详细步骤，第一章到第五章全是 placeholder |
| DA-2 | online_guide_system.py 团队提取是 mock | `online_guide_system.py:248-249` | "TODO: implement real team extraction from guide text"，攻略搜索返回 mock 数据 |

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| DA-3 | bagel_events/events.jsonl 生产状态不明 | `data/bagel_events/events.jsonl` | 3.85MB 数据存在但未验证：是否真被写入、schema 是否稳定、是否被消费 |

---

## 十六、telemetry/ — 遥测层

### P0 阻断

| # | Gap | 文件 | 详情 |
|---|-----|------|------|
| TL-1 | event_schema.py 完全空（0 字节） | `telemetry/event_schema.py` | 无事件 schema 定义 |
| TL-2 | metrics.py 完全空（0 字节） | `telemetry/metrics.py` | 无指标收集 |
| TL-3 | replay_index.py 完全空（0 字节） | `telemetry/replay_index.py` | 无回放索引 |
| TL-4 | video_recorder.py 完全空（0 字节） | `telemetry/video_recorder.py` | 无视频录制 |
| TL-5 | __init__.py 空 | `telemetry/__init__.py` | 模块无导出 |

**结论：telemetry 整个目录是空壳，无任何实现。**

---

## 十七、runtime/ — 运行时基础设施

### P2 中等

| # | Gap | 文件:行 | 详情 |
|---|-----|---------|------|
| RT-1 | hot_reload_manager 无回滚 | `hot_reload_manager.py` | `importlib.reload()` 后失败只 log，不回滚到旧版本，无依赖追踪 |
| RT-2 | content_versioning 手动检测 | `content_versioning.py` | 版本变化必须手动调用 `check_ui_change()` 等，无自动检测，有硬编码 `_KNOWN_VERSIONS` |

---

## 十八、orchestration/ — 编排层

### P2 中等

| # | Gap | 文件 | 详情 |
|---|-----|------|------|
| OR-1 | interrupt_handler.py 完全空（0 字节） | `orchestration/interrupt_handler.py` | 中断处理器未实现 |
| OR-2 | __init__.py 空 | `orchestration/__init__.py` | 模块无公共导出 |

---

## 十九、scripts/ — 入口脚本

### P2 中等

| # | Gap | 文件 | 详情 |
|---|-----|------|------|
| SC-1 | calibrate_viewport.py 完全空（0 字节） | `scripts/calibrate_viewport.py` | 校准脚本未实现 |
| SC-2 | replay_run.py 完全空（0 字节） | `scripts/replay_run.py` | 回放脚本未实现 |

---

## 二十、tests/ — 测试

### P2 中等

| # | Gap | 文件 | 详情 |
|---|-----|------|------|
| TS-1 | 30% 测试文件使用 mock（80/262） | `tests/` | 大量 `_MockBackend`、`_fake_frame()`、`fake_response`，验证逻辑但不验证真实集成 |
| TS-2 | 0 个测试连接真实游戏窗口 | `tests/` | 所有 SafeWindowInputBackend 测试用 mock SendInput |
| TS-3 | stub helper 模式普遍 | 多文件 | `_StubEngine`、`StubSearchBackend` 等返回预设结果 |

---

## 二十一、configs/ — 配置

### P3 次要

| # | Gap | 文件 | 详情 |
|---|-----|------|------|
| CF-1 | default.yaml 极简 | `configs/default.yaml` | 仅 1 行，大部分配置散落在代码中作为硬编码常量 |

---

## 二十二、架构级跨切面 Gap

| # | Gap | 影响范围 | 详情 |
|---|-----|---------|------|
| XA-1 | 不一致的错误处理模式 | 全局 | 多处返回 False/None 而非 raise，静默吞异常，调试困难 |
| XA-2 | 多套并行状态追踪 | StateBus + SomaticState + ProgressState | 三个独立状态系统，无统一视图 |
| XA-3 | 硬编码常量散落 | 全局 | HSV 范围、ROI 坐标、超时阈值、动作序列到处写死，无集中配置 |
| XA-4 | 无 LLM 调用成本/延迟监控 | llm/ + agent/ | 不知道每次规划花多少 token/延迟 |
| XA-5 | 无并发安全审计 | 多线程模块 | StateBus 有锁但 tick 循环、学习管道等并发场景未审计 |

---

## 统计

| 严重级别 | 数量 |
|---------|------|
| P0 阻断 | 9 |
| P1 关键 | 28 |
| P2 中等 | 30 |
| P3 次要 | 10 |
| **总计** | **77** |

| 子系统 | P0 | P1 | P2 | P3 | 小计 |
|--------|----|----|----|----|------|
| agent_kernel | 2 | 5 | 4 | 3 | 14 |
| execution | 2 | 3 | 2 | 2 | 9 |
| core | 0 | 3 | 4 | 0 | 7 |
| control | 0 | 3 | 3 | 1 | 7 |
| app_service | 0 | 3 | 2 | 0 | 5 |
| agent | 0 | 2 | 2 | 0 | 4 |
| llm | 0 | 0 | 2 | 0 | 2 |
| combat | 0 | 2 | 4 | 0 | 6 |
| navigation | 0 | 3 | 2 | 0 | 5 |
| perception | 2 | 5 | 4 | 0 | 11 |
| bagel | 0 | 3 | 2 | 0 | 5 |
| learning | 0 | 3 | 1 | 0 | 4 |
| planning | 0 | 0 | 1 | 0 | 1 |
| capsules | 0 | 2 | 0 | 0 | 2 |
| data/knowledge | 0 | 2 | 1 | 0 | 3 |
| telemetry | 5 | 0 | 0 | 0 | 5 |
| runtime | 0 | 0 | 2 | 0 | 2 |
| orchestration | 0 | 0 | 2 | 0 | 2 |
| scripts | 0 | 0 | 2 | 0 | 2 |
| tests | 0 | 0 | 3 | 0 | 3 |
| configs | 0 | 0 | 0 | 1 | 1 |
| 跨切面 | 0 | 0 | 5 | 0 | 5 |

---

## 附录：已报告 6 大关键缺口

以下 6 项在前次诚实评估报告中已作为核心结论提出，不重复详述：

1. **0 个测试连接真实游戏窗口** — 全 mock
2. **DecisionMemory 空（0 条策略）** — 学习系统准备好但没积累
3. **CerebrumAgent 是 keyword fallback** — live_factory 用的不是 LLM 大脑
4. **Genshin providers 多数是 stub** — 6/7 provider 无真实逻辑
5. **CodingAgent LLM 默认 None** — self-programming 不存在
6. **EvolutionEngine 补丁不反馈执行** — 归纳闭环断在最后一步

---

*生成时间：2026-06-02*
*审计方法：6 路 Explore agent 并行扫描，覆盖 685 文件 / 137K LOC*
*与 `docs/honest_exploration_20260602.md` 互补阅读*
