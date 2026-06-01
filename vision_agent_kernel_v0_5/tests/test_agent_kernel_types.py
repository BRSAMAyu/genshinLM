"""Tests for agent_kernel.types — all new Kernel contract types.

Validates instantiation, frozen/slots behaviour, and game-agnostic purity.
"""
from __future__ import annotations

import importlib
import time
from dataclasses import FrozenInstanceError

import pytest

from agent_kernel.types import (
    Affordance,
    CapsulePatchProposal,
    ClaimEvidence,
    OperatorCommand,
    RuntimeOverride,
    SceneGraph,
    SceneObject,
    SkillRecipe,
    SkillStep,
    StateDeltaClaim,
    TaskSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.perf_counter()


# ---------------------------------------------------------------------------
# SceneObject
# ---------------------------------------------------------------------------

class TestSceneObject:

    def test_basic_instantiation(self) -> None:
        obj = SceneObject(
            object_id="npc_001",
            kind="npc",
            label="Katheryne",
            bbox_norm=(0.1, 0.2, 0.3, 0.4),
        )
        assert obj.object_id == "npc_001"
        assert obj.kind == "npc"
        assert obj.confidence == 0.0
        assert obj.source == "unknown"
        assert obj.spatial_hint == ""

    def test_frozen(self) -> None:
        obj = SceneObject(object_id="e1", kind="enemy", label="Slime", bbox_norm=None)
        with pytest.raises(FrozenInstanceError):
            obj.label = "Hilichurl"  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        obj = SceneObject(object_id="b1", kind="button", label="OK", bbox_norm=None)
        assert not hasattr(obj, "__dict__")

    def test_optional_bbox_none(self) -> None:
        obj = SceneObject(object_id="w1", kind="waypoint", label="TP", bbox_norm=None)
        assert obj.bbox_norm is None


# ---------------------------------------------------------------------------
# Affordance
# ---------------------------------------------------------------------------

class TestAffordance:

    def test_basic_instantiation(self) -> None:
        aff = Affordance(
            affordance_id="aff_01",
            verb="talk",
            target_object_id="npc_001",
        )
        assert aff.verb == "talk"
        assert aff.risk_level == "low"
        assert aff.preconditions == ()

    def test_frozen(self) -> None:
        aff = Affordance(affordance_id="a", verb="attack", target_object_id="e1")
        with pytest.raises(FrozenInstanceError):
            aff.verb = "flee"  # type: ignore[misc]

    def test_with_preconditions(self) -> None:
        aff = Affordance(
            affordance_id="aff_02",
            verb="open",
            target_object_id="door_01",
            preconditions=("has_key", "near_door"),
            risk_level="medium",
        )
        assert len(aff.preconditions) == 2
        assert aff.risk_level == "medium"


# ---------------------------------------------------------------------------
# SceneGraph
# ---------------------------------------------------------------------------

class TestSceneGraph:

    def test_basic_instantiation(self) -> None:
        sg = SceneGraph(timestamp=_now(), scene_state="world_hud")
        assert sg.scene_state == "world_hud"
        assert sg.objects == ()
        assert sg.affordances == ()
        assert sg.frame_id == 0

    def test_with_objects_and_affordances(self) -> None:
        obj = SceneObject(object_id="b1", kind="button", label="Map", bbox_norm=(0.0, 0.0, 0.1, 0.1))
        aff = Affordance(affordance_id="a1", verb="select", target_object_id="b1")
        sg = SceneGraph(
            timestamp=_now(),
            scene_state="menu",
            objects=(obj,),
            affordances=(aff,),
            frame_id=42,
            confidence=0.95,
        )
        assert len(sg.objects) == 1
        assert len(sg.affordances) == 1
        assert sg.confidence == 0.95

    def test_frozen(self) -> None:
        sg = SceneGraph(timestamp=0.0, scene_state="x")
        with pytest.raises(FrozenInstanceError):
            sg.scene_state = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SkillStep
# ---------------------------------------------------------------------------

class TestSkillStep:

    def test_basic_instantiation(self) -> None:
        step = SkillStep(step_id="s1", intent="navigate", target_query="teleport waypoint")
        assert step.locator_policy == "affordance_then_vlm"
        assert step.retry_policy == "resample_relocate_replan"

    def test_frozen(self) -> None:
        step = SkillStep(step_id="s1", intent="click", target_query="OK button")
        with pytest.raises(FrozenInstanceError):
            step.intent = "scroll"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SkillRecipe
# ---------------------------------------------------------------------------

class TestSkillRecipe:

    def test_basic_instantiation(self) -> None:
        recipe = SkillRecipe(
            skill_id="skill_teleport",
            title="Teleport to waypoint",
            goal_template="arrive at {waypoint_name}",
        )
        assert recipe.version == "1.0"
        assert recipe.risk_level == "low"
        assert recipe.steps == ()

    def test_with_steps(self) -> None:
        s1 = SkillStep(step_id="s1", intent="open_map", target_query="map button")
        s2 = SkillStep(step_id="s2", intent="select_waypoint", target_query="target waypoint icon")
        recipe = SkillRecipe(
            skill_id="skill_tp",
            title="TP",
            goal_template="arrive",
            steps=(s1, s2),
            verifiers=("check_coordinates",),
        )
        assert len(recipe.steps) == 2
        assert recipe.verifiers[0] == "check_coordinates"

    def test_frozen(self) -> None:
        recipe = SkillRecipe(skill_id="x", title="y", goal_template="z")
        with pytest.raises(FrozenInstanceError):
            recipe.title = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TaskSpec
# ---------------------------------------------------------------------------

class TestTaskSpec:

    def test_basic_instantiation(self) -> None:
        ts = TaskSpec(task_id="t1", objective="mainline_progress")
        assert ts.execution_mode == "dry_run"
        assert ts.priority == 50
        assert ts.parent_task_id == ""

    def test_custom_policies(self) -> None:
        ts = TaskSpec(
            task_id="t2",
            objective="character_level_up",
            dialog_policy="skip_all",
            resource_policy="no_rare_consumables",
            uncertainty_policy="ask_user_after_120s",
            execution_mode="safe_window",
            priority=80,
        )
        assert ts.dialog_policy == "skip_all"
        assert ts.priority == 80

    def test_frozen(self) -> None:
        ts = TaskSpec(task_id="t1", objective="x")
        with pytest.raises(FrozenInstanceError):
            ts.objective = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RuntimeOverride
# ---------------------------------------------------------------------------

class TestRuntimeOverride:

    def test_basic_instantiation(self) -> None:
        ro = RuntimeOverride(
            override_id="ro1",
            target_parameter="max_retry",
            new_value="5",
        )
        assert ro.source == "user"
        assert ro.scope == "session"
        assert ro.confidence == 1.0

    def test_frozen(self) -> None:
        ro = RuntimeOverride(override_id="ro1", target_parameter="x", new_value="y")
        with pytest.raises(FrozenInstanceError):
            ro.new_value = "10"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CapsulePatchProposal
# ---------------------------------------------------------------------------

class TestCapsulePatchProposal:

    def test_basic_instantiation(self) -> None:
        cpp = CapsulePatchProposal(
            proposal_id="p1",
            capsule_id="capsule_teleport",
            yaml_path="skills/teleport.yaml",
        )
        assert cpp.patch_data == ()
        assert cpp.verified is False
        assert cpp.user_confirmed is False

    def test_with_patch_data(self) -> None:
        cpp = CapsulePatchProposal(
            proposal_id="p2",
            capsule_id="c1",
            yaml_path="s.yaml",
            patch_data=(("steps[0].intent", "open_menu"), ("version", "1.1")),
            reason="fix step ordering",
            verified=True,
        )
        assert len(cpp.patch_data) == 2
        assert cpp.verified is True

    def test_frozen(self) -> None:
        cpp = CapsulePatchProposal(proposal_id="p", capsule_id="c", yaml_path="y")
        with pytest.raises(FrozenInstanceError):
            cpp.reason = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# OperatorCommand
# ---------------------------------------------------------------------------

class TestOperatorCommand:

    def test_basic_instantiation(self) -> None:
        oc = OperatorCommand(
            command_id="cmd1",
            user_text="teleport to Mondstadt",
            parsed_intent="set_goal",
        )
        assert oc.parameters == ()
        assert oc.confidence == 0.0

    def test_with_parameters(self) -> None:
        oc = OperatorCommand(
            command_id="cmd2",
            user_text="change retry to 10",
            parsed_intent="adjust_policy",
            parameters=(("key", "max_retry"), ("value", "10")),
            confidence=0.92,
        )
        assert len(oc.parameters) == 2
        assert oc.confidence > 0.9

    def test_frozen(self) -> None:
        oc = OperatorCommand(command_id="c", user_text="t", parsed_intent="abort")
        with pytest.raises(FrozenInstanceError):
            oc.parsed_intent = "confirm"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ClaimEvidence
# ---------------------------------------------------------------------------

class TestClaimEvidence:

    def test_basic_instantiation(self) -> None:
        ce = ClaimEvidence(
            claim_id="ce1",
            evidence_type="ocr_text",
            value="Level 90",
        )
        assert ce.confidence == 0.0
        assert ce.source == ""
        assert ce.timestamp == 0.0

    def test_frozen(self) -> None:
        ce = ClaimEvidence(claim_id="ce1", evidence_type="screenshot_hash", value="abc123")
        with pytest.raises(FrozenInstanceError):
            ce.value = "xyz"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StateDeltaClaim
# ---------------------------------------------------------------------------

class TestStateDeltaClaim:

    def test_basic_instantiation(self) -> None:
        sdc = StateDeltaClaim(
            claim_id="sdc1",
            expected_state="dialog_visible",
            observed_state="dialog_visible",
        )
        assert sdc.verified is False
        assert sdc.evidence == ()

    def test_with_evidence(self) -> None:
        ev = ClaimEvidence(
            claim_id="e1",
            evidence_type="vlm_description",
            value="Dialog box with Katheryne visible",
            confidence=0.95,
        )
        sdc = StateDeltaClaim(
            claim_id="sdc2",
            expected_state="dialog_visible",
            observed_state="dialog_visible",
            evidence=(ev,),
            verified=True,
            confidence=0.95,
            timestamp=_now(),
        )
        assert len(sdc.evidence) == 1
        assert sdc.verified is True
        assert sdc.confidence > 0.9

    def test_frozen(self) -> None:
        sdc = StateDeltaClaim(claim_id="s", expected_state="a", observed_state="b")
        with pytest.raises(FrozenInstanceError):
            sdc.verified = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# No game-specific imports
# ---------------------------------------------------------------------------

class TestNoGameSpecificImports:

    def test_types_module_has_no_game_imports(self) -> None:
        """Verify agent_kernel.types imports nothing from game modules."""
        mod = importlib.import_module("agent_kernel.types")
        source = importlib.util.find_spec("agent_kernel.types")
        assert source is not None
        # Read the source and check for game-specific import patterns
        import inspect
        src = inspect.getsource(mod)
        forbidden = [
            "from genshin",
            "import genshin",
            "from perception.genshin",
            "from planning.genshin",
            "from combat",
            "from navigation",
        ]
        for pattern in forbidden:
            assert pattern not in src, f"Found forbidden import pattern: {pattern}"

    def test_all_new_types_importable_from_package(self) -> None:
        """All new types are re-exported from agent_kernel.__init__."""
        import agent_kernel
        for name in [
            "SceneObject", "Affordance", "SceneGraph",
            "SkillStep", "SkillRecipe",
            "TaskSpec",
            "RuntimeOverride", "CapsulePatchProposal",
            "OperatorCommand",
            "ClaimEvidence", "StateDeltaClaim",
        ]:
            assert hasattr(agent_kernel, name), f"{name} not exported from agent_kernel"


# ---------------------------------------------------------------------------
# Slots presence on all types
# ---------------------------------------------------------------------------

class TestSlotsPresent:

    @pytest.mark.parametrize("cls", [
        SceneObject, Affordance, SceneGraph,
        SkillStep, SkillRecipe,
        TaskSpec,
        RuntimeOverride, CapsulePatchProposal,
        OperatorCommand,
        ClaimEvidence, StateDeltaClaim,
    ])
    def test_has_slots(self, cls: type) -> None:
        assert hasattr(cls, "__slots__"), f"{cls.__name__} missing __slots__"
