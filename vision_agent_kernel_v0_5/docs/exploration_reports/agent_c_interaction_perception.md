# Agent C: 交互与感知层探索报告

## Round 1 — 模块摸底

### 1. 文件清单

#### perception/ (80 个 .py 文件)

**核心管线:**
- `pipeline.py` — PerceptionPipeline 主循环
- `capture_base.py` — ScreenCapturer 协议 + FramePacket
- `dxcam_capture.py` — DXCam 高帧率截屏
- `frame_source.py` — DemoFrameSource, Win32WindowCapturer, FrameSourceFactory
- `viewport.py` — ViewportTransformer (分辨率归一化)

**检测/跟踪:**
- `detector_base.py`, `tracker_base.py` — Detector/Tracker 协议
- `yolo_detector.py` — YOLO 目标检测 (Ultralytics)
- `ultralytics_tracker.py` — BoT-SORT 跟踪器
- `target_selector.py` — 多目标评分选择
- `visual_trigger_detector.py` — HSV 颜色目标检测
- `region_aware_detector.py` — 七国区域检测

**屏幕分类:**
- `genshin_screen_classifier.py` — 11种指示器, 12种屏幕状态
- `hsr_screen_classifier.py` — HSR 屏幕分类
- `screen_state_tree.py` — ScreenStateTree 结构化

**OCR 模块 (8个):**
- `ocr_base.py`, `ocr_engine.py` (PaddleOCR), `ocr_router.py`
- `easy_ocr_provider.py`, `glm_ocr_provider.py`
- `ocr_post_processor.py`, `ocr_roi_registry.py`, `ocr_claim_builder.py`

**VLM/深度:**
- `vlm_post_processor.py` — 异步 VLM 分析
- `vlm_performance_monitor.py`
- `depth_anything_estimator.py` — 单目深度估计

**战斗感知:**
- `combat_perception.py` — HP bar, character switch, stamina
- `genshin_combat_detector.py` — 盾元素/Boss阶段/受击
- `fusion_runtime.py` — CombatSignal 融合

**原神专用检测器 (30+):**
adventure_rank_detector, elemental_reaction_detector, aoe_ground_detector, enemy_type_classifier, map_screen_detector, minimap_flow_tracker, timer_ocr_reader, damage_number_parser, hp_ocr_reader, cooldown_ocr_reader 等

#### interaction/ (17 个 .py 文件)

- `ui_anchor.py` — UIAnchor + NormalizedRect
- `capsule_anchors.py` — Capsule UI Anchor 注册
- `desktop_tree.py` — Desktop UI Tree
- `ui_flow_engine.py` — UIFlowExecutor 声明式 UI 流程引擎
- `npc_shop_interactor.py` — NPC 商店交互 (2x4 grid)
- `dialog_driver.py` — 对话驱动
- `dialog_branch_analyzer.py` — 对话分支分析
- `popup_handler.py` — 弹窗处理
- `menu_flows.py` — 菜单流
- `puzzle_handler.py` — 解谜处理
- `statue_interaction.py`, `chest_interaction.py`, `crafting_interaction.py`

#### combat/ (52 个 .py 文件)

**核心框架:** playbook_schema, playbook_runtime, combat_context, combat_policy, combat_verifier, combat_fallback_policy, genshin_skill_loader
**执行器:** genshin_playbook_executor, hsr_playbook_executor, live_combat_actuator, combat_rotation_runners
**规划器:** genshin_combat_planner, hsr_combat_planner
**资源/冷却:** resource_manager, genshin_cooldown_manager, shield_cooldown_manager, energy_particle_detector, energy_optimizer
**防御/生存:** danger_detector, dodge_policy, combat_survival, survival_runtime, reflex_evasion, flanking_policy
**Boss:** boss_schema, boss_tracker, boss_combat_runtime, boss_enrage_manager, boss_mechanic_router, boss_combat_bridge
**元素:** genshin_element_reactions, reaction_damage_calc, reaction_executor
**团队:** team_capability, character_switch_manager, team_build_validator, food_manager
**深渊:** spiral_abyss, abyss_split_planner

#### navigation/ (14 个 .py 文件)

- `genshin_navigator.py` — Dijkstra 路径规划 + minimap 导航
- `genshin_dialog_handler.py` — 对话检测/推进
- `hsr_navigator.py`, `hsr_dialog_handler.py` — HSR 版本
- `map_navigation_runtime.py` — WaypointGraph + NavigationPlan
- `quest_marker_follower.py` — 实时任务标记跟随
- `teleport_sequence.py` — 传送序列 (UIFlow preferred)
- `minimap_quest_reader.py` — 小地图任务标记读取
- `special_movement.py` — 游泳/滑翔/冲刺
- `lost_recovery.py` — 迷路恢复

#### capsules/ (4 个 Capsule)

| Capsule | 游戏 | 能力 |
|---------|------|------|
| genshin | 原神 | arpg_navigation, arpg_combat, danger_reflex, quest_following |
| hsr | 星穹铁道 | hsr_screen_classification, hsr_dialog_progression, hsr_turn_based_combat |
| demo_arpg | 通用 ARPG | generic_arpg_navigation, generic_arpg_combat |
| desktop_ui | 桌面 UI | ui_grounding, safe_desktop_interaction |

Capsule YAML 字段: capsule_id, version, runtime_package, entrypoint, providers, capabilities, frame_processors, slots, skills, transitions, verifiers, detectors, keymaps, ui_anchors, resources

#### data/skills/ (6 YAML + 2 JSON)

- `genshin_combat_skills.yaml` — safe_combat, boss_combat, dodge_reflex
- `genshin_collection_skills.yaml` — collect_plant, mine_ore, open_chest
- `genshin_navigation_skills.yaml` — teleport_and_navigate, minimap_navigate, handle_dialog
- `genshin_commission_skills.yaml` — platform_glide, balloon_escort, katheryne_rewards
- `index.json` — 技能总索引 + 版本管理

### 2. 感知 Pipeline

```
ScreenCapture -> FramePacket -> ViewportTransformer
  -> PerceptionPipeline._run_loop()
    -> DetectionTrackingPostProcessor (YOLO -> BoT-SORT -> TargetTrack)
    -> GenshinScreenClassifierPostProcessor (HSV -> screen_state)
    -> VLMPostProcessor (async VLM analysis)
    -> (Capsule custom post-processors)
  -> StateBus.publish_observation(observation)
  -> ObservationBuilder.build() -> ObservationGraph (13 node kinds)
  -> ObservationQualityChecker.check()
```

### 3. GenshinDialogHandler

- 检测: screen_state=="dialog" + ROI 裁剪底部1/4 + Canny边缘检测数按钮
- 推进: click_at dialog_area_center, 500ms cooldown
- 选择: click_at dialog_choice_{index}
- 结束检测: prev=="dialog" && current valid

### 4. NPCShopInteractor

2x4 grid (8 slots). Col x=[0.35, 0.55], Row y=[0.35, 0.50, 0.65, 0.80]
select_item_by_index/buy_item/scroll_page API

### 5. GenshinSkillLoader

加载流程: scan genshin_*.yaml -> match skill_id -> resolve_inheritance (extends) -> build GenshinSkill -> cache
必填验证: skill级9字段, step级3字段, trigger级3字段
异常: SkillNotFoundError, SkillValidationError, SkillInheritanceError

### 6. 导航架构

```
MapNavigationRuntime (WaypointGraph + Dijkstra)
  -> GenshinNavigator (plan_route + minimap + 3D avoidance)
    -> TeleportSequence (UIFlow preferred, raw fallback)
    -> QuestMarkerFollower (WASP + CameraServo, max 300 steps)
```
