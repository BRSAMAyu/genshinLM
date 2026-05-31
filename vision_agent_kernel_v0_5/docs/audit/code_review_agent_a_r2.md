# Agent A Round 2 深度验证报告

## 验证结果

### 验证项1: request_pause() priority

| 项目 | 内容 |
|------|------|
| **原发现** | `human_override.py:52` 使用 `priority=1` |
| **当前代码** | `priority=1` (第52行) |
| **验证结论** | **不合理** |

**理由**:

1. **优先级常量错位**：
   - `mode_arbiter.py:41` 定义 `P1_WATCHDOG = 10` (P1级别)
   - `mode_arbiter.py:42` 定义 `P2_HUMAN_OVERRIDE = 20` (P2级别)
   - `request_pause()` 使用 `priority=1`，既非 P1_WATCHDOG(10) 也非 P2_HUMAN_OVERRIDE(20)

2. **语义不一致**：
   - 紧急停止使用 `priority=0` — 正确 (P0_EMERGENCY)
   - 暂停请求使用 `priority=1` — **错误**，暗示是 P1_WATCHDOG 级别
   - 人类触发的暂停应属于人类干预类别(P2=20)，而非监控超时类别(P1=10)

3. **优先级数值意义**：
   - 数值越小优先级越高
   - `priority=1` 实际上会 **优先于** `priority=10` (P1_WATCHDOG)
   - 这意味着 HUMAN_PAUSE 中断会抢占 WATCHDOG_TIMEOUT 中断，**行为与设计意图相反**

4. **文档定义矛盾**：
   - `docs/GENSHIN_ERROR_RECOVERY_ARCHITECTURE.md:97` 明确定义：`0=P0_EMERGENCY, 10=P1_WATCHDOG, 20=P2_HUMAN_OVERRIDE`
   - `request_pause()` 使用的 `priority=1` 不在定义范围内

**修复建议**:
```python
# human_override.py:50-68
def request_pause(self, reason: str = "human_pause") -> Interrupt:
    interrupt = Interrupt(
        priority=20,  # 改为 P2_HUMAN_OVERRIDE，与语义一致
        timestamp=self._timebase.now(),
        code="HUMAN_PAUSE",
        source="human_override",
        payload={"reason": reason, "hotkey": self._config.pause_hotkey},
        recoverable=True,
        requires_input_release=True,
    )
```

---

## 深入分析

### 潜在问题1: StateBus 并发安全性

**文件**: `core/state_bus.py:273-283`

```python
def publish(self, event_type: str, data: Any) -> None:
    with self._listeners_lock:
        listeners = list(self._listeners.get(event_type, []))
    for callback in listeners:
        try:
            callback(data)
        except Exception as e:
            ...
```

**问题描述**:
- 在 `with self._listeners_lock` 块结束后才执行 `callback`
- 期间可能有其他线程 `unsubscribe()`，导致 `callback` 引用已被释放
- 虽然 `listeners = list(...)` 复制了列表，但如果回调函数内部持有关联资源（捕获的 self），可能在已销毁对象上调用

**影响分析**: 中等 — 若订阅者在回调执行期间注销，可能触发 AttributeError 或死锁

**修复建议**:
```python
def publish(self, event_type: str, data: Any) -> None:
    with self._listeners_lock:
        listeners = list(self._listeners.get(event_type, []))
    for callback in listeners:
        try:
            callback(data)
        except Exception:
            pass  # 吞掉异常，避免影响其他监听器
```

---

### 潜在问题2: InputWorker DeadmanSwitch 释放逻辑

**文件**: `execution/input_worker.py:192-204`

```python
def _run_deadman_check(self) -> None:
    now = self._timebase.now()
    expired = self._lease_store.expire_due(now)
    if not expired.expired_lease_ids:
        return

    self._log(
        "deadman expired leases "
        f"now={now:.6f} lease_ids={expired.expired_lease_ids} "
        f"keys_to_release={expired.keys_to_release}"
    )
    for key in expired.keys_to_release:
        self._backend.key_up(key, reason="deadman_expired")
```

**问题描述**:
- DeadmanSwitch **仅释放过期的 lease 对应的按键**
- 如果同一按键被多个 lease 持有（未去重），且只有部分过期，可能导致按键状态不一致
- 未验证 `key_up` 是否成功

**影响分析**: 低 — 实际场景中同一按键通常不会被多个 lease 持有（InputLeaseStore 应防重）

---

### 潜在问题3: ModeArbiter 状态转换竞态条件

**文件**: `core/mode_arbiter.py:80-100`

```python
def submit(self, request: ModeRequest) -> ModeDecision:
    if not self._is_valid_mode(request.requested_mode):
        raise ValueError(f"invalid requested mode: {request.requested_mode}")

    with self._lock:
        if not self._can_preempt_locked(request):
            return ModeDecision(...)
        self._current_mode = request.requested_mode
        self._active_request = request
        return ModeDecision(...)
```

**问题描述**:
- `submit()` 持有锁期间修改 `_current_mode` 和 `_active_request`
- 但 `drain_once()` (line 102-109) 先调用 `state_bus.next_mode_request()`，再调用 `submit()`
- 若两个线程同时调用 `drain_once()` 并获取到不同的 request，第一个完成后第二个仍会成功修改模式（因为 `next_mode_request` 在锁外）

**影响分析**: 低 — 高频调用场景可能出现短时不一致，但最终状态正确

---

## 问题卡

### [ISSUE-A-R2-001]
**严重性**: P2
**文件**: `execution/human_override.py:52`
**问题描述**: `request_pause()` 使用 `priority=1`，语义与 P1_WATCHDOG(10) 不符，应使用 `priority=20` (P2_HUMAN_OVERRIDE)

**证据**:
```python
# human_override.py:50-52
def request_pause(self, reason: str = "human_pause") -> Interrupt:
    interrupt = Interrupt(
        priority=1,  # 错误：应为 20
```

与 `mode_arbiter.py:42` 定义 `P2_HUMAN_OVERRIDE = 20` 不一致。

**修复建议**:
```python
def request_pause(self, reason: str = "human_pause") -> Interrupt:
    interrupt = Interrupt(
        priority=20,  # 修复：使用 P2_HUMAN_OVERRIDE
```

---

### [ISSUE-A-R2-002]
**严重性**: P3
**文件**: `core/state_bus.py:273-283`
**问题描述**: `publish()` 方法在锁释放后执行回调，若订阅者在此期间注销，可能导致问题

**证据**:
```python
def publish(self, event_type: str, data: Any) -> None:
    with self._listeners_lock:
        listeners = list(self._listeners.get(event_type, []))
    for callback in listeners:  # 锁外执行
        ...
```

**修复建议**: 在回调执行时使用 try-except 保护，避免异常传播

---

## 总结

1. **确认问题**: `request_pause()` 的 `priority=1` 确实是错误配置，应改为 `priority=20`
2. **新发现问题**: StateBus 的 `publish()` 方法存在潜在的竞态条件
3. **建议优先级**: ISSUE-A-R2-001 应在下一个 sprint 修复

---

## 参考资料

- `core/mode_arbiter.py:40-46` — 优先级常量定义
- `docs/GENSHIN_ERROR_RECOVERY_ARCHITECTURE.md:97` — 优先级架构文档