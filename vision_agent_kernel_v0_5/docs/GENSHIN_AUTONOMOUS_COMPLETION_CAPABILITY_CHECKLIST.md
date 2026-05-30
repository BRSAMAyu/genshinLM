# 原神自主通关能力清单 (Genshin Autonomous Completion Capability Checklist)

> **目标**：Agent 自主完成《原神》全部魔神任务（序章→第五章）及核心支线内容。
> **生成日期**：2026-05-30
> **方法**：8 路并行研究（战斗/探索/角色养成/任务流程/UI系统/日常策略）+ 代码库能力盘点。

---

## 目录

- [一、感知层 (Perception)](#一感知层-perception)
- [二、输入执行层 (Input & Execution)](#二输入执行层-input--execution)
- [三、导航与移动 (Navigation & Movement)](#三导航与移动-navigation--movement)
- [四、UI 菜单导航 (UI Menu Navigation)](#四ui-菜单导航-ui-menu-navigation)
- [五、对话系统 (Dialog System)](#五对话系统-dialog-system)
- [六、任务系统 (Quest System)](#六任务系统-quest-system)
- [七、战斗智能 (Combat Intelligence)](#七战斗智能-combat-intelligence)
- [八、角色养成 (Character Progression)](#八角色养成-character-progression)
- [九、探索与收集 (Exploration & Collection)](#九探索与收集-exploration--collection)
- [十、资源管理 (Resource Management)](#十资源管理-resource-management)
- [十一、抽卡与商店 (Wish & Shop)](#十一抽卡与商店-wish--shop)
- [十二、日常循环 (Daily Loop)](#十二日常循环-daily-loop)
- [十三、战略决策大脑 (Strategic Brain)](#十三战略决策大脑-strategic-brain)
- [十四、元学习与适应 (Meta-Learning)](#十四元学习与适应-meta-learning)
- [附录 A：现有代码库能力映射](#附录-a现有代码库能力映射)
- [附录 B：魔神任务完整依赖链](#附录-b魔神任务完整依赖链)
- [附录 C：全部 PC 热键速查](#附录-c全部-pc-热键速查)

---

## 一、感知层 (Perception)

### 1.1 屏幕状态识别

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| P-01 | 大世界状态检测 | 检测：大世界/战斗/对话/加载/死亡/菜单/秘境入口/通知 | ✅ 已有 (genshin_screen_classifier.py) |
| P-02 | 战斗指示器检测 | 检测红光闪烁、伤害数字、Boss 仇恨指示 | ✅ 已有 |
| P-03 | 小地图分析 | 检测任务标记方向、传送点图标、探索进度 | ✅ 已有 (HoughCircles) |
| P-04 | HP 条/技能冷却检测 | 读取队伍角色血量、E/Q 技能冷却状态 | ✅ 部分有 |
| P-05 | 交互提示检测 | 检测 "F" 键提示（NPC 对话/宝箱/采集/传送点激活） | ✅ 已有 (interaction_detector.py) |
| P-06 | 对话框检测 | 检测对话框出现、对话选项、NPC 肖像 | ✅ 已有 (dialog_driver.py) |
| P-07 | 加载画面检测 | 检测加载画面出现/消失，防止加载中误操作 | ✅ 已有 (loading_transition_protector.py) |
| P-08 | 死亡/复活画面检测 | 检测角色死亡画面、复活选项 | ✅ 已有 |
| P-09 | 弹窗/通知检测 | 检测成就弹窗、升级通知、邮件提示 | ⚠️ 部分有 |
| P-10 | Boss 阶段转换检测 | 检测 Boss 进入无敌/新阶段的视觉信号（发光、形态变化） | ✅ 已有 (genshin_visual_detectors.py BossPhaseDetection) |
| P-11 | AoE 地面指示器检测 | 检测红色/橙色地面圆圈（即将到来的范围攻击） | ⚠️ 部分有 (danger_detector.py) |
| P-12 | 元素附着可视化检测 | 检测敌人身上的元素附着状态（火光环、冰蓝色等） | ✅ 已有 (genshin_visual_detectors.py ElementalAuraDetection) |
| P-13 | 草原核/反应物检测 | 检测地面上的草原核、燃烧区域等可交互反应物 | ✅ 已有 (genshin_visual_detectors.py elemental auras) |
| P-14 | 天气/环境效果检测 | 检测严寒（龙脊雪山）、雷暴（稻妻）等环境计量条 | ✅ 已有 (genshin_visual_detectors.py EnvironmentGauge) |
| P-15 | 体力条检测 | 检测角色体力条当前值（攀爬/游泳/滑翔时关键） | ✅ 已有 (genshin_visual_detectors.py StaminaBarState) |
| P-16 | 倒计时/计时器检测 | 检测限时挑战的倒计时 UI 元素 | ✅ 已有 (genshin_visual_detectors.py CountdownTimer) |
| P-17 | 宝箱品质识别 | 区分 普通/精致/珍贵/华丽/奇珍 宝箱 | ✅ 已有 (genshin_visual_detectors.py ChestDetection) |
| P-18 | 任务标记颜色区分 | 区分黄色（魔神）/蓝色（传说/世界）/特殊图标 | ⚠️ 部分有 |

### 1.2 OCR 与文字识别

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| P-19 | 任务目标文字 OCR | 读取任务追踪器的文字目标 | ✅ 已有 (glm_ocr_provider.py) |
| P-20 | 对话文字 OCR | 读取 NPC 对话内容和选项文字 | ✅ 已有 |
| P-21 | 数值读取 | 读取伤害数字、血量数值、资源数量 | ⚠️ 部分有 |
| P-22 | 菜单文字 OCR | 读取角色属性、材料数量、商店价格等 | ⚠️ 需加强 |
| P-23 | 地图地名/区域名 OCR | 读取地图上的地名标注 | ❌ 缺失 |
| P-24 | 材料名称识别 | 在背包/合成台中识别材料名称和数量 | ❌ 缺失 |
| P-25 | 技能描述文字 OCR | 读取天赋描述、技能效果文字 | ❌ 缺失 |

### 1.3 VLM 视觉理解

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| P-26 | 场景整体理解 | VLM 分析当前屏幕场景语义 | ✅ 已有 (GLM-4V-Flash) |
| P-27 | 可交互物体识别 | 识别可交互的 NPC、物品、机关 | ⚠️ 需加强 |
| P-28 | 敌人类型识别 | 识别敌人种类、元素属性、护盾类型 | ⚠️ 部分有 (YOLO) |
| P-29 | 谜题状态识别 | 识别谜题当前状态（已激活/未激活/错误） | ❌ 缺失 |
| P-30 | 角色当前状态识别 | 识别当前操控角色、队伍配置 | ⚠️ 部分有 |

---

## 二、输入执行层 (Input & Execution)

### 2.1 基础输入

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| I-01 | 键盘输入 | WASD 移动、E/Q 技能、1-4 切人、F 交互 | ✅ 已有 (SafeWindowInputBackend) |
| I-02 | 鼠标移动/点击 | 精确鼠标定位和点击 | ✅ 已有 |
| I-03 | 按键组合 | Alt+1~4（切人并放大）、Shift（冲刺） | ✅ 已有 |
| I-04 | 长按/按住 | 按住鼠标中键（元素视野）、按住 W（持续移动） | ✅ 已有 |
| I-05 | 窗口焦点保护 | 每次输入前验证目标窗口焦点 | ✅ 已有 (SafeWindowInputBackend) |

### 2.2 安全机制

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| I-06 | 死人开关 | 租约过期/线程死亡/焦点丢失 → 立即释放所有按键 | ✅ 已有 (InputWorker) |
| I-07 | 紧急停止 | F9 键 / Ctrl+C / 看门狗超时 → release_all | ✅ 已有 |
| I-08 | 输入租约系统 | 所有输入必须通过 InputLease 授权 | ✅ 已有 |
| I-09 | 模式仲裁 | 优先级抢占，EMERGENCY_STOPPED 只能自转 | ✅ 已有 (ModeArbiter) |

### 2.3 操作序列执行

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| I-10 | 视觉动作块 | 分块执行 + 视觉触发等待 + 中断检查 | ✅ 已有 (VisualActionBlock) |
| I-11 | 传送序列 | M → 地图 → 点击传送点 → 确认 → 等待加载 | ✅ 已有 (teleport_sequence.py) |
| I-12 | 加载等待 | 检测加载画面并等待直到消失 | ✅ 已有 (loading_waiter.py) |
| I-13 | UI 操作序列 | 预定义的多步 UI 操作（如打开角色菜单→升级→确认） | ⚠️ 需要大量模板 |
| I-14 | 条件分支执行 | 根据视觉状态决定下一步操作 | ✅ 已有 (branch_on_visual_state) |
| I-15 | 精确鼠标拖拽 | 地图拖拽、物品拖拽（队伍配置、圣遗物装备） | ❌ 缺失 |
| I-16 | 滚轮操作 | 地图缩放、列表滚动 | ❌ 缺失 |

---

## 三、导航与移动 (Navigation & Movement)

### 3.1 世界导航

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| N-01 | 世界图寻路 | 基于 83KB 世界图的 Dijkstra 最短路径 | ✅ 已有 (genshin_navigator.py) |
| N-02 | 传送点间快速移动 | 多段传送：传送点A → 传送点B → 步行到目标 | ✅ 已有 |
| N-03 | 任务标记跟随 | 跟随小地图上的任务标记导航 | ✅ 已有 (quest_marker_follower.py) |
| N-04 | 小地图任务标记读取 | 解析小地图上的任务方向标记 | ✅ 已有 (minimap_quest_reader.py) |
| N-05 | 开放世界步移导航 | 在大世界中控制角色移动到指定位置 | ⚠️ 部分有 |
| N-06 | 相机伺服 | FOV 感知的像素→角度转换，追踪目标 | ✅ 已有 (camera_servo.py) |

### 3.2 特殊移动

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| N-07 | 攀爬控制 | 在可攀爬表面移动，管理体力消耗 | ✅ 已有 (special_movement.py ClimbingController) |
| N-08 | 游泳控制 | 水面游泳、潜水（枫丹水下区域） | ✅ 已有 (special_movement.py SwimmingController) |
| N-09 | 滑翔控制 | 从高处起飞、控制滑翔方向 | ✅ 已有 (special_movement.py GlidingController) |
| N-10 | 冲刺管理 | 管理冲刺体力消耗，避免耗尽导致坠落/溺水 | ✅ 已有 (special_movement.py SprintManager) |
| N-11 | 元素视野使用 | 按住鼠标中键开启元素视野寻找隐藏物体 | ✅ 已有 (special_movement.py ElementalSightController) |
| N-12 | 载具/变身使用 | 纳塔的 Saurian 附身、四叶印飞行等区域特殊移动 | ✅ 已有 (special_movement.py VehicleController) |
| N-13 | 地下区域导航 | 多层地图切换、洞穴网络寻路 | ✅ 已有 (special_movement.py UndergroundNavigator) |
| N-14 | 环境危害回避 | 龙脊严寒、稻妻雷暴等环境伤害的管理 | ✅ 已有 (special_movement.py EnvironmentHazardAvoidance) |

### 3.3 路径规划

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| N-15 | 多目标路径优化 | 规划访问多个目标的最优顺序 | ❌ 缺失 |
| N-16 | 动态障碍回避 | 绕过敌人营地、地形障碍 | ⚠️ 部分有 (obstacle_policy.py) |
| N-17 | 迷路恢复 | 检测迷路状态并恢复到已知位置 | ⚠️ 部分有 (recovery_policy.py) |
| N-18 | 三维空间导航 | 地下洞穴、多层建筑内的上下层导航 | ❌ 缺失 |

---

## 四、UI 菜单导航 (UI Menu Navigation)

### 4.1 核心菜单

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| U-01 | 派蒙菜单 (Esc) | 打开主菜单，导航到各子系统 | ⚠️ 需模板 |
| U-02 | 角色菜单 (C) | 属性/武器/圣遗物/天赋/命座 标签切换 | ⚠️ 需模板 |
| U-03 | 背包 (B) | 武器/圣遗物/角色培养/食物/材料/小工具/任务 标签 | ⚠️ 需模板 |
| U-04 | 地图 (M) | 地图缩放、传送点选择、区域切换 | ✅ 已有 |
| U-05 | 任务菜单 (J) | 魔神/传说/世界/委托/活动 分类浏览 | ⚠️ 需模板 |
| U-06 | 队伍配置 (L) | 角色拖放排列、队伍保存/切换 | ❌ 缺失 |
| U-07 | 祈愿 (F3) | 卡池选择、十连/单抽、购买纠缠之缘 | ❌ 缺失 |
| U-08 | 冒险之证 (F1) | 章节/敌人/秘境/收藏 追踪 | ❌ 缺失 |
| U-09 | 纪行 (F4) | 每日/每周任务完成、奖励领取 | ❌ 缺失 |
| U-10 | 活动面板 (F5) | 活动导航、参与、奖励领取 | ❌ 缺失 |
| U-11 | 好友/联机 (F2/O) | 联机模式进出 | ❌ 缺失 |
| U-12 | 设置菜单 | 调整图形/控制/音频设置 | ❌ 缺失 |

### 4.2 UI 操作原子能力

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| U-13 | 标签切换 | 在菜单内不同标签间切换（点击标签按钮） | ✅ 已有 (ui_primitives.py tab_switch) |
| U-14 | 列表滚动 | 在长列表中滚动到目标项 | ✅ 已有 (ui_primitives.py list_scroll_to) |
| U-15 | 确认/取消弹窗 | 处理确认弹窗（点击确认/取消按钮） | ✅ 已有 (ui_primitives.py confirm_popup/cancel_popup) |
| U-16 | 数量选择 | 在数量选择弹窗中调整数字（升级材料、商店购买） | ✅ 已有 (ui_primitives.py quantity_adjust) |
| U-17 | 下拉菜单选择 | 选择下拉选项（角色筛选、排序方式等） | ✅ 已有 (ui_primitives.py dropdown_select) |
| U-18 | 拖放操作 | 拖放角色到队伍槽位 | ✅ 已有 (ui_primitives.py drag_drop_party_slot) |
| U-19 | 地图缩放/平移 | 鼠标滚轮缩放、拖拽平移地图 | ✅ 已有 (ui_primitives.py map_zoom/map_pan) |
| U-20 | 自动识别当前 UI 页面 | VLM/分类器判断当前处于哪个菜单页面 | ✅ 已有 (ui_primitives.py PageIdentifier) |
| U-21 | 选项卡切换 | 冒险之证的 6 个选项卡切换 | ✅ 已有 (ui_primitives.py handbook_tab) |
| U-22 | 搜索/筛选 | 在武器/圣遗物列表中使用筛选功能 | ✅ 已有 (ui_primitives.py filter_open/filter_option) |

### 4.3 关键 UI 操作流程（需实现的宏）

| # | 流程名 | 步骤概要 | 状态 |
|---|--------|---------|------|
| U-23 | 角色升级流程 | Esc → C → 选角色 → 属性 → 升级 → 选材料 → 确认 | ✅ 已有 (ui_flows CHARACTER_LEVEL_UP) |
| U-24 | 角色突破流程 | Esc → C → 选角色 → 属性 → 突破 → 确认材料 → 突破 | ✅ 已有 (ui_flows CHARACTER_ASCEND) |
| U-25 | 天赋升级流程 | Esc → C → 选角色 → 天赋 → 选天赋 → 升级 → 确认 | ✅ 已有 (ui_flows CHARACTER_TALENT_UPGRADE) |
| U-26 | 武器装备流程 | Esc → C → 选角色 → 武器 → 换装 → 选择武器 → 装备 | ✅ 已有 (ui_flows WEAPON_EQUIP) |
| U-27 | 武器强化流程 | Esc → B → 武器 → 选武器 → 详情 → 强化 → 选材料 → 确认 | ✅ 已有 (ui_flows WEAPON_ENHANCE) |
| U-28 | 圣遗物装备流程 | Esc → C → 选角色 → 圣遗物 → 空槽 → 选择 → 装备 | ✅ 已有 (ui_flows ARTIFACT_EQUIP) |
| U-29 | 圣遗物强化流程 | Esc → C → 选角色 → 圣遗物 → 选圣遗物 → 强化 → 选材料 → 确认 | ✅ 已有 (ui_flows ARTIFACT_ENHANCE) |
| U-30 | 队伍配置流程 | Esc/L → 拖放角色 → 保存队伍 | ✅ 已有 (ui_flows PARTY_QUICK_CONFIG + ui_primitives drag_drop_party_slot) |
| U-31 | 抽卡流程 | Esc → F3 → 选卡池 → 十连/单抽 → 观看动画 → 查看结果 | ✅ 已有 (ui_flows WISH_TEN_PULL) |
| U-32 | 合成台操作 | 走到合成台 → F → 选择配方 → 调整数量 → 制作 | ✅ 已有 (ui_flows CRAFTING_BENCH_INTERACT + ui_primitives quantity_adjust) |
| U-33 | 锻造操作 | 走到铁匠 → F → 选择武器/矿 → 锻造 | ⚠️ 需模板 (交互原语已有，需铁匠UI流程) |
| U-34 | 烹饪操作 | 走到烹饪台 → F → 选择食谱 → 手动/自动烹饪 | ✅ 已有 (ui_flows COOKING_INTERACT + COOKING_AUTO_COOK) |
| U-35 | 商店购买 | 走到NPC → F → 浏览商品 → 选择数量 → 购买 | ⚠️ 部分有 (ui_primitives quantity_adjust 已有，需NPC商店流程) |
| U-36 | 派蒙商店购买 | Esc → 商店 → 派蒙的议价 → 星辉/星尘兑换 | ✅ 已有 (ui_flows SHOP_OPEN_PAIMON_BARGAINS + SHOP_BUY_MONTHLY_FATES) |
| U-37 | 冒险之证追踪 | Esc → F1 → 选择目标 → 追踪 | ✅ 已有 (ui_flows HANDBOOK_TRACK_ENEMY) |
| U-38 | 秘境进入/退出 | 传送到秘境 → F → 组队选择 → 开始 → 完成 → 领奖/退出 | ✅ 已有 (ui_flows DOMAIN_ENTER_AND_CLAIM) |
| U-39 | 密境领奖 | 秘境完成后消耗树脂领取奖励 | ✅ 已有 (ui_flows DOMAIN_ENTER_AND_CLAIM 含领奖步骤) |
| U-40 | 七天神像供奉 | 走到神像 → F → 供奉 → 选择神瞳数量 → 确认 | ✅ 已有 (ui_flows STATUE_OFFER_OCULI) |
| U-41 | 食物使用 | Esc → B → 食物 → 选择食物 → 使用 → 选目标角色 | ✅ 已有 (ui_flows FOOD_USE_FROM_BACKPACK) |
| U-42 | 快捷食物使用 | 战斗中通过食物菜单快速使用复活/治疗食物 | ⚠️ 需集成 (combat_survival.py CombatFoodState 已有逻辑) |
| U-43 | 时间调整 | Esc → 时间 → 调整时间 → 确认（部分任务需要） | ✅ 已有 (ui_flows TIME_ADJUST) |
| U-44 | 元素转换 | 走到七天神像 → F → 与 [某元素] 共鸣 | ⚠️ 需模板 (statue_interaction.py 已有基础) |

---

## 五、对话系统 (Dialog System)

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| D-01 | 对话推进 | 自动按 F/点击推进对话 | ✅ 已有 (dialog_driver.py) |
| D-02 | 对话选项选择 | 识别选项并选择（通常选第一个/推进型） | ✅ 已有 (dialog_branch_analyzer.py) |
| D-03 | 对话自动播放 | 开启自动播放模式以加速对话 | ⚠️ 需检测设置 |
| D-04 | 对话跳过 | 快速跳过已看过的对话（F+Space 交替） | ⚠️ 部分有 |
| D-05 | 过场动画处理 | 等待/跳过过场动画 | ⚠️ 部分有 |
| D-06 | 邀约事件分支 | 识别邀约事件的关键分支选择（影响结局） | ❌ 缺失 |
| D-07 | NPC 交互触发 | 检测并靠近有任务标记的 NPC，按 F 对话 | ⚠️ 部分有 |
| D-08 | 对话内容理解 | VLM/OCR 理解对话内容以做出正确选择 | ⚠️ 部分有 |
| D-09 | 多轮对话管理 | 处理与同一 NPC 的多轮对话（任务链） | ❌ 缺失 |

---

## 六、任务系统 (Quest System)

### 6.1 任务管理

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| Q-01 | 魔神任务跟踪 | 跟踪当前魔神任务章节和步骤 | ✅ 已有 (quest_state_machine.py) |
| Q-02 | 任务目标检测 | 从屏幕检测当前任务目标 | ✅ 已有 (quest_objective_detector.py) |
| Q-03 | 任务导航 | 按 V 激活任务导航线 | ⚠️ 部分有 |
| Q-04 | 前置条件检查 | 检查 AR/前置任务是否满足 | ✅ 已有 |
| Q-05 | 任务日志管理 | 在任务菜单中浏览、追踪、切换任务 | ✅ 已有 (quest_ui_manager.py QuestLogManager) |
| Q-06 | 世界任务发现 | 发现并接取世界任务（NPC 黄色感叹号） | ✅ 已有 (quest_ui_manager.py WorldQuestDiscovery) |
| Q-07 | 委托任务识别 | 识别每日委托的类型和位置 | ✅ 已有 (quest_ui_manager.py CommissionManager) |
| Q-08 | 任务完成确认 | 检测任务完成通知和奖励弹窗 | ✅ 已有 (quest_ui_manager.py QuestCompletionDetector) |
| Q-09 | 任务占用处理 | 处理"NPC 被其他任务占用"的情况 | ✅ 已有 (quest_ui_manager.py NPCOccupationHandler) |

### 6.2 特殊任务机制

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| Q-10 | 潜行任务 | 蒙德璃月千岩军潜行、稻妻离岛逃脱等潜行场景 | ✅ 已有 (quest_mechanism_router.py StealthHandler) |
| Q-11 | 护送任务 | 保护 NPC 移动到目标地点 | ✅ 已有 (quest_mechanism_router.py EscortHandler) |
| Q-12 | 限时挑战 | 在时间限制内完成战斗/收集 | ✅ 已有 (quest_mechanism_router.py TimedHandler) |
| Q-13 | 调查任务 | 枫丹梅罗彼得堡调查（线索收集、审讯） | ✅ 已有 (quest_mechanism_router.py InvestigationHandler) |
| Q-14 | 梦境序列 | 须弥梦境循环解谜 | ✅ 已有 (quest_mechanism_router.py DreamHandler) |
| Q-15 | 秘境任务执行 | 进入任务专属秘境，完成战斗+解谜 | ✅ 已有 (quest_mechanism_router.py DomainQuestHandler) |
| Q-16 | AR 突破任务 | 完成 AR 25/35/45/50 的突破域 | ✅ 已有 (quest_mechanism_router.py ARBreakthroughHandler) |

---

## 七、战斗智能 (Combat Intelligence)

### 7.1 基础战斗

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| C-01 | 技能循环执行 | 按 E/Q 技能的自动循环输出 | ✅ 已有 (genshin_playbook_executor.py) |
| C-02 | 角色切换 | 按时序切换 1-4 角色执行轮转 | ✅ 已有 (character_switch_manager.py) |
| C-03 | 普通攻击连击 | 按住/点击鼠标左键执行普通攻击循环 | ✅ 已有 |
| C-04 | 冷却管理 | 跟踪 E/Q 技能冷却时间 | ✅ 已有 (genshin_cooldown_manager.py) |
| C-05 | 能量管理 | 管理元素微粒收集和大招能量 | ⚠️ 部分有 |
| C-06 | 瞄准模式 | 弓箭手 R 键瞄准，精确射击弱点 | ❌ 缺失 |

### 7.2 元素反应系统

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| C-07 | 反应链规划 | 根据队伍组成规划最优元素反应顺序 | ✅ 已有 (genshin_element_reactions.py) |
| C-08 | 反应执行器 | 按正确顺序施放技能触发目标反应 | ✅ 已有 (reaction_executor.py) |
| C-09 | 敌人元素状态感知 | 感知敌人当前附着元素（视觉信号） | ✅ 已有 (combat_survival.py elemental awareness) |
| C-10 | 反应物交互 | 主动触发草原核（雷/火）、结晶（岩）等 | ✅ 已有 (reaction_executor.py) |
| C-11 | 元素盾破坏 | 识别敌人元素盾类型，使用克制元素破盾 | ✅ 已有 (combat_survival.py SHIELD_COUNTERS + get_shield_counter) |

### 7.3 闪避与生存

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| C-12 | 危险检测 | 多信号危险检测（红色区域、投射物、HP 骤降） | ✅ 已有 (danger_detector.py) |
| C-13 | 反射闪避 | P1 中断 → 冲刺闪避 | ✅ 已有 (reflex_evasion.py) |
| C-14 | 大招无敌帧利用 | 利用 Q 技能无敌帧规避大伤害 | ✅ 已有 (combat_survival.py burst_iframe decision) |
| C-15 | 体力管理（战斗中） | 冲刺闪避的体力预算管理 | ✅ 已有 (combat_survival.py stamina_ratio check) |
| C-16 | 食物使用（战斗中） | 战斗中使用治疗/复活/增益食物 | ✅ 已有 (combat_survival.py CombatFoodState + use_food) |
| C-17 | 角色死亡处理 | 角色死亡时切换到存活角色，使用复活食物 | ✅ 已有 (combat_survival.py revive_slot decision) |
| C-18 | 全灭恢复 | 全队阵亡后的复活/重新挑战流程 | ✅ 已有 (combat_survival.py all_dead retreat + daily_loop FailureAnalyzer) |

### 7.4 Boss 战

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| C-19 | Boss 攻击模式识别 | 识别 Boss 蓄力动画，预判攻击类型 | ✅ 已有 (combat_survival.py BossAttackPattern + BOSS_PHASES) |
| C-20 | Boss 阶段转换处理 | 检测阶段转换，在无敌期停止输出保存技能 | ✅ 已有 (combat_survival.py BossPhaseInfo + phase tracking) |
| C-21 | Boss 弱点攻击 | 在弱点暴露时集中攻击（如遗迹守卫核心） | ✅ 已有 (combat_survival.py damage_window_after) |
| C-22 | Boss 机制应对 | 处理特殊机制（如女士的寒冰/烈焰花朵，散兵的元素核心） | ✅ 已有 (combat_survival.py special_mechanics per boss) |
| C-23 | 周本 Boss 策略 | 针对不同周本 Boss 的专门战术 | ✅ 已有 (combat_survival.py BOSS_PHASES + genshin_f2p_builds BOSS_STRATEGIES) |
| C-24 | 世界 Boss 轮刷 | 自动传送到 Boss 位置、战斗、消耗树脂领奖、循环 | ⚠️ 部分有 (teleport + combat, need loop integration) |

### 7.5 深境螺旋

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| C-25 | 深境队伍配置 | 构建两队各 4 人的深境阵容 | ❌ 缺失 |
| C-26 | 深境房间识别 | 读取房间敌人阵容和元素盾需求 | ❌ 缺失 |
| C-27 | 深境增益选择 | 根据队伍选择最优深境增益 | ❌ 缺失 |
| C-28 | 深境自动挑战 | 自动完成深境 3 个房间并领奖 | ❌ 缺失 |

### 7.6 战斗策略

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| C-29 | 队伍轮转执行 | 20-25 秒循环：辅助增益 → 副C 部署 → 主C 输出 → 充能 | ✅ 已有 (playbook schema) |
| C-30 | 战斗计划生成 | LLM 根据队伍和敌人生成战斗 playbook | ✅ 已有 (genshin_combat_planner.py) |
| C-31 | 战斗动态调整 | 根据战斗进展动态调整策略 | ⚠️ 部分有 |
| C-32 | 战败分析 | 分析失败原因（输出不足/生存困难/机制错误） | ✅ 已有 (combat_survival.py BossMechanismLearner.get_failure_diagnosis + daily_loop FailureAnalyzer) |
| C-33 | 放弃判断 | 判断当前战斗是否无法胜利，选择撤退 | ✅ 已有 (combat_survival.py should_retreat + daily_loop S-11) |
| C-34 | 极限发挥 | 在可赢的困难战斗中优化操作到极限 | ✅ 已有 (meta_learning.py strategy iteration) |

---

## 八、角色养成 (Character Progression)

### 8.1 角色升级与突破

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| R-01 | 升级材料需求计算 | 计算从当前等级到目标等级所需的经验书和摩拉 | ✅ 已有 (genshin_character_progression.py + character_build_planner.py) |
| R-02 | 突破材料需求计算 | 计算突破所需的全部材料清单 | ✅ 已有 (total_ascension_mats_to_level) |
| R-03 | 材料获取路径规划 | 规划获取缺失材料的最优路径（Boss/秘境/采集） | ✅ 已有 (character_build_planner.generate_acquisition_plan) |
| R-04 | 自动角色升级 | 执行完整的角色升级 UI 操作流程 | ⚠️ UI流已定义 (CHARACTER_LEVEL_UP) |
| R-05 | 自动角色突破 | 执行完整的角色突破 UI 操作流程 | ⚠️ UI流已定义 (CHARACTER_ASCEND) |
| R-06 | 养成优先级排序 | 根据队伍需求排列角色养成优先级 | ✅ 已有 (CharacterBuildPlanner.prioritize_characters) |

### 8.2 天赋升级

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| R-07 | 天赋书日程管理 | 知道今天是哪些天赋书可刷的日子 | ✅ 已有 (TALENT_BOOK_SCHEDULE + books_available_today) |
| R-08 | 天赋升级优先级 | 知道每个角色的哪个天赋优先升（通常是 Q > E > 平A） | ✅ 已有 (BUILD_INVESTMENT_PRIORITY + talent_targets) |
| R-09 | 天赋材料需求计算 | 计算天赋升级所需的书本/Boss材料/敌人掉落 | ✅ 已有 (get_talent_cost + _add_talent_needs) |
| R-10 | 自动天赋升级 | 执行完整的天赋升级 UI 操作流程 | ⚠️ UI流已定义 (CHARACTER_TALENT_UPGRADE) |
| R-11 | 周本材料转换 | 使用梦之溶剂转换周本材料为所需类型 | ✅ 已有 (knowledge module DreamSolvent转换) |

### 8.3 武器管理

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| R-12 | 武器选择推荐 | 根据角色推荐最佳武器（考虑稀有度和可用性） | ✅ 已有 (genshin_f2p_builds.py F2P_WEAPON_REC) |
| R-13 | 武器升级 | 执行武器强化 UI 操作流程 | ⚠️ UI流已定义 (WEAPON_ENHANCE) |
| R-14 | 武器突破 | 执行武器突破 UI 操作流程 | ⚠️ UI流已定义 (WEAPON_EQUIP) |
| R-15 | 武器精炼 | 执行武器精炼 UI 操作流程（消耗重复武器） | ❌ 缺失 |
| R-16 | 武器材料日程 | 武器突破秘境的日程管理 | ✅ 已有 (TALENT_BOOK_SCHEDULE 框架可复用) |
| R-17 | 锻造武器 | 在铁匠处锻造武器/强化矿 | ⚠️ UI流已定义 (CRAFTING_BENCH_INTERACT) |

### 8.4 圣遗物管理

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| R-18 | 圣遗物套装知识 | 知道每个角色适合什么圣遗物套装 | ✅ 已有 (genshin_f2p_builds.py ARTIFACT_SETS) |
| R-19 | 圣遗物主词条知识 | 知道每个角色需要的沙/杯/头主词条 | ⚠️ 部分有 (genshin_f2p_builds 有推荐) |
| R-20 | 圣遗物副词条评估 | 评估圣遗物副词条质量（暴击率/暴击伤害/充能等） | ❌ 缺失 |
| R-21 | 圣遗物自动装备 | 为角色快速装备最佳可用圣遗物 | ⚠️ UI流已定义 (ARTIFACT_EQUIP) |
| R-22 | 圣遗物自动强化 | 选择有价值圣遗物并强化到目标等级 | ⚠️ UI流已定义 (ARTIFACT_ENHANCE) |
| R-23 | 圣遗物回收/喂养 | 将垃圾圣遗物作为强化材料消耗 | ❌ 缺失 |
| R-24 | 圣遗物合成台 | 使用神秘供奉转化 3 个五星圣遗物为目标套装 | ❌ 缺失 |
| R-25 | 圣遗物域刷取 | 自动刷取指定圣遗物秘境 | ⚠️ UI流已定义 (DOMAIN_ENTER_AND_CLAIM) |

### 8.5 队伍构建

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| R-26 | 队伍角色搭配 | 根据已有角色构建最优队伍（考虑元素共鸣和反应） | ⚠️ 部分有 (team_capability.py) |
| R-27 | 队伍配置执行 | 在队伍配置 UI 中排列角色 | ❌ 缺失 |
| R-28 | 队伍保存/切换 | 保存多个预设队伍并快速切换 | ❌ 缺失 |
| R-29 | 元素共鸣利用 | 根据队伍元素构成利用共鸣加成（双火+25%ATK 等） | ❌ 缺失 |
| R-30 | 针对性配队 | 根据敌人/秘境特性调整队伍配置 | ❌ 缺失 |

---

## 九、探索与收集 (Exploration & Collection)

### 9.1 传送点解锁

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| E-01 | 传送点发现 | 在大世界中发现未激活的传送点 | ✅ 已有 (exploration_engine.py + VLM) |
| E-02 | 传送点激活 | 走近传送点并按 F 激活 | ✅ 已有 (interaction_detector.py + teleport) |
| E-03 | 七天神像激活 | 找到并激活区域七天神像（揭示地图区域） | ✅ 已有 (STATUE_OFFER_OCULI flow) |
| E-04 | 系统化传送点收集 | 按区域规划路径解锁所有传送点 | ✅ 已有 (ExplorationEngine.plan_waypoint_sweep) |

### 9.2 宝箱与收集

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| E-05 | 宝箱发现 | 通过视觉/宝箱罗盘发现附近宝箱 | ✅ 已有 (exploration_engine + interaction_detector) |
| E-06 | 宝箱开启 | 走近宝箱按 F 开启，处理可能的敌人守护 | ✅ 已有 (chest_interaction.py) |
| E-07 | 宝箱罗盘使用 | 装备并使用区域宝箱罗盘道具 | ✅ 已有 (exploration_engine compass slot) |
| E-08 | 神瞳收集 | 发现并收集各区域的神瞳（风神瞳/岩神瞳等） | ✅ 已有 (ExplorationEngine.oculus offerings) |
| E-09 | 神瞳共鸣石使用 | 使用神瞳共鸣石道具定位附近神瞳 | ✅ 已有 (exploration_engine resonance stone) |
| E-10 | 材料采集 | 采集世界中的植物/矿石/动物材料 | ✅ 已有 (exploration_engine material collection) |
| E-11 | 区域探索率追踪 | 追踪各区域探索完成百分比 | ✅ 已有 (RegionProgress tracking) |

### 9.3 谜题解决

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| E-12 | 元素方尖碑激活 | 用正确元素攻击元素方尖碑 | ✅ 已有 (exploration_engine puzzle types) |
| E-13 | 火把谜题 | 解 Lights-Out 类火把谜题 | ✅ 已有 (exploration_engine puzzle framework) |
| E-14 | 赛伊尔引导 | 引导赛伊尔回到赛伊尔庭院 | ✅ 已有 (exploration_engine Seelie pursuit) |
| E-15 | 时间挑战 | 完成限时跑酷/收集/战斗挑战 | ✅ 已有 (exploration_engine timed challenges) |
| E-16 | 压力板谜题 | 踩压力板触发机关 | ✅ 已有 (exploration_engine pressure plates) |
| E-17 | 区域特殊谜题 | 各区域特有谜题机制（稻妻雷立方、须弥四叶印、枫丹水泡等） | ✅ 已有 (exploration_engine regional puzzles) |
| E-18 | VLM 辅助解谜 | 使用 VLM 分析谜题状态并推理解决方案 | ✅ 已有 (exploration_engine VLM integration) |

### 9.4 区域探索

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| E-19 | 区域解锁推进 | 按序推进蒙德→璃月→稻妻→须弥→枫丹→纳塔 | ✅ 已有 (exploration_engine region progression) |
| E-20 | 系统化区域扫荡 | 按区域规划高效收集路线 | ✅ 已有 (ExplorationEngine.plan_region_sweep) |
| E-21 | 地下区域探索 | 导航层岩巨渊、须弥洞穴、枫丹水下等地下区域 | ✅ 已有 (exploration_engine underground support) |
| E-22 | 环境适应 | 适应不同区域环境（严寒、雷暴、沙漠沙暴） | ✅ 已有 (exploration_engine environmental hazard management) |

---

## 十、资源管理 (Resource Management)

### 10.1 货币管理

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| M-01 | 摩拉预算管理 | 跟踪摩拉收支，确保升级需求不超支 | ✅ 已有 (resource_manager.py MoraBudget) |
| M-02 | 原石预算管理 | 跟踪原石收入，规划抽卡预算 | ✅ 已有 (resource_manager.py PrimogemBudget) |
| M-03 | 树脂管理 | 跟踪树脂恢复进度，确保不溢出 | ✅ 已有 (resource_manager.py ResinState) |
| M-04 | 树脂分配策略 | 根据当前 AR 和需求分配树脂到不同活动 | ✅ 已有 (daily_loop_scheduler.py _recommend_resin_spend) |
| M-05 | 浓缩树脂制作 | 在合成台制作浓缩树脂（40 原粹+晶核） | ❌ 缺失 |

### 10.2 材料管理

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| M-06 | 背包材料盘点 | 读取背包中各类材料的数量 | ❌ 缺失 |
| M-07 | 材料合成 | 在合成台将低级材料合成为高级（3:1） | ❌ 缺失 |
| M-08 | 元素宝石转换 | 使用阿佐特之尘转换元素宝石 | ❌ 缺失 |
| M-09 | 材料缺口分析 | 对比目标养成计划和当前库存，列出缺口 | ✅ 已有 (character_build_planner.py unsatisfied_needs) |
| M-10 | 材料获取计划 | 根据缺口生成材料获取任务列表（刷哪个Boss/秘境） | ✅ 已有 (character_build_planner.generate_acquisition_plan) |

### 10.3 食物与消耗品

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| M-11 | 食物烹饪 | 在烹饪台制作食物 | ⚠️ UI流已定义 (COOKING_AUTO_COOK) |
| M-12 | 食物库存管理 | 跟踪食物库存，确保关键食物充足（复活/治疗/增益） | ✅ 已有 (resource_manager.py FoodStock) |
| M-13 | 战斗前食物准备 | 在困难战斗前使用增益食物（ATK/暴击/防御） | ✅ 已有 (combat_survival.py pre_boss_atk_buff) |

### 10.4 探险与被动收入

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| M-14 | 探险派遣 | 每天派遣角色进行 20 小时探险 | ❌ 缺失 |
| M-15 | 参量质变仪 | 每周提交材料获取随机奖励 | ❌ 缺失 |
| M-16 | 尘歌壶收集 | 收集洞天宝钱、购买树脂/材料 | ❌ 缺失 |

---

## 十一、抽卡与商店 (Wish & Shop)

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| W-01 | 保底计数器 | 跟踪当前卡池的抽卡数和保底状态 | ✅ 已有 (wish_shop_system.py PityCounter) |
| W-02 | 卡池分析 | 分析当前卡池角色/武器的价值 | ✅ 已有 (wish_shop_system.py WishStrategy) |
| W-03 | 抽卡执行 | 自动执行抽卡 UI 操作 | ⚠️ UI流已定义 (WISH_TEN_PULL) |
| W-04 | 抽卡结果处理 | 识别抽卡结果，更新库存 | ⚠️ 部分有 (wish_shop_system 结果追踪) |
| W-05 | 派蒙商店月购 | 每月购买纠缠之缘（5 个，750 星尘）和相遇之缘（5 个，375 星尘） | ✅ 已有 (wish_shop_system.py monthly_shop_plan) |
| W-06 | 星辉角色购买 | 用星辉购买轮换 4 星角色（每月 2 个，各 34 星辉） | ✅ 已有 (wish_shop_system.py starglitter_exchange) |
| W-07 | 纪念品商店购买 | 用元素之印购买角色突破材料和武器蓝图 | ⚠️ UI流已定义 (SHOP_OPEN_PAIMON_BARGAINS) |
| W-08 | 抽卡策略决策 | 决定是否抽当前卡池还是攒原石等未来卡池 | ✅ 已有 (wish_shop_system.py F2P wish strategy) |

---

## 十二、日常循环 (Daily Loop)

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| DL-01 | 每日委托完成 | 完成 4 个每日委托 + 凯瑟琳领奖 | ✅ 已有 (daily_loop_executor.py CommissionExecutor) |
| DL-02 | 树脂消耗循环 | 根据日程表和优先级消耗树脂 | ✅ 已有 (daily_loop_executor.py ResinSpendingExecutor) |
| DL-03 | 周本 Boss 挑战 | 每周完成 3 个折扣周本 | ✅ 已有 (daily_loop_executor.py WeeklyBossExecutor) |
| DL-04 | 派遣收集 | 每天重置派遣任务 | ✅ 已有 (daily_loop_executor.py ExpeditionExecutor) |
| DL-05 | 纪行任务完成 | 完成每日/每周纪行任务 | ✅ 已有 (daily_loop_executor.py BattlePassExecutor) |
| DL-06 | 限时活动参与 | 参与当前版本的限时活动 | ✅ 已有 (daily_loop_executor.py EventExecutor) |
| DL-07 | 日常循环调度器 | 统一调度所有日常任务的执行顺序 | ✅ 已有 (daily_loop_executor.py DailyLoopExecutor) |

---

## 十三、战略决策大脑 (Strategic Brain)

### 13.1 游戏阶段判断

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| S-01 | 当前阶段识别 | 判断当前处于早期(AR1-30)/中期(AR30-45)/后期(AR45+) | ✅ 已有 (daily_loop_scheduler.py determine_phase) |
| S-02 | 阶段优先级切换 | 根据阶段调整行动优先级 | ✅ 已有 (StrategicDecisionEngine.evaluate phase-based routing) |
| S-03 | 瓶颈识别 | 识别当前阻碍进展的瓶颈（等级/装备/材料/任务） | ✅ 已有 (FailureAnalyzer + _should_push_archon) |
| S-04 | 下一步行动规划 | 综合所有信息决定当前应该做什么 | ⚠️ 部分有 (hierarchical_planner.py) |

### 13.2 关键决策点

| # | 决策 | 逻辑 |
|---|------|------|
| S-05 | 推进剧情 vs 养成角色 | 有未完成魔神任务且角色足够 → 推剧情；角色不够 → 先养成 |
| S-06 | 养成优先级 | 武器等级 > 圣遗物主词条 > 天赋 > 角色等级 > 圣遗物副词条 |
| S-07 | 世界等级突破 | 4个角色达到当前等级上限 + 能轻松打败世界Boss → 突破 |
| S-08 | AR 45 前/后策略 | AR45 前不刷圣遗物域，AR45 后全力刷五星圣遗物 |
| S-09 | 树脂分配 | AR<45: 突破/天赋/武器秘境；AR≥45: 圣遗物秘境优先 |
| S-10 | 战斗失败恢复 | 分析失败原因 → 升武器/天赋/换队伍/学Boss机制/用食物 |
| S-11 | 打不过就跑 | 判断角色太弱无法胜利 → 放弃，先去养成再回来 |
| S-12 | 抽卡策略 | F2P 优先角色池，跳过武器池，为确定提升的卡池攒原石 |

### 13.3 外部知识获取

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| S-13 | 在线攻略搜索 | 搜索 Boss 攻略、角色配队、圣遗物推荐 | ❌ 缺失 |
| S-14 | 攻略信息提取 | 从搜索结果中提取可执行的操作建议 | ❌ 缺失 |
| S-15 | 知识库维护 | 维护角色配队、Boss 机制、材料日程等知识库 | ⚠️ 部分有 (knowledge/) |
| S-16 | 版本更新感知 | 感知游戏版本更新内容和新机制 | ❌ 缺失 |

---

## 十四、元学习与适应 (Meta-Learning)

| # | 能力 | 描述 | 状态 |
|---|------|------|------|
| L-01 | 战斗经验积累 | 记录每次战斗的经过和结果，积累经验 | ✅ 已有 (meta_learning.py FightRecord + BAGEL) |
| L-02 | Boss 模式学习 | 从多次 Boss 战中总结攻击模式和弱点窗口 | ✅ 已有 (combat_survival.py BossMechanismLearner) |
| L-03 | 战斗计划迭代 | 每次战斗失败后优化下一次的战斗 playbook | ✅ 已有 (meta_learning.py strategy iteration) |
| L-04 | 失败归因分析 | 区分"角色太弱"vs"操作不当"vs"不了解机制" | ✅ 已有 (meta_learning.py get_failure_diagnosis + FailureAnalyzer) |
| L-05 | 养成效果评估 | 评估升级/换装后的战斗力变化 | ✅ 已有 (meta_learning.py evaluate_build_change) |
| L-06 | 策略自适应 | 根据长期表现自动调整策略参数 | ✅ 已有 (meta_learning.py StrategyAdapter) |
| L-07 | 跨 Boss 知识迁移 | 从一个 Boss 学到的模式迁移到类似 Boss | ✅ 已有 (meta_learning.py cross_boss_knowledge_transfer) |
| L-08 | 在线攻略利用 | 搜索并利用人类玩家的攻略和经验 | ✅ 已有 (meta_learning.py online_guide_integration) |

---

## 附录 A：现有代码库能力映射

### 已完成 (Production-Ready)

| 模块 | 文件 | 能力 |
|------|------|------|
| 屏幕分类 | `perception/genshin_screen_classifier.py` | HSV 颜色分析、小地图检测、HP条、技能图标 |
| 对象检测 | `perception/yolo_detector.py` | YOLO 目标检测 |
| 对象追踪 | `perception/ultralytics_tracker.py` | BoT-SORT 追踪 |
| OCR | `perception/glm_ocr_provider.py` | GLM-4V OCR |
| VLM | `perception/zhipu_vlm_provider.py` | GLM-4V 视觉理解 |
| 世界图 | `knowledge/genshin_world_graph.yaml` | 83KB 完整世界图 |
| 怪物库 | `knowledge/genshin_monsters.yaml` | 160+ 怪物条目 |
| 魔神任务 | `knowledge/genshin_archon_quests.py` | 序章~第五章任务数据 |
| 导航 | `navigation/genshin_navigator.py` | Dijkstra 世界图寻路 |
| 传送序列 | `navigation/teleport_sequence.py` | 完整传送编排 |
| 相机伺服 | `control/camera_servo.py` | FOV 感知角度转换 |
| 进度监督 | `control/progress_supervisor.py` | EWMA 进度追踪+挫折评分 |
| 危险检测 | `combat/danger_detector.py` | 多信号危险检测 |
| 反射闪避 | `combat/reflex_evasion.py` | P1 中断闪避 |
| 战斗计划 | `combat/genshin_combat_planner.py` | LLM 战斗计划生成 |
| 技能执行 | `combat/genshin_playbook_executor.py` | Playbook 图执行 |
| 元素反应 | `combat/genshin_element_reactions.py` | 完整反应表 |
| 冷却管理 | `combat/genshin_cooldown_manager.py` | 技能冷却追踪 |
| 角色切换 | `combat/character_switch_manager.py` | 队伍切换逻辑 |
| 食物管理 | `combat/food_manager.py` | 食物使用逻辑 |
| 输入后端 | `execution/safe_window_backend.py` | Win32 安全输入 |
| 输入工作线程 | `execution/input_worker.py` | 线程安全+死人开关 |
| 视觉动作块 | `execution/visual_action_block.py` | 分块执行+中断 |
| 加载等待 | `execution/loading_waiter.py` | 加载画面保护 |
| 验证器 | `execution/declarative_verifier.py` | 15+ 验证步骤类型 |
| 对话驱动 | `interaction/dialog_driver.py` | 自动对话推进 |
| 任务状态机 | `planning/quest_state_machine.py` | 任务链管理 |
| 状态总线 | `core/state_bus.py` | 中央状态枢纽 |
| 模式仲裁 | `core/mode_arbiter.py` | 优先级抢占状态机 |
| BAGEL | `bagel/runtime.py` | 完整信念系统 |
| LLM | `planning/hierarchical_planner.py` | GLM-5.1 层级规划 |

### 待建设 (Missing/Stub)

| 模块 | 缺失能力 |
|------|---------|
| UI 操作模板库 | 所有 UI 流程宏（U-23 到 U-44） |
| 角色养成系统 | 升级/突破/天赋/武器/圣遗物 的全自动化 |
| 探索引擎 | 传送点收集、宝箱搜索、神瞳收集、谜题求解 |
| 日常调度器 | 统一的日常/周常任务调度系统 |
| 商店/抽卡 | 抽卡执行、商店购买、保底管理 |
| 战斗学习 | Boss 模式学习、失败归因、策略迭代 |
| 食物/烹饪 | 战斗食物使用、烹饪系统 |
| 环境适应 | 严寒/雷暴等环境效果管理 |
| 队伍自动构建 | 根据角色池和目标自动构建队伍 |
| 3D 导航 | 地下/水下等复杂 3D 空间导航 |

---

## 附录 B：魔神任务完整依赖链

```
Prologue Act I (AR 1) — 蒙德教程
  └→ Prologue Act II (AR 10)
      └→ Prologue Act III (AR 15) — 风龙 Boss 战
          └→ Chapter I Act I (AR 23) — 璃月开启
              └→ Chapter I Act II (AR 25) — 潜行逃脱
                  └→ Chapter I Act III (AR 28) — 公子 Boss 战 (3阶段)
                      ├→ Interlude Act I (AR 28)
                      └→ Chapter II Prologue (AR 30) — 稻妻开启
                          └→ Chapter II Act I (AR 30) — 离岛逃脱
                              └→ Chapter II Act II (AR 30) — 女士 Boss 战
                                  └→ Chapter II Act III (AR 30) — 雷电将军 Boss 战
                                      ├→ Interlude Act II (AR 28) — 层岩巨渊
                                      └→ Chapter III Act I (AR 35) — 须弥开启
                                          └→ III Act II → III Act III → III Act IV
                                              └→ Chapter III Act V (AR 35) — 正机之神 Boss 战
                                                  ├→ Interlude Act III (AR 35) — 散兵间章
                                                  ├→ Interlude Act IV (AR 40) — 悖论
                                                  └→ Chapter IV Act I (AR 40) — 枫丹开启
                                                      └→ IV Act II → IV Act III → IV Act IV
                                                          └→ Chapter IV Act V (AR 40) — 吞星之鲸 Boss 战
                                                              └→ Chapter IV Act VI (AR 40)
                                                                  └→ Chapter V Act I (AR 40) — 纳塔开启
                                                                      └→ V Act II → V Act III → V Act IV
                                                                          └→ Chapter V Act V (AR 40) — 复活的炽热颂歌
                                                                              └→ Chapter VI (预计 2026.8) — 至冬国
```

**关键 Boss 战清单（必须通过才能推进剧情）：**

| Boss | 所在章节 | 阶段数 | 难度 | 特殊机制 |
|------|---------|--------|------|---------|
| 风魔龙 Dvalin | 序章 Act III | 1 | ★★ | 飞行射击+平台战斗 |
| 公子 Childe | 第一章 Act III | 3 | ★★★ | Hydro/Electro/双元素三阶段 |
| 女士 Signora | 第二章 Act II | 2 | ★★★ | 冰/火双阶段，极端温度管理 |
| 雷电将军 Raiden | 第二章 Act III | 1 | ★★★★ | 特殊机制（剧情必败→反转） |
| 正机之神 Shouki no Kami | 第三章 Act V | 3 | ★★★★ | 巨型 Boss，元素核心机制 |
| 吞星之鲸 Narwhal | 第四章 Act V | 2 | ★★★★ | 超大型 Boss 战 |
| 深渊入侵（纳塔） | 第五章 Act V | 多波 | ★★★★★ | 大规模战斗序列 |

---

## 附录 C：全部 PC 热键速查

| 热键 | 功能 |
|------|------|
| **WASD** | 移动 |
| **鼠标左键** | 普通攻击 |
| **鼠标右键** | 瞄准（弓）/ 冲刺（移动中） |
| **E** | 元素战技 |
| **Q** | 元素爆发 |
| **1/2/3/4** | 切换角色 |
| **Alt+1/2/3/4** | 切换角色并立即放 Q |
| **F** | 交互/拾取 |
| **Space** | 跳跃 |
| **Left Shift** | 冲刺 |
| **R** | 瞄准模式切换 |
| **鼠标中键(按住)** | 元素视野 |
| **Esc** | 派蒙菜单 |
| **B** | 背包 |
| **C** | 角色菜单 |
| **M** | 地图 |
| **J** | 任务菜单 |
| **L** | 队伍配置 |
| **O** | 好友 |
| **Y** | 通知 |
| **V** | 任务导航 |
| **G** | 教程 |
| **Z** | 小工具快捷使用 |
| **Enter** | 聊天 |
| **Tab** | 快捷菜单轮盘 |
| **F1** | 冒险之证 |
| **F2** | 联机 |
| **F3** | 祈愿 |
| **F4** | 纪行 |
| **F5** | 活动 |
| **F12** | 隐藏 UI |
| **P** | 放弃挑战 |

---

## 统计总结

> **更新日期**：2026-05-30（Phase 1-8 + Q/P 实现后更新）

| 类别 | 总条目 | ✅ 已完成 | ⚠️ 部分有 | ❌ 缺失 |
|------|--------|----------|----------|---------|
| 感知层 (Perception) | 30 | 18 | 6 | 6 |
| 输入执行 (Input) | 16 | 10 | 1 | 5 |
| 导航移动 (Navigation) | 18 | 5 | 4 | 9 |
| UI 菜单 (UI) | 44 | 1 | 15 | 28 |
| 对话系统 (Dialog) | 9 | 3 | 4 | 2 |
| 任务系统 (Quest) | 16 | 16 | 0 | 0 |
| 战斗智能 (Combat) | 34 | 25 | 3 | 6 |
| 角色养成 (Progression) | 30 | 9 | 10 | 11 |
| 探索收集 (Exploration) | 22 | 22 | 0 | 0 |
| 资源管理 (Resource) | 16 | 7 | 3 | 6 |
| 抽卡商店 (Wish/Shop) | 8 | 5 | 2 | 1 |
| 日常循环 (Daily) | 7 | 1 | 0 | 6 |
| 战略大脑 (Strategy) | 16 | 3 | 1 | 12 |
| 元学习 (Meta-Learning) | 8 | 8 | 0 | 0 |
| **总计** | **274** | **143** | **49** | **82** |

**完成率：52.2%（143/274）| 部分完成：17.9%（49/274）| 需新建：29.9%（82/274）**

---

> **当前优先级**：补齐 **UI 自动化执行**（U-13~U-44，将 ⚠️ 流程模板升级为完整可执行流程）和 **导航特殊移动**（N-07~N-14，攀爬/游泳/滑翔）。这两类是当前最大的缺失块。
