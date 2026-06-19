"""Unified induction output types — thin adapter layer over three induction systems.

Three independent induction pipelines coexist in the project:

1. ``InductionPipeline`` (learning/skill_induction/pipeline.py)
   → outputs ``SkillDef`` (skills/schema.py)

2. ``SkillInductionGate`` (learning/skill_induction_gate.py)
   → outputs ``SkillCatalogEntry`` (planning/skill_capability_catalog.py)

3. ``ParameterizedSkillInductor`` (learning/parameterized_skill_induction.py)
   → outputs ``SkillTemplate`` (learning/parameterized_skill_induction.py)

Each has a distinct native type, but downstream consumers (planner, telemetry,
checkpoint) benefit from a single, flat representation.  ``InductionOutput`` is
that representation — a frozen dataclass carrying the subset of fields that all
three systems can populate.

Adapter functions are provided for each native type and live as plain module
functions so that they can be used without touching the original classes.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Unified output type
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class InductionOutput:
    """Common denominator produced by every induction system.

    Fields:
        skill_id:     Unique identifier for the induced skill/template.
        action:       Top-level action category (e.g. "procedure", "ui",
                      the template name, or the first capability).
        steps:        Ordered sequence of step dicts.  Each dict is a
                      lightweight serialisation of the native step type.
        parameters:   Named parameters that the skill accepts.  Empty for
                      non-parameterised induction (pipeline / gate).
        confidence:   0.0 – 1.0 confidence score.  When the source system
                      does not produce one, defaults to 1.0.
        source:       Which system produced this output — one of
                      ``"pipeline"``, ``"gate"``, or ``"parameterized"``.
    """

    skill_id: str
    action: str
    steps: tuple[dict, ...]
    parameters: tuple[str, ...]
    confidence: float
    source: str


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

def from_skill_def(skill_def: object) -> InductionOutput:
    """Adapt a ``SkillDef`` (from ``InductionPipeline``) to ``InductionOutput``."""
    # SkillDef is a frozen dataclass — access attributes directly.
    steps: tuple[dict, ...] = ()
    raw_steps = getattr(skill_def, "steps", ())
    if raw_steps:
        steps = tuple(
            {
                "action": getattr(s, "action", ""),
                "target": getattr(s, "target", ""),
                "wait_until": getattr(s, "wait_until", ""),
                "timeout_ms": getattr(s, "timeout_ms", 0),
            }
            for s in raw_steps
        )

    tier = getattr(skill_def, "tier", "draft")
    # Higher tier → higher confidence heuristic
    tier_confidence = {
        "raw_trace": 0.2,
        "draft": 0.4,
        "experimental": 0.6,
        "candidate": 0.8,
        "stable": 0.9,
        "trusted": 0.95,
    }.get(tier, 0.5)

    return InductionOutput(
        skill_id=getattr(skill_def, "skill_id", ""),
        action=getattr(skill_def, "kind", "procedure"),
        steps=steps,
        parameters=(),
        confidence=tier_confidence,
        source="pipeline",
    )


def from_catalog_entry(entry: object) -> InductionOutput:
    """Adapt a ``SkillCatalogEntry`` (from ``SkillInductionGate``) to ``InductionOutput``."""
    capabilities = getattr(entry, "capabilities", [])
    action = capabilities[0] if capabilities else getattr(entry, "kind", "ui")

    # Catalog entries don't carry step sequences — synthesise a single
    # placeholder step so the tuple is never empty when there is semantic
    # content to represent.
    verifiers = getattr(entry, "verifiers", [])
    steps: tuple[dict, ...] = ()
    if verifiers:
        steps = tuple({"verify": v} for v in verifiers)

    return InductionOutput(
        skill_id=getattr(entry, "skill_id", ""),
        action=action,
        steps=steps,
        parameters=(),
        confidence=1.0,
        source="gate",
    )


def from_skill_template(template: object) -> InductionOutput:
    """Adapt a ``SkillTemplate`` (from ``ParameterizedSkillInductor``) to ``InductionOutput``."""
    raw_params = getattr(template, "parameters", ())
    param_names = tuple(p.name for p in raw_params) if raw_params else ()

    raw_steps = getattr(template, "steps", ())
    steps: tuple[dict, ...] = ()
    if raw_steps:
        steps = tuple(
            {
                "step_id": getattr(s, "step_id", ""),
                "action_type": getattr(s, "action_type", ""),
                "target_template": getattr(s, "target_template", ""),
                "condition": getattr(s, "condition", ""),
                "loop_condition": getattr(s, "loop_condition", ""),
            }
            for s in raw_steps
        )

    return InductionOutput(
        skill_id=getattr(template, "template_id", ""),
        action=getattr(template, "name", ""),
        steps=steps,
        parameters=param_names,
        confidence=getattr(template, "generalization_confidence", 0.0),
        source="parameterized",
    )
