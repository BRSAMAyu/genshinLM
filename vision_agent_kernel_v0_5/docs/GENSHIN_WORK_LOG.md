# Genshin Optimization Work Log

> 工作进度追踪文档。每次完成关键节点后更新。

---

## Phase 1: 基础适配

| # | 任务 | 状态 | 提交 | 备注 |
|---|------|------|------|------|
| 1 | genshin_1920x1080 Profile | pending | - | 锚点校准向导 |
| 2 | 窗口状态分类器 | pending | - | 17种屏幕状态检测 |
| 3 | 数据采集脚本 | pending | - | 感知哈希去重 |
| 4 | YOLO 模型配置与管道 | pending | - | 训练数据+类别+配置 |
| 5 | PaddleOCR 集成 | pending | - | CD数字/交互文本/对话选项 |
| 6 | Camera servo 补偿 | pending | - | Y轴75% + 加速度补偿 |

## Phase 2: 核心闭环

| # | 任务 | 状态 | 提交 | 备注 |
|---|------|------|------|------|
| 7 | GenshinDangerSignalExtractor | pending | - | 红圈/HP骤降/投射物 |
| 8 | 战斗 Skill 库 | pending | - | 安全战斗+Boss+闪避 |
| 9 | 采集 Skill 库 | pending | - | F键+矿石攻击+宝箱 |
| 10 | 资源/怪物知识库 | pending | - | YAML knowledge files |
| 11 | 区域自适应检测 | pending | - | RegionAwareDetector |
| 12 | 冷却管理增强 | pending | - | OCR+灰化+弧形+发光 |

## Phase 3: 体验打磨

| # | 任务 | 状态 | 提交 | 备注 |
|---|------|------|------|------|
| 13 | 导航 Skill | pending | - | 地图传送+小地图路径 |
| 14 | 对话处理 Skill | pending | - | 自动推进+选项选择 |
| 15 | LLM 战斗规划 | pending | - | 队伍+敌人→Playbook |
| 16 | 伴游 Persona | pending | - | 事件→台词映射 |
| 17 | 元素反应策略 | pending | - | LLM生成反应链 |
| 18 | 多区域 Profile 适配 | pending | - | 分辨率缩放 |

## Phase 4: 进阶能力

| # | 任务 | 状态 | 提交 | 备注 |
|---|------|------|------|------|
| 19 | 日常委托自动化 | pending | - | 4委托+交任务 |
| 20 | 树脂消耗自动化 | pending | - | 圣遗物本/地脉循环 |
| 21 | 失败学习 | pending | - | TelemetryIngestor增强 |
| 22 | 版本更新自动适配 | pending | - | GenshinVersionAdapter |
| 23 | 社区 Skill 分享 | pending | - | 导入导出标准化 |
| 24 | Co-Op 模式适配 | pending | - | 队友视觉干扰过滤 |

---

## Changelog

### 2026-05-20
- 基线提交 `ed04217`: pre-genshin-optimization baseline
- 创建工作进度文档
- 开始 Phase 1
