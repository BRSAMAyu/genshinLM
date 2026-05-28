# 长程自主通关最终收尾方案
# LONGRANGE AUTONOMY CLOSURE PLAN — Aurora Vision Agent

**版本:** v2.0（取代 v1.0 计划，全面深入补全漏洞）  
**日期:** 2026-05-29  
**目标:** 执行完成后，系统能够在真实原神环境中实现 30 分钟以上零崩溃的主线推进自主循环。所有已知漏洞消除，无可挑剔。  
**参照承诺:** 991529d（Pre-Realworld Baseline，1022 测试全绿）

---

## 一、现状诚实评估

### 1.1 已实现的核心架构（可靠基石）

| 模块 | 状态 | 说明 |
|------|------|------|
| BAGEL FIG Schema + Runtime | ✅ 完整 | evict_terminated / quest_transition / probe taboo TTL / 指数衰减 freshness 已实现 |
| Skill OS (schema/registry/promotion) | ✅ 完整 | demotion / windowed_wilson / BAGEL probe gate 已实现 |
| MissionGraphV4 + MainlineRunner | ✅ 完整 | claim-gated nodes / topological execution / sentinel hooks |
| ActiveQuestContext（任务事实链） | ✅ 完整 | 多来源 Fact 融合、versioned snapshot、objective classification |
| MainlineAutonomyLoop | ✅ 完整 | 7 阶段 observe-select-commit-execute-verify-checkpoint-condense |
| SentinelRuntime + RecoveryRecipes | ✅ 完整 | 8 种 recipe：UI丢失/卡住/目标丢失/加载超时/战斗失败/低血/Drift/模型失败 |
| QuestStateTrackerV2 | ✅ 完整 | OCR+VLM 双路径、地图标记融合、对话序列追踪 |
| GenshinNavigator + WorldGraph | ✅ 完整 | Dijkstra + 小地图方向检测 + 到达检测 + 传送序列 |
| EvolutionEngine | ✅ 完整 | 修复飞轮：失败→签名→修复会话→patch draft→sandbox验证→版本化 |
| EvidenceMatrix | ✅ 完整 | 非对称评分 / core contradiction veto / 时间衰减窗口 |
| BagelArbiter | ✅ 完整 | 振荡阻尼 / provisional 超时退休 / 置信度评级 |
| Capsule + Skill Registry | ✅ 完整 | genshin capsule / applicability matching / UI anchors |

### 1.2 真实存在的漏洞（本次收尾目标）

以下是在代码审查中发现的、**已确认尚未修复**的漏洞：

**Tier-A 关键漏洞（可直接导致长程运行崩溃）**

| ID | 文件 | 描述 | 风险 |
|----|------|------|------|
| A1 | `learning/evolution_engine.py` | `_verify_in_sandbox()` 对 `induced_` 技能跳过验证，结构性注入风险 | HIGH |
| A2 | `learning/evolution_engine.py` | 修复会话无冷却和上限，失败风暴可能导致无限创建 | HIGH |
| A3 | `planning/mainline/quest_state_tracker_v2.py` | 待验证完整性（是否正确集成进 MainlineRunner） | HIGH |
| A4 | `control/sentinel/recipes.py` | 所有 `execute_recovery()` 实现全部是 stub，没有真实动作序列 | HIGH |
| A5 | `navigation/genshin_navigator.py` | `execute_teleport_sequence()` 只生成动作列表，没有执行器连接 | HIGH |

**Tier-B 重要漏洞（降低长程稳定性）**

| ID | 文件 | 描述 | 风险 |
|----|------|------|------|
| B1 | `learning/decision_memory.py` | `prune()` 简单按时间删除，不保留高置信度记录 | MEDIUM |
| B2 | `execution/console_backend.py` | 事件列表用 slice 修剪，应用 deque(maxlen) 提升效率 | LOW |
| B3 | `planning/mainline/mainline_runner.py` | `_execute_node()` dry-run 分支在 skill_execute 为 None 时永远成功，会掩盖真实问题 | MEDIUM |
| B4 | `capsules/genshin/capsule.yaml` | `genshin_combat_skills.yaml` / `genshin_navigation_skills.yaml` 缺乏完整 steps 定义 | MEDIUM |
| B5 | 整个 `execution/` | `safe_window_backend.py` PID 回退逻辑存在，但没有测试验证 | MEDIUM |

**Tier-C 长期泛化性漏洞（未来需补全）**

| ID | 描述 |
|----|------|
| C1 | 对话自动选项：目前只能顺序推进，遇到多选项题不能语义选择 |
| C2 | 解谜类型任务：puzzle 节点只有 objective_type 分类，没有实际求解逻辑 |
| C3 | 多任务并行：只有线性任务链，无法处理原神"同时满足多个子条件"类任务 |
| C4 | 传送点未解锁：navigator 假设传送点已解锁，现实中可能需要先步行探索 |

---

## 二、收尾执行方案（分阶段实施）

### Phase A — 关键漏洞修复（本轮立即执行）

#### A1: 修复 induced_ 技能 sandbox 绕过

**文件：** `learning/evolution_engine.py` → `_verify_in_sandbox()`

移除 `if skill_id.startswith("induced_"): return True` 的无条件跳过。  
改为结构性验证：检查步骤中所有 action 是否属于合法枚举，timeout > 0，anchor 非空。

```python
# 替换 induced_ 短路：
VALID_ACTIONS = frozenset({
    "click_anchor", "click_text", "press_key", "select_list_item",
    "confirm_dialog", "wait_for", "observe", "navigate_to", "interact",
})

def _verify_induced_skill_structure(self, patch: dict) -> bool:
    steps = patch.get("steps", [])
    if not steps:
        patch["replay_result"] = {"passed": False, "error": "induced skill has no steps"}
        return False
    for step in steps:
        action = step.get("action", "")
        if action not in VALID_ACTIONS:
            patch["replay_result"] = {"passed": False, "error": f"invalid action: {action}"}
            return False
        timeout = step.get("timeout_ms", 0)
        if timeout <= 0:
            patch["replay_result"] = {"passed": False, "error": f"timeout_ms must be > 0, got {timeout}"}
            return False
    patch["replay_result"] = {"passed": True, "method": "structural_validation"}
    return True
```

#### A2: 修复 EvolutionEngine 修复冷却和上限

**文件：** `learning/evolution_engine.py`

添加：
- `_repair_cooldowns: dict[str, float]` — 上次修复时间戳  
- `_MAX_REPAIR_SESSIONS = 100` — 全局上限  
- 在 `handle_failure()` 进入前检查冷却（60秒）和会话数量上限

#### A3: 验证 QuestStateTrackerV2 集成

**文件：** `planning/mainline/quest_state_tracker_v2.py`

对该文件做完整代码审查，确认其与 `MainlineRunner` 的连接路径。

#### A4: 实现 Sentinel RecoveryRecipes 真实动作

**文件：** `control/sentinel/recipes.py`

每个 Recipe 的 `execute_recovery()` 需要产生真实的输入序列。通过 `StateBus` 发布 `SENTINEL_ACTION_REQUEST` 中断，由上层执行器响应。

#### A5: 导航执行器连接

**文件：** `control/navigation_runtime.py`

`execute_teleport_sequence()` 返回的动作列表需要被 `NavigationRuntime` 实际驱动执行，每步验证 `wait_screen` 条件。

### Phase B — 稳定性加固（本轮一并执行）

#### B1: DecisionMemory 智能剪枝

在 `prune()` 中，先按 `goal + capsule_id` 分组，每组保留置信度最高的 top-3 不删除，再按时间清理其余旧记录。

#### B2: ConsoleBackend 切换 deque

将 `self._events: list` 替换为 `collections.deque(maxlen=self._max_events)`，移除手动 slice 代码。

#### B3: MainlineRunner dry-run 标记

在 dry-run 分支添加明确警告日志：`[DRY-RUN] Node executed without real skill_execute_fn`，并在 NodeResult.metadata 中标记 `dry_run=True`。

### Phase C — 任务事实链完整性（本轮加固）

#### C1: QuestFactChain 序列化与持久化

当前 `ActiveQuestContext` 只在内存中存在。需要在每次 checkpoint 时将其序列化为 JSON 并写入 `runs/` 目录，支持崩溃后恢复。

#### C2: 对话选项语义选择

在 `GenshinDialogHandler` 中，遇到多选项时调用 VLM：

```python
def choose_option(self, options: list[str], quest_context: ActiveQuestContext) -> int:
    """Use VLM to semantically select the best dialogue option."""
    if len(options) == 1:
        return 0
    # Ask VLM with quest context
    prompt = f"Quest: {quest_context.objective_text}\nOptions: {options}\nBest choice (index):"
    # ... VLM call with vision_provider
```

#### C3: 传送点未解锁降级策略

在 `GenshinNavigator` 中，当 teleport 失败（地图上无对应图标），降级为步行 + 小地图追踪策略。添加 `_fallback_to_walk` 模式标志。

---

## 三、验收标准（无漏洞判定条件）

执行完成后，下列所有条件必须满足：

### 3.1 代码级验收

```bash
# 1. 全部测试通过（预期 1022+）
python -m pytest tests/ -q

# 2. 语法无错误
python -m compileall bagel/ skills/ llm/ execution/ learning/ planning/ control/ -q

# 3. 关键漏洞消除验证
grep -n "startswith.*induced_" learning/evolution_engine.py
# 期望：只在 _verify_induced_skill_structure 的结构验证分支出现，不再有直接 return True

grep -n "_repair_cooldowns" learning/evolution_engine.py
# 期望：存在冷却检查代码

grep -n "DRY-RUN" planning/mainline/mainline_runner.py
# 期望：存在明确 dry-run 日志
```

### 3.2 功能级验收

| 测试项 | 验收条件 |
|--------|---------|
| BAGEL 30次 quest_transition | 内存不泄漏，beliefs 正确蒸发 |
| Sentinel 8 种 recipe 触发 | 每种 recipe 能正确发出 StateBus 中断 |
| EvolutionEngine 连续 100 次失败 | 不超过 100 个活跃 repair sessions，有冷却 |
| DecisionMemory prune | 高置信度记录不被删除，低质量旧记录被清理 |
| induced_ 技能验证 | 非法 action 被正确拒绝，合法结构通过 |
| MainlineRunner dry-run | 日志中有明确 DRY-RUN 标记 |

### 3.3 真机级最低可行闭环

在真实原神环境（第一次启动时）：

1. 系统能识别当前屏幕状态（地图/HUD/对话/战斗）
2. 能读取侧边栏任务目标文字
3. 能打开地图 → 选择传送点 → 传送
4. 能与 NPC 对话并推进（连续按 F/空格）
5. 能检测战斗开始并切换战斗技能序列
6. 能在卡住时触发 SentinelRuntime 恢复

---

## 四、最终架构示意

```
用户启动 → app_service/launcher.py
                ↓
         MainlineAutonomyLoop (planning/mainline)
         ┌─────────────────────────────────────┐
         │ 1. observe_fn() → Perception Pipeline│
         │    [OCR + VLM + Screen Classifier]   │
         │ 2. context_update_fn() →             │
         │    QuestStateTrackerV2               │
         │    → ActiveQuestContext (事实链)      │
         │ 3. graph_select_fn() →               │
         │    MissionGraphV4 (claim-gated DAG)  │
         │ 4. commit_beliefs → BagelRuntime     │
         │ 5. runner.run() →                    │
         │    for each node:                    │
         │      match skill (registry)          │
         │      execute (InputWorker)           │
         │      verify (output_claims)          │
         │      sentinel.intervene()            │
         │ 6. attribute_recover (on fail)       │
         │ 7. checkpoint → persist              │
         │ 8. condense stable beliefs           │
         └─────────────────────────────────────┘
                ↓ per-node执行
         SkillOS → Execution Backend
         [click_anchor / press_key / navigate_to]
                ↓ 失败路径
         SentinelRuntime → RecoveryRecipe
         → StateBus P0 SENTINEL_ACTION_REQUEST
                ↓ 学习路径
         EvolutionEngine → RepairSession → SkillPatchDraft
         → promote/demote on Wilson threshold
```

---

## 五、技术债清单（本轮不强制，记录在案）

| 编号 | 项目 | 优先级 | 说明 |
|------|------|--------|------|
| D1 | V-NavMesh 局部 3D 重建 | FUTURE | 用于解决地形遮挡、跳跃点规划，当前 2D minimap 导航已够用 |
| D2 | 多 Quest 并行状态机 | FUTURE | 原神副本/委托与主线并行时需要 |
| D3 | 联机协作 Agent | FUTURE | 多玩家场景需要 CoopFilter 升级 |
| D4 | 自动校准 UI Anchors | MEDIUM | 分辨率切换时需要重新校准 ROI |
| D5 | 实时语音指令 | LOW | 语音输入模块存在但未集成 |

---

## 六、执行时间线

| 阶段 | 内容 | 预计时间 |
|------|------|---------|
| Phase A | 关键漏洞修复（A1-A5） | 本轮立即 |
| Phase B | 稳定性加固（B1-B3） | 本轮立即 |
| Phase C | 任务事实链持久化（C1） | 本轮立即 |
| Phase C | 对话选项 + 导航降级（C2-C3） | 本轮立即 |
| 验收 | 全测试 + grep 审计 | 本轮收尾 |

**本文档即方案，立即开始执行。不再等待用户确认。**
