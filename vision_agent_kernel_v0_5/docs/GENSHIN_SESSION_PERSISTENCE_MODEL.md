# 原神多会话持久化与账号状态模型
# Genshin Impact Session Persistence & Account State Model
# Sparkle Project — Vision Agent Kernel v0.5
# Version: 1.0
# Last Updated: 2026-05-31

> **目的**: 定义 Agent 跨多次会话持续工作的完整数据模型与会话管理协议。原神主线通关需要数十小时游戏时间，不可能单次会话完成。Agent 必须在每次启动时快速恢复上下文，并在会话中持续保存进度。
>
> **范围**: 会话生命周期、账号状态持久化、检查点系统、恢复协议、优先级规划、数据存储实现。
>
> **与现有代码关联**: 对应 `planning/meta_learning.py` (元学习), `planning/daily_loop_scheduler.py` (日常调度), `planning/resource_manager.py` (资源管理), `planning/quest_tracker.py` (任务追踪), `planning/hierarchical_planner.py` (层级规划), `knowledge/genshin_archon_quests.py` (魔神任务), `knowledge/genshin_character_progression.py` (角色养成), `planning/activity_priority_system.py` (活动优先级).

---

## 目录

- [第一章：会话生命周期模型](#第一章会话生命周期模型)
- [第二章：账号状态数据模型](#第二章账号状态数据模型)
- [第三章：检查点（Checkpoint）系统](#第三章检查点checkpoint系统)
- [第四章：会话恢复协议](#第四章会话恢复协议)
- [第五章：优先级队列与任务规划](#第五章优先级队列与任务规划)
- [第六章：多会话连续性场景](#第六章多会话连续性场景)
- [第七章：数据存储实现指南](#第七章数据存储实现指南)
- [附录 A：完整账号状态 JSON Schema](#附录-a完整账号状态-json-schema)
- [附录 B：检查点文件格式示例](#附录-b检查点文件格式示例)
- [附录 C：会话日志格式](#附录-c会话日志格式)

---

## 第一章：会话生命周期模型

会话（Session）是 Agent 从启动到关闭的完整工作周期。一次会话对应玩家的一段连续游戏时间，可能从几分钟到几小时不等。Agent 必须支持完整会话的持久化管理。

### 1.1 会话状态定义

```
SessionState 枚举:
  INITIALIZING    — Agent 正在启动，加载上下文
  RUNNING         — 会话正常运行中
  PAUSED          — 临时暂停（等待用户输入或游戏加载）
  CHECKPOINTING   — 正在保存检查点
  RECOVERING      — 正在从检查点恢复
  SHUTTING_DOWN   — 优雅关闭中
  CRASHED         — 异常中断
```

### 1.2 会话启动协议

当 Agent 启动时，按以下顺序恢复运行状态：

**阶段 0: 环境验证（T+0~2s）**

1. 检测游戏进程是否运行（进程名: `Genshin Impact.exe` 或 ` YuanShen.exe`）
2. 检测窗口焦点（必须聚焦在游戏窗口上）
3. 读取版本号（游戏设置页面）并与上次保存的版本对比
4. 验证存档完整性（检查 `last_session.json` 是否存在）

**阶段 1: 上下文加载（T+2~5s）**

1. 加载 `accounts/{uid}/latest_session.json` — 获取上次会话结束状态
2. 加载 `accounts/{uid}/account_state.json` — 获取完整账号状态
3. 加载 `accounts/{uid}/meta_learning.json` — 获取元学习数据
4. 解析 `last_active_quest_id` 和 `last_active_step_index` — 确认上次停在哪里

**阶段 2: 状态同步（T+5~15s）**

1. 导航到游戏主页面（按 ESC 清空菜单）
2. 通过 OCR 读取当前 AR、当前区域、当前时间
3. 对比持久化状态与实际状态，检测不一致（详见第四章）
4. 若状态过时，触发增量同步流程

**阶段 3: 任务续接（T+15~30s）**

1. 根据 `last_active_quest_id` 和当前任务追踪器状态决定续接策略
2. 若任务已完成：调用战略决策引擎重新计算优先级
3. 若任务仍在进行：恢复上次中断的具体步骤
4. 若游戏状态完全不一致（如玩家手动推进了任务）：重新评估当前状态

**阶段 4: 会话正式开始**

1. 发布 `ModeRequest(ORCHESTRATION, session_started)` 到 StateBus
2. 启动心跳监控（每 5 秒验证一次游戏焦点）
3. 启动增量保存定时器（每 30 秒或关键操作后保存）

### 1.3 会话执行中的增量保存策略

Agent 不在每次操作后立即保存完整状态（I/O 开销过大），而是采用增量保存策略：

**触发增量保存的事件**（任一发生即保存）：

| 触发条件 | 保存内容 | 优先级 |
|---------|---------|--------|
| 任务步骤完成 | 任务进度 + 位置 | HIGH |
| 区域切换 | 新区域 + 任务状态 | HIGH |
| 树脂变化（消耗/回复） | 树脂量 + 时间戳 | MEDIUM |
| 角色等级/突破完成 | 角色状态 | HIGH |
| 队伍配置变更 | 队伍配置 | MEDIUM |
| 每 30 秒定时 | 完整会话状态快照 | LOW |

**增量保存格式**：

```json
{
  "delta_type": "quest_step_complete | region_change | resource_update | team_change",
  "timestamp": "2026-05-31T15:30:00Z",
  "checksum": "sha256...",
  "changes": { ... }
}
```

**并发保护**：保存操作使用文件锁（`flock`）或原子重命名（写临时文件后 `os.rename`），确保多线程安全。

### 1.4 优雅关闭流程（用户主动结束）

```
用户请求关闭
  → [SHUTTING_DOWN]
  → 完成当前原子操作（如正在对话则推进到下一选项）
  → 发布 P5 中断（Idle 模式）
  → 执行最终检查点保存
  → 写入 "session_end_reason": "user_request"
  → 关闭 StateBus 心跳
  → 释放所有 InputLease
  → 进程退出
```

**关键原则**：优雅关闭必须等待当前操作的"安全点"（safe point），即不会留下半完成状态。例如，正在进行的世界任务不能中断在"与 NPC 对话中"的状态。

### 1.5 异常中断后的恢复（崩溃/断电/进程被杀）

**异常中断分类**：

| 类型 | 特征 | 恢复策略 |
|------|------|---------|
| 游戏崩溃 | 游戏进程消失 | 等游戏重启，验证存档，从检查点恢复 |
| 进程被杀 | Agent 被强制终止 | 从 latest_checkpoint.json 恢复 |
| 断电/蓝屏 | 进程无信号消失 | 下次启动时检测 "abnormal_end" 标记，触发强制恢复 |
| 游戏闪退 | 进程异常退出码 | 记录退出码，重启后验证状态 |

**异常检测机制**：

```python
# StateBus shutdown_flag 检测
if state_bus.shutdown_flag.is_set():
    # 收到 SIGTERM/SIGINT，优雅关闭路径
    graceful_shutdown()
elif heartbeat.missed_count > 3:
    # 心跳丢失超过 3 次，判定为异常中断
    trigger_crash_recovery()
```

**恢复流程**：

```
检测到异常中断标记
  → 加载 latest_checkpoint.json
  → 验证 checkpoint 的 checksum（检测损坏）
  → 尝试启动游戏（若游戏崩溃）
  → 从 checkpoint 恢复任务状态
  → 记录 "last_session.abnormal": true
  → 重新执行中断前的操作或重新评估任务
```

**"脏读"防护**：异常中断后，游戏状态可能已被玩家手动修改。Agent 不能假设持久化状态与实际状态一致，必须重新验证（见第四章）。

---

## 第二章：账号状态数据模型

### 2.1 静态账号信息

这些数据很少变化，除非玩家主动进行了影响账号基础属性的操作。

```json
{
  "account_static": {
    "uid": "123456789",
    "server": "asia01",
    "account_name": "玩家昵称",
    "ar": 35,
    "world_level": 4,
    "ar_unlocked_at": "2026-01-15T10:30:00Z",
    "wl_increased_at": "2026-03-20T14:00:00Z"
  }
}
```

**已解锁角色列表**（`characters` 字段）：

```json
{
  "characters": [
    {
      "character_id": "xiangling",
      "constellation": 6,
      "level": 80,
      "ascension_phase": 6,
      "friendship_level": 10,
      "equipped_weapon_id": "the Catch",
      "equipped_artifacts": ["flower_1", "feather_1", "sands_1", "goblet_1", "circlet_1"],
      "talents": {
        "normal_attack": 8,
        "elemental_skill": 8,
        "elemental_burst": 8
      },
      "is_locked": false,
      "owned_since": "2026-02-10"
    }
  ],
  "unlocked_regions": ["mondstadt", "liyue", "inazuma", "sumeru"],
  "unlocked_teleport_waypoints": ["mondstadt_01", "mondstadt_02", "liyue_01"],
  "activated_statues_of_the_seven": ["mondstadt_statue", "liyue_statue"],
  "world_quests_completed": ["WQ001", "WQ002"],
  "world_quest_progress": {
    "WQ003": {
      "steps_completed": 5,
      "total_steps": 12
    }
  }
}
```

**已解锁武器列表**（`weapons` 字段）：

```json
{
  "weapons": [
    {
      "weapon_id": "the_catch",
      "level": 90,
      "ascension_phase": 6,
      "refinement_rank": 5,
      "is_equipped": true,
      "equipped_to_character": "xiangling"
    }
  ]
}
```

**圣遗物库存摘要**（`artifacts_summary` 字段）：

```json
{
  "artifacts_summary": {
    "5_star_count": 45,
    "4_star_count": 120,
    "3_star_count": 200,
    "by_set": {
      "Emblem_of_Severed_Fate": {"count": 8, "full_sets": 1},
      "Noblesse_Oblige": {"count": 6, "full_sets": 1}
    }
  }
}
```

**魔神任务完成进度**（`archon_quest_progress` 字段）：

```json
{
  "archon_quest_progress": {
    "prologue": {
      "act_1": "completed",
      "act_2": "completed",
      "act_3": "completed"
    },
    "chapter_1": {
      "act_1": "completed",
      "act_2": "in_progress",
      "act_2_current_step": "interact_with_zhongli"
    },
    "chapter_2": "not_started"
  }
}
```

### 2.2 动态会话状态

这些字段在每次会话中都会变化，需要高频更新。

```json
{
  "session_dynamic": {
    "current_location": {
      "region": "liyue",
      "subregion": "mt_culant",
      "waypoint_near": "liyue_teleport_05",
      "coordinates_estimate": {"x": 1200, "y": 350, "z": 800}
    },
    "current_quest": {
      "quest_id": "chapter_1_act_2",
      "quest_title": "浮浪浮浪",
      "current_step_index": 7,
      "current_step_objective": "与钟离交谈",
      "is_blocked": false,
      "blocked_reason": ""
    },
    "resources": {
      "original_resin": 120,
      "resin_update_timestamp": "2026-05-31T15:00:00Z",
      "condensed_resin": 2,
      "fragile_resin": 5,
      "mora": 1250000,
      "primogems": 3200,
      "stardust": 150,
      "starglitter": 25
    }
  }
}
```

**每日已完成内容**（`daily_completion` 字段）：

```json
{
  "daily_completion": {
    "date": "2026-05-31",
    "commissions_completed": 4,
    "commission_rewards_claimed": true,
    " ley_lines_daily": {"blue": 2, "gold": 0},
    "world_boss_completed": [],
    "domain_completed": [],
    "expeditions": [
      {"character_id": "traveler", "target": "mingle_joy_resin_20", "hours_remaining": 14},
      {"character_id": "kaeya", "target": "clearwater_resin_20", "hours_remaining": 8}
    ]
  }
}
```

**本周已完成内容**（`weekly_completion` 字段）：

```json
{
  "weekly_completion": {
    "week_start": "2026-05-26",
    "trounce_domain_discounts_used": 2,
    "trounce_domain_discounts_remaining": 1,
    "spiral_abyss_floor_reached": 9,
    "spiral_abyss_stars": 27
  }
}
```

**当前队伍配置**（`active_team` 字段）：

```json
{
  "active_team": {
    "slot_1": {"character_id": "xiangling", "role": "main_dps"},
    "slot_2": {"character_id": "xingqiu", "role": "sub_dps"},
    "slot_3": {"character_id": "bennett", "role": "support"},
    "slot_4": {"character_id": "xiyan", "role": "support"}
  }
}
```

### 2.3 Agent 学习状态（跨会话积累）

这些数据由 `planning/meta_learning.py` 的 `MetaLearningEngine` 管理，跨会话持久化。

```json
{
  "agent_learning_state": {
    "combat_records": [
      {
        "encounter_id": "enc_20260531_001",
        "enemy_name": "ruin_guard",
        "outcome": "win",
        "duration_sec": 45.2,
        "team": ["xiangling", "xingqiu", "bennett", "xiyan"],
        "timestamp": "2026-05-31T14:30:00Z"
      }
    ],
    "enemy_profiles": {
      "ruin_guard": {
        "total_encounters": 12,
        "wins": 10,
        "win_rate": 0.833,
        "best_duration_sec": 32.1,
        "best_team": ["xiangling", "xingqiu", "bennett", "xiyan"],
        "attack_patterns_learned": ["spinning_attack", "missile_volley"],
        "recommended_strategy": "Dodge spinning attack, burst during vulnerable phase"
      }
    },
    "strategy_adjustments": [
      {
        "adjustment_type": "change_team",
        "reason": "Ruin Guard win rate < 40%",
        "priority": 15,
        "applied": false
      }
    ]
  }
}
```

**常见错误模式**（`error_patterns` 字段）：

```json
{
  "error_patterns": [
    {
      "pattern_id": "ERR_001",
      "pattern_type": "teleport_misclick",
      "occurrence_count": 3,
      "last_occurrence": "2026-05-30T22:00:00Z",
      "mitigation": "Always verify waypoint on map before confirming teleport"
    }
  ]
}
```

**用户偏好记录**（`user_preferences` 字段）：

```json
{
  "user_preferences": {
    "preferred_session_duration_min": 45,
    "max_fragile_resin_per_day": 2,
    "skip_cutscenes": false,
    "auto_use_food_threshold_hp": 0.3,
    "preferred_exploration_order": ["sumeru", "fontaine"],
    "abyss_priority": "high"
  }
}
```

---

## 第三章：检查点（Checkpoint）系统

### 3.1 检查点触发条件

检查点是会话状态的完整快照，用于快速恢复。触发条件分为四类：

**A. 关键节点触发（High Priority）**：

| 触发事件 | 检查点内容 |
|---------|-----------|
| 任务步骤完成 | 任务状态 + 位置 + 资源快照 |
| 区域切换完成 | 新区域 + 所有开放传送点 |
| Boss 战胜利 | 战利品 + 任务进度 |
| 角色等级/突破完成 | 角色完整状态 |
| 树脂消耗完成（秘境/Boss） | 更新后树脂量 |

**B. 时间触发（Medium Priority）**：

| 触发条件 | 说明 |
|---------|------|
| 每 5 分钟运行中 | 增量检查点（只保存变化量） |
| 每 30 分钟运行中 | 完整检查点（全量保存） |

**C. 关键操作前后触发（Medium Priority）**：

| 触发条件 | 说明 |
|---------|------|
| 传送前 | 保存当前位置和目标区域 |
| 对话开始前 | 保存当前任务状态 |
| 进入秘境/副本前 | 保存队伍配置和资源 |
| 重要选择前（任务分支） | 保存当前进度，便于回滚 |

**D. 异常触发（Emergency）**：

| 触发条件 | 说明 |
|---------|------|
| 心跳丢失 | 立即保存当前状态 |
| 游戏窗口失焦 > 30s | 保存并暂停 |
| 资源耗尽（树脂=0，角色死亡） | 保存当前状态 |

### 3.2 检查点数据格式

每个检查点保存为 JSON 文件，文件名格式：`checkpoint_{timestamp}_{sequence}.json`

```json
{
  "checkpoint_id": "ck_20260531_153045_001",
  "checkpoint_type": "incremental | full",
  "created_at": "2026-05-31T15:30:45Z",
  "agent_version": "v0.5.1",
  "game_version": "5.4",
  "session_id": "sess_a1b2c3d4",
  "triggered_by": "quest_step_complete",
  "account_state": {
    "ar": 35,
    "resin": 80,
    "current_quest_id": "chapter_1_act_2",
    "current_step_index": 7,
    "current_region": "liyue"
  },
  "task_state": {
    "active_mission_id": "msn_001",
    "nodes_completed": 5,
    "current_node_id": "node_006",
    "loop_iterations": 0
  },
  "location": {
    "region": "liyue",
    "waypoint": "liyue_07",
    "coordinates": {"x": 800, "y": 200, "z": 1200}
  },
  "resources_snapshot": {
    "original_resin": 80,
    "mora": 1200000,
    "fragile_resin": 5
  },
  "checksum": "sha256_a1b2c3d4e5f6..."
}
```

### 3.3 检查点版本管理

采用滚动窗口策略管理检查点历史：

```
checkpoints/
  latest_checkpoint.json          ← 始终指向最新检查点（符号链接）
  checkpoint_20260531_153045.json ← 完整检查点
  checkpoint_20260531_153000.json ← 增量检查点
  checkpoint_20260531_152500.json ← 完整检查点
  checkpoint_20260531_152000.json ← 增量检查点
  checkpoint_20260531_151500.json ← (已过期，删除)
  ...
```

**版本管理规则**：

- 保留最近 20 个检查点（覆盖约 2 小时增量数据）
- 每 10 个增量检查点后保存一个完整检查点
- 完整检查点保留最近 5 个
- 检查点超过 7 天自动删除
- 支持手动触发"强制完整检查点"（用于长时间任务开始前）

### 3.4 检查点压缩策略

为避免磁盘空间无限增长，采用以下压缩策略：

1. **增量压缩**：只保存变化量，不重复保存未变化的字段
2. **历史快照压缩**：超过 3 天的检查点 gzip 压缩
3. **资源快照最小化**：树脂、摩拉等高频变化字段使用差分编码
4. **废弃检查点删除**：任务完成后删除该任务相关的中间检查点

```
压缩前估算（假设每 5 分钟一个检查点）：
  每天 = 288 个检查点 × ~20KB = ~5.7MB/天
  每月 = ~170MB

压缩后目标：
  每月 < 50MB（通过增量保存和 gzip 压缩历史检查点）
```

### 3.5 检查点校验

每个检查点包含 SHA-256 校验和，读取时自动验证：

```python
def load_checkpoint(path: str) -> CheckpointData:
    data = json.load(open(path))
    stored_checksum = data.pop("checksum")
    computed = sha256(json.dumps(data, sort_keys=True).encode())
    if computed != stored_checksum:
        raise CorruptedCheckpointError(f"Checksum mismatch: expected {stored_checksum}, got {computed}")
    return data
```

**损坏检测与修复**：

1. checksum 校验失败 → 尝试加载上一个检查点
2. 连续 2 个检查点损坏 → 标记账号状态需要全量同步
3. 触发紧急检查点（强制完整保存当前状态）

---

## 第四章：会话恢复协议

### 4.1 恢复阶段 1：环境验证

会话启动后首先验证游戏环境：

**检查项**：

| 检查项 | 预期状态 | 失败处理 |
|--------|---------|---------|
| 游戏进程运行 | `Genshin Impact.exe` 存在 | 等待 30s，若仍无则报错"游戏未运行" |
| 游戏窗口焦点 | 窗口标题包含 "Genshin Impact" | 提示用户聚焦游戏窗口 |
| 游戏版本匹配 | 版本与上次保存一致 | 若版本更新，记录并重新验证 API 兼容性 |
| 存档完整性 | 存档可读取 | 若损坏，从最新完整检查点恢复 |

**验证脚本示例**：

```python
def verify_environment(state_bus: StateBus) -> EnvironmentStatus:
    # 1. 检测进程
    if not is_process_running("Genshin Impact.exe"):
        return EnvironmentStatus.GAME_NOT_RUNNING

    # 2. 检测焦点
    if not verify_window_focus():
        return EnvironmentStatus.WINDOW_NOT_FOCUSED

    # 3. 读取游戏版本
    version = read_game_version()
    if version != config.last_game_version:
        log.warning(f"Game version changed: {config.last_game_version} -> {version}")

    # 4. 验证存档
    if not verify_save_integrity():
        return EnvironmentStatus.SAVE_CORRUPTED

    return EnvironmentStatus.READY
```

### 4.2 恢复阶段 2：状态同步

从检查点加载状态后，需要与游戏实际状态进行对比验证：

**同步检查项**：

```python
SYNC_CHECKLIST = [
    ("ar", read_current_ar(), "account_static.ar"),          # AR 是否匹配
    ("region", read_current_region(), "session_dynamic.current_location.region"),  # 区域是否匹配
    ("resin", read_current_resin(), "session_dynamic.resources.original_resin"),   # 树脂是否匹配
    ("quest", read_active_quest(), "session_dynamic.current_quest.quest_id"),     # 当前任务是否匹配
]
```

**状态对比算法**：

```python
def sync_state(persisted: AccountState, game_actual: GameState) -> SyncResult:
    mismatches = []
    for check_name, game_value, persisted_value in SYNC_CHECKLIST:
        if game_value != persisted_value:
            mismatches.append({
                "field": check_name,
                "persisted": persisted_value,
                "actual": game_value,
                "deviation_seconds": estimate_time_deviation(persisted_value, game_value)
            })

    if len(mismatches) == 0:
        return SyncResult.VERIFIED
    elif len(mismatches) <= 2:
        return SyncResult.MINOR_DIVERGENCE  # 可以通过简单修复恢复
    else:
        return SyncResult.MAJOR_DIVERGENCE  # 需要重新评估整个会话状态
```

### 4.3 恢复阶段 3：任务续接

根据同步结果决定任务续接策略：

**策略 A：状态完全匹配（VERIFIED）**

```
直接恢复到中断点，继续执行当前任务步骤
  → 验证目标 NPC/物体是否可交互
  → 若可交互，执行下一步
  → 若不可交互（被遮挡/移动），重新导航
```

**策略 B：微小偏差（MINOR_DIVERGENCE）**

```
例：树脂从 120 变为 115（自然消耗了 5 点）
  → 更新持久化状态中的树脂值
  → 继续原任务（树脂差异不影响大多数任务）
```

**策略 C：重大偏差（MAJOR_DIVERGENCE）**

```
例：玩家手动完成了当前任务，进入了下一个任务
  → 标记原任务为"已完成"（标记完成时间戳）
  → 调用战略决策引擎重新计算优先级
  → 从新任务开始
```

**策略 D：状态完全不一致**

```
例：AR 从 35 变为 40（玩家手动升级）
  → 更新 AR 相关数据（WL、角色等级上限）
  → 重新评估账号状态是否过时
  → 与用户确认是否继续原计划
```

### 4.4 状态过时处理策略

当检测到持久化状态与实际状态不一致时：

```python
STALENESS_HANDLER = {
    "resource_mismatch": {
        "severity": "low",
        "action": "increment_sync",
        "description": "资源数量轻微不匹配，通过增量同步修复"
    },
    "quest_diverged": {
        "severity": "medium",
        "action": "quest_recovery",
        "description": "任务进度与预期不符，需要重新评估任务状态"
    },
    "region_drift": {
        "severity": "medium",
        "action": "re_localize",
        "description": "当前位置与预期不符，需要重新定位"
    },
    "ar_level_up": {
        "severity": "low",
        "action": "update_ar_state",
        "description": "AR 提升，更新账号静态信息"
    },
    "equipment_changed": {
        "severity": "medium",
        "action": "verify_inventory",
        "description": "装备/圣遗物可能被手动更换，验证并同步"
    },
    "abnormal_time_gap": {
        "severity": "high",
        "action": "full_resync",
        "description": "上次会话结束到现在的间隔异常（>24小时），可能存在大量未记录的变化"
    }
}
```

---

## 第五章：优先级队列与任务规划

### 5.1 优先级计算模型

Agent 使用多因子优先级算法决定在给定时间内应该执行什么任务。参考 `planning/strategic_decision_extensions.py` 的 `OverInvestmentDetector` 和 `planning/activity_priority_system.py` 的 `LimitedTimeEvent`。

**优先级因子**：

| 因子 | 权重 | 说明 |
|------|------|------|
| AR 要求紧迫度 | 0.25 | 魔神任务对 AR 的硬性要求（无法绕过） |
| 树脂效率 | 0.20 | 单位时间树脂收益（秘境 > 世界 Boss > 委托） |
| 限时活动 | 0.20 | 距离活动结束的时间（越近优先级越高） |
| 用户偏好 | 0.15 | 用户在 `user_preferences` 中设置的目标 |
| 战略价值 | 0.10 | 对角色养成/队伍构建的贡献 |
| 元学习优化 | 0.10 | 基于历史表现调整（失败率高的任务降低优先级） |

**优先级计算公式**：

```
Priority(task) = Σ(factor_i × weight_i × normalized_score_i)

normalized_score_i = (raw_score - min) / (max - min)  # Min-Max 归一化
```

### 5.2 短期规划（本次会话 15-60 分钟）

基于当前账号状态和可用时间，生成会话任务列表：

```python
def plan_short_term(current_state: AccountState, available_time_min: int) -> MissionQueue:
    """Generate session plan for next 15-60 minutes."""

    # 1. 计算本次会话树脂预算
    resin_budget = calculate_resin_budget(
        current_state.resources.original_resin,
        current_state.daily_completion.resin_used_today,
        available_time_min
    )

    # 2. 生成候选任务列表
    candidates = generate_task_candidates(current_state)

    # 3. 计算每个任务的优先级分数
    scored_tasks = [
        (task, calculate_priority(task, current_state))
        for task in candidates
    ]

    # 4. 按优先级排序并分配时间
    sorted_tasks = sorted(scored_tasks, key=lambda x: -x[1])
    allocated = allocate_time(sorted_tasks, available_time_min)

    # 5. 生成 MissionQueue
    return build_mission_queue(allocated)
```

**典型 45 分钟会话规划**：

```
45 分钟会话计划：
  ├─ 日常委托（4个）≈ 15 分钟
  ├─ 树脂消耗（120 树脂）≈ 20 分钟
  │   ├─ 秘境 × 2（每次 20 分钟，留 20 分钟缓冲）
  │   └─ 树脂可能不足则改为地脉花
  └─ 任务推进（剩余时间）≈ 10 分钟
      └─ 推进当前魔神任务步骤
```

### 5.3 中期规划（1-7 天）

中期规划以"目标"而非"单次会话"为单位。参考 `planning/resource_manager.py` 的 `MultiCharacterResinPlanner`。

**中期目标示例**：

| 目标 | 时长 | 关键里程碑 |
|------|------|-----------|
| 角色升级到 80 | 2-3 天 | 每日树脂 + 地脉花 |
| 主线第三章完成 | 5-7 天 | AR 45 解锁（届时可刷五星圣遗物） |
| 雷电将军突破材料完成 | 3-4 天 | 刷雷音权现、采集天云草实 |
| 深渊 9-12 层通关 | 7-14 天 | 需要两个完整队伍 + 80 级角色 |

**中期规划器**：

```python
@dataclass
class MediumTermGoal:
    goal_id: str
    description: str
    target_date: str
    required_resources: dict[str, int]
    milestones: list[str]
    progress: float = 0.0  # 0.0 - 1.0

class MediumTermPlanner:
    """Plans goals over 1-7 days."""

    def __init__(self):
        self._active_goals: list[MediumTermGoal] = []

    def add_goal(self, goal: MediumTermGoal) -> None:
        self._active_goals.append(goal)

    def compute_daily_targets(self) -> list[Task]:
        """Compute what needs to be done today to stay on track."""
        tasks = []
        for goal in self._active_goals:
            days_remaining = (goal.target_date - today) / 86400
            remaining_progress = 1.0 - goal.progress
            daily_needed = remaining_progress / days_remaining
            tasks.extend(self._decompose_goal(goal, daily_needed))
        return sorted(tasks, key=lambda t: -t.priority)
```

### 5.4 长期规划（主线推进里程碑）

参考 `docs/GENSHIN_MAINLINE_PROGRESSION_CHAIN.md` 的 AR 阶段定义和 `knowledge/genshin_archon_quests.py` 的任务结构。

**长期里程碑**（按 AR 阶段）：

| 阶段 | AR 范围 | 里程碑 | 预计会话数 |
|------|---------|--------|-----------|
| 新手期 | AR 1-20 | 完成序章，获得基础角色 | 3-5 次 |
| 成长期 | AR 20-35 | 国家队 4 人升到 60，序章~一章完成 | 8-12 次 |
| 突破期 | AR 35-45 | 天赋升级，主线推进到 3.5 章 | 10-15 次 |
| 毕业期 | AR 45-55 | 五星圣遗物，深渊满星 | 15-20 次 |

**长期规划数据结构**：

```json
{
  "long_term_milestones": [
    {
      "milestone_id": "ms_ar50",
      "description": "AR 50 解锁，WL7，世界等级封顶",
      "target_ar": 50,
      "required_quests": ["chapter_3_act_4"],
      "estimated_sessions": 15,
      "key_requirements": {
        "character_levels": "minimum_4_chars_at_80",
        "weapon_levels": "4_weapons_at_90",
        "talent_levels": "core_team_talents_at_8"
      }
    }
  ]
}
```

### 5.5 动态调整

会话执行过程中，可能出现意外情况需要调整计划：

| 意外情况 | 调整策略 |
|---------|---------|
| 任务失败（战斗/谜题） | 重试 1-2 次，若持续失败则跳过，标记为待解决 |
| 资源不足（树脂/摩拉） | 切换到资源获取任务（如地脉花），推迟原任务 |
| 游戏崩溃/闪退 | 保存当前状态，重新验证并继续 |
| 限时活动新增 | 插入高优先级活动任务，原计划顺延 |
| 用户临时干预 | 暂停当前任务，接受用户指令，处理完成后恢复 |
| 发现更优路线 | 记录到 `meta_learning.json`，下次会话使用新策略 |

---

## 第六章：多会话连续性场景

### 场景 1：日常循环（每天 15 分钟，持续 7 天）

**会话 1（D+0）**：

```
目标：建立日常习惯基线

进入状态：
  - AR 32, WL 3
  - 树脂 120/200
  - 日常未完成

会话计划（15 分钟）：
  1. 执行 4 个委托（~8 分钟）
  2. 领取凯瑟琳奖励（~1 分钟）
  3. 消耗 80 树脂（秘境 × 2）（~5 分钟）
  4. 保存检查点

输出状态：
  - 日常完成
  - 树脂 40/200
  - meta_learning 更新：记录委托完成时间
```

**会话 2-7（持续 6 天）**：

```
每日状态变化：
  - 树脂每日回复 180 点（加上自然恢复）
  - 周本刷新（第 3 天）：若可用，执行周本Boss × 1
  - 检查点每会话保存，记录连续执行天数

优先级变化（基于日常循环）：
  - 日常委托始终是最高优先级（奖励固定）
  - 树脂超过 160 时自动触发秘境任务
  - 周本冷却刷新时优先执行
```

**连续性关键点**：

- `daily_completion` 字段记录每日完成状态，重启后无需重复
- 树脂跟踪器跨会话保存，下次会话从实际树脂量开始
- 7 天连续执行后，任务标记为"日常习惯已完成"并更新元学习

### 场景 2：角色养成（雷电将军，从获得到完全养成，跨 2-3 周）

**会话 1-2（D+0~1）：材料收集阶段**

```
目标：收集升级材料

进入状态：
  - 雷电将军 Lv 1，刚抽到
  - 需要：摩拉、天云草实、旧刀镡、最胜紫晶碎屑

会话计划：
  1. 导航到稻妻清籁岛
  2. 采集天云草实 × 3
  3. 击杀野伏众获取旧刀镡 × 3
  4. 打雷音权现获取碎屑（30 树脂）
  5. 升级到 Lv 20

检查点保存：
  - checkpoint_after_raiden_materials.json
  - character_state.raiden.level = 20
```

**会话 3-5（D+2~7）：等级提升阶段**

```
目标：将雷电将军升到 80

进入状态：
  - 雷电将军 Lv 20（第一次突破完成）
  - 树脂 160+

会话计划：
  - 每会话消耗 ~160 树脂刷地脉花（经验书 + 摩拉）
  - 每 2-3 天执行一次雷音权现获取突破材料
  - 突破节点：Lv 40, Lv 50, Lv 60, Lv 70, Lv 80

检查点保存：
  - 每个突破节点保存完整角色状态
  - 保存剩余材料需求到 resource_manager
```

**会话 6-8（D+8~14）：天赋升级阶段**

```
目标：升级天赋（E, Q, 普通攻击）

进入状态：
  - 雷电将军 Lv 80，已突破
  - 需要：雷霆之蝶（第 1-3 天）、周三/六刷

会话计划：
  - 参考天赋书日程表（knowledge/genshin_character_progression.py）
  - 每周三/六执行天赋秘境 × 3
  - 保存天赋升级进度

检查点保存：
  - checkpoint_after_raiden_talents.json
  - character_state.raiden.talents = {e: 6, q: 6, na: 6}
```

**会话 9-10（D+15~21）：武器与圣遗物阶段**

```
目标：装备鱼获（The Catch），刷樋套

进入状态：
  - 雷电将军 Lv 80，Talent 6/6/6
  - 武器：鱼获精 5（需钓鱼兑换）
  - 圣遗物：需从零开始刷绝缘套

会话计划：
  - 第一天：完成钓鱼任务换取鱼获
  - 后续每天：刷绝缘套秘境（20 树脂/次）
  - 参考 meta_learning 调整秘境选择

检查点保存：
  - checkpoint_after_raiden_build.json
  - character_state.raiden.equipped = {weapon, artifacts}
```

**跨会话关键点**：

- `character_build_planner`（`planning/character_build_planner.py`）跟踪每个角色的养成进度
- 每会话从检查点恢复时，验证角色实际等级/装备是否与保存一致
- 资源需求清单跨会话持久化，不需要每次重新计算

### 场景 3：主线推进（AR 25 到 AR 35，跨 5-8 次会话）

**场景概述**：

```
AR 25-29（WL 2）：
  - 目标：完成序章 Act III（风魔龙Boss）+ 序章 Act IV（公子）
  - 预计：2-3 次会话
  - 关键：AR 28 解锁稻妻

AR 29-35（WL 3）：
  - 目标：完成第一章 + 第二章序
  - 预计：4-6 次会话
  - 关键：AR 30 解锁深渊 9-11 层，AR 33 解锁稻妻
```

**会话 1（AR 26）**：

```
目标：完成序章 Act III（风魔龙战斗）

进入状态：
  - AR 26, WL 2
  - 序章 Act III 进行中（步骤 3/7）
  - 角色等级：平均 Lv 40

会话计划：
  1. 导航到风龙废墟
  2. 战斗准备（切换队伍，确认食物）
  3. 执行风魔龙 Boss 战（约 10-15 分钟）
  4. 若胜利：过场动画 + 与温迪对话（~5 分钟）
  5. 保存检查点（标记序章完成）

输出状态：
  - 序章 Act III 完成
  - AR 提升（26 -> 28）
  - 解锁周本：风龙废墟
```

**会话 2-3（AR 28~30）**：

```
目标：完成序章 Act IV + 第一章序

进入状态：
  - AR 28（刚完成风魔龙）
  - 序章 Act IV：与公子战斗

会话计划：
  1. 序章 Act IV：前往北风龙王神殿，与公子对话，战斗
  2. 序章完成，获得 4 星香菱（如果还没获得）
  3. 第一章序：前往璃月，与凝光交谈

输出状态：
  - 序章全部完成
  - AR 提升到 29-30
  - 解锁第一章
```

**会话 4-8（AR 30~35）**：

```
目标：完成第一章（甘雨传说任务 + 钟离传说任务）+ 第二章序

进入状态：
  - AR 30+, WL 3
  - 需要：角色等级 Lv 50+，武器 Lv 50+

会话计划：
  - 第一章 Act I：往生堂（钟离）— 2 次会话
  - 第一章 Act II：岩下化的航海（公子在稻妻后需要稻妻解锁）
  - 第一章 Act III：殊典之滨（钟离）— 2 次会话

检查点关键点：
  - 每个 Act 完成时保存完整检查点
  - 记录每个步骤的 NPC 位置（用于恢复）
  - 记录已完成/未完成的子任务
```

**跨会话关键点**：

- `archon_quest_progress` 字段详细记录每个 Act 的步骤进度
- 魔神任务有严格的 AR 前置要求（见 `knowledge/genshin_archon_quests.py`）
- 部分步骤需要特定角色/等级，必须在检查点中记录当前队伍配置
- 稻妻解锁（AR 30）是关键里程碑，需要在 AR 28-30 会话中优先推进

### 场景 4：版本更新（停玩 2 周后恢复，有新内容）

**场景概述**：

```
场景：玩家停玩 2 周（版本 5.3），期间游戏更新到 5.4
风险：
  - 游戏版本变化可能影响截图识别
  - 新活动/限时内容需要重新评估优先级
  - 角色/武器图鉴可能更新（需更新检测模板）
```

**会话 0（恢复准备）**：

```
Agent 启动时检测到：
  1. 上次会话时间：2 周前
  2. 游戏版本：从 5.3 更新到 5.4
  3. 新增内容：版本 5.4 新限时活动

操作：
  1. 加载上次检查点（2 周前的存档）
  2. 读取 changelog（游戏启动界面或公告）
  3. 识别新增的 UI 元素（可能需要重新训练分类器）
  4. 更新 VLM prompt（包含新活动描述）
  5. 重新验证所有感知模块
```

**会话 1（恢复执行）**：

```
目标：验证账号状态 + 执行新活动

进入状态：
  - AR 38, WL 4（2 周自然增长约 +2 AR）
  - 上次会话结束在：第一章 Act III 步骤 5
  - 新活动：版本 5.4 限时活动（还剩 12 天）

会话计划：
  1. 全量状态同步（验证 AR、树脂、任务是否匹配）
  2. 检测到状态偏差（AR 38 vs 上次的 36）：
     - 调用 strategic_decision_extensions 更新 AR 状态
  3. 评估新活动优先级：
     - 活动还剩 12 天，优先级设为 HIGH
     - 检查活动是否与当前任务冲突
  4. 执行：优先完成新活动（如果奖励丰富），原任务顺延

输出状态：
  - 账号状态更新到最新
  - 新活动进度记录
  - 原任务继续（可能需要调整步骤）
```

**恢复关键点**：

- `abnormal_time_gap` 检测：超过 24 小时的间隔触发全量同步
- 新 UI 元素检测：启动时执行 UI 元素扫描，对比已知的模板库
- 活动优先级重算：`activity_priority_system` 重新评估所有活动的剩余时间和奖励价值
- 策略调整：若游戏版本导致某些 Boss 机制变化，`meta_learning` 中的旧记录需要重新验证

### 场景 5：活动限时（新活动上线，14 天内完成）

**场景概述**：

```
活动：版本 5.4 限时活动 "星轨之旅"（14 天）
奖励：420 原石 + 大量材料
难度：中等（推荐 AR 30+）
预计耗时：3-5 次会话，每次 30-60 分钟
```

**会话 1（D+0，活动第一天）**：

```
目标：了解活动规则 + 完成第一阶段

进入状态：
  - AR 35, WL 4
  - 活动：全新（从未完成过）

会话计划：
  1. 导航到活动面板（蒙德冒险者协会）
  2. 阅读活动规则（VLM 解析关键信息）
  3. 识别活动任务类型（可能包含：跑酷、战斗、解谜）
  4. 执行第一阶段任务（~30 分钟）
  5. 保存检查点（标记活动第一阶段完成）

输出状态：
  - 活动进度：阶段 1 完成
  - 原石获得：+80
  - 新增任务：阶段 2 待完成
```

**会话 2-3（D+1~3）**：

```
目标：完成阶段 2-4

进入状态：
  - 活动阶段 1 完成
  - 剩余 11 天

会话计划：
  - 每会话完成 1-2 个阶段
  - 若活动包含战斗：应用 meta_learning 中的战斗策略
  - 若活动包含跑酷/解谜：参考探索引擎策略

优先级调整：
  - 活动优先级设为 CRITICAL（限时 14 天）
  - 日常委托降级为"完成但不优先"（仅当活动任务需要在大世界执行时）
  - 树脂优先用于活动相关秘境
```

**会话 4-5（D+5~10）**：

```
目标：完成剩余阶段 + 领取最终奖励

进入状态：
  - 活动阶段 4-5 进行中
  - 剩余时间：8-4 天

会话计划：
  - 完成所有可完成阶段
  - 收集所有可获得的材料奖励
  - 最后一天：领取所有奖励，检查是否有遗漏

检查点关键点：
  - 每阶段完成时保存检查点
  - 标记每个阶段的奖励是否已领取
```

**会话 6（D+13，最后一天）**：

```
目标：确保完成所有内容

进入状态：
  - 活动还剩 1 天
  - 可能还有未完成的阶段或遗漏的奖励

会话计划：
  1. 全量检查活动完成度
  2. 补完所有遗漏内容
  3. 领取所有奖励
  4. 更新 agent_learning_state，记录活动完成记录

输出状态：
  - 活动完成（100% 奖励）
  - 原石获得：+420（+ 每日委托额外）
  - meta_learning 更新：记录活动完成策略
```

**跨会话关键点**：

- `LimitedTimeEvent` 数据结构记录活动的剩余时间、奖励、完成状态
- 活动优先级计算中，时间因子权重最高（越接近结束，优先级越高）
- 活动完成后，更新 `user_preferences` 记录该活动的价值评分（用于未来活动评估）

---

## 第七章：数据存储实现指南

### 7.1 存储格式选择

| 格式 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **JSON** | 账号状态、检查点、会话日志 | 人类可读，易调试，跨语言兼容 | 冗余较多，序列化/反序列化开销 |
| **JSON + gzip** | 历史检查点、大文件 | 压缩率高，节省空间 | 需要额外解压 |
| **SQLite** | 大量战斗记录、元学习数据 | 查询高效，支持索引 | 需要额外库 |
| **YAML** | 配置文件、任务规格 | 可读性好，适合配置 | 不适合大量数据 |

**推荐策略**：

```
accounts/{uid}/
  account_state.json        ← 当前账号状态（JSON，明文）
  checkpoint/
    latest.json             ← 最新检查点
    history/
      ck_20260531_*.json.gz ← 压缩历史检查点
  meta_learning.db          ← SQLite 数据库（战斗记录、策略调整）
  session_logs/
    2026-05-31.jsonl        ← 会话日志（JSONL）
  config/
    user_preferences.json   ← 用户偏好
    agent_config.json       ← Agent 配置
```

### 7.2 文件组织结构

```
vision_agent_kernel_v0_5/
  data/
    genshin/
      accounts/
        {uid}/
          account_state.json          # 账号静态+动态状态
          checkpoint/
            latest_checkpoint.json    # 符号链接或引用文件
            full/
              ck_full_20260531_150000.json
            incremental/
              ck_inc_20260531_151500.json
              ck_inc_20260531_152000.json
          meta_learning.sqlite        # 元学习数据库
          session_logs/
            2026-05-29.jsonl
            2026-05-30.jsonl
            2026-05-31.jsonl
          quest_progress/
            archon_quests.json        # 魔神任务进度
            world_quests.json        # 世界任务进度
            story_quests.json        # 传说/邀约任务进度
          character_builds/
            xiangling.json           # 各角色养成规划
            raiden.json
            bennett.json
          activity_progress/
            event_5_4_starry_trip.json  # 限时活动进度
          backups/
            backup_20260530_180000.json  # 每日备份
```

### 7.3 并发访问保护

Agent 在多线程环境下运行，必须保护数据文件的并发访问：

```python
import fcntl  # Unix
import threading
from pathlib import Path

class AccountStateLock:
    """File-level locking for account state writes."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def acquire(self, uid: str):
        """Acquire exclusive write lock for account."""
        lock_path = Path(f"data/genshin/accounts/{uid}/.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = open(lock_path, 'w')
        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)

    def release(self):
        """Release write lock."""
        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        self._lock_file.close()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
```

**原子写入模式**：

```python
def save_account_state(uid: str, state: AccountState):
    """Atomically save account state using write-rename pattern."""
    with AccountStateLock.get_instance().acquire(uid):
        # Write to temporary file
        tmp_path = f"data/genshin/accounts/{uid}/account_state.tmp.json"
        with open(tmp_path, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)

        # Verify write
        with open(tmp_path) as f:
            computed_checksum = sha256(f.read().encode())

        # Atomic rename
        dest_path = f"data/genshin/accounts/{uid}/account_state.json"
        os.rename(tmp_path, dest_path)

        # Update checksum file
        checksum_path = f"data/genshin/accounts/{uid}/account_state.sha256"
        with open(checksum_path, 'w') as f:
            f.write(computed_checksum)
```

### 7.4 数据迁移策略

当 Agent 版本升级时，可能需要迁移数据格式：

```python
class DataMigrationManager:
    """Handles data migration between agent versions."""

    MIGRATIONS = {
        "v0.4->v0.5": [
            ("account_state.json", self._migrate_04_to_05),
            ("checkpoint/*.json", self._migrate_checkpoint_format),
        ]
    }

    def run_migrations(self, current_version: str, target_version: str):
        """Run necessary migrations for version upgrade."""
        migration_key = f"{current_version}->{target_version}"
        if migration_key not in self.MIGRATIONS:
            return  # No migration needed

        for pattern, migration_func in self.MIGRATIONS[migration_key]:
            files = glob.glob(pattern)
            for file_path in files:
                backup_path = file_path + ".backup"
                shutil.copy(file_path, backup_path)
                try:
                    migration_func(file_path)
                    log.info(f"Migrated: {file_path}")
                except Exception as e:
                    log.error(f"Migration failed: {file_path}, restoring backup")
                    shutil.copy(backup_path, file_path)
                    raise

    def _migrate_checkpoint_format(self, path: str):
        """Add new fields to checkpoint format."""
        data = json.load(open(path))
        data["agent_version"] = "v0.5"  # Add new field
        data["migration_timestamp"] = time.time()
        json.dump(data, open(path, 'w'), indent=2)
```

**迁移规则**：

1. 所有迁移必须是**向前兼容**（新版本能读旧数据）
2. 迁移前自动创建备份
3. 迁移失败时回滚到备份
4. 记录迁移日志到 `migration.log`

### 7.5 隐私与安全

**敏感信息处理**：

```python
SENSITIVE_FIELDS = [
    "uid",                    # 账号ID
    "account_name",           # 玩家昵称
    "primogems",              # 原石数量（可能关联消费）
    "email",                  # 绑定邮箱（若有）
]

def sanitize_for_logging(data: dict) -> dict:
    """Remove or mask sensitive fields before logging."""
    sanitized = copy.deepcopy(data)
    for field in SENSITIVE_FIELDS:
        if field in sanitized:
            sanitized[field] = "[REDACTED]"
    return sanitized

def encrypt_backup(backup_path: str, key: bytes):
    """Encrypt sensitive backups with AES-256-GCM."""
    from cryptography.fernet import Fernet
    f = Fernet(Fernet.generate_key())
    with open(backup_path, 'rb') as f_in:
        encrypted = f.encrypt(f_in.read())
    with open(backup_path + ".enc", 'wb') as f_out:
        f_out.write(encrypted)
```

**数据存储安全建议**：

1. 账号数据存储在本地，不上传到云端
2. 备份文件使用加密存储
3. 日志文件中脱敏处理敏感信息
4. 定期清理超过 90 天的历史数据
5. 崩溃报告不包含账号ID等直接标识符

---

## 附录 A：完整账号状态 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "genshin_account_state.json",
  "title": "Genshin Account State",
  "description": "Complete account state for Genshin Impact autonomous agent",
  "type": "object",
  "properties": {
    "version": {
      "type": "string",
      "pattern": "^v\\d+\\.\\d+"
    },
    "account_static": {
      "type": "object",
      "properties": {
        "uid": {"type": "string"},
        "server": {"type": "string"},
        "account_name": {"type": "string"},
        "ar": {"type": "integer", "minimum": 1, "maximum": 60},
        "world_level": {"type": "integer", "minimum": 0, "maximum": 8},
        "ar_unlocked_at": {"type": "string", "format": "date-time"},
        "wl_increased_at": {"type": "string", "format": "date-time"}
      },
      "required": ["uid", "ar", "world_level"]
    },
    "characters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "character_id": {"type": "string"},
          "constellation": {"type": "integer", "minimum": 0, "maximum": 6},
          "level": {"type": "integer", "minimum": 1, "maximum": 90},
          "ascension_phase": {"type": "integer", "minimum": 0, "maximum": 6},
          "friendship_level": {"type": "integer", "minimum": 0, "maximum": 10},
          "equipped_weapon_id": {"type": "string"},
          "equipped_artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 5,
            "maxItems": 5
          },
          "talents": {
            "type": "object",
            "properties": {
              "normal_attack": {"type": "integer"},
              "elemental_skill": {"type": "integer"},
              "elemental_burst": {"type": "integer"}
            }
          }
        }
      }
    },
    "weapons": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "weapon_id": {"type": "string"},
          "level": {"type": "integer", "minimum": 1, "maximum": 90},
          "ascension_phase": {"type": "integer", "minimum": 0, "maximum": 6},
          "refinement_rank": {"type": "integer", "minimum": 1, "maximum": 5},
          "is_equipped": {"type": "boolean"},
          "equipped_to_character": {"type": "string"}
        }
      }
    },
    "resources": {
      "type": "object",
      "properties": {
        "original_resin": {"type": "integer", "minimum": 0, "maximum": 200},
        "condensed_resin": {"type": "integer", "minimum": 0},
        "fragile_resin": {"type": "integer", "minimum": 0},
        "mora": {"type": "integer", "minimum": 0},
        "primogems": {"type": "integer", "minimum": 0},
        "stardust": {"type": "integer", "minimum": 0},
        "starglitter": {"type": "integer", "minimum": 0}
      }
    },
    "current_quest": {
      "type": "object",
      "properties": {
        "quest_id": {"type": "string"},
        "quest_title": {"type": "string"},
        "current_step_index": {"type": "integer"},
        "current_step_objective": {"type": "string"},
        "is_blocked": {"type": "boolean"},
        "blocked_reason": {"type": "string"}
      }
    },
    "archon_quest_progress": {
      "type": "object",
      "additionalProperties": {
        "oneOf": [
          {"type": "string", "enum": ["completed", "not_started"]},
          {"type": "object", "properties": {"steps_completed": {"type": "integer"}, "total_steps": {"type": "integer"}, "current_step": {"type": "string"}}}
        ]
      }
    },
    "meta_learning": {
      "type": "object",
      "properties": {
        "combat_records": {"type": "array"},
        "enemy_profiles": {"type": "object"},
        "error_patterns": {"type": "array"},
        "strategy_adjustments": {"type": "array"}
      }
    },
    "user_preferences": {
      "type": "object",
      "properties": {
        "preferred_session_duration_min": {"type": "integer"},
        "max_fragile_resin_per_day": {"type": "integer"},
        "skip_cutscenes": {"type": "boolean"},
        "auto_use_food_threshold_hp": {"type": "number"},
        "abyss_priority": {"type": "string", "enum": ["high", "medium", "low"]}
      }
    }
  },
  "required": ["version", "account_static"]
}
```

---

## 附录 B：检查点文件格式示例

### B.1 完整检查点

```json
{
  "checkpoint_id": "ck_20260531_153045_001",
  "checkpoint_type": "full",
  "created_at": "2026-05-31T15:30:45.123Z",
  "agent_version": "v0.5.1",
  "game_version": "5.4",
  "session_id": "sess_a1b2c3d4e5f6",
  "triggered_by": "periodic_full",
  "account_state": {
    "ar": 35,
    "world_level": 4,
    "resin": 80,
    "mora": 1250000,
    "primogems": 3200,
    "current_region": "liyue"
  },
  "task_state": {
    "active_mission_id": "msn_chapter1_act2",
    "mission_goal": {"type": "quest", "resource_id": "chapter_1_act_2"},
    "nodes_completed": ["node_001", "node_002", "node_003", "node_004", "node_005"],
    "current_node": {
      "id": "node_006",
      "type": "action",
      "skill_binding": "npc_interaction",
      "verifier": "dialog_complete"
    },
    "loop": null
  },
  "location": {
    "region": "liyue",
    "subregion": "mingle_joy_tavern",
    "waypoint": "liyue_teleport_07",
    "coordinates": {"x": 800, "y": 200, "z": 1200},
    "indoor": false
  },
  "team_state": {
    "active_team": ["xiangling", "xingqiu", "bennett", "xiyan"],
    "character_states": {
      "xiangling": {"hp_percent": 1.0, "energy_percent": 0.8},
      "xingqiu": {"hp_percent": 1.0, "energy_percent": 0.6}
    }
  },
  "daily_progress": {
    "commissions_completed": 4,
    "resin_used_today": 120,
    "events_completed": []
  },
  "checksum": "sha256_a1b2c3d4e5f6..."
}
```

### B.2 增量检查点

```json
{
  "checkpoint_id": "ck_20260531_153000_inc",
  "checkpoint_type": "incremental",
  "created_at": "2026-05-31T15:30:00.000Z",
  "agent_version": "v0.5.1",
  "session_id": "sess_a1b2c3d4e5f6",
  "triggered_by": "periodic_incremental",
  "base_checkpoint_id": "ck_20260531_152500_001",
  "changes": {
    "resources": {
      "original_resin": {"from": 100, "to": 80},
      "timestamp": "2026-05-31T15:28:00Z"
    },
    "task_state": {
      "current_node": {"from": "node_005", "to": "node_006"}
    }
  },
  "checksum": "sha256_b2c3d4e5f6g7..."
}
```

---

## 附录 C：会话日志格式

会话日志使用 JSONL（JSON Lines）格式，每行一个 JSON 对象，便于流式追加和增量读取。

### C.1 日志条目类型

```json
// Session start
{"type": "session_start", "timestamp": "2026-05-31T14:00:00Z", "session_id": "sess_a1b2c3d4", "game_version": "5.4"}

// Mission node start
{"type": "node_start", "timestamp": "2026-05-31T14:05:00Z", "node_id": "node_006", "skill_binding": "npc_interaction", "target": "zhongli"}

// Visual observation
{"type": "observation", "timestamp": "2026-05-31T14:05:30Z", "frame_id": 12345, "ui_state": "dialog", "confidence": 0.95}

// Action taken
{"type": "action", "timestamp": "2026-05-31T14:05:32Z", "action_type": "click", "target": "dialog_advance_button", "result": "success"}

// Mission node complete
{"type": "node_complete", "timestamp": "2026-05-31T14:07:00Z", "node_id": "node_006", "duration_sec": 120}

// Error
{"type": "error", "timestamp": "2026-05-31T14:10:00Z", "error_code": "NAV_TARGET_NOT_FOUND", "context": {"target": "teleport_waypoint"}}

// Checkpoint saved
{"type": "checkpoint", "timestamp": "2026-05-31T14:15:00Z", "checkpoint_id": "ck_20260531_141500_001", "type": "full"}

// Session end
{"type": "session_end", "timestamp": "2026-05-31T14:45:00Z", "session_id": "sess_a1b2c3d4", "reason": "user_request", "duration_min": 45, "nodes_completed": 3}
```

### C.2 日志轮转策略

```
session_logs/
  2026-05-29.jsonl      ← 保留 7 天
  2026-05-30.jsonl      ← 保留 7 天
  2026-05-31.jsonl      ← 当前会话追加

单文件大小超过 10MB 时，轮转到新文件：
  2026-05-31_001.jsonl
  2026-05-31_002.jsonl
```

---

## 修订历史

| 版本 | 日期 | 修改内容 |
|------|------|---------|
| 1.0 | 2026-05-31 | 初始版本，涵盖会话生命周期、账号状态模型、检查点系统、恢复协议、优先级规划、连续性场景、存储实现 |