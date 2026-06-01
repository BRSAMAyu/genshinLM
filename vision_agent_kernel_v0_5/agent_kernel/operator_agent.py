"""OperatorAgent — L9 M3 user-facing dialogue agent.

Translates natural language into TaskSpec, RuntimeOverride, and
CapsulePatchProposal using pure keyword matching (no LLM/VLM).

The OperatorAgent is the rule-based front-end that handles common user
requests before they reach the CerebrumAgent (L7-L8). It can:
  - Parse task requests into structured TaskSpecs
  - Generate RuntimeOverrides from parameter adjustment requests
  - Propose CapsulePatchProposals from verified overrides
  - Explain current agent state in human-readable form
  - Handle confirm/abort flow for pending actions
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from agent_kernel.types import (
    CapsulePatchProposal,
    OperatorCommand,
    RuntimeOverride,
    TaskSpec,
)


# ---------------------------------------------------------------------------
# OperatorSession — tracks state of an ongoing operator session
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OperatorSession:
    """Immutable snapshot of an operator session state.

    Each mutation returns a new OperatorSession instance.
    """
    session_id: str
    current_task: TaskSpec | None = None
    pending_overrides: tuple[RuntimeOverride, ...] = ()
    confirmed_patches: tuple[CapsulePatchProposal, ...] = ()
    state_history: tuple[tuple[float, str], ...] = ()
    created_at: float = 0.0

    def start_task(self, task: TaskSpec) -> OperatorSession:
        """Return a new session with the given task started."""
        return OperatorSession(
            session_id=self.session_id,
            current_task=task,
            pending_overrides=self.pending_overrides,
            confirmed_patches=self.confirmed_patches,
            state_history=(*self.state_history, (time.perf_counter(), f"task_started:{task.task_id}")),
            created_at=self.created_at,
        )

    def add_pending_override(self, override: RuntimeOverride) -> OperatorSession:
        """Return a new session with a pending override added."""
        return OperatorSession(
            session_id=self.session_id,
            current_task=self.current_task,
            pending_overrides=(*self.pending_overrides, override),
            confirmed_patches=self.confirmed_patches,
            state_history=(*self.state_history, (time.perf_counter(), f"override_added:{override.override_id}")),
            created_at=self.created_at,
        )

    def confirm_action(self) -> OperatorSession:
        """Return a new session with the latest pending override confirmed.

        Moves the last pending override to state_history as confirmed.
        """
        if not self.pending_overrides:
            return self
        confirmed = self.pending_overrides[-1]
        return OperatorSession(
            session_id=self.session_id,
            current_task=self.current_task,
            pending_overrides=self.pending_overrides[:-1],
            confirmed_patches=self.confirmed_patches,
            state_history=(*self.state_history, (time.perf_counter(), f"override_confirmed:{confirmed.override_id}")),
            created_at=self.created_at,
        )

    def abort_action(self) -> OperatorSession:
        """Return a new session with the latest pending override aborted."""
        if not self.pending_overrides:
            return self
        aborted = self.pending_overrides[-1]
        return OperatorSession(
            session_id=self.session_id,
            current_task=self.current_task,
            pending_overrides=self.pending_overrides[:-1],
            confirmed_patches=self.confirmed_patches,
            state_history=(*self.state_history, (time.perf_counter(), f"override_aborted:{aborted.override_id}")),
            created_at=self.created_at,
        )

    def add_confirmed_patch(self, patch: CapsulePatchProposal) -> OperatorSession:
        """Return a new session with a confirmed capsule patch added."""
        return OperatorSession(
            session_id=self.session_id,
            current_task=self.current_task,
            pending_overrides=self.pending_overrides,
            confirmed_patches=(*self.confirmed_patches, patch),
            state_history=(*self.state_history, (time.perf_counter(), f"patch_confirmed:{patch.proposal_id}")),
            created_at=self.created_at,
        )

    def get_status_summary(self) -> dict[str, Any]:
        """Return a human-readable summary of the session state."""
        task_summary = ""
        if self.current_task is not None:
            task_summary = f"{self.current_task.objective} (id={self.current_task.task_id})"
        return {
            "session_id": self.session_id,
            "current_task": task_summary,
            "pending_overrides_count": len(self.pending_overrides),
            "confirmed_patches_count": len(self.confirmed_patches),
            "history_event_count": len(self.state_history),
            "created_at": self.created_at,
        }


def _new_session() -> OperatorSession:
    """Create a fresh OperatorSession."""
    return OperatorSession(
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
        created_at=time.perf_counter(),
    )


# ---------------------------------------------------------------------------
# Intent parsing helpers
# ---------------------------------------------------------------------------

# Task intent keywords — longest-first matching
_TASK_KEYWORDS: dict[str, str] = {
    # Chinese
    "升级": "character_level_up",
    "突破": "character_ascend",
    "强化": "enhance",
    "精炼": "refine",
    "祈愿": "wish_pull",
    "天赋": "talent_upgrade",
    "圣遗物": "artifact_manage",
    "武器": "weapon_manage",
    "打怪": "combat",
    "战斗": "combat",
    "探索": "explore",
    "宝箱": "explore_chest",
    "传送": "teleport",
    "任务": "quest",
    "日常": "daily",
    "主线": "mainline",
    # English
    "level up": "character_level_up",
    "ascend": "character_ascend",
    "enhance": "enhance",
    "refine": "refine",
    "wish": "wish_pull",
    "talent": "talent_upgrade",
    "artifact": "artifact_manage",
    "weapon": "weapon_manage",
    "combat": "combat",
    "fight": "combat",
    "explore": "explore",
    "chest": "explore_chest",
    "teleport": "teleport",
    "quest": "quest",
    "daily": "daily",
    "mainline": "mainline",
}

# Policy keywords
_POLICY_KEYWORDS: dict[str, tuple[str, str]] = {
    # Chinese → (policy_field, policy_value)
    "不要消耗稀有资源": ("resource_policy", "no_rare_consumables"),
    "不消耗稀有": ("resource_policy", "no_rare_consumables"),
    "节省资源": ("resource_policy", "conserve_resources"),
    "跳过所有对话": ("dialog_policy", "skip_all"),
    "推进对话": ("dialog_policy", "progress_main_story"),
    "谨慎模式": ("uncertainty_policy", "ask_user_after_60s"),
    "保守策略": ("uncertainty_policy", "ask_user_after_60s"),
    "安全模式": ("execution_mode", "dry_run"),
    "试运行": ("execution_mode", "dry_run"),
    "正式运行": ("execution_mode", "safe_window"),
    # English
    "no rare resources": ("resource_policy", "no_rare_consumables"),
    "conserve resources": ("resource_policy", "conserve_resources"),
    "skip all dialog": ("dialog_policy", "skip_all"),
    "advance dialog": ("dialog_policy", "progress_main_story"),
    "cautious mode": ("uncertainty_policy", "ask_user_after_60s"),
    "conservative": ("uncertainty_policy", "ask_user_after_60s"),
    "dry run": ("execution_mode", "dry_run"),
    "safe mode": ("execution_mode", "dry_run"),
    "live mode": ("execution_mode", "safe_window"),
}

# Override keywords — patterns for parameter adjustment
_OVERRIDE_PATTERNS: list[tuple[str, str]] = [
    # Chinese patterns: specific parameter names first (before generic patterns)
    (r"置信度\s*(?:调到|调为|设为|设到|到)\s*([0-9.]+)", "confidence_threshold"),
    (r"(?:设置)?超时(?:时间)?\s*(?:调到|调为|设置为?|设到|到|为)\s*([0-9]+)\s*秒", "timeout_sec"),
    (r"重试.{0,4}?([0-9]+)", "max_retries"),
    (r"频率\s*(?:调到|调为|设为|设到|到)\s*([0-9.]+)", "frequency"),
    # Generic Chinese patterns: "设置 X 为 Y" or "把 X 调到 Y"
    (r"设置\s*(.+?)\s*为\s*(.+)", "generic_param_set"),
    (r"把\s*(.+?)\s*调到\s*([0-9.]+)", "generic_param"),
    # English patterns
    (r"set\s+confidence\s+(?:to\s+)?([0-9.]+)", "confidence_threshold"),
    (r"set\s+timeout\s+(?:to\s+)?([0-9]+)\s*s(?:ec)?", "timeout_sec"),
    (r"set\s+retries\s+(?:to\s+)?([0-9]+)", "max_retries"),
    (r"set\s+frequency\s+(?:to\s+)?([0-9.]+)", "frequency"),
    (r"adjust\s+(\w+)\s+to\s+([0-9.]+)", "generic_param"),
]

# Explanation triggers
_EXPLANATION_TRIGGERS_CN = ("当前在做什么", "在做什么", "状态", "当前状态", "怎么回事", "现在")
_EXPLANATION_TRIGGERS_EN = ("what are you doing", "current state", "status", "what's happening", "explain")

# Confirm/abort triggers
_CONFIRM_TRIGGERS = ("确认", "确定", "好的", "执行", "confirm", "yes", "ok", "okay", "proceed", "go ahead")
_ABORT_TRIGGERS = ("取消", "放弃", "停止", "cancel", "abort", "no", "stop", "discard")


def _parse_intent(text: str) -> str:
    """Classify user text into one of: set_goal, adjust_policy, adjust_param, explain, confirm, abort, unknown."""
    text_lower = text.lower().strip()

    for trigger in _CONFIRM_TRIGGERS:
        if text_lower == trigger or text_lower == trigger.strip():
            return "confirm"

    for trigger in _ABORT_TRIGGERS:
        if text_lower == trigger or text_lower == trigger.strip():
            return "abort"

    for trigger in _EXPLANATION_TRIGGERS_CN:
        if trigger in text_lower:
            return "explain"
    for trigger in _EXPLANATION_TRIGGERS_EN:
        if trigger in text_lower:
            return "explain"

    # Check policy keywords before task keywords (policy phrases are more specific)
    for keyword in _POLICY_KEYWORDS:
        if keyword in text_lower:
            return "adjust_policy"

    # Check override patterns (try both original and lowered for Chinese)
    for pattern, _ in _OVERRIDE_PATTERNS:
        if re.search(pattern, text) or re.search(pattern, text_lower):
            return "adjust_param"

    # Check task keywords (longest first)
    for keyword in sorted(_TASK_KEYWORDS, key=len, reverse=True):
        if keyword in text_lower:
            return "set_goal"

    return "unknown"


def _match_task_keyword(text: str) -> tuple[str, float]:
    """Return (capability, confidence) from task keyword matching."""
    text_lower = text.lower()
    for keyword in sorted(_TASK_KEYWORDS, key=len, reverse=True):
        if keyword in text_lower:
            return _TASK_KEYWORDS[keyword], 0.8
    return "unknown", 0.3


def _match_policy(text: str) -> tuple[str, str] | None:
    """Return (policy_field, policy_value) or None."""
    text_lower = text.lower()
    # Sort by keyword length descending for longest match
    for keyword in sorted(_POLICY_KEYWORDS, key=len, reverse=True):
        if keyword in text_lower:
            return _POLICY_KEYWORDS[keyword]
    return None


def _match_override(text: str) -> tuple[str, str, str] | None:
    """Return (target_parameter, new_value, reason) or None."""
    text_lower = text.lower()
    for pattern, target_param in _OVERRIDE_PATTERNS:
        # Try both original and lowered text to handle mixed Chinese+English
        match = re.search(pattern, text) or re.search(pattern, text_lower)
        if match:
            groups = match.groups()
            if target_param in ("generic_param", "generic_param_set") and len(groups) >= 2:
                return (groups[0].strip(), groups[1].strip(), text.strip())
            if len(groups) >= 1:
                return (target_param, groups[0].strip(), text.strip())
    return None


# ---------------------------------------------------------------------------
# OperatorAgent — abstract base implementing CompanionAgent protocol
# ---------------------------------------------------------------------------

class OperatorAgent:
    """Base class for operator agents implementing the CompanionAgent protocol.

    Provides the public API; subclasses may override _parse methods.
    This class itself is concrete enough for testing via the keyword-based
    parsing defined above.
    """

    def __init__(self) -> None:
        self._session: OperatorSession = _new_session()

    @property
    def session(self) -> OperatorSession:
        return self._session

    def handle_user_message(
        self,
        message: str,
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle a user message and return a structured response.

        Returns dict with keys:
          - display_message: str — human-readable response
          - technical_action: dict — structured action for the system
          - patch_draft: CapsulePatchProposal | None
        """
        intent = _parse_intent(message)
        cmd = OperatorCommand(
            command_id=f"cmd_{uuid.uuid4().hex[:8]}",
            user_text=message,
            parsed_intent=intent,
            parameters=(),
            confidence=0.8 if intent != "unknown" else 0.3,
        )

        if intent == "set_goal":
            return self._handle_set_goal(message, cmd)
        elif intent == "adjust_policy":
            return self._handle_adjust_policy(message, cmd)
        elif intent == "adjust_param":
            return self._handle_adjust_param(message, cmd)
        elif intent == "explain":
            return self._handle_explain(current_context)
        elif intent == "confirm":
            return self._handle_confirm()
        elif intent == "abort":
            return self._handle_abort()
        else:
            return {
                "display_message": f"未理解指令: {message}",
                "technical_action": {"intent": "unknown", "command": cmd},
                "patch_draft": None,
            }

    def propose_override(
        self,
        user_text: str,
        current_state: dict[str, Any],
    ) -> RuntimeOverride | None:
        """Parse user text into a RuntimeOverride proposal."""
        match = _match_override(user_text)
        if match is None:
            return None
        target_param, new_value, reason = match
        return RuntimeOverride(
            override_id=f"ovr_{uuid.uuid4().hex[:8]}",
            target_parameter=target_param,
            new_value=new_value,
            reason=reason,
            source="user",
            scope="session",
            confidence=0.85,
        )

    def propose_capsule_patch(
        self,
        override: RuntimeOverride,
        session_outcome: str,
    ) -> CapsulePatchProposal | None:
        """Propose making a runtime override permanent as a Capsule YAML patch.

        Only proposes if the session outcome was successful.
        """
        if session_outcome != "success":
            return None
        return CapsulePatchProposal(
            proposal_id=f"patch_{uuid.uuid4().hex[:8]}",
            capsule_id="runtime_params",
            yaml_path=f"parameters/{override.target_parameter}",
            patch_data=((override.target_parameter, override.new_value),),
            reason=f"Promoted from session override: {override.reason}",
            verified=False,
            user_confirmed=False,
        )

    def explain_current_state(self, state: dict[str, Any]) -> str:
        """Generate a human-readable explanation of the current agent state."""
        lines: list[str] = []

        task = state.get("current_task")
        if task:
            if isinstance(task, dict):
                lines.append(f"当前任务: {task.get('objective', '未知')}")
            else:
                lines.append(f"当前任务: {task}")
        else:
            lines.append("当前无活跃任务")

        mode = state.get("execution_mode", "dry_run")
        mode_display = {"dry_run": "试运行", "safe_window": "安全窗口", "console": "控制台"}.get(mode, mode)
        lines.append(f"执行模式: {mode_display}")

        progress = state.get("progress")
        if progress is not None:
            lines.append(f"进度: {progress}")

        pending = state.get("pending_actions", 0)
        if pending:
            lines.append(f"待处理操作: {pending} 项")

        errors = state.get("recent_errors", [])
        if errors:
            lines.append(f"最近错误: {len(errors)} 项")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_set_goal(self, message: str, cmd: OperatorCommand) -> dict[str, Any]:
        capability, confidence = _match_task_keyword(message)
        task = TaskSpec(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            objective=capability,
            execution_mode="dry_run",
            priority=50,
        )
        self._session = self._session.start_task(task)
        display = f"已创建任务: {capability} (id={task.task_id})"
        return {
            "display_message": display,
            "technical_action": {"intent": "set_goal", "task": task, "command": cmd},
            "patch_draft": None,
        }

    def _handle_adjust_policy(self, message: str, cmd: OperatorCommand) -> dict[str, Any]:
        policy = _match_policy(message)
        if policy is None:
            return {
                "display_message": f"未识别的策略调整: {message}",
                "technical_action": {"intent": "adjust_policy", "command": cmd},
                "patch_draft": None,
            }
        field_name, value = policy
        display = f"已调整策略: {field_name} = {value}"
        return {
            "display_message": display,
            "technical_action": {
                "intent": "adjust_policy",
                "field": field_name,
                "value": value,
                "command": cmd,
            },
            "patch_draft": None,
        }

    def _handle_adjust_param(self, message: str, cmd: OperatorCommand) -> dict[str, Any]:
        override = self.propose_override(message, {})
        if override is None:
            return {
                "display_message": f"未识别的参数调整: {message}",
                "technical_action": {"intent": "adjust_param", "command": cmd},
                "patch_draft": None,
            }
        self._session = self._session.add_pending_override(override)
        display = (
            f"已创建参数调整提案: {override.target_parameter} = {override.new_value}\n"
            f"请确认或取消此操作。"
        )
        return {
            "display_message": display,
            "technical_action": {"intent": "adjust_param", "override": override, "command": cmd},
            "patch_draft": None,
        }

    def _handle_explain(self, context: dict[str, Any]) -> dict[str, Any]:
        explanation = self.explain_current_state(context)
        return {
            "display_message": explanation,
            "technical_action": {"intent": "explain"},
            "patch_draft": None,
        }

    def _handle_confirm(self) -> dict[str, Any]:
        if not self._session.pending_overrides:
            return {
                "display_message": "没有待确认的操作。",
                "technical_action": {"intent": "confirm", "result": "no_pending"},
                "patch_draft": None,
            }
        self._session = self._session.confirm_action()
        display = "操作已确认执行。"
        return {
            "display_message": display,
            "technical_action": {"intent": "confirm", "result": "confirmed"},
            "patch_draft": None,
        }

    def _handle_abort(self) -> dict[str, Any]:
        if not self._session.pending_overrides:
            return {
                "display_message": "没有待取消的操作。",
                "technical_action": {"intent": "abort", "result": "no_pending"},
                "patch_draft": None,
            }
        self._session = self._session.abort_action()
        display = "操作已取消。"
        return {
            "display_message": display,
            "technical_action": {"intent": "abort", "result": "aborted"},
            "patch_draft": None,
        }


# ---------------------------------------------------------------------------
# SimpleOperatorAgent — concrete implementation with extended parsing
# ---------------------------------------------------------------------------

class SimpleOperatorAgent(OperatorAgent):
    """Concrete OperatorAgent with extended keyword matching.

    Adds support for:
      - Target extraction from task requests (e.g. "升级胡桃到90级")
      - Priority inference from adverbs ("尽快", "马上" → high priority)
      - Bilingual display messages
    """

    # Priority modifiers
    _PRIORITY_HIGH_CN = ("尽快", "马上", "立刻", "紧急", "赶紧")
    _PRIORITY_HIGH_EN = ("asap", "urgent", "immediately", "right now")
    _PRIORITY_LOW_CN = ("慢慢", "不急", "有空")
    _PRIORITY_LOW_EN = ("whenever", "no rush", "eventually")

    # Target extraction pattern: noun followed by task keyword
    _TARGET_PATTERNS: list[tuple[str, str]] = [
        (r"升级\s*(\S+)\s*到", "level_up_target"),
        (r"(?:把|将)\s*(\S+)\s*升级", "level_up_target"),
        (r"突破\s*(\S+)", "ascend_target"),
        (r"强化\s*(\S+)", "enhance_target"),
        (r"level\s+up\s+(\S+)", "level_up_target"),
        (r"ascend\s+(\S+)", "ascend_target"),
    ]

    def _infer_priority(self, text: str) -> int:
        """Infer task priority from text modifiers."""
        text_lower = text.lower()
        for marker in self._PRIORITY_HIGH_CN:
            if marker in text_lower:
                return 80
        for marker in self._PRIORITY_HIGH_EN:
            if marker in text_lower:
                return 80
        for marker in self._PRIORITY_LOW_CN:
            if marker in text_lower:
                return 20
        for marker in self._PRIORITY_LOW_EN:
            if marker in text_lower:
                return 20
        return 50

    def _extract_target(self, text: str) -> str:
        """Extract a target entity from the user text."""
        for pattern, _ in self._TARGET_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""

    def _handle_set_goal(self, message: str, cmd: OperatorCommand) -> dict[str, Any]:
        """Extended set_goal handler with target extraction and priority inference."""
        capability, confidence = _match_task_keyword(message)
        target = self._extract_target(message)
        priority = self._infer_priority(message)

        params: tuple[tuple[str, str], ...] = ()
        if target:
            params = (("target", target),)

        task = TaskSpec(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            objective=capability,
            execution_mode="dry_run",
            priority=priority,
        )
        self._session = self._session.start_task(task)

        parts = [f"已创建任务: {capability}"]
        if target:
            parts.append(f"目标: {target}")
        parts.append(f"优先级: {priority}")
        parts.append(f"(id={task.task_id})")

        return {
            "display_message": " | ".join(parts),
            "technical_action": {
                "intent": "set_goal",
                "task": task,
                "target": target,
                "command": cmd,
            },
            "patch_draft": None,
        }

    def handle_user_message(
        self,
        message: str,
        current_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle user message with extended bilingual support."""
        result = super().handle_user_message(message, current_context)
        # Add bilingual note for English messages
        if message.strip().isascii() and result["technical_action"].get("intent") != "unknown":
            original = result["display_message"]
            result["display_message"] = original  # keep the Chinese response
        return result
