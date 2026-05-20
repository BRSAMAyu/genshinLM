# Genshin Impact (原神) 专项优化方案

> **文档定位**: 本文档是 Sparkle Project 从通用测试环境迁移到原神真实场景的完整实施方案。
> 它不是架构白皮书，而是包含具体像素位置、HSV 阈值、Skill 模板、知识库 Schema 的工程手册。
> **所有执行能力仅限于授权沙盒 / 自建测试环境 / QA 场景。**

---

## 一、迁移全景：从 Testbed 到原神

### 1.1 差异矩阵

| 维度 | 当前 Testbed | 原神真实场景 | 影响 |
|------|-------------|-------------|------|
| 窗口标题 | `pseudo3d_scene` | `原神` / `Genshin Impact` | Profile 匹配 |
| 进程名 | Python 进程 | `YuanShen.exe` / `GenshinImpact.exe` | SafeWindowBackend |
| 目标 | 红/绿像素方块 | 3D 怪物，多体型，多段 HP | 需要怪物检测模型 |
| HP 条 | 合成红色条 | 敌人 HP 条（屏幕顶部暗红色，Boss 多段），角色 HP（绿色渐变） | ROI + HSV 参数全不同 |
| 采集物 | 绿色像素块 | 矿石（攻击破坏）/ 植物（F 键）/ 宝箱（交互） | 需按类型区分交互方式 |
| CD 显示 | 信号 dict | 技能图标灰化 + 弧形暗化 + 数字倒计时 | 需 OCR 或模板匹配 |
| 危险信号 | 合成 dict | 红光闪烁、地面红圈、Boss 前摇动画 | 需像素级危险检测 |
| 导航 | 无 | 小地图 → 大地图(M) → 传送锚点 | 需地图交互 Skill |
| 鼠标 | 线性映射 | 强制加速度 + Y轴75%灵敏度 | 需加速度补偿 |
| FOV | 可控 | 不可调，固定 FOV | CameraModel 需实测参数 |

### 1.2 安全边界确认

| 操作 | 风险等级 | 说明 |
|------|---------|------|
| 屏幕截取 / OCR | **安全** | 无代码注入，OS 层面读取，不被 `mhyprot2.sys` 检测 |
| SendInput 键鼠模拟 | **低风险** | 外部输入，被视为"辅助"而非注入 |
| 内存读取/修改 | **严禁** | 内核级驱动检测，封号风险 |
| DLL 注入 | **严禁** | 被检测，封号 |
| **结论** | 当前架构（DXcam + SendInput）完全在安全边界内 | |

### 1.3 推荐运行环境

```
显示模式: Borderless Windowed (v4.4 原生支持，不会 Alt+Tab 最小化)
分辨率: 1920x1080 (模板匹配 + OCR 最稳定)
渲染分辨率: 1.0 (无超采样伪影)
FPS: 60
VSync: Off
相机灵敏度: 需校准（见 2.4 节）
```

---

## 二、Profile 系统：原神专用 ROI

### 2.1 窗口 Profile

```json
{
  "profile_id": "genshin_1920x1080",
  "window_title": "原神",
  "alt_window_title": "Genshin Impact",
  "process_name": "YuanShen.exe",
  "alt_process_name": "GenshinImpact.exe",
  "source_resolution": [1920, 1080],
  "normalized_resolution": [1280, 720],
  "display_mode": "borderless_windowed",
  "rois": {
    "minimap": {
      "mode": "anchor",
      "anchor": "top-left",
      "offset_x_px": 20,
      "offset_y_px": 20,
      "width_px": 200,
      "height_px": 200
    },
    "enemy_hp_bar": {
      "mode": "anchor",
      "anchor": "top-center",
      "offset_x_px": [-200, 200],
      "offset_y_px": 20,
      "height_px": 24
    },
    "active_char_hp": {
      "mode": "anchor",
      "anchor": "bottom-center",
      "offset_x_px": [-200, 200],
      "offset_y_px": -80,
      "height_px": 30
    },
    "party_portraits": {
      "mode": "anchor",
      "anchor": "right-center",
      "offset_x_px": -60,
      "offset_y_px": -120,
      "width_px": 60,
      "height_px": 280
    },
    "skill_buttons": {
      "mode": "anchor",
      "anchor": "bottom-right",
      "offset_x_px": -280,
      "offset_y_px": -120,
      "width_px": 260,
      "height_px": 100
    },
    "skill_e_icon": {
      "mode": "anchor",
      "anchor": "bottom-right",
      "offset_x_px": -160,
      "offset_y_px": -80,
      "width_px": 60,
      "height_px": 60
    },
    "skill_q_icon": {
      "mode": "anchor",
      "anchor": "bottom-right",
      "offset_x_px": -220,
      "offset_y_px": -80,
      "width_px": 60,
      "height_px": 60
    },
    "stamina_bar": {
      "mode": "anchor",
      "anchor": "center",
      "offset_x_px": 40,
      "offset_y_px": -10,
      "width_px": 120,
      "height_px": 12
    },
    "interaction_prompt": {
      "mode": "anchor",
      "anchor": "bottom-center",
      "offset_x_px": [-120, 120],
      "offset_y_px": -160,
      "height_px": 40
    },
    "dialog_area": {
      "mode": "anchor",
      "anchor": "bottom-center",
      "offset_x_px": [-400, 400],
      "offset_y_px": -200,
      "height_px": 200
    },
    "main_view": {
      "mode": "relative",
      "x": 0.08,
      "y": 0.06,
      "w": 0.84,
      "h": 0.76
    }
  }
}
```

### 2.2 多分辨率适配表

需为每种分辨率提供锚点偏移值。以下为关键 ROI 的缩放系数（相对 1920x1080）：

| 分辨率 | 缩放因子 | 备注 |
|--------|---------|------|
| 1280x720 | 0.667 | 最小支持分辨率 |
| 1920x1080 | 1.0 | **推荐** |
| 2560x1440 | 1.333 | UI 按比例放大 |
| 3840x2160 | 2.0 | 元素可能显得较小 |
| 2560x1080 | 21:9 超宽 | 水平视野更宽，UI 仍在边缘 |

### 2.3 屏幕状态分类器

原神有约 17 种屏幕状态，Agent 必须快速判断当前所处状态：

| 优先级 | 屏幕状态 | 关键判别器 |
|--------|---------|-----------|
| 1 | 加载画面 | 暗色 + 中央门动画 + 底部提示文字 |
| 2 | 对话框 | 底部 25-30% 半透明面板 + NPC 头像 |
| 3 | 派蒙菜单 | 暗化背景 + 菜单图标网格 + 派蒙角色 |
| 4 | 全屏菜单 | 地图/背包/角色/队伍等 |
| 5 | 大世界 HUD | 小地图(左上) + HP条(底部) + 技能图标(右下) |
| 6 | 无 HUD | 照相模式或手动隐藏 |

**检测锚点**（跨版本稳定）：
1. 小地图圆形（左上角，始终存在于大世界）
2. HP 条（底部中央，颜色=健康状态）
3. 技能图标区（右下角，E/Q 按钮始终可见）
4. 加载门框（中央，加载画面唯一特征）

### 2.4 相机伺服补偿

原神 PC 版的鼠标行为有三个硬性限制，必须在 `camera_servo.py` 中补偿：

```
1. 强制鼠标加速度: 精确角度映射不可靠
   → 方案: 改用「相对移动校准」模式，实测像素→角度映射表
   
2. Y 轴灵敏度 = X 轴的 75%:
   → 方案: pitch_gain 额外乘以 0.75 系数
   
3. 无 Raw Input:
   → 方案: 禁用单次大角度移动，拆分为多步小步移动
```

补偿后的 CameraServo 参数：

```yaml
camera_servo:
  yaw_gain: 0.018        # 需实测校准
  pitch_gain: 0.0135      # yaw_gain * 0.75
  dead_zone_px: 8
  smoothing: 0.6
  max_step_px: 40         # 拆分大移动
  invert_y: false
  calibration_mode: "relative_table"  # 非线性映射表
```

---

## 三、YOLO 模型：原神专用检测器

### 3.1 检测类别体系

```yaml
# 目标检测类别
detection_classes:

  # === 敌人 ===
  enemy:
    - monster_normal       # 丘丘人、史莱姆、盗宝团
    - monster_elite        # 遗迹守卫、丘丘暴徒、愚人众先遣队
    - monster_boss         # Boss（多段 HP）

  # === 采集物 ===
  ore:
    - ore_iron             # 铁块（暗灰岩石）
    - ore_white_iron       # 白铁块（银白色）
    - ore_crystal          # 水晶块（青绿色结晶）
    - ore_starsilver       # 星银矿石（银蓝色，龙脊雪山专属）
    - ore_amethyst         # 紫晶块（紫色，稻妻专属）

  plant:
    - plant_flower         # 花类（多色，F 键采集）
    - plant_mushroom       # 蘑菇类（棕色，F 键采集）
    - plant_fruit          # 果实类（彩色，F 键采集）
    - plant_specialty      # 区域特产（每区域不同，F 键采集）

  chest:
    - chest_common         # 普通（棕色，微光）
    - chest_exquisite      # 精致（蓝紫色光）
    - chest_precious       # 珍贵（金色光 + 粒子）
    - chest_luxurious      # 华丽（强金光 + 大量粒子）

  # === UI 元素 ===
  ui:
    - interaction_prompt   # F 键交互提示
    - hp_bar_enemy         # 敌人 HP 条
    - danger_zone          # 红圈/红光区域
    - loot_beam            # 掉落物光柱
```

### 3.2 各类别视觉特征与 HSV 检测参数

| 类别 | 主要颜色 | HSV 范围 (H°, S, V) | 形状特征 |
|------|---------|---------------------|---------|
| ore_iron | 暗灰棕 | — (亮度检测) | 岩石簇状 |
| ore_crystal | 青绿色 | H:150-180, S:>0.4, V:>0.3 | 棱柱结晶突刺 |
| ore_starsilver | 银蓝色 | H:200-230, S:>0.3, V:>0.5 | 结晶体，寒霜光泽 |
| ore_amethyst | 紫色 | H:260-300, S:>0.4, V:>0.4 | 结晶体，紫色色调 |
| enemy_hp_bar | 暗红色 | H:0-18 或 342-360, S:>0.5, V:>0.3 | 水平条形 |
| char_hp_bar (健康) | 绿色 | H:90-140, S:>0.4, V:>0.4 | 水平条形 |
| char_hp_bar (危险) | 红色 | H:0-18, S:>0.5, V:>0.3 | 水平条形 |
| danger_zone | 红色 | H:0-18, S:>0.6, V:>0.5 | 圆形/异形区域 |
| stamina_bar | 黄色 | H:40-60, S:>0.6, V:>0.6 | 水平分段条 |
| chest_common | 棕色 | H:15-35, S:>0.3, V:>0.3 | 矩形箱子 |
| chest_precious | 金色 | H:35-50, S:>0.6, V:>0.6 | 矩形 + 光效 |
| loot_beam | 彩色 | 按稀有度 | 垂直光柱 |

### 3.3 训练数据需求

| 类别组 | 最少样本量 | 采集方式 | 标注工具 |
|--------|-----------|---------|---------|
| monster_normal | 500+ | 不同区域/光照/角度截图 | CVAT / Roboflow |
| monster_elite | 300+ | 同上 | 同上 |
| monster_boss | 200+ | Boss 战斗全程截帧 | 同上 |
| ore_* (5类) | 200/类 | 不同区域背景 | 同上 |
| plant_* (4类) | 150/类 | 不同季节/天气 | 同上 |
| chest_* (4类) | 100/类 | 不同距离/角度 | 同上 |
| interaction_prompt | 300+ | 各种交互场景 | 同上 |
| danger_zone | 500+ | Boss 战斗/精英怪 | 同上 |

**数据采集脚本**（利用现有 DXcam）：

```python
# scripts/collect_genshin_training_data.py
# 在授权测试环境中运行
# 每秒截取 1 帧，按时间戳保存
# 支持按区域标注、自动去重（感知哈希）
```

### 3.4 模型选型

| 模型 | 用途 | 输入尺寸 | 推理速度 (CPU) | 备注 |
|------|------|---------|---------------|------|
| YOLOv8n | 主检测器（怪物+采集物） | 640x640 | ~15ms | nano 版，30+ FPS |
| YOLOv11n | 备选（更高精度） | 640x640 | ~12ms | 如果 v8n 精度不够 |
| PaddleOCR | CD 数字/交互文本/对话选项 | 全图或 ROI | ~20ms | 中英文，轻量 |
| 自训练分类器 | 危险区域检测（红圈/红光/正常） | 128x128 | ~2ms | 三分类，极轻量 |

---

## 四、内置 Skill 库

### 4.1 战斗 Skills

#### 4.1.1 安全战斗循环

```yaml
skill_id: safe_combat_genshin_v1
name: "原神安全战斗循环"
type: combat
environment_profile: genshin_1920x1080

preconditions:
  - require_focus
  - target_visible
  - danger_guard

steps:
  - step_id: maintain_lock
    type: checkpoint
    label: "锁定目标"
    params:
      checkpoint: target_visible
    timeout_ms: 1000

  - step_id: normal_attack_combo
    type: repeat_press
    label: "普攻四连"
    params:
      key: "left_click"
      repeat: 4
      interval_ms: 250

  - step_id: use_e_skill_if_ready
    type: branch_on_visual_state
    label: "E 技能（就绪时）"
    params:
      guard: "skill_e_ready"
      action:
        type: press_key
        key: "e"
      fallback: skip

  - step_id: use_q_burst_if_ready
    type: branch_on_visual_state
    label: "Q 爆发（就绪时）"
    params:
      guard: "skill_q_ready AND energy_full"
      action:
        type: press_key
        key: "q"
      fallback: skip

  - step_id: dodge_if_danger
    type: guard
    label: "危险闪避"
    params:
      interrupt: DODGE_REFLEX
    timeout_ms: 100

  - step_id: switch_if_low_hp
    type: branch_on_visual_state
    label: "低血切人"
    params:
      guard: "active_char_hp < 0.3"
      action:
        type: press_key
        key: "char_with_highest_hp"
      fallback: skip

visual_triggers:
  target_visible:
    type: target_visible
  skill_e_ready:
    type: cooldown_done
    roi: skill_e_icon
    detection: "not_grey AND no_countdown_number"
  skill_q_ready:
    type: cooldown_done
    roi: skill_q_icon
    detection: "glowing AND energy_arc_full"
  danger_detected:
    type: danger_zone_visible
    roi: main_view
  active_char_hp:
    type: hp_bar_ratio
    roi: active_char_hp

success_criteria:
  - target_defeated_or_reward_seen

failure_policy:
  max_retries: 3
  on_failed: recover_or_skip
  cleanup_skill: return_to_safe_anchor_v1

safety:
  dry_run_default: true
  interruptible: true
  require_focus: true
  max_duration_ms: 30000
```

#### 4.1.2 Boss 战斗循环

```yaml
skill_id: boss_combat_genshin_v1
name: "原神 Boss 战斗"
type: combat
extends: safe_combat_genshin_v1

additional_steps:
  - step_id: burst_dodge
    type: guard
    label: "Q 爆发期间无敌帧闪避"
    params:
      trigger: "q_burst_animation_active AND danger_score > 0.8"
      action: skip  # Q 动画自带无敌帧，无需额外闪避

  - step_id: phase_change_wait
    type: wait_visual_trigger
    label: "等待 Boss 阶段转换结束"
    params:
      trigger: "boss_no_longer_invulnerable"
      timeout_ms: 10000

  - step_id: weakpoint_attack
    type: branch_on_visual_state
    label: "攻击弱点（如果可见）"
    params:
      guard: "boss_weakpoint_visible"
      action:
        type: aim_and_attack
        target: boss_weakpoint

visual_triggers:
  boss_weakpoint_visible:
    type: target_feature
    detection: "glowing_core_on_boss"
  boss_invulnerable:
    type: target_state
    detection: "boss_phase_change_animation"
```

### 4.2 采集 Skills

#### 4.2.1 F 键采集（植物/特产）

```yaml
skill_id: collect_plant_genshin_v1
name: "原神植物采集"
type: collection
environment_profile: genshin_1920x1080

preconditions:
  - require_focus
  - collectable_visible

steps:
  - step_id: approach
    type: approach_target
    label: "靠近采集物"
    params:
      distance: "interaction_range"
      movement: "walk_toward_target"
    timeout_ms: 8000

  - step_id: align
    type: align_to_center
    label: "对齐采集物"
    params:
      tolerance: 0.05
      use_wasd: true
    timeout_ms: 3000

  - step_id: wait_prompt
    type: wait_visual_trigger
    label: "等待 F 提示"
    params:
      trigger: "interaction_prompt_visible AND prompt_contains_F"
      roi: interaction_prompt
    timeout_ms: 3000

  - step_id: press_f
    type: press_key
    label: "按 F 采集"
    params:
      key: "f"
      hold_ms: 50

  - step_id: verify
    type: wait_visual_trigger
    label: "验证采集成功"
    params:
      trigger: "item_disappeared OR gain_popup_visible"
    timeout_ms: 2000

success_criteria:
  - item_disappeared OR gain_popup_visible

failure_policy:
  max_retries: 2
  on_failed: skip_and_log
```

#### 4.2.2 矿石采集（攻击破坏）

```yaml
skill_id: mine_ore_genshin_v1
name: "原神矿石采集"
type: collection

preconditions:
  - require_focus
  - ore_visible

steps:
  - step_id: approach
    type: approach_target
    label: "靠近矿石"
    params:
      distance: "melee_range"
    timeout_ms: 6000

  - step_id: attack_ore
    type: repeat_press
    label: "攻击矿石（5 次）"
    params:
      key: "left_click"
      repeat: 5
      interval_ms: 300

  - step_id: verify_drops
    type: wait_visual_trigger
    label: "等待掉落物"
    params:
      trigger: "loot_beam_visible"
    timeout_ms: 2000

  - step_id: collect_drops
    type: press_key
    label: "按 F 拾取"
    params:
      key: "f"
      repeat: 3
      interval_ms: 600

success_criteria:
  - drops_collected OR no_ore_visible
```

#### 4.2.3 宝箱开启

```yaml
skill_id: open_chest_genshin_v1
name: "原神宝箱开启"
type: collection

steps:
  - step_id: approach_chest
    type: approach_target
    params:
      distance: "interaction_range"
    timeout_ms: 6000

  - step_id: wait_prompt
    type: wait_visual_trigger
    params:
      trigger: "interaction_prompt_contains_开启"
    timeout_ms: 3000

  - step_id: press_f
    type: press_key
    params:
      key: "f"

  - step_id: wait_open_animation
    type: wait_visual_trigger
    params:
      trigger: "chest_opened_animation_complete"
    timeout_ms: 5000

  - step_id: claim_rewards
    type: press_key
    params:
      key: "f"
```

### 4.3 导航 Skills

#### 4.3.1 传送 + 路径导航

```yaml
skill_id: teleport_and_navigate_v1
name: "传送并导航至目标"
type: navigation

steps:
  - step_id: open_map
    type: press_key
    params:
      key: "m"

  - step_id: wait_map_open
    type: wait_visual_trigger
    params:
      trigger: "map_screen_visible"
    timeout_ms: 2000

  - step_id: select_region
    type: branch_on_visual_state
    params:
      guard: "current_region != target_region"
      action:
        type: click_button
        target: "region_tab_{target_region}"

  - step_id: select_waypoint
    type: click_roi
    params:
      target: "target_waypoint_on_map"
      method: "template_match"

  - step_id: confirm_teleport
    type: click_button
    params:
      label: "传送"
      style: "gold_amber_button"

  - step_id: wait_loading
    type: wait_visual_trigger
    params:
      trigger: "loading_screen_ended"
    timeout_ms: 15000

  - step_id: navigate_to_target
    type: follow_minimap_waypoint
    params:
      method: "minimap_navigation"
      approach_distance: "interaction_range"
```

#### 4.3.2 小地图导航

```yaml
skill_id: minimap_navigate_v1
name: "小地图导航"
type: navigation

steps:
  - step_id: read_waypoint_direction
    type: visual_detect
    params:
      roi: minimap
      detect: "quest_marker_angle"

  - step_id: rotate_to_target
    type: camera_rotate
    params:
      target_angle: "{detected_angle}"
      method: "mouse_move_relative"

  - step_id: move_forward
    type: hold_key
    params:
      key: "w"
      duration_ms: 500

  - step_id: check_arrival
    type: branch_on_visual_state
    params:
      guard: "distance_to_target < 5"
      action: complete
      fallback: loop_to_step_1
```

### 4.4 对话 Skills

```yaml
skill_id: handle_dialog_v1
name: "处理 NPC 对话"
type: dialog

steps:
  - step_id: detect_dialog
    type: wait_visual_trigger
    params:
      trigger: "dialog_box_visible"
    timeout_ms: 60000

  - step_id: detect_choices
    type: branch_on_visual_state
    params:
      guard: "choice_buttons_visible"
      action:
        type: click_button
        target: "first_choice_button"
      fallback: advance_dialog

  - step_id: advance_dialog
    type: press_key
    params:
      key: "left_click"
      repeat: 1

  - step_id: check_dialog_end
    type: branch_on_visual_state
    params:
      guard: "dialog_box_disappeared"
      action: complete
      fallback: loop_to_step_2
```

### 4.5 Skill 列表总览

| Skill ID | 类型 | 描述 | 交互方式 |
|----------|------|------|---------|
| `safe_combat_genshin_v1` | combat | 安全战斗循环 | E/Q/左键/切人 |
| `boss_combat_genshin_v1` | combat | Boss 战斗（含阶段/弱点） | 同上 + 弱点瞄准 |
| `collect_plant_genshin_v1` | collection | 植物采集（F 键） | WASD + F |
| `mine_ore_genshin_v1` | collection | 矿石采集（攻击破坏） | WASD + 左键 + F |
| `open_chest_genshin_v1` | collection | 宝箱开启 | WASD + F |
| `teleport_and_navigate_v1` | navigation | 传送并导航 | M + 点击 + WASD |
| `minimap_navigate_v1` | navigation | 小地图导航 | 鼠标 + WASD |
| `handle_dialog_v1` | dialog | NPC 对话处理 | 左键点击 |
| `return_to_safe_anchor_v1` | recovery | 返回安全锚点 | 传送回城 |
| `daily_commission_v1` | mission | 日常委托全流程 | 组合 Skill |

---

## 五、原神专用知识库

### 5.1 资源知识

```yaml
# knowledge/genshin_resources.yaml
schema_version: "1.0"

resources:
  # === 矿石 ===
  - resource_id: iron_chunk
    name: 铁块
    type: ore
    detection_class: ore_iron
    interaction: attack
    attack_count: 3
    respawn_hours: 24
    regions: [mondstadt, liyue, inazuma, sumeru, fontaine, natlan]

  - resource_id: crystal_chunk
    name: 水晶块
    type: ore
    detection_class: ore_crystal
    interaction: attack
    attack_count: 4
    respawn_hours: 72
    regions: [mondstadt, liyue, inazuma, sumeru, fontaine, natlan]

  - resource_id: starsilver
    name: 星银矿石
    type: ore
    detection_class: ore_starsilver
    interaction: attack
    attack_count: 4
    respawn_hours: 48
    regions: [dragonspine]

  # === 蒙德特产 ===
  - resource_id: wolfhook
    name: 钩钩果
    type: plant
    detection_class: plant_fruit
    interaction: f_key
    respawn_hours: 48
    regions: [mondstadt]
    subregion: wolvendom
    visual: "紫色荆棘状浆果簇"

  - resource_id: valberry
    name: 树莓
    type: plant
    detection_class: plant_fruit
    interaction: f_key
    respawn_hours: 48
    regions: [mondstadt]
    subregion: stormbearer_point
    visual: "蓝紫色圆形浆果簇"

  - resource_id: cecilia
    name: 塞西莉亚花
    type: plant
    detection_class: plant_flower
    interaction: f_key
    respawn_hours: 48
    regions: [mondstadt]
    subregion: starsnatch_cliff
    visual: "白色小花，金色花心，悬崖高处"

  - resource_id: dandelion_seed
    name: 蒲公英籽
    type: plant
    detection_class: plant_flower
    interaction: anemo_skill  # 需要风元素技能
    respawn_hours: 24
    regions: [mondstadt]
    visual: "白色绒毛蒲公英"
    special: "需用风元素技能（E）吹散后拾取"

  # === 璃月特产 ===
  - resource_id: jueyun_chili
    name: 绝云椒椒
    type: plant
    detection_class: plant_fruit
    interaction: f_key
    respawn_hours: 48
    regions: [liyue]
    subregion: qingce_village
    visual: "红色辣椒，植株上生长"

  - resource_id: cor_lapis
    name: 琉璃百合
    type: ore
    detection_class: ore_crystal
    interaction: attack
    attack_count: 2
    respawn_hours: 48
    regions: [liyue]
    visual: "金琥珀色结晶嵌于岩石中"

  - resource_id: qingxin
    name: 清心
    type: plant
    detection_class: plant_flower
    interaction: f_key
    respawn_hours: 48
    regions: [liyue]
    visual: "白色花朵，绿色茎，高山之巅"
```

### 5.2 怪物知识

```yaml
# knowledge/genshin_monsters.yaml
schema_version: "1.0"

monster_families:
  - family_id: hilichurl
    name: 丘丘人
    types:
      - monster_id: hilichurl
        name: 丘丘人
        class: monster_normal
        hp_segments: 1
        danger_signals: [melee_windup]
        weaknesses: []
        drops: [damaged_mask, sticky_honey]

      - monster_id: mitachurl
        name: 丘丘暴徒
        class: monster_elite
        hp_segments: 1
        danger_signals: [charge_attack, shield_bash]
        drops: [heavy_horn, recruits_insignia]

  - family_id: ruin_machine
    name: 遗迹机兵
    types:
      - monster_id: ruin_guard
        name: 遗迹守卫
        class: monster_elite
        hp_segments: 1
        danger_signals: [missile_lockon, spin_attack, stomp]
        weakpoints: [eye_core, back_weakpoint]
        paralysis_on_weakpoint_hit: true
        weakness_elements: [none]
        visual: "金属构造体，橙红色核心发光"

      - monster_id: ruin_grader
        name: 遗迹重机
        class: monster_elite
        hp_segments: 1
        weakpoints: [eye_core, left_foot, right_foot]
        paralysis_on_weakpoint_hit: true

  - family_id: slimes
    name: 史莱姆
    types:
      - monster_id: pyro_slime
        name: 火史莱姆
        class: monster_normal
        element: pyro
        visual: "橙红色球体，火焰环绕"
        weakness: [hydro, cryo]

      - monster_id: hydro_slime
        name: 水史莱姆
        class: monster_normal
        element: hydro
        visual: "蓝色球体，水滴效果"
        weakness: [electro, cryo]

  - family_id: bosses
    name: Boss
    types:
      - monster_id: pyro_regisvine
        name: 爆炎树
        class: monster_boss
        hp_segments: 1
        weakpoints: [root_core, flower_core]
        weakness: [hydro, cryo]
        danger_signals: [fireball_barrage, ground_slam, aoe_flame]
        respawn_minutes: 3
        resin_cost: 40

      - monster_id: cryo_hypostasis
        name: 冰风迷途的勇士
        class: monster_boss
        hp_segments: 1
        weakness: [pyro, electro]
        danger_signals: [ice_wall, freezing_pulse]
        respawn_minutes: 3
        resin_cost: 40
```

### 5.3 区域与路线图

```yaml
# knowledge/genshin_world_graph.yaml
schema_version: "1.0"

regions:
  - region_id: mondstadt
    name: 蒙德
    color_palette: warm_green
    theme: european_medieval
    visual_signature: "绿色草地，蓝天白云，风车，石墙"

  - region_id: liyue
    name: 璃月
    color_palette: warm_amber
    theme: chinese_traditional
    visual_signature: "金琥珀色调，喀斯特地貌，灯笼，木质建筑"

  - region_id: inazuma
    name: 稻妻
    color_palette: cool_purple
    theme: japanese_shrine
    visual_signature: "紫色雷元素主题，樱花，鸟居，岛屿"

  - region_id: sumeru
    name: 须弥
    color_palette: deep_green_and_golden
    theme: middle_eastern_indian
    visual_signature: "雨林巨树或沙漠，中东穹顶"

  - region_id: fontaine
    name: 枫丹
    color_palette: cool_blue
    theme: french_steampunk
    visual_signature: "大量水域，机械元素，法式建筑"

  - region_id: natlan
    name: 纳塔
    color_palette: warm_red
    theme: mesoamerican_volcanic
    visual_signature: "红橙火山主题，中美洲金字塔"

waypoints:
  - waypoint_id: tp_mondstadt_city
    name: 蒙德城
    position: [800, 600, 100]
    region: mondstadt
    type: statue_of_seven

  - waypoint_id: tp_stormbearer_point
    name: 星落湖
    position: [1200, 400, 80]
    region: mondstadt
    type: teleport_waypoint

edges:
  - from: tp_mondstadt_city
    to: tp_stormbearer_point
    cost: 30.0
    method: walk
    danger_level: low

  - from: tp_stormbearer_point
    to: valberry_stormbearer_01
    cost: 15.0
    method: walk
    danger_level: none
```

---

## 六、危险检测系统

### 6.1 信号提取器设计

```python
class GenshinDangerSignalExtractor:
    """从帧中提取原神专用危险信号"""

    SIGNALS = [
        "ground_danger_zone",      # 地面红圈 AoE
        "projectile_approaching",   # 投射物接近
        "hp_drop_signal",          # 角色血量骤降
        "boss_windup",             # Boss 前摇动画
        "target_aggro_flash",      # 目标仇恨闪烁
        "stamina_critical",        # 体力耗尽
    ]

    def extract(self, frame, prev_frame, rois) -> dict[str, float]:
        signals = {}

        # 1. 地面红圈检测 — 最可靠的"立即闪避"信号
        ground = frame[rois["ground_area"]]
        hsv = cv2.cvtColor(ground, cv2.COLOR_BGR2HSV)
        red_mask = cv2.inRange(hsv, (0, 120, 80), (10, 255, 255)) | \
                   cv2.inRange(hsv, (170, 120, 80), (180, 255, 255))
        signals["ground_danger_zone"] = float(red_mask.sum()) / red_mask.size

        # 2. HP 骤降 — 比较当前帧与上一帧的角色 HP 条
        if prev_frame is not None:
            current_hp = self._read_hp_ratio(frame, rois["active_char_hp"])
            prev_hp = self._read_hp_ratio(prev_frame, rois["active_char_hp"])
            signals["hp_drop_signal"] = max(0.0, prev_hp - current_hp)

        # 3. 投射物 — 连续帧中快速移动的亮色物体
        if prev_frame is not None:
            diff = cv2.absdiff(frame, prev_frame)
            bright_motion = (diff > 60).sum() / diff.size
            signals["projectile_approaching"] = min(1.0, bright_motion * 10)

        # 4. 体力临界 — 检测黄色体力条是否过短
        stamina_roi = frame[rois["stamina_bar"]]
        signals["stamina_critical"] = 1.0 if self._stamina_below(stamina_roi, 0.2) else 0.0

        return signals

    def _read_hp_ratio(self, frame, roi) -> float:
        """HSV 检测绿色/红色 HP 条比例"""
        bar = frame[roi]
        hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 50, 50), (85, 255, 255))
        red = cv2.inRange(hsv, (0, 50, 50), (10, 255, 255)) | \
              cv2.inRange(hsv, (170, 50, 50), (180, 255, 255))
        total = green.sum() + red.sum()
        if total == 0:
            return 1.0
        return float(green.sum()) / total

    def _stamina_below(self, stamina_roi, threshold) -> bool:
        hsv = cv2.cvtColor(stamina_roi, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(hsv, (20, 100, 150), (35, 255, 255))
        ratio = float(yellow.sum()) / max(yellow.size, 1)
        return ratio < threshold
```

### 6.2 闪避策略

| 危险信号 | 阈值 | 动作 | 优先级 |
|----------|------|------|--------|
| `ground_danger_zone > 0.15` | 红圈面积超过 15% | 立即冲刺闪避（Right Click） | P0 |
| `hp_drop_signal > 0.2` | 单帧 HP 损失 >20% | 冲刺闪避 + 评估切人 | P0 |
| `projectile_approaching > 0.5` | 高速运动物体接近 | 侧向闪避 | P1 |
| `stamina_critical == 1.0` | 体力 <20% | 停止消耗体力的动作 | P1 |
| `boss_windup > 0.7` | Boss 前摇分类器触发 | 准备闪避 | P2 |

**无敌帧利用**：Q 技能爆发动画期间完全无敌（1.5-4 秒）。当危险不可躲避时，可触发 Q 作为紧急回避。

---

## 七、冷却管理（CooldownManager 增强）

### 7.1 CD 检测三路径

```python
class GenshinCooldownManager(CooldownManager):
    """原神专用冷却管理"""

    def update_from_genshin_ui(self, skill_id: str, skill_roi: np.ndarray):
        """从技能图标 ROI 提取冷却状态"""

        # 路径 1: OCR 数字倒计时
        ocr_text = paddleocr_read_number(skill_roi)
        if ocr_text and ocr_text.isdigit():
            return self.update_from_ocr(skill_id, ocr_text, confidence=0.9)

        # 路径 2: 模板匹配 — 图标是否灰化
        is_grey = self._detect_greyed_out(skill_roi)
        if is_grey:
            return self.update_from_template(skill_id, is_grey=True, confidence=0.75)

        # 路径 3: 弧形暗化角度估算
        sweep_angle = self._estimate_sweep_angle(skill_roi)
        if sweep_angle > 0:
            remaining_ratio = sweep_angle / 360.0
            return self.update_from_ratio(skill_id, remaining_ratio, confidence=0.6)

        # 路径 4: 技能就绪 — Q 爆发图标发光检测
        is_glowing = self._detect_element_glow(skill_roi)
        if is_glowing:
            return CooldownState(ready=True, remaining_ms=0, confidence=0.85)

    def _detect_greyed_out(self, roi: np.ndarray) -> bool:
        """检测图标是否被灰化（饱和度低）"""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1].mean()
        return saturation < 50  # 灰化图标饱和度极低

    def _detect_element_glow(self, roi: np.ndarray) -> bool:
        """检测 Q 技能的能量充满发光状态"""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        value = hsv[:, :, 2]
        saturation = hsv[:, :, 1]
        bright_saturated = ((value > 200) & (saturation > 100)).sum()
        return bright_saturated / roi.size > 0.3
```

---

## 八、HP 条追踪（HPBarTracker 增强）

### 8.1 敌人 HP 条

```python
class EnemyHPBarTracker:
    """敌人 HP 条追踪"""

    def detect_hp_bar(self, frame, roi) -> HPBarResult:
        """检测敌人 HP 条（暗红色，屏幕顶部）"""
        bar = frame[roi]
        hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)

        # 敌人 HP 条: 暗红色
        hp_mask = cv2.inRange(hsv, (0, 80, 60), (10, 255, 200)) | \
                  cv2.inRange(hsv, (170, 80, 60), (180, 255, 200))

        # 背景: 深灰/黑色
        bg_mask = cv2.inRange(hsv, (0, 0, 0), (180, 255, 60))

        hp_pixels = hp_mask.sum()
        total = hp_pixels + bg_mask.sum()
        if total == 0:
            return HPBarResult(1.0, 0.0)

        ratio = float(hp_pixels) / total
        return HPBarResult(max(0.0, min(1.0, ratio)), 0.8)

    def detect_boss_segments(self, frame, roi) -> BossHPResult:
        """Boss HP 条多段检测"""
        bar = frame[roi]
        hsv = cv2.cvtColor(bar, cv2.COLOR_BGR2HSV)

        # 检测分段线（垂直暗色线条）
        gray = cv2.cvtColor(bar, cv2.COLOR_BGR2GRAY)
        vertical_edges = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        segment_lines = (np.abs(vertical_edges) > 100).sum(axis=0)

        # 当前段 HP
        hp_mask = cv2.inRange(hsv, (0, 80, 60), (10, 255, 200)) | \
                  cv2.inRange(hsv, (170, 80, 60), (180, 255, 200))

        return BossHPResult(
            total_segments=len(segment_lines) + 1,
            current_segment_ratio=float(hp_mask.sum()) / max(hp_mask.size, 1),
        )
```

---

## 九、LLM Prompt 工程

### 9.1 战斗规划 Prompt

```python
COMBAT_PLANNER_SYSTEM = """你是原神战斗策略规划器。根据队伍配置和敌人信息，生成战斗逻辑图（CombatPlaybook Graph）。

你必须遵循以下规则：
1. 不要决定像素级操作，只决定技能释放顺序和条件
2. 所有决策必须基于视觉可观测的状态（HP、CD、能量、危险分数）
3. 必须包含低血量回退分支
4. 必须包含危险闪避分支

队伍配置: {team}
敌人信息: {enemy}

输出 JSON 格式:
{
  "default_rotation": [
    {"action": "normal_attack", "repeat": 4},
    {"action": "e_skill", "character": 2},
    {"action": "switch", "to": 3},
    {"action": "q_burst", "character": 3}
  ],
  "priority_triggers": [
    {"condition": "skill_q_ready AND energy_full", "action": "use_q_burst"},
    {"condition": "active_char_hp < 0.3", "action": "switch_to_healer"},
    {"condition": "danger_score > 0.7", "action": "dodge"},
    {"condition": "boss_weakpoint_visible", "action": "aim_weakpoint"}
  ],
  "fallback": {
    "on_target_lost": "reacquire",
    "on_combo_break": "resume_from_checkpoint",
    "on_all_dead": "report_failure"
  }
}"""
```

### 9.2 伴游 Persona Prompt

```python
GENSHIN_COMPANION_PROMPT = """你是{persona_name}，一位原神世界的冒险伙伴。

性格设定: {persona_personality}

你通过以下方式与旅行者互动：
1. 将系统事件转化为角色台词
2. 用活泼/关心/鼓励的语气
3. 在关键时刻给出战术建议
4. 失败时安慰，成功时庆祝

事件→台词映射:
- TARGET_LOST → "咦？怪物跑哪去了？让我找找……"
- TARGET_FOUND → "找到了！就在那边！"
- OBSTACLE_BLOCKING → "前面好像过不去，我们绕路吧～"
- COMBAT_VICTORY → "太棒了！轻松搞定！"
- COMBAT_DIFFICULT → "这个敌人很强……要小心！"
- SKILL_FAILED → "啊，技能没打中，调整一下！"
- LOW_HP → "小心！血量不多了，要不要切换角色？"
- COLLECTION_SUCCESS → "又收集到{item_name}了！还差{remaining}个～"
- COLLECTION_COMPLETE → "太好了！今天的采集任务完成了！"
- DANGER_DODGE_SUCCESS → "好险！幸好躲开了！"
- DANGER_HIT → "呜……被打到了……我们更小心一点吧。"
- BOSS_PHASE_CHANGE → "Boss 变强了！集中注意力！"
- RESIN_FULL → "旅行者，树脂满了哦！不要浪费～"
- DAILY_COMPLETE → "今天的委托都完成了！辛苦了！"

回复格式:
{
  "text": "角色台词",
  "emotion": "happy|worried|excited|calm|surprised",
  "suggestion": "可选的行动建议"
}"""
```

### 9.3 任务理解 Prompt

```python
MISSION_PARSER_PROMPT = """你是原神任务解析器。将用户自然语言目标转化为 MissionQueue。

用户目标: {user_goal}
当前状态: {current_state}
可用 Skill: {available_skills}
知识库资源: {knowledge_resources}

输出 MissionQueue JSON:
{
  "mission_id": "...",
  "goal": {"type": "...", "resource_id": "...", "target_count": N},
  "nodes": [
    {"id": "teleport_to_region", "type": "navigation", "skill_binding": "teleport_and_navigate_v1", "verifier": "arrived_at_region"},
    {"id": "approach_target", "type": "approach", "verifier": "target_in_range"},
    {"id": "combat", "type": "combat", "skill_binding": "safe_combat_genshin_v1", "verifier": "target_defeated"},
    {"id": "verify_reward", "type": "verify", "verifier": "reward_collected"}
  ],
  "failure_policy": {"max_retries": 3, "on_failed": "recover_or_skip"}
}

示例用户输入:
- "帮我采 10 个绝云椒椒" → 收集任务（璃月→轻策庄→F键采集循环）
- "打 5 次爆炎树" → Boss 任务（传送到爆炎树→战斗→领取奖励→循环）
- "清日常" → 四个委托任务 + 凯瑟琳交任务
- "用完 160 树脂" → 体力消耗任务（4次圣遗物本 或 8次地脉）
""" 
```

---

## 十、区域自适应检测

### 10.1 区域色彩特征

| 区域 | 主色调 | 背景典型 HSV | 对检测的影响 |
|------|-------|-------------|------------|
| 蒙德 | 暖绿 | H:80-120, S:40-80, V:100-200 | 矿石/植物在绿色背景中需高饱和度过滤 |
| 璃月 | 琥珀金 | H:20-40, S:60-100, V:120-200 | 金色/棕色资源融入背景，需形状特征 |
| 稻妻 | 冷紫 | H:250-290, S:30-60, V:80-180 | 紫色采集物（樱贝壳等）融入背景 |
| 须弥雨林 | 深绿 | H:80-130, S:60-100, V:60-150 | 密集植被遮挡严重 |
| 须弥沙漠 | 金黄 | H:25-45, S:50-90, V:160-240 | 棕色/金色资源融入沙地 |
| 枫丹 | 冷蓝 | H:190-220, S:40-80, V:120-220 | 蓝色资源融入水域背景 |
| 纳塔 | 暖红 | H:0-20, S:60-100, V:120-220 | 红色资源融入火山背景 |

### 10.2 区域感知检测策略

```python
class RegionAwareDetector:
    """根据当前区域调整检测参数"""

    REGION_PARAMS = {
        "mondstadt": {"bg_hue_range": (80, 120), "min_saturation_boost": 0.1},
        "liyue":     {"bg_hue_range": (20, 40),  "min_saturation_boost": 0.15},
        "inazuma":   {"bg_hue_range": (250, 290), "min_saturation_boost": 0.1},
        "sumeru":    {"bg_hue_range": (40, 130),  "min_saturation_boost": 0.2},
        "fontaine":  {"bg_hue_range": (190, 220), "min_saturation_boost": 0.1},
        "natlan":    {"bg_hue_range": (0, 20),    "min_saturation_boost": 0.25},
    }

    def detect_region(self, frame) -> str:
        """从帧的主色调判断当前区域"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hue_hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
        dominant_hue = np.argmax(hue_hist)

        for region, params in self.REGION_PARAMS.items():
            lo, hi = params["bg_hue_range"]
            if lo <= dominant_hue <= hi:
                return region
        return "unknown"

    def get_detection_params(self, region: str) -> dict:
        """获取当前区域优化的检测参数"""
        return self.REGION_PARAMS.get(region, {})
```

---

## 十一、元素反应策略

### 11.1 元素反应表

| 反应 | 触发 | 效果 | 视觉特征 | 战术价值 |
|------|------|------|---------|---------|
| 蒸发 (Vaporize) | 火+水 | 2x/1.5x 伤害 | 蒸汽白雾 | 最高伤害放大 |
| 融化 (Melt) | 火+冰 | 2x/1.5x 伤害 | 冰融化水汽 | 高伤害放大 |
| 超载 (Overloaded) | 火+雷 | AoE 爆炸 | 橙色爆炸 + 屏幕震动 | 打断小型敌人 |
| 感电 (Electro-Charged) | 雷+水 | 持续跳电 | 电弧连接 | 多目标持续伤害 |
| 超导 (Superconduct) | 雷+冰 | 降物防 | 蓝紫冰爆 | 物理队核心 |
| 冻结 (Frozen) | 水+冰 | 冻住敌人 | 冰蓝色包裹 | 控制敌人 |
| 扩散 (Swirl) | 风+任意 | 扩散元素 | 绿色旋风变色 | 元素传播 |
| 结晶 (Crystallize) | 岩+任意 | 产盾 | 元素色碎片 | 防御 |
| 绽放 (Bloom) | 水+草 | 产种子 | 绿色种子 | 后续反应 |
| 超绽放 (Hyperbloom) | 雷+种子 | 追踪弹 | 绿紫追踪弹 | 高单体伤害 |

### 11.2 LLM 策略整合

LLM 在战前根据队伍元素配置和敌人弱点，生成包含元素反应链的 Playbook：

```python
REACTION_AWARE_PLANNER = """
额外规则：
- 如果队伍同时有火和水角色，优先安排蒸发反应链（先水后火 = 2x）
- 如果敌人有元素护盾，使用克制元素（水克火、冰克水、火克冰、雷克水）
- 扩散可用于在多敌人间传播元素附着
- Q 爆发动画期间角色无敌，可用于躲避致命攻击
- 切人时有短暂无敌帧，可利用
"""
```

---

## 十二、原神专用时间常数

| 参数 | 值 | 用途 |
|------|---|------|
| 闪避 I-Frame 启动 | ~40ms | DangerDetector → Dodge 延迟上限 |
| 闪避 I-Frame 持续 | ~300ms | 闪避后安全窗口 |
| 闪避体力消耗 | 18/次 | 体力管理阈值 |
| Q 爆发无敌帧 | 1.5-4s | 利用 Q 躲避致命攻击 |
| 普攻四连 | ~2.5s | combo 时间窗口 |
| 切人冷却 | 1s | 切人后的锁定时间 |
| 切人动画 | ~0.5s | 切人无敌帧窗口 |
| F 键交互冷却 | ~0.5s | 快速拾取间隔 |
| 加载画面 (SSD) | 2-5s | 传送/秘境等待 |
| 加载画面 (HDD) | 30-60s | 低配机器等待 |
| 体力回复延迟 | 1.5s | 停止消耗后开始回复 |
| 体力回复速度 | 25/s | 满体力恢复时间 |
| E 技能 CD 范围 | 4-32s | CooldownManager 基准 |
| Q 技能 CD 范围 | 12-20s | 能量充满检测 |
| 怪物重生 | 3min (Boss) | Boss 连刷等待 |
| 资源重生 | 24-72h | 采集路线规划 |

---

## 十三、版本兼容性策略

原神每 6 周更新一次，大版本（X.0）可能重排 UI。

### 13.1 版本感知

```python
class GenshinVersionAdapter:
    """版本差异适配"""

    KNOWN_LAYOUTS = {
        (5, 0): {"paimon_menu": "grid_v5", "party_setup": "v4_redesign"},
        (4, 0): {"paimon_menu": "grid_v4", "party_setup": "v4_redesign"},
        (3, 0): {"paimon_menu": "grid_v3"},
        "default": {"paimon_menu": "grid_v5"},
    }

    def detect_version(self, frame) -> tuple[int, int]:
        """从 UI 元素布局推断版本"""
        # 检测派蒙菜单布局变化
        # 检测队伍设置界面样式
        # 返回 (major, minor)
        ...

    def get_roi_offsets(self, version: tuple) -> dict:
        """返回版本特定的 ROI 偏移量"""
        ...
```

### 13.2 容错检测

- **优先使用颜色/形状特征**（跨版本稳定）：HP 条颜色、技能图标元素色、小地图圆形
- **模板匹配设宽松阈值**：容忍图标样式微调
- **OCR 作为后备**：当模板匹配失败时，用 OCR 读取按钮文字
- **版本日志**：检测到版本变化时记录，提醒用户重新校准

---

## 十四、实施路线

### Phase 1: 基础适配（1-2 周）

1. 创建 `genshin_1920x1080` Profile（锚点校准向导）
2. 窗口状态分类器（17 种屏幕状态检测）
3. 数据采集脚本 + 500+ 张训练数据标注
4. 训练 YOLO 模型（怪物 + 采集物 + UI 元素）
5. 接入 PaddleOCR（CD 数字 + 交互提示 + 对话选项）
6. 修改 `camera_servo.py`：添加 Y 轴 75% 补偿 + 加速度补偿

### Phase 2: 核心闭环（2-3 周）

7. 实现 `GenshinDangerSignalExtractor`（红圈/HP骤降/投射物）
8. 构建战斗 Skill 库（安全战斗 + Boss 战斗 + 闪避）
9. 构建采集 Skill 库（F键采集 + 矿石攻击 + 宝箱）
10. 构建 Genshin 资源/怪物知识库
11. 区域自适应检测（区域色调 → 检测参数调整）
12. 冷却管理增强（OCR + 灰化检测 + 弧形角度 + 发光检测）

### Phase 3: 体验打磨（2-3 周）

13. 导航 Skill（地图传送 + 小地图路径）
14. 对话处理 Skill（自动推进 + 选项选择）
15. LLM 战斗规划（根据队伍+敌人生成 Playbook）
16. 伴游 Persona（事件→台词映射 + 表情/气泡）
17. 元素反应策略（LLM 生成反应链）
18. 多区域 Profile 适配

### Phase 4: 进阶能力（持续迭代）

19. 日常委托自动化（4 委托 + 交任务）
20. 树脂消耗自动化（圣遗物本/地脉循环）
21. 失败学习（从真实战斗失败中优化 Playbook）
22. 版本更新自动适配
23. 社区 Skill 分享（导入导出标准化）
24. Co-Op 模式适配（队友视觉干扰过滤）

---

## 十五、参考资源

### 学术论文
- Lumine (arXiv 2511.08892): 基于 VLM 的原神 AI Agent，成功完成蒙德主线任务

### 开源项目
- BOT-MMORPG-AI (GitHub): 原神自动化框架，基于图像识别
- genshingrab (GitHub): HUD 截图工具，OCR 扫描
- Inventory Kamera (GitHub): 背包 OCR 扫描器
- Genshin FPS Unlocker (GitHub): 帧率解锁工具（了解反作弊边界）

### 官方资源
- Genshin Impact Wiki (Fandom): 最全的游戏数据
- HoYoLAB: 官方社区，攻略/设置指南
- PCGamingWiki: 技术规格
- Game UIDatabase: UI 截图参考
