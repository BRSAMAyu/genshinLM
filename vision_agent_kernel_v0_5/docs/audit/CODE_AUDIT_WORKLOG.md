# Sparkle Project 全项目代码审查工作流

> **审查分支**: codex/pre-realworld-closure
> **审查日期**: 2026-05-31
> **审查方法**: 4个并行Agent × 4轮地毯式审查
> **治理模式**: 三权分立（审查员→验收员→执行员）

---

## 一、审查范围与分工

### Agent A — 核心基础设施 (Agent a1)
**范围**: `core/`, `perception/`, `execution/`
- `core/state_bus.py`, `core/events.py`, `core/mode_arbiter.py`, `core/types.py`
- `perception/screen_capture/`, `perception/detection/`, `perception/ocr/`
- `execution/input_worker.py`, `execution/human_override.py`

**职责**:
- 验证五平面架构实现的正确性
- 检查StateBus/Interrupt/ModeArbiter的线程安全
- 审查感知检测的实时性能
- 验证输入安全的DeadmanSwitch机制

### Agent B — 控制与编排 (Agent a2)
**范围**: `control/`, `orchestration/`, `planning/`
- `control/camera_servo.py`, `control/progress_supervisor.py`, `control/recovery_policy.py`
- `orchestration/task_spec.py`, `orchestration/skill_executor.py`
- `planning/goal_planner.py`, `planning/quest_skill_adapter.py`

**职责**:
- 验证控制平面的FOV感知→像素→角度转换
- 审查ProgressSupervisor的EWMA+斜率判断逻辑
- 检查Orchestration的任务图和技能调度
- 审查Planning的战略决策和任务适配

### Agent C — 测试与集成 (Agent a3)
**范围**: `tests/`, `scripts/`, `configs/`, `bagel/`
- `tests/test_*.py`, `tests/conftest.py`
- `scripts/run_*.py`, `scripts/*.sh/.ps1`
- `configs/*.yaml`, `configs/*.json`

**职责**:
- 验证测试覆盖率是否达到验收标准
- 检查测试用例的隔离性和可重复性
- 审查CI/CD脚本的正确性
- 检查配置文件的版本兼容性

### Agent D — 文档与知识 (Agent a4)
**范围**: `docs/`, `knowledge/`, `data/`, 根目录配置
- `docs/GENSHIN_*.md` (17份场景文档)
- `docs/audit/*.md` (8份审查报告)
- `CLAUDE.md`, `PROJECT_ALIGNMENT.md`, `README.md`

**职责**:
- 交叉验证文档与代码的一致性
- 检查场景文档的能力映射是否完整
- 审查知识库与实际实现的对应
- 验证文档的内部一致性和格式规范

---

## 二、三权分立治理

### 审查员 (Reviewer) — 每轮执行
- 只负责发现漏洞、缺陷和改进点
- 输出带证据的问题卡（Issue Card）
- 不做修复决策，只报告问题

### 验收员 (Validator) — Round 2执行
- 验证审查员发现的问题是否真实可复现
- 过滤掉误报和低价值问题
- 只批准值得修复的问题进入执行阶段

### 执行员 (Fixer) — Round 3-4执行
- 只负责修复已批准的问题
- 不能擅自扩大修改范围
- 修复后必须通过测试验证

### 最终报告 (Reporter) — Round 4结束
- 汇总所有通过验证的问题
- 按优先级和模块分类
- 给出修复建议和风险评估

---

## 三、执行计划

### Round 1 (R1): 初始扫描 — 4 Agent并行
每个Agent执行：
1. 读取分配范围内的所有文件
2. 识别明显问题（语法错误、类型错误、逻辑漏洞）
3. 检查架构组件的接口一致性
4. 输出第一轮问题清单

### Round 2 (R2): 深度验证 — 4 Agent并行
每个Agent执行：
1. 验证Round 1发现的问题
2. 深入分析复杂逻辑（如状态机、并发处理）
3. 检查边界条件和异常路径
4. 交叉验证与其他模块的交互
5. 输出带证据的问题卡

### Round 3 (R3): 修复执行
根据R2结果：
1. 合并所有通过验证的问题
2. 按优先级排序（P0/P1/P2）
3. 执行员开始修复高优先级问题
4. 每修复一个模块，提交一个commit

### Round 4 (R4): 回归验证
1. 验证所有修复是否完整
2. 检查是否引入新问题
3. 运行测试套件验证
4. 输出最终审查报告

---

## 四、验收标准

### 代码质量标准
- 所有Python文件通过`ruff check`
- 所有核心类型通过`mypy strict`
- 无未处理的异常路径
- 线程安全正确性（有Lock的都有释放）

### 架构一致性标准
- 五平面通信通过StateBus（无直接跨平面调用）
- 输入安全通过InputLease（无直接os.input调用）
- 状态机转换有完整的守卫条件

### 测试覆盖标准
- 核心模块（state_bus/mode_arbiter/input_worker）≥90%覆盖
- 感知模块（screen_classifier/detector）≥70%覆盖
- 控制模块（progress_supervisor/camera_servo）≥60%覆盖

---

## 五、问题卡格式

每个发现的问题输出为标准格式：

```markdown
## [ISSUE-XXX] 问题标题

**严重性**: P0 / P1 / P2
**模块**: agent_a / agent_b / agent_c / agent_d
**文件**: `path/to/file.py:line_number`
**发现时间**: Round N

### 问题描述
具体描述问题内容

### 证据
```python
# 证据代码或引用
```

### 影响分析
此问题的影响范围

### 修复建议
具体的修复方案

### 验证方法
如何验证修复是否正确
```

---

## 六、进度追踪

| 阶段 | Agent A | Agent B | Agent C | Agent D | 状态 |
|------|---------|---------|---------|---------|------|
| R1 初始扫描 | ⏳ | ⏳ | ⏳ | ⏳ | - |
| R2 深度验证 | ⏳ | ⏳ | ⏳ | ⏳ | - |
| R3 修复执行 | ⏳ | ⏳ | ⏳ | ⏳ | - |
| R4 回归验证 | ⏳ | ⏳ | ⏳ | ⏳ | - |
| 最终报告 | ⏳ | ⏳ | ⏳ | ⏳ | - |

## 七、Git提交规范

每次修复必须包含：
- commit message: `fix(module): 问题描述`
- 在issue card中记录commit hash
- 包含测试验证结果

---

*审查开始时间: 2026-05-31*
*目标: 在4轮内完成全项目地毯式审查*