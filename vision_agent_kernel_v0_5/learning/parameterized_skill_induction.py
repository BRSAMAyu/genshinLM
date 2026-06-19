"""Parameterized Skill Induction — extract variable parts from successful traces.

Gap #3: Induced skills are fixed step sequences with no parameters, conditions,
or loops. This module compares multiple successful traces of the "same" task and
extracts:
- Fixed parts → template steps (always the same)
- Variable parts → parameters (change per execution)
- Conditional branches → when certain steps differ based on context
- Repetition patterns → loops (e.g., "attack until enemy dead")

The result is a parameterized SkillTemplate that generalizes across similar tasks.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger(__name__)


# -- Parameter types --------------------------------------------------------

ParameterType = Literal[
    "target",       # What to act on (e.g., enemy name, NPC name)
    "position",     # Where to navigate (e.g., waypoint, coordinates)
    "count",        # How many times (e.g., number of items to buy)
    "selection",    # Which option (e.g., dialog choice index)
    "timing",       # Duration/delay (e.g., wait time in ms)
    "key_sequence", # Dynamic key sequence (e.g., combat combo)
    "team",         # Team composition (e.g., character list)
    "strategy",     # Approach variant (e.g., aggressive vs defensive)
]


@dataclass(frozen=True, slots=True)
class SkillParameter:
    """A parameter extracted from comparing multiple traces."""
    name: str
    param_type: ParameterType
    description: str
    default_value: str
    extracted_values: tuple[str, ...]
    variability_score: float  # 0=always same, 1=always different
    required: bool = True


@dataclass(frozen=True, slots=True)
class TemplateStep:
    """A step in a parameterized skill template."""
    step_id: str
    action_type: str  # click, key_press, wait, navigate, etc.
    target_template: str  # May contain {param_name} placeholders
    condition: str = ""  # When this step should execute (e.g., "{enemy_alive} == true")
    loop_condition: str = ""  # Loop until this is false (e.g., "{items_remaining} > 0")
    max_loop_iterations: int = 1  # Safety cap for loops
    timeout_ms: int = 1000
    delay_ms: int = 0
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillTemplate:
    """A parameterized skill template induced from multiple traces."""
    template_id: str
    name: str
    parameters: tuple[SkillParameter, ...]
    steps: tuple[TemplateStep, ...]
    source_trace_count: int  # How many traces contributed
    generalization_confidence: float  # How well the template covers all traces
    applicable_contexts: tuple[str, ...]  # e.g., ("combat", "boss_fight")
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.perf_counter())

    def instantiate(self, **kwargs: str) -> list[dict[str, Any]]:
        """Create concrete steps from template by filling parameters."""
        concrete: list[dict[str, Any]] = []
        for step in self.steps:
            target = step.target_template
            for param in self.parameters:
                placeholder = "{" + param.name + "}"
                if placeholder in target:
                    value = kwargs.get(param.name, param.default_value)
                    target = target.replace(placeholder, value)

            concrete.append({
                "step_id": step.step_id,
                "type": step.action_type,
                "target": target,
                "timeout_ms": step.timeout_ms,
                "delay_ms": step.delay_ms,
                "condition": step.condition,
                "loop": step.loop_condition != "",
                "loop_condition": step.loop_condition,
                "max_loop_iterations": step.max_loop_iterations,
                **step.params,
            })
        return concrete


# -- Trace comparison and parameter extraction -------------------------------

def _extract_step_signature(step: dict[str, Any]) -> str:
    """Create a normalized signature for a step to compare across traces."""
    action_type = step.get("type", step.get("action_type", "unknown"))
    # Normalize coordinates to "click_at_position" to abstract away specific pixels
    if action_type in ("click", "mouse_click"):
        return "click"
    if action_type in ("key_press", "key_tap"):
        key = step.get("params", {}).get("key", step.get("target", ""))
        return f"key:{key}"
    if action_type in ("wait",):
        return "wait"
    if action_type in ("navigate", "navigation"):
        return "navigate"
    return f"{action_type}"


def _compare_traces(traces: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Align and compare multiple traces to find common and variable parts.

    Uses a simple longest-common-subsequence approach to align steps across traces.
    """
    if not traces:
        return []

    # Use first trace as reference, align others to it
    reference = traces[0]
    aligned: list[dict[str, Any]] = []

    for ref_idx, ref_step in enumerate(reference):
        ref_sig = _extract_step_signature(ref_step)
        step_info: dict[str, Any] = {
            "ref_index": ref_idx,
            "action_type": ref_step.get("type", ref_step.get("action_type", "unknown")),
            "ref_target": ref_step.get("target", ref_step.get("params", {}).get("key", "")),
            "other_targets": [],
            "matches_all": True,
        }

        for other_trace in traces[1:]:
            # Find best matching step in other trace at approximately same position
            best_match = None
            best_score = 0.0

            # Prefer exact position match first
            if ref_idx < len(other_trace):
                other_step = other_trace[ref_idx]
                other_sig = _extract_step_signature(other_step)
                if other_sig == ref_sig:
                    best_match = other_step
                    best_score = 1.0

            # Fall back to nearby search if no exact match
            if best_match is None:
                search_start = max(0, ref_idx - 1)
                search_end = min(len(other_trace), ref_idx + 2)

                for o_idx in range(search_start, search_end):
                    other_step = other_trace[o_idx] if o_idx < len(other_trace) else {}
                    other_sig = _extract_step_signature(other_step)
                    if other_sig == ref_sig:
                        best_match = other_step
                        best_score = 0.8
                        break

            if best_match is not None:
                other_target = best_match.get("target", best_match.get("params", {}).get("key", ""))
                step_info["other_targets"].append(other_target)
            else:
                step_info["matches_all"] = False

        aligned.append(step_info)

    return aligned


def _compute_variability(values: list[str]) -> float:
    """Compute how variable a set of values is (0=all same, 1=all different)."""
    if not values:
        return 0.0
    unique = len(set(values))
    if unique == 1:
        return 0.0
    return (unique - 1) / (len(values) - 1) if len(values) > 1 else 0.0


class ParameterizedSkillInductor:
    """Induce parameterized skill templates from multiple successful traces.

    Algorithm:
    1. Collect N traces of the same task type
    2. Align steps across traces (LCS-based)
    3. For each aligned position:
       - If all traces have same target → fixed step
       - If targets vary → extract as parameter
    4. Detect repetition patterns (consecutive similar steps)
    5. Build SkillTemplate with parameters and conditional steps

    Usage:
        inductor = ParameterizedSkillInductor()
        template = inductor.induce("boss_fight", traces)
        concrete = template.instantiate(target="Stormterror", strategy="ranged")
    """

    def __init__(self, min_traces: int = 2) -> None:
        self._min_traces = min_traces
        self._templates: dict[str, SkillTemplate] = {}

    def induce(
        self,
        task_name: str,
        traces: list[list[dict[str, Any]]],
        contexts: tuple[str, ...] = (),
    ) -> SkillTemplate | None:
        """Induce a parameterized skill template from multiple traces.

        Args:
            task_name: Name of the task (e.g., "boss_fight", "npc_shop_buy")
            traces: List of successful execution traces
            contexts: Applicable contexts (e.g., ("combat", "boss_fight"))

        Returns:
            SkillTemplate or None if insufficient data
        """
        if len(traces) < self._min_traces:
            log.warning(
                "[ParamSkillInductor] Need at least %d traces, got %d for '%s'",
                self._min_traces, len(traces), task_name,
            )
            return None

        # 1. Align and compare traces
        aligned = _compare_traces(traces)

        # 2. Extract parameters from variable parts
        parameters: list[SkillParameter] = []
        steps: list[TemplateStep] = []

        for info in aligned:
            ref_target = info["ref_target"]
            all_targets = [ref_target] + info["other_targets"]
            variability = _compute_variability(all_targets)

            action_type = info["action_type"]

            if variability > 0.3 and info["matches_all"]:
                # Variable part → parameter
                param_name = f"param_{len(parameters)}"
                param_type = self._infer_parameter_type(action_type, all_targets)
                parameters.append(SkillParameter(
                    name=param_name,
                    param_type=param_type,
                    description=f"Variable {action_type} target",
                    default_value=ref_target,
                    extracted_values=tuple(all_targets),
                    variability_score=variability,
                ))
                target_template = "{" + param_name + "}"
            else:
                # Fixed part → literal
                target_template = ref_target

            # Check for repetition patterns (3+ consecutive similar steps)
            loop_condition = ""
            max_loop = 1
            step_idx = info["ref_index"]
            if step_idx >= 2:
                prev1 = aligned[step_idx - 1] if step_idx - 1 < len(aligned) else {}
                prev2 = aligned[step_idx - 2] if step_idx - 2 < len(aligned) else {}
                if (prev1.get("action_type") == action_type and
                        prev2.get("action_type") == action_type):
                    loop_condition = "{target_alive} == true"
                    max_loop = 30  # Safety cap

            steps.append(TemplateStep(
                step_id=f"step_{len(steps) + 1}",
                action_type=action_type,
                target_template=target_template,
                loop_condition=loop_condition,
                max_loop_iterations=max_loop,
                timeout_ms=1000,
                delay_ms=100,
            ))

        # 3. Compute generalization confidence
        if aligned:
            match_rate = sum(1 for a in aligned if a["matches_all"]) / len(aligned)
        else:
            match_rate = 0.0

        confidence = match_rate * 0.7 + min(1.0, len(traces) / 5.0) * 0.3

        template = SkillTemplate(
            template_id=f"tpl_{uuid.uuid4().hex[:8]}",
            name=f"Parameterized {task_name}",
            parameters=tuple(parameters),
            steps=tuple(steps),
            source_trace_count=len(traces),
            generalization_confidence=round(confidence, 3),
            applicable_contexts=contexts or (task_name,),
        )

        self._templates[template.template_id] = template

        log.info(
            "[ParamSkillInductor] Induced template '%s' from %d traces: %d params, %d steps, confidence=%.2f",
            template.name, len(traces), len(parameters), len(steps), confidence,
        )

        return template

    def induce_from_patterns(
        self,
        target: str,
        failure_mode: str,
        successful_plans: list[list[dict[str, Any]]],
    ) -> SkillTemplate | None:
        """Bridge entry point for MetaLearningBridge.

        Converts pattern-based induction request into trace-based induction.
        Each successful plan becomes a trace; target+failure_mode form the
        task name and context.
        """
        if not successful_plans:
            return None

        task_name = f"{target}_{failure_mode}"
        contexts = (target, failure_mode)

        return self.induce(
            task_name=task_name,
            traces=successful_plans,
            contexts=contexts,
        )

    def get_template(self, template_id: str) -> SkillTemplate | None:
        return self._templates.get(template_id)

    def list_templates(self) -> list[SkillTemplate]:
        return list(self._templates.values())

    @staticmethod
    def _infer_parameter_type(action_type: str, values: list[str]) -> ParameterType:
        """Infer parameter type from action type and observed values."""
        if action_type in ("click", "mouse_click"):
            return "selection"
        if action_type in ("key_press", "key_tap"):
            return "key_sequence"
        if action_type in ("navigate", "navigation"):
            return "position"
        if action_type in ("wait",):
            return "timing"
        return "target"
