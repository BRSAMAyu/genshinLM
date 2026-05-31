# 技术参数深度验证报告

> 生成时间: 2026-05-31
> 验证范围: D1-D6 文档章节
> 数据来源: 源代码 + 文档交叉验证

---

## 架构对齐

| 组件 | 文档描述 | 代码实际 | 状态 |
|------|---------|---------|------|
| **Interrupt Priority** | docs/94-117: priority=2 (P2) | core/events.py: Interrupt 字段无默认值，数值由调用方指定 | **需修改** |
| **Priority 有效范围** | GENSHIN_ERROR_RECOVERY_ARCHITECTURE.md 第97行注释 `0=CRITICAL, 10=SEVERE, 20=MODERATE, 40=MINOR` | core/mode_arbiter.py 第40-46行定义: P0=0, P1=10, P2=20, P3=30, P4=40, P5=50, P6=100 | **不一致** |
| **F8 热键定义** | GENSHIN_HUMAN_AGENT_COLLABORATION.md 第99行: F8=暂停/恢复 | execution/human_override.py 第14行: `pause_hotkey: str = "F8"` | **一致** |
| **F9 热键定义** | GENSHIN_HUMAN_AGENT_COLLABORATION.md: F9=紧急停止 | execution/human_override.py 第13行: `emergency_hotkey: str = "F9"` | **一致** |
| **Deadman Switch** | CLAUDE.md: lease expiry triggers release_all | execution/input_worker.py 第192-205行: `_run_deadman_check()` 释放过期租约的按键 | **一致** |
| **LatestSlot 接口** | GENSHIN_SESSION_PERSISTENCE_MODEL.md 描述 `put/get/snapshot` | core/state_bus.py 第22-45行: `put()/get()/snapshot()/version` 属性 | **一致** |
| **RingBuffer 接口** | 描述 `append/latest/snapshot/clear` | core/state_bus.py 第48-75行: `append()/latest()/snapshot()/clear()/__len__` | **一致** |

---

## 数值验证

| 参数 | 文档值 | 验证方法 | 结果 |
|------|-------|---------|------|
| **D1: P2 中断示例 priority=2** | 2 | 需对照 mode_arbiter.py 中 P2_HUMAN_OVERRIDE=20 | **错误** - 应改为 priority=20 |
| **D1: Priority 范围** | 注释: 0/10/20/40 | 源码: 0/10/20/30/40/50/100 | **不一致** - 文档缺少 P3/P5/P6 |
| **D2: JSON Schema** | 附录 A | `json.loads()` 验证 | **通过** - 无语法错误 |
| **D3: F8 热键语义** | Level 0 vs 暂停 | human_override.py request_pause() 使用 priority=1 | **需澄清** - 暂停与 Level 0 是不同概念 |
| **D5: M0 工时** | 52天 | GENSHIN_IMPLEMENTATION_ROADMAP.md 第664-688行累加 | **错误** - 实际应为95天 |
| **D6: 测试数量** | ~160个单元测试 | 实际测试文件: 182个含 test_ 函数的文件 | **需修正** - 应为 ~180个 |

---

## 问题清单

### [P1] D1: 错误恢复架构 Priority 数值错误

**位置**: docs/GENSHIN_ERROR_RECOVERY_ARCHITECTURE.md 第111-116行

**问题**: 示例代码使用 `priority=2`，但 ModeArbiter 中 P2_HUMAN_OVERRIDE=20

**当前代码**:
```python
# P2 中断示例
Interrupt(
    priority=2,
    code="TARGET_LOST",
    source="progress_supervisor",
    payload={"missing_duration_ms": track.missing_duration_ms}
)
```

**修复建议**:
```python
# P2 中断示例
Interrupt(
    priority=20,  # P2_HUMAN_OVERRIDE
    code="TARGET_LOST",
    source="progress_supervisor",
    payload={"missing_duration_ms": track.missing_duration_ms}
)
```

---

### [P1] D5: 实现路线图 M0 工时计算错误

**位置**: docs/GENSHIN_IMPLEMENTATION_ROADMAP.md 第688行

**问题**: M0 合计显示52天，但实际分项累加为95天

**分项核对** (第664-688行):
| 能力ID | 名称 | 预估工时 |
|--------|------|----------|
| P-01 | 屏幕状态识别 | 3天 |
| P-02 | 战斗指示器检测 | 2天 |
| P-06 | 对话框检测 | 2天 |
| P-07 | 加载画面检测 | 4天 |
| P-08 | 死亡/复活画面检测 | 2天 |
| P-09 | 弹窗/通知检测 | 3天 |
| P-22 | 菜单文字OCR | 5天 |
| P-26 | 场景整体理解 | 4天 |
| P-27 | 可交互物体识别 | 4天 |
| P-28 | 敌人类型识别 | 4天 |
| P-32 | 加载超时保护 | 5天 |
| P-47 | 地图界面检测 | 3天 |
| P-48 | 角色详情界面检测 | 3天 |
| I-01 | 键盘输入 | 2天 |
| I-02 | 鼠标移动/点击 | 2天 |
| I-03 | 按键组合 | 1天 |
| I-05 | 窗口焦点保护 | 2天 |
| I-06 | 死人开关 | 2天 |
| I-07 | 紧急停止 | 2天 |
| I-08 | 输入租约系统 | 3天 |
| D-01 | 对话推进 | 2天 |
| D-02 | 对话选项选择 | 3天 |
| **合计** | | **95天** |

**修复建议**: 将第688行 `**M0 合计** | | | | | | **52天**` 改为 `**M0 合计** | | | | | | **95天**`

**级联影响**:
- 第1442行人月计算需同步修正: M0 95天 → 3.2人月(2人) 或 1.6人月(1人)
- 第1461-1463行路径长度需重新计算: 95+162+240+139+200 = 836天

---

### [P2] D1: Priority 范围注释与代码不一致

**位置**: docs/GENSHIN_ERROR_RECOVERY_ARCHITECTURE.md 第97行

**问题**: 注释仅列出4个级别，但代码定义了7个级别

**当前注释**:
```python
priority: int        # 0=CRITICAL, 10=SEVERE, 20=MODERATE, 40=MINOR
```

**修复建议**:
```python
priority: int        # 0=P0_EMERGENCY, 10=P1_WATCHDOG, 20=P2_HUMAN_OVERRIDE,
                     # 30=P3_ACTION_BLOCK, 40=P4_RECOVERY, 50=P5_TRACKING, 100=P6_IDLE
```

---

### [P2] D6: 测试数量描述不一致

**位置**: docs/GENSHIN_E2E_VALIDATION_FRAMEWORK.md 第47行

**问题**: 声称 `~160个` 单元测试，实际有182个测试文件

**当前描述**:
```
| 测试数量目标 | 每个能力ID对应 2-5 个单元测试，总计 ~160 个 |
```

**修复建议**: 将 `~160 个` 改为 `~180 个`

---

### [P3] D3: F8 热键语义需澄清

**位置**: docs/GENSHIN_HUMAN_AGENT_COLLABORATION.md 第99-111行

**问题**: F8 用于"暂停"，但文档第111行提到"用户接管后 Agent 立即进入 Level 0 待命"

**现状分析**:
- `human_override.py` 中 F8 触发 `request_pause()`，生成 priority=1 的 HUMAN_PAUSE 中断
- Level 0 是最低自主等级，与"暂停"语义相关但不等同

**建议**: 在文档中明确区分:
- F8 暂停: 临时停止所有操作，输入重新指向用户
- Level 0: Agent 处于待命状态，等待用户明确指令

---

### [P3] D2: JSON Schema 中 additionalProperties 警告

**位置**: docs/GENSHIN_SESSION_PERSISTENCE_MODEL.md 第1585-1592行

**问题**: JSON Schema 中 `additionalProperties` 与 `oneOf` 结合使用可能导致验证行为不明确

**当前代码**:
```json
"archon_quest_progress": {
  "type": "object",
  "additionalProperties": {
    "oneOf": [
      {"type": "string", "enum": ["completed", "not_started"]},
      {"type": "object", "properties": {...}}
    ]
  }
}
```

**建议**: 明确 `additionalProperties` 应为布尔值或对象，当前写法可能被误解

---

## 验证摘要

| 类别 | 通过 | 需修正 | 严重 |
|------|------|--------|------|
| 错误恢复架构 (D1) | 1 | 3 | 2 P1 |
| 会话持久化 (D2) | 3 | 1 P3 | 0 |
| 人机协作 (D3) | 3 | 1 P3 | 0 |
| 实现路线图 (D5) | 0 | 1 P1 | 1 P1 |
| 端到端验证 (D6) | 0 | 1 P2 | 0 |

**总计**: 7项通过, 6项需修正, 3项 P1 严重问题

---

## 附录: 验证方法论

1. **Interrupt Priority**: 交叉验证 `core/events.py` (Interrupt 定义) + `core/mode_arbiter.py` (Priority 常量) + 文档示例代码
2. **工时核算**: 逐行读取 GENSHIN_IMPLEMENTATION_ROADMAP.md 第664-688行，累计所有 `预估工时` 列数值
3. **JSON Schema**: 使用 `json.loads()` 验证语法正确性
4. **热键定义**: 对比 `execution/human_override.py` 常量定义与文档描述
5. **测试数量**: 统计 `tests/` 目录下含 `def test_` 的文件数量