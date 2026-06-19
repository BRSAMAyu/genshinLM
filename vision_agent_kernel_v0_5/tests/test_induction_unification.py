"""Tests for unified induction output types (learning/skill_induction/types.py).

Verifies that all three induction systems can produce a consistent
``InductionOutput`` and that adapter functions preserve key invariants.
"""
from __future__ import annotations

import pytest

from learning.parameterized_skill_induction import (
    SkillParameter,
    SkillTemplate,
    TemplateStep,
)
from learning.skill_induction.types import (
    InductionOutput,
    from_catalog_entry,
    from_skill_def,
    from_skill_template,
)
from planning.skill_capability_catalog import SkillCatalogEntry
from skills.schema import SkillDef, SkillStep


# ---------------------------------------------------------------------------
# Helpers — lightweight factories
# ---------------------------------------------------------------------------

def _make_skill_def(
    skill_id: str = "test_skill",
    kind: str = "procedure",
    tier: str = "draft",
    steps: tuple[SkillStep, ...] = (),
) -> SkillDef:
    return SkillDef(skill_id=skill_id, kind=kind, tier=tier, steps=steps)


def _make_catalog_entry(
    skill_id: str = "induced_test_abc",
    kind: str = "ui",
    capabilities: list[str] | None = None,
    verifiers: list[str] | None = None,
) -> SkillCatalogEntry:
    return SkillCatalogEntry(
        skill_id=skill_id,
        capsule_id="core",
        source="induced_skill",
        kind=kind,
        capabilities=capabilities or ["open_menu"],
        verifiers=verifiers or ["anchor_post_click"],
    )


def _make_template(
    template_id: str = "tpl_deadbeef",
    name: str = "Parameterized test_task",
    params: tuple[SkillParameter, ...] = (),
    steps: tuple[TemplateStep, ...] = (),
    confidence: float = 0.85,
) -> SkillTemplate:
    return SkillTemplate(
        template_id=template_id,
        name=name,
        parameters=params,
        steps=steps,
        source_trace_count=3,
        generalization_confidence=confidence,
        applicable_contexts=("test",),
    )


# ---------------------------------------------------------------------------
# Test 1: InductionPipeline → InductionOutput
# ---------------------------------------------------------------------------

class TestFromSkillDef:
    def test_basic_conversion(self) -> None:
        steps = (
            SkillStep(action="click_anchor", target="btn_ok"),
            SkillStep(action="press_key", target="Enter"),
        )
        sd = _make_skill_def(steps=steps)
        out = from_skill_def(sd)

        assert isinstance(out, InductionOutput)
        assert out.skill_id == "test_skill"
        assert out.action == "procedure"
        assert len(out.steps) == 2
        assert out.steps[0]["action"] == "click_anchor"
        assert out.source == "pipeline"

    def test_confidence_maps_to_tier(self) -> None:
        trusted = _make_skill_def(tier="trusted")
        raw = _make_skill_def(tier="raw_trace")

        out_trusted = from_skill_def(trusted)
        out_raw = from_skill_def(raw)

        assert out_trusted.confidence > out_raw.confidence
        assert out_trusted.source == "pipeline"

    def test_empty_steps_produces_empty_tuple(self) -> None:
        sd = _make_skill_def(steps=())
        out = from_skill_def(sd)
        assert out.steps == ()


# ---------------------------------------------------------------------------
# Test 2: SkillInductionGate → InductionOutput
# ---------------------------------------------------------------------------

class TestFromCatalogEntry:
    def test_basic_conversion(self) -> None:
        entry = _make_catalog_entry()
        out = from_catalog_entry(entry)

        assert isinstance(out, InductionOutput)
        assert out.skill_id == "induced_test_abc"
        assert out.action == "open_menu"  # first capability
        assert out.source == "gate"
        assert out.confidence == 1.0

    def test_verifiers_become_steps(self) -> None:
        entry = _make_catalog_entry(verifiers=["v1", "v2"])
        out = from_catalog_entry(entry)
        assert len(out.steps) == 2
        assert out.steps[0]["verify"] == "v1"

    def test_parameters_always_empty(self) -> None:
        entry = _make_catalog_entry()
        out = from_catalog_entry(entry)
        assert out.parameters == ()


# ---------------------------------------------------------------------------
# Test 3: ParameterizedSkillInduction → InductionOutput
# ---------------------------------------------------------------------------

class TestFromSkillTemplate:
    def test_basic_conversion(self) -> None:
        params = (
            SkillParameter(
                name="target_enemy",
                param_type="target",
                description="enemy to fight",
                default_value="Slime",
                extracted_values=("Slime", "Hilichurl"),
                variability_score=0.5,
            ),
        )
        steps = (
            TemplateStep(
                step_id="step_1",
                action_type="navigate",
                target_template="{target_enemy}",
            ),
        )
        tpl = _make_template(params=params, steps=steps, confidence=0.9)
        out = from_skill_template(tpl)

        assert isinstance(out, InductionOutput)
        assert out.skill_id == "tpl_deadbeef"
        assert out.source == "parameterized"
        assert out.confidence == 0.9

    def test_parameters_extracted(self) -> None:
        params = (
            SkillParameter(
                name="p_a",
                param_type="selection",
                description="a",
                default_value="",
                extracted_values=("x", "y"),
                variability_score=0.8,
            ),
            SkillParameter(
                name="p_b",
                param_type="timing",
                description="b",
                default_value="100",
                extracted_values=("100", "200"),
                variability_score=0.5,
            ),
        )
        tpl = _make_template(params=params)
        out = from_skill_template(tpl)

        assert out.parameters == ("p_a", "p_b")

    def test_steps_contain_target_template(self) -> None:
        steps = (
            TemplateStep(
                step_id="s1",
                action_type="click",
                target_template="{target}",
                condition="visible",
                loop_condition="{alive}",
            ),
        )
        tpl = _make_template(steps=steps)
        out = from_skill_template(tpl)

        assert len(out.steps) == 1
        assert out.steps[0]["target_template"] == "{target}"
        assert out.steps[0]["condition"] == "visible"
        assert out.steps[0]["loop_condition"] == "{alive}"


# ---------------------------------------------------------------------------
# Test 4: Cross-system invariants
# ---------------------------------------------------------------------------

class TestCrossSystemInvariants:
    def test_all_outputs_share_same_type(self) -> None:
        outputs = [
            from_skill_def(_make_skill_def()),
            from_catalog_entry(_make_catalog_entry()),
            from_skill_template(_make_template()),
        ]
        for o in outputs:
            assert type(o) is InductionOutput
            assert isinstance(o.steps, tuple)
            assert isinstance(o.parameters, tuple)
            assert isinstance(o.confidence, float)
            assert o.source in ("pipeline", "gate", "parameterized")

    def test_source_field_distinguishes_systems(self) -> None:
        assert from_skill_def(_make_skill_def()).source == "pipeline"
        assert from_catalog_entry(_make_catalog_entry()).source == "gate"
        assert from_skill_template(_make_template()).source == "parameterized"

    def test_pipeline_output_has_no_parameters(self) -> None:
        out = from_skill_def(_make_skill_def())
        assert out.parameters == ()

    def test_gate_output_has_no_parameters(self) -> None:
        out = from_catalog_entry(_make_catalog_entry())
        assert out.parameters == ()

    def test_parameterized_output_has_parameters(self) -> None:
        params = (
            SkillParameter(
                name="target",
                param_type="target",
                description="d",
                default_value="x",
                extracted_values=("x", "y"),
                variability_score=0.6,
            ),
        )
        out = from_skill_template(_make_template(params=params))
        assert len(out.parameters) > 0
