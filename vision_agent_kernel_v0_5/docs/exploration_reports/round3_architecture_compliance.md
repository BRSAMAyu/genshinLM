# Round 3: 架构合规性审查报告

## 1. 五平面通信纪律合规

### CRITICAL 违规
- **V-C1**: SomaticStateSupervisor 绕过 StateBus 创建独立 InputWorker+StateBus (`control/sentinel/somatic_state_supervisor.py:335-342`)
- **V-C2**: core/state_bus.py 反向依赖 planning 层 (`core/state_bus.py:11`)

### HIGH 违规
- **V-H1**: controller_protocol.py 导入 execution/perception 类型 (line 6-8)
- **V-H2**: execution -> perception 5 处直接导入 (ObservationGraph, GenshinScreenClassifier, OcrPurpose)
- **V-H3**: execution -> planning 3 处直接导入 (ScreenStateClaimBuilder, DailySchedule)
- **V-H4**: hold_click fallback 直接 Win32 API (`ui_flow_engine.py:526`)

### MEDIUM 违规
- V-M1: notification_handler TYPE_CHECKING 导入 (可接受)
- V-M2: execution -> interaction 6+ 处 (UIFlowSkillAdapter 是桥接层，灰色地带)

## 2. 关键设计规则合规

### 规则 1: No blocking waits
- **严重**: `learning/evolution_engine.py:116` — `time.sleep(30)` 30秒阻塞
- **中等**: 交互层 4 处 `time.sleep(1-2s)` (chest, crafting, statue, launcher)
- **合规**: 多处使用 `_chunked_sleep` 模式

### 规则 2: No single-frame decisions
- **合规**: 所有 current_frame/previous_frame 使用均在感知层图像特征提取
- **合规**: ProgressState 正确使用 EWMA + 时间窗口斜率

### 规则 3: Monotonic clock only
- **P1 违规**: `agent_kernel/adapters.py:501-502` 使用 `time.time()` 生成 InputLease 时间戳（影响 deadman switch）
- **P1 违规**: `runtime/audit_scheduler.py` 全部使用 `time.time()` 调度逻辑
- **P1 违规**: `learning/decision_memory.py:119,211` 使用 `time.time()` 逻辑比较
- **P2**: ~20 个核心文件中 `time.time()` 用于逻辑判断

### 规则 4: LLM stays strategic
- **合规**: 未发现 LLM 像素级决策

### 规则 5: Every action has a fallback
- **P1**: ~34 个语义动作是 stub，无实际执行
- **P1**: SentinelRuntime 恢复通道断路
- **P1**: CrashRecovery 完全隔离

## 3. 安全模型合规

### dry-run 默认模式: 基本合规
### InputLease -> InputWorker 路径: 合规，但有 3 处绕过
### Deadman Switch: 合规，但 time.time() 影响准确性
### Emergency Stop: 基本合规，4 条路径确认

## 4. 类型系统合规

### slots=True: core/ 全部合规，5 个非核心 dataclass 缺失
### Protocol-only: 高度合规，无 ABC 使用
### 类型不匹配: 4 处关键问题 (obs.image, 双SomaticState, ScreenStateKind, CombatAction vs InputLease)
### from __future__ import annotations: 278 个文件缺失 (45%)

## 5. 优先级整理

详见 `final_exploration_summary.md`
