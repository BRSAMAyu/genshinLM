# Operator Agent Specification

> **Purpose**: Define the companion dialog Agent, RuntimeOverride, and user confirmation protocol.
> **Status**: Partially implemented (runtime/claim_runtime.py::RuntimeOverrideClaim, execution/human_override.py)
> **Parent**: SPARKLE_AGENT_KERNEL_DESIGN.md

---

## Overview

The **Operator Agent** is the user-facing conversational interface. It translates natural
language into framework-internal parameters, strategies, and verified tasks. The user
should never need to directly adjust low-level parameters.

```
User natural language
  → Operator Agent parses intent
  → RuntimeOverrideClaim (if parameter override)
     → Policy validator
     → ActionContract regeneration
     → scoped execution
  → TaskSpec (if new task)
     → ClosedLoopRunner pipeline
  → CapsulePatchProposal (if permanent change)
     → schema → diff → replay → confirm → commit
```

## RuntimeOverrideClaim

A runtime override is a temporary or session-scoped parameter change. It is NOT direct
input — it produces a policy patch that regenerates ActionContracts.

```python
@dataclass(frozen=True, slots=True)
class RuntimeOverrideClaim:
    override_id: str
    target_component: str        # skill_id, policy_name, or node_id
    override_type: Literal["param", "skill", "policy", "threshold", "skip", "retry"]
    proposed_value: Any
    justification: str
    confidence: float            # 0.0-1.0
    status: Literal["pending", "validated", "rejected", "applied", "expired", "rolled_back"]
    scope: Literal["session", "mission", "permanent"]
    risk_level: RiskLevel
```

### Safety Rules

1. **Critical overrides** (risk_level="critical") require human confirmation.
2. **Permanent scope** overrides are rejected — must use CapsulePatchProposal instead.
3. **Confidence < 0.5** blocks auto-apply.
4. **Rollback** is always possible for session/mission scoped overrides.

### Validation Pipeline

```
RuntimeOverrideClaim(status="pending")
  → SimpleOverridePolicyValidator.validate()
  → status="validated" | "rejected"
  → if validated and is_safe_to_apply(): apply()
  → execution through normal ActionContract pipeline
  → post-action verification
```

## CapsulePatchProposal

For permanent changes to capsule YAML:

```
draft → schema_validated → diff_reviewed → replay_verified → user_confirmed → committed
```

Rules:
- Cannot skip stages.
- Committing without user_confirmed → rejected.
- Each transition produces a new immutable object.
- Version recorded in metadata.

## User Confirmation Protocol

All permanent and critical-scope changes require explicit user confirmation. The protocol:

1. **Display**: Show diff of proposed change (current vs proposed YAML).
2. **Preview**: Offer dry-run / replay of the proposed change.
3. **Confirm**: User explicitly confirms or rejects.
4. **Record**: Version, timestamp, user ID recorded in patch metadata.
5. **Audit**: Patch history available for review.

No silent permanent writes. No auto-committing overrides to YAML.

## Companion Dialog Flow

```
User: "把升级确认阈值调到0.2"
  → Operator parses: target=threshold, value=0.2, scope=session
  → RuntimeOverrideClaim(override_type="threshold", proposed_value=0.2)
  → Policy validator checks: not critical, session scope, confidence OK
  → Override applied for session duration
  → Session end: override expires, no YAML written

User: "永久跳过角色突破确认"
  → Operator parses: target=skip_ascend_confirm, scope=permanent
  → Rejected as RuntimeOverride (permanent scope)
  → CapsulePatchProposal created instead
  → schema → diff → replay → user confirmation required
```

---

*Source: `runtime/claim_runtime.py::RuntimeOverrideClaim`, `runtime/claim_runtime.py::CapsulePatchProposal`, `execution/closed_loop_runner.py`*
