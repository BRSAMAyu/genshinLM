# Aurora Phase 1-4 修复与完善任务清单

> 本文档为 Coding Agent 提供精确到行号的修复指令。每个任务包含：文件路径、行号、问题描述、期望修复方式。
> 最后审计时间：2026-05-26 | 基线 commit：`84884a9`

---

## H: 高优先级（正确性 / 架构问题）

### H1. 生产代码引入 `unittest.mock.MagicMock`

**文件**: `agent/autonomous_task_brain.py`  
**行号**: 140-143

**问题**:
```python
from unittest.mock import MagicMock
self._evolution_engine = EvolutionEngine(
    self._state_bus if self._state_bus is not None else MagicMock()
)
```

`unittest.mock` 是测试依赖，不应出现在生产代码中。`EvolutionEngine` 的构造参数 `StateBus` 在为 None 时用 MagicMock 替代，这是一个隐式的 null object 模式。

**修复方式**:
1. 在 `learning/evolution_engine.py` 中检查 `EvolutionEngine.__init__` 的第一个参数类型和用途
2. 如果 StateBus 参数可选（内部已处理 None），直接传 `None` 而非 `MagicMock()`
3. 如果 StateBus 参数必须非 None，在 `EvolutionEngine` 中添加对 `None` 的处理（graceful degradation，不发布事件），而非在外部用 MagicMock 填充
4. 删除 `from unittest.mock import MagicMock` 这行 import
5. 确保相关测试仍通过

---

### H2. `SkillInductionGate` 调用 `EvolutionEngine` 私有方法

**文件**: `learning/skill_induction_gate.py`  
**行号**: 116

**问题**:
```python
verified = self._engine._verify_in_sandbox(patch_record)
```

调用 `EvolutionEngine` 的 `_verify_in_sandbox` 私有方法。下划线前缀表示这是内部实现细节，随时可能被重构或删除。测试也 mock 了这个私有方法（`test_exploration_and_induction.py` L72, L93, L98, L120, L137），导致测试与实现细节强耦合。

**修复方式**:
1. 在 `learning/evolution_engine.py` 中为 `_verify_in_sandbox` 添加一个 public wrapper：
   ```python
   def verify_skill_in_sandbox(self, patch_record: dict) -> bool:
       """Public API for sandbox verification of a skill patch."""
       return self._verify_in_sandbox(patch_record)
   ```
2. 将 `skill_induction_gate.py` L116 改为调用 `self._engine.verify_skill_in_sandbox(patch_record)`
3. 更新 `tests/test_exploration_and_induction.py` 中所有 `engine._verify_in_sandbox` mock 为 `engine.verify_skill_in_sandbox`
4. 确保测试全部通过

---

### H3. 单事件 Skill 归纳限制了 Skill 复杂度

**文件**: `agent/autonomous_task_brain.py`  
**行号**: 350-369

**问题**:
```python
event = RecordedEvent(...)  # 只创建一个事件
induced = self._skill_induction_gate.induce_skill_from_trace(
    [event], node.semantic_action, self._current_claim.screen_state
)
```

每次探索只传一个 `RecordedEvent` 给 `induce_skill_from_trace`。但真正的 Skill 可能需要多步操作（例如"打开菜单 → 点击任务 → 领取奖励"）。单事件归纳只能产生单步 Skill。

**修复方式**:
1. 在 `AutonomousTaskBrain.__init__` 中新增一个实例变量 `self._exploration_trace: list[RecordedEvent] = []`
2. 在探索成功时，将 event **追加**到 trace 列表而非只传 `[event]`：
   ```python
   self._exploration_trace.append(event)
   induced = self._skill_induction_gate.induce_skill_from_trace(
       self._exploration_trace, node.semantic_action, ...
   )
   ```
3. 在探索失败时（`success = False`），清空 trace：`self._exploration_trace = []`
4. 在 Skill 归纳成功后，也清空 trace：`self._exploration_trace = []`
5. 在新测试中验证：传入两个带有不同 anchor_id 的 RecordedEvent，induce 后产生的 Skill 包含两个 anchor

---

## M: 中优先级（代码卫生 / 潜在风险）

### M1. 未使用的 `Any` import（3 处）

**文件 1**: `planning/applicability_gate.py` L5
```python
from typing import Any  # 未使用
```

**文件 2**: `planning/quest_tracker.py` L7
```python
from typing import Any  # 未使用
```

**文件 3**: `benchmarks/thesis_suite.py` L6
```python
from typing import Any  # 未使用
```

**修复方式**: 删除这三个文件中未使用的 `Any` import。运行 `ruff check planning/applicability_gate.py planning/quest_tracker.py benchmarks/thesis_suite.py` 确认无其他 lint 错误。

---

### M2. `quest_tracker.py` 中 `tracked_target` 是死字段

**文件**: `planning/quest_tracker.py`  
**行号**: L36（赋值为 `""`），L97（永远不被更新）

**问题**: `QuestState.tracked_target` 字段在 `update_state` 中始终赋值为空字符串 `""`，从未被填充任何实际值。这是一个死字段，对外暴露无意义的数据。

**修复方式（二选一）**:
- **方案 A（推荐）**: 从 `QuestState` dataclass 中删除 `tracked_target` 字段，并更新 `update_state` 中的构造调用。同步更新 `tests/test_quest_state_tracker.py` 中所有构造 `QuestState` 的地方。
- **方案 B**: 如果需要保留该字段以兼容未来功能，至少在 `update_state` 中添加一个 TODO 注释说明该字段尚未实现。

---

### M3. `exploration_agent.py` 死代码分支

**文件**: `agent/exploration_agent.py`  
**行号**: 66-69

**问题**:
```python
if isinstance(vlm_res.ui_elements, dict):           # L66
    target_prompt = vlm_res.ui_elements.get(...)     # L67
elif hasattr(vlm_res, "ui_elements") and isinstance(vlm_res.ui_elements, dict):  # L68
    target_prompt = vlm_res.ui_elements.get(...)     # L69
```

L68-69 是死代码。如果 L66 的 `isinstance(vlm_res.ui_elements, dict)` 为 False，那 L68 的 `isinstance(vlm_res.ui_elements, dict)` 也必然为 False。

**修复方式**: 删除 L68-69 的 `elif` 分支，只保留 L66-67 的 `if` 分支。如果需要处理 `ui_elements` 不存在的情况，加一个 else 分支保留 `target_prompt = "target"` 的默认值。

---

### M4. `exploration_agent.py` 盲点首元素点击缺安全验证

**文件**: `agent/exploration_agent.py`  
**行号**: 92-101

**问题**:
```python
# Fallback 2: Interactive elements exist, click the first one if safe
if actionable:
    first = actionable[0]
    return ExplorationAction(
        action_type="click_anchor",
        target=first.element_id,
        ...
        requires_human_approval=requires_approval,
    )
```

当目标与所有可操作元素都不匹配时，直接点击第一个元素。这是最后一个 fallback，但可能点击危险元素（如"删除"、"购买"、"确认充值"）。

**修复方式**:
1. 新增一个危险关键词列表（如 `"delete"`, `"remove"`, `"purchase"`, `"buy"`, `"confirm"`, `"delete"`, `"删除"`, `"购买"`, `"确认"`）
2. 在 Fallback 2 中，跳过 `text` 匹配危险关键词的元素
3. 如果所有可操作元素都被过滤掉，走 Fallback 3（observe）
4. 为此路径新增测试：传入一个可操作元素但 text 为 "Delete"，验证返回的是 observe 而非 click

---

### M5. `skill_capability_catalog.py` 缩进不一致

**文件**: `planning/skill_capability_catalog.py`  
**行号**: 98-100

**问题**: 在 `from_sources` 方法中，manifest 路径构造 `SkillCatalogEntry(...)` 时，L98-100 的缩进为 16 spaces，而相邻参数行为 20 spaces。Python 允许这种不一致（只要在开括号右侧即可），但破坏了代码可读性。

**修复方式**: 将 L98-100 的缩进对齐到与其他参数行一致（20 spaces）：
```python
                entry = SkillCatalogEntry(
                    skill_id=spec.skill_id,
                    capsule_id=manifest.capsule_id,
                    source="capsule_manifest",
                    kind=spec.kind,
                    capabilities=list(spec.capabilities),
                    resources=list(spec.resources),
                    verifiers=list(spec.verifiers),           # <- 对齐
                    ui_anchors=list(getattr(spec, "ui_anchors", [])),  # <- 对齐
                    planner_tags=list(spec.planner_tags),      # <- 对齐
                    risk_level=spec.risk_level,
                    capabilities_required=list(spec.capabilities_required),
                    capabilities_provided=caps_prov,
                    failure_modes=list(spec.failure_modes),
                    recovery_policy=dict(spec.recovery_recovery),
                )
```

---

### M6. `autonomous_task_brain.py` 跨层导入 `app_service.skill_manager`

**文件**: `agent/autonomous_task_brain.py`  
**行号**: 39

**问题**:
```python
from app_service.skill_manager import RecordedEvent
```

`agent/` 是核心层，不应依赖 `app_service/` 应用层。`RecordedEvent` 应该定义在更低层的位置。

**修复方式**:
1. 检查 `app_service/skill_manager.py` 中 `RecordedEvent` 的定义
2. 如果 `RecordedEvent` 是一个简单的数据类，将其移到 `recording/record_schema.py` 或 `execution/` 下
3. 在 `app_service/skill_manager.py` 中改为从新位置 re-import
4. 更新 `agent/autonomous_task_brain.py` 和 `tests/test_exploration_and_induction.py` 的 import 路径

---

## L: 低优先级（测试覆盖不足）

### L1. 缺失测试：exploration_agent 盲点首元素点击 fallback

**文件**: `tests/test_exploration_and_induction.py`

**新增测试**: 验证当 goal 不匹配任何可操作元素的 text 时，系统点击第一个非危险元素或返回 observe。

```python
def test_exploration_agent_fallback_first_safe_element(self, mock_perception):
    """When no element matches the goal, click first non-dangerous element."""
    agent = ExplorationAgent(mock_perception, risk_level="medium")
    state = ScreenStateClaim(
        game_id="hsr",
        screen_state="menu",
        confidence=0.9,
        source="vlm",
        ui_elements=(
            UIElementClaim("el1", "button", "Settings", (0.1, 0.2, 0.3, 0.1), 0.9, "ocr"),
        ),
    )
    action = agent.explore_next_step(np.zeros((10, 10, 3)), "领取", state)
    assert action.action_type == "click_anchor"
    assert action.target == "el1"
```

---

### L2. 缺失测试：`distill()` 异常路径

**文件**: `tests/test_exploration_and_induction.py`

**新增测试**: 验证当 `SemanticSkillDistiller.distill()` 抛出异常时，`SkillInductionGate.induce_skill_from_trace()` 返回 None 而非崩溃。

```python
def test_skill_induction_gate_distill_exception(self):
    distiller = MagicMock(spec=SemanticSkillDistiller)
    distiller.distill.side_effect = RuntimeError("distill failed")
    engine = MagicMock(spec=EvolutionEngine)

    gate = SkillInductionGate(distiller, engine)
    events = [RecordedEvent(
        event_type="mouse_click", timestamp=100.0,
        active_window_title="hsr", observation_summary={},
        target_state="TRACKED", payload={"anchor_id": "btn"},
    )]
    entry = gate.induce_skill_from_trace(events, "test", "menu")
    assert entry is None
```

---

### L3. 缺失测试：quest_tracker VLM scene description fallback

**文件**: `tests/test_quest_state_tracker.py`

**新增测试**: 验证当 OCR 未匹配任务文本时，VLM scene description 的 fallback 提取。

```python
def test_quest_tracker_vlm_scene_fallback(self):
    tracker = QuestStateTracker()
    claim = ScreenStateClaim(
        game_id="genshin",
        screen_state="overworld",
        confidence=0.9,
        source="vlm",
        raw_ocr_texts=("Some unrelated text",),
        scene_description="The quest goal is to defeat three slimes",
    )
    state = tracker.update_state(claim)
    assert state.objective_text != ""
    assert "defeat three slimes" in state.objective_text.lower() or state.objective_text != "No active quest"
```

---

### L4. 缺失测试：quest_tracker 中文无冒号 pattern

**文件**: `tests/test_quest_state_tracker.py`

**新增测试**: 验证 `quest_tracker.py` L51-52 中 `委托\s*(.*)` 和 `追踪\s*(.*)` 两个无冒号的中文 pattern。

```python
def test_quest_tracker_chinese_patterns_no_colon(self):
    tracker = QuestStateTracker()
    claim = ScreenStateClaim(
        game_id="genshin",
        screen_state="overworld",
        confidence=0.9,
        source="ocr",
        raw_ocr_texts=("委托调查附近区域",),
    )
    state = tracker.update_state(claim)
    assert state.objective_text != "No active quest"
```

---

### L5. 缺失测试：`goal_stack.to_list()`

**文件**: `tests/test_quest_state_tracker.py`

**新增测试**:
```python
def test_goal_stack_to_list(self):
    stack = GoalStack()
    stack.push("a")
    stack.push("b")
    stack.push("c")
    assert stack.to_list() == ["a", "b", "c"]
    assert stack.to_list() is not stack.to_list()  # 返回副本
```

---

### L6. 缺失测试：quest_tracker failure_count 重置

**文件**: `tests/test_quest_state_tracker.py`

**新增测试**: 验证当任务目标改变时 `failure_count` 重置为 0。

```python
def test_quest_tracker_failure_count_resets_on_objective_change(self):
    tracker = QuestStateTracker()
    # First: blocked
    claim1 = ScreenStateClaim(
        game_id="genshin", screen_state="overworld", confidence=0.9,
        source="ocr", raw_ocr_texts=("Quest: Go to A", "stuck"),
    )
    state1 = tracker.update_state(claim1)
    assert state1.failure_count == 1

    # Then: new objective (not blocked)
    claim2 = ScreenStateClaim(
        game_id="genshin", screen_state="overworld", confidence=0.9,
        source="ocr", raw_ocr_texts=("Quest: Talk to NPC",),
    )
    state2 = tracker.update_state(claim2)
    assert state2.failure_count == 0
    assert state2.objective_text == "Talk to NPC"
```

---

## F: Flaky Test 修复

### F1. `test_genshin_perception_bridge_publishes_to_slots` 超时

**文件**: `tests/test_genshin_app_integration.py`

**问题**: 3 秒超时在 CI 或高负载下不够。

**修复方式**: 将超时从 3.0s 增加到 10.0s，或将轮询 wait 改为更短的 sleep 间隔（50ms）以更快检测到状态变化。

---

### F2. `test_genshin_app_full_pipeline_dryrun` 超时

**文件**: `tests/test_phase4_dryrun.py`

**问题**: 4 秒超时不够完成整个 pipeline 启动到 COMPLETE 流程。

**修复方式**: 将超时从 4.0s 增加到 15.0s，或将轮询 wait interval 从当前值减小到 100ms。

---

## 验证清单

修复完成后，执行以下命令验证：

```bash
# 1. 全量测试
python -m pytest tests/ -q

# 2. Lint
ruff check agent/ planning/ learning/ benchmarks/ tests/

# 3. 类型检查
mypy agent/ planning/ learning/ --ignore-missing-imports

# 4. Core 边界
python scripts/check_core_boundaries.py --root .

# 5. 编译检查
python -m compileall agent/ planning/ learning/ benchmarks/ tests/ -q
```

所有修复必须通过以上全部验证，且不引入新的测试失败。
