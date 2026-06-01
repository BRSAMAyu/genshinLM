# M3 Operator Agent Audit Report

**Date**: 2026-06-01
**Auditor**: Opus Architecture Auditor
**Files**: `agent_kernel/operator_agent.py`, `tests/test_operator_agent.py`
**Status**: **CONDITIONAL PASS** with 3 issues

---

## Verdict Summary

| Check | Result |
|-------|--------|
| 1. Protocol conformance | PASS |
| 2. Type safety | **FAIL** (game-specific keyword leakage) |
| 3. Session immutability | PASS |
| 4. Intent parsing | PASS |
| 5. Override flow | PASS |
| 6. State explanation | PASS |
| 7. Test coverage | PASS |

---

## 1. Protocol Conformance — PASS

`OperatorAgent` correctly implements `CompanionAgent` from `agent_kernel/protocols.py`:

- `handle_user_message(str, dict[str, Any]) -> dict` ✓
- `propose_override(str, dict[str, Any]) -> RuntimeOverride | None` ✓
- `propose_capsule_patch(RuntimeOverride, str) -> CapsulePatchProposal | None` ✓
- `explain_current_state(dict[str, Any]) -> str` ✓
- Runtime checkable (`@runtime_checkable`) confirms protocol via `isinstance(agent, CompanionAgent)` ✓

---

## 2. Type Safety — **FAIL**

### Issue: Game-Specific Keyword Leakage

The `_TASK_KEYWORDS` dict contains Genshin-specific vocabulary embedded directly in the kernel:

```python
_TASK_KEYWORDS: dict[str, str] = {
    "升级": "character_level_up",
    "突破": "character_ascend",
    # ...
}
```

**Problem**: While no game-specific *imports* exist (confirmed by `TestNoGameImports`, line 562-572), the keyword list itself encodes game knowledge:
- Chinese keywords like 升级, 突破, 精炼 are Genshin-specific terminology
- These terms are not universally applicable (e.g., "突破" is ascension in Genshin)

**Violation**: SPARKLE_AGENT_KERNEL_DESIGN.md §3.1 states: "Kernel 不能知道...游戏 Capsule、Skill 经验、可验证流程、或可过期的知识包" and §7.2 explicitly lists "突破" and "精炼" as Genshin terminology that "不应长期依赖".

**Recommendation**: The keyword matching should be delegated to the Capsule layer. The kernel should only handle generic intent classification (set_goal, adjust_param, explain, confirm, abort) and let the Capsule provide the vocabulary mapping.

---

## 3. Session Immutability — PASS

`OperatorSession` is correctly implemented:
- `@dataclass(frozen=True, slots=True)` ✓
- All mutation methods (`start_task`, `add_pending_override`, `confirm_action`, `abort_action`, `add_confirmed_patch`) return new instances ✓
- Frozen enforcement tested (lines 52-60) ✓
- `state_history` maintains immutability with tuple append pattern ✓

---

## 4. Intent Parsing — PASS

All documented intent types are handled:

| Intent | Trigger Keywords | Handler |
|--------|-----------------|---------|
| set_goal | 18 CN/EN keywords (升级, level up, etc.) | `_handle_set_goal` |
| adjust_policy | 14 policy keywords (不要消耗稀有, no rare, etc.) | `_handle_adjust_policy` |
| adjust_param | 11 regex patterns | `_handle_adjust_param` |
| explain | 8 triggers (当前在做什么, what are you doing, etc.) | `_handle_explain` |
| confirm | 9 triggers (确认, yes, ok, etc.) | `_handle_confirm` |
| abort | 8 triggers (取消, no, cancel, etc.) | `_handle_abort` |
| unknown | Fallback | Returns "未理解指令" |

Priority ordering is correct: confirm/abort before explain, policy before task keywords.

---

## 5. Override Flow — PASS

`propose_override → propose_capsule_patch` chain works correctly:

```python
# Step 1: propose_override
override = agent.propose_override("把置信度调到0.2", {})
# Creates RuntimeOverride with target_parameter="confidence_threshold"

# Step 2: propose_capsule_patch  
patch = agent.propose_capsule_patch(override, "success")
# Only returns CapsulePatchProposal when session_outcome == "success"
# Returns None for "failed" or "partial"
```

Confirmed by tests (lines 427-457).

---

## 6. State Explanation — PASS

`explain_current_state()` produces meaningful output with all specified fields:

- `current_task` → "当前任务: X" or "当前无活跃任务" ✓
- `execution_mode` → Display name mapping (dry_run→试运行, safe_window→安全窗口) ✓
- `progress` → "进度: X%" ✓
- `pending_actions` → "待处理操作: N 项" ✓
- `recent_errors` → "最近错误: N 项" ✓

Tests confirm behavior (lines 466-481).

---

## 7. Test Coverage — PASS

109 tests covering:

| Category | Coverage |
|----------|----------|
| Frozen/slots enforcement | 5 tests |
| Intent parsing | 50+ param cases |
| Keyword matching | 11 tests |
| Session state tracking | 12 tests |
| `handle_user_message` | 6 tests |
| `propose_override` | 4 tests |
| `propose_capsule_patch` | 3 tests |
| `explain_current_state` | 3 tests |
| `SimpleOperatorAgent` | 6 tests |
| Full session flow | 3 tests |
| No game imports | 1 test |
| Protocol conformance | 3 tests |

All methods have edge case coverage including empty sessions, no-match scenarios, and confirm/abort with no pending actions.

---

## Issue Summary

| Priority | Issue | Recommendation |
|----------|-------|----------------|
| **High** | Game-specific keywords in `_TASK_KEYWORDS` violate Kernel/Capsule separation | Move keyword-to-capability mapping to Capsule layer; Kernel only classifies intent type |
| **Medium** | `SimpleOperatorAgent._TARGET_PATTERNS` extracts Genshin character names | Delegate target extraction to Capsule |
| **Low** | `_TASK_KEYWORDS` sorted longest-first but policy keywords (more specific) are checked first — correct but fragile | Add explicit comment documenting why policy check precedes task check |

---

## Conclusion

The M3 Operator Agent implementation is **functionally correct and well-tested**. Protocol conformance, type safety (import-level), session immutability, intent handling, override flow, and test coverage all pass. The critical issue is the **game-specific keyword vocabulary embedded in the Kernel layer**, which violates the Kernel/Capsule separation principle established in SPARKLE_AGENT_KERNEL_DESIGN.md.

The implementation should be refactored so that the keyword vocabulary is provided by the active Capsule rather than hardcoded in the Kernel.