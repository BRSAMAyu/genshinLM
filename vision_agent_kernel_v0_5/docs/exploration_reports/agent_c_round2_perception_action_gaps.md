# Agent C Round 2: 感知到动作管线验证

## 2.1 Observation -> ScreenStateClaim 转换链

### 数据流（已确认工作）
1. GenshinScreenClassifier.classify(frame) -> ScreenState(state, confidence, indicators)
2. 两条独立路径写入 Observation:
   - 路径 A: _GenshinPerceptionBridge -> obs.extensions["genshin_screen"]
   - 路径 B: PerceptionFusionRuntime -> obs.ui_state + StateBus.screen_claim
3. PerceptionFusionRuntime._build_screen_state_claim() 构建 ScreenStateClaim

### Gap
- **GAP-C1 (Medium)**: 分类器每帧运行两次（_GenshinPerceptionBridge + FusionRuntime）
- **GAP-C2 (Low)**: ScreenStateKind Literal 有 28 种状态，分类器只生成 11 种
- **GAP-C3 (High)**: ScreenStateClaim.ui_elements 从未填充，actionable_elements() 始终为空
- **GAP-C4 (High)**: 分类器生成 "world_hud"/"full_menu" 不在 ScreenStateKind Literal 中，fusion 映射为 "unknown"

## 2.2 UIFlowSkillAdapter 动作映射验证

### 映射结构
- _DEFAULT_ALIASES: ~180 个语义别名
- _primitive_handlers: ~130 个处理程序

### 有实质处理逻辑
- UI Flow routing (~80): execute_flow_as_semantic() -> UIFlowExecutor
- confirm/interact/wait (14): 直接 backend 按键
- combat keys (14): _handle_combat() -> backend.key_down/up
- Exploration interact (8): F-key + ESC 序列
- Quest dialog/cutscene (6): F-key / ESC

### Stub (log + action_intent, 无实际效果)
- Daily/chain/mainline (14): action_intent no-op
- Boss combat (6): 只记录 Boss ID
- Environment combat (2): action_intent no-op

### 关键 Gap
- **GAP-C5 (High)**: Boss combat actions 是 stub，不与 BossCombatRuntime 集成
- **GAP-C6 (Medium)**: Daily/chain/mainline actions 是 stub
- **GAP-C7 (CRITICAL)**: Observation 无 image 字段，但 UIFlowSkillAdapter 在 5 处访问 obs.image，将导致 AttributeError 崩溃

## 2.3 UIFlowEngine 声明式流程

### 格式
UIFlow dataclass: name, steps (UIStep tuple), precondition_state, escape_on_failure
UIStep 支持 18 种类型: press_key, click_at, wait_state, wait_loading, delay, scroll, confirm, cancel, hold_click, drag, loop, verify_ocr_number 等

### 已注册: 58 个命名 UI Flows
覆盖: menu nav(8), character progression(10), weapon ops(6), artifact ops(4), party(2), teleport(2), wish(3), shop(3), crafting(4), mail/quest(5), exploration(8), combat support(2), batch(8)

### Gap
- **GAP-C8 (Medium)**: UI flow 状态名称与 fusion runtime 状态验证混淆
- **GAP-C9 (Medium)**: 没有 UI flow 用于 combat start/execute/end cycle
- **GAP-C10 (Medium)**: hold_click fallback 直接调用 Win32 API，绕过安全抽象

## 2.4 Capsule 注册链

### 已验证链
capsule.yaml声明 -> CapsuleRegistry.register() -> GenshinApp.install() -> add_post_processor() -> Pipeline._post_processors

### Gap
- **GAP-C11 (Low)**: capsule.yaml frame_processors 名称是死文本，无 string-to-class loader
- **GAP-C12 (Medium)**: 两个 frame processor 都运行分类器（冗余计算）
- **GAP-C13 (Medium)**: danger_extractor lazy-loaded 静默失败，禁用闪避

## 2.5 Combat Pipeline 完整性

### 已验证路径
GenshinCombatDetector.detect() -> CombatSignal -> StateBus.combat_signal -> BossCombatBridge._run() -> BossCombatRuntime.tick() -> PlaybookExecutor.tick()

### 关键 Gap
- **GAP-C14 (High)**: 无 visual combat_ended 检测（screen_state "combat"->"world_hud" 不触发 combat_ended）
- **GAP-C15 (High)**: GenshinCombatDetector 未连接到 FusionRuntime —— 只用 basic default signal
- **GAP-C16 (High)**: PlaybookExecutor 返回 CombatAction，BossCombatBridge 处理 InputLease —— 类型不匹配，无适配器
- **GAP-C17 (Low)**: 文件名 genshin_playbook_executor.py 与类名 PlaybookExecutor 不匹配

## 2.6 导航 -> 对话 -> 任务 衔接

### 已验证路径
QuestMarkerFollower.navigate_to_marker() -> WASD + CameraServo -> "arrived" -> QuestSkillAdapter.drive_dialog()

### 关键 Gap
- **GAP-C18 (CRITICAL)**: detect_dialog_end() 总是返回 True（只检查 prev=="dialog" && frame.size>0，不检查 current != "dialog"）
- **GAP-C19 (Medium)**: 无自动从导航到对话的切换机制
- **GAP-C20 (Low)**: QuestStateMachine 从未在应用代码中实例化
- **GAP-C21 (Medium)**: StateBus 无 quest_state slot，发布静默失败

## Gap 汇总

### Critical (2)
7. Observation 无 image 字段，UIFlowSkillAdapter 5 处访问 obs.image 将崩溃
18. detect_dialog_end() 总是返回 True，对话永远不会正确结束

### High (6)
3. ScreenStateClaim.ui_elements 从未填充
4. 分类器状态名不在 ScreenStateKind Literal 中
5. Boss combat actions 是 stub
14. 无 visual combat_ended 检测
15. GenshinCombatDetector 未连接 FusionRuntime
16. CombatAction vs InputLease 类型不匹配

### Medium (9)
1. 重复屏幕分类（每帧2次）
6. Daily/chain/mainline actions 是 stub
8. UI flow 状态名称混淆
9. 无 combat UI flow
10. hold_click 直接 Win32 API
12. 两个 frame processor 都运行分类器
13. danger_extractor 静默失败
19. 无自动导航到对话切换
21. StateBus 无 quest_state slot

### Low (4)
2. ScreenStateKind 有 28 种但分类器只生成 11 种
11. capsule.yaml frame_processors 死文本
17. 文件名与类名不匹配
20. QuestStateMachine 未实例化
