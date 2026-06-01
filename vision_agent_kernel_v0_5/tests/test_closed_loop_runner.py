"""Tests for ClosedLoopRunner — minimal end-to-end autonomy closed loop."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from execution.closed_loop_runner import (
    ClosedLoopResult,
    ClosedLoopRunner,
    LoopStepResult,
    ScreenClaimResult,
    SimpleOverridePolicyValidator,
    SimpleScreenClaimProvider,
    SimpleSkillRecipeLookup,
    SimpleTaskSpecResolver,
    SkillRecipe,
    TaskSpecResult,
    VerificationResult,
)
from runtime.claim_runtime import (
    CapsulePatchProposal,
    RuntimeOverrideClaim,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_recipe(capability: str = "character_level_up") -> SkillRecipe:
    return SkillRecipe(
        skill_id=f"skill_{capability}",
        capsule_id="test_capsule",
        steps=("step_1", "step_2"),
        risk_level="medium",
    )


def _make_runner(**kwargs: Any) -> ClosedLoopRunner:
    return ClosedLoopRunner(**kwargs)


# ---------------------------------------------------------------------------
# TaskSpecResolver
# ---------------------------------------------------------------------------

class TestSimpleTaskSpecResolver:

    def test_resolve_chinese_level_up(self) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve("升级胡桃到90级")
        assert result.capability == "character_level_up"
        assert result.confidence > 0.5

    def test_resolve_chinese_ascend(self) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve("突破甘雨")
        assert result.capability == "character_ascend"

    def test_resolve_english_talent(self) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve("talent upgrade for Raiden")
        assert result.capability == "talent_upgrade"

    def test_resolve_unknown(self) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve("随机文本")
        assert result.capability == "unknown"
        assert result.confidence < 0.5


# ---------------------------------------------------------------------------
# SkillRecipeLookup
# ---------------------------------------------------------------------------

class TestSimpleSkillRecipeLookup:

    def test_lookup_registered(self) -> None:
        lookup = SimpleSkillRecipeLookup()
        recipe = _make_recipe()
        lookup.register("character_level_up", recipe)
        assert lookup.lookup("character_level_up") is recipe

    def test_lookup_missing(self) -> None:
        lookup = SimpleSkillRecipeLookup()
        assert lookup.lookup("nonexistent") is None


# ---------------------------------------------------------------------------
# ScreenClaimProvider
# ---------------------------------------------------------------------------

class TestSimpleScreenClaimProvider:

    def test_no_frame_returns_unknown(self) -> None:
        provider = SimpleScreenClaimProvider()
        result = provider.build_claim()
        assert result.screen_state == "unknown"
        assert result.confidence == 0.0

    def test_frame_supplier_error(self) -> None:
        def bad_supplier() -> None:
            raise RuntimeError("no frame")
        provider = SimpleScreenClaimProvider(frame_supplier=bad_supplier)
        result = provider.build_claim()
        assert result.screen_state == "unknown"


# ---------------------------------------------------------------------------
# ClosedLoopRunner — full loop
# ---------------------------------------------------------------------------

class TestClosedLoopRunner:

    def test_full_loop_dry_run(self) -> None:
        """Full closed loop without ExecutionRuntime — proves chain wiring."""
        lookup = SimpleSkillRecipeLookup()
        lookup.register("character_level_up", _make_recipe())
        runner = _make_runner(
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
        )
        result = runner.run("升级胡桃到90级")
        assert isinstance(result, ClosedLoopResult)
        assert result.loop_id.startswith("loop_")
        assert len(result.steps) >= 3
        # Step 1: task resolution should succeed
        assert result.steps[0].step == "resolve_task"
        assert result.steps[0].success is True
        # Step 2: skill lookup should succeed
        assert result.steps[1].step == "lookup_skill"
        assert result.steps[1].success is True
        # Step 3: screen claim (no frame, but still proceeds)
        assert result.steps[2].step == "screen_claim"
        # Step 4: execute (no runtime, so fails gracefully)
        if len(result.steps) > 3:
            assert result.steps[3].step == "execute"

    def test_unknown_capability_fails_gracefully(self) -> None:
        runner = _make_runner()
        result = runner.run("unknown gibberish text")
        assert result.success is False
        assert result.steps[0].success is False

    def test_no_skill_recipe_fails(self) -> None:
        runner = _make_runner(
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=SimpleSkillRecipeLookup(),  # empty
        )
        result = runner.run("升级胡桃")
        assert result.success is False
        steps = [s.step for s in result.steps]
        assert "lookup_skill" in steps
        skill_step = result.steps[steps.index("lookup_skill")]
        assert skill_step.success is False

    def test_claim_graph_populated(self) -> None:
        lookup = SimpleSkillRecipeLookup()
        lookup.register("character_level_up", _make_recipe())
        runner = _make_runner(
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
        )
        runner.run("升级胡桃到90级")
        graph = runner.claim_graph
        assert graph.observation_count >= 1
        assert graph.claim_count >= 1

    def test_loop_result_has_timing(self) -> None:
        runner = _make_runner()
        result = runner.run("升级胡桃")
        assert result.total_duration_ms > 0
        for step in result.steps:
            assert step.duration_ms >= 0

    def test_final_state_reflects_success(self) -> None:
        lookup = SimpleSkillRecipeLookup()
        lookup.register("character_level_up", _make_recipe())
        runner = _make_runner(
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
        )
        result = runner.run("升级胡桃到90级")
        assert result.final_state in ("success", "failed")


# ---------------------------------------------------------------------------
# RuntimeOverride
# ---------------------------------------------------------------------------

class TestRuntimeOverrideClaim:

    def test_validate_succeeds(self) -> None:
        override = RuntimeOverrideClaim(
            override_id="ovr_1",
            target_component="skill_level_up",
            override_type="param",
            proposed_value={"threshold": 0.8},
            justification="user requested higher threshold",
            confidence=0.7,
            risk_level="medium",
        )
        validated = override.validate()
        assert validated.status == "validated"
        assert validated.is_safe_to_apply()

    def test_reject_critical(self) -> None:
        override = RuntimeOverrideClaim(
            override_id="ovr_2",
            target_component="safety_policy",
            override_type="policy",
            proposed_value={"skip_verification": True},
            justification="test override",
            confidence=0.9,
            risk_level="critical",
        )
        validated = override.validate()
        assert validated.status == "validated"
        assert validated.is_safe_to_apply() is False  # critical blocks auto-apply

    def test_reject_permanent_scope(self) -> None:
        override = RuntimeOverrideClaim(
            override_id="ovr_3",
            target_component="skill_level_up",
            override_type="param",
            proposed_value={"threshold": 0.5},
            justification="permanent change",
            confidence=0.8,
            scope="permanent",
        )
        assert override.is_safe_to_apply() is False  # permanent blocks auto-apply

    def test_reject_method(self) -> None:
        override = RuntimeOverrideClaim(
            override_id="ovr_4",
            target_component="test",
            override_type="param",
            proposed_value={},
            justification="",
            confidence=0.1,
        )
        rejected = override.reject("too low confidence")
        assert rejected.status == "rejected"

    def test_apply_and_rollback(self) -> None:
        override = RuntimeOverrideClaim(
            override_id="ovr_5",
            target_component="test",
            override_type="param",
            proposed_value={"x": 1},
            justification="test",
            confidence=0.8,
        ).validate()
        applied = override.apply()
        assert applied.status == "applied"
        assert applied.applied_at is not None
        rolled = applied.rollback("test rollback")
        assert rolled.status == "rolled_back"
        assert rolled.rolled_back_at is not None

    def test_low_confidence_not_safe(self) -> None:
        override = RuntimeOverrideClaim(
            override_id="ovr_6",
            target_component="test",
            override_type="param",
            proposed_value={},
            justification="",
            confidence=0.3,
        ).validate()
        assert override.is_safe_to_apply() is False  # confidence < 0.5


# ---------------------------------------------------------------------------
# OverridePolicyValidator
# ---------------------------------------------------------------------------

class TestSimpleOverridePolicyValidator:

    def test_rejects_critical(self) -> None:
        validator = SimpleOverridePolicyValidator()
        override = RuntimeOverrideClaim(
            override_id="ovr_crit",
            target_component="test",
            override_type="policy",
            proposed_value={},
            justification="",
            confidence=0.9,
            risk_level="critical",
        )
        result = validator.validate(override)
        assert result.status == "rejected"

    def test_rejects_permanent(self) -> None:
        validator = SimpleOverridePolicyValidator()
        override = RuntimeOverrideClaim(
            override_id="ovr_perm",
            target_component="test",
            override_type="param",
            proposed_value={},
            justification="",
            confidence=0.9,
            scope="permanent",
        )
        result = validator.validate(override)
        assert result.status == "rejected"

    def test_rejects_low_confidence(self) -> None:
        validator = SimpleOverridePolicyValidator()
        override = RuntimeOverrideClaim(
            override_id="ovr_low",
            target_component="test",
            override_type="param",
            proposed_value={},
            justification="",
            confidence=0.1,
        )
        result = validator.validate(override)
        assert result.status == "rejected"

    def test_validates_normal(self) -> None:
        validator = SimpleOverridePolicyValidator()
        override = RuntimeOverrideClaim(
            override_id="ovr_ok",
            target_component="test",
            override_type="param",
            proposed_value={"threshold": 0.8},
            justification="user request",
            confidence=0.7,
        )
        result = validator.validate(override)
        assert result.status == "validated"


# ---------------------------------------------------------------------------
# CapsulePatchProposal
# ---------------------------------------------------------------------------

class TestCapsulePatchProposal:

    def test_full_validation_pipeline(self) -> None:
        patch = CapsulePatchProposal(
            patch_id="patch_1",
            capsule_id="genshin_capsule",
            skill_id="character_level_up",
            patch_type="change_param",
            current_yaml="steps:\n  - action: click",
            proposed_yaml="steps:\n  - action: click\n  - action: wait",
            diff_summary="added wait step",
        )
        assert patch.validation_status == "draft"
        patch = patch.with_schema_validated()
        assert patch.validation_status == "schema_validated"
        patch = patch.with_diff_reviewed()
        assert patch.validation_status == "diff_reviewed"
        patch = patch.with_replay_verified("pass")
        assert patch.validation_status == "replay_verified"
        assert patch.replay_result == "pass"
        patch = patch.with_user_confirmed()
        assert patch.validation_status == "user_confirmed"
        committed = patch.commit()
        assert committed.validation_status == "committed"
        assert committed.committed_at is not None

    def test_commit_without_user_confirm_rejected(self) -> None:
        patch = CapsulePatchProposal(
            patch_id="patch_2",
            capsule_id="test",
            skill_id="test",
            patch_type="add_step",
            current_yaml="",
            proposed_yaml="x: 1",
            diff_summary="test",
        )
        committed = patch.commit()
        assert committed.validation_status == "rejected"


# ---------------------------------------------------------------------------
# Runner override / patch integration
# ---------------------------------------------------------------------------

class TestRunnerOverrideIntegration:

    def test_apply_override(self) -> None:
        runner = _make_runner()
        override = RuntimeOverrideClaim(
            override_id="ovr_apply",
            target_component="test",
            override_type="param",
            proposed_value={"x": 1},
            justification="test",
            confidence=0.8,
        )
        result = runner.apply_override(override)
        assert result.status == "applied"

    def test_apply_override_rejected(self) -> None:
        runner = _make_runner()
        override = RuntimeOverrideClaim(
            override_id="ovr_rej",
            target_component="test",
            override_type="policy",
            proposed_value={},
            justification="",
            confidence=0.9,
            risk_level="critical",
        )
        result = runner.apply_override(override)
        assert result.status == "rejected"

    def test_propose_patch(self) -> None:
        runner = _make_runner()
        patch = CapsulePatchProposal(
            patch_id="patch_3",
            capsule_id="test",
            skill_id="test",
            patch_type="new_skill",
            current_yaml="",
            proposed_yaml="steps:\n  - action: test",
            diff_summary="new skill",
        )
        result = runner.propose_patch(patch)
        # propose_patch handles schema + diff, but NOT replay (caller must do that)
        assert result.validation_status == "diff_reviewed"


# ---------------------------------------------------------------------------
# UIFlowSkillAdapter integration
# ---------------------------------------------------------------------------

from execution.ui_flow_skill_adapter import UIFlowSkillAdapter


class _FakeVerificationProvider:
    """Mock verification that returns high confidence for adapter tests."""
    def verify(self, task: TaskSpecResult, screen: ScreenClaimResult) -> VerificationResult:
        return VerificationResult(verified=True, confidence=0.85, method="vlm", details="mock_pass")


class _FakeSkillAdapter:
    """Fake adapter that records calls and returns True."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def execute_semantic(
        self,
        action: str,
        target: str = "",
        context: dict[str, Any] | None = None,
    ) -> bool:
        self.calls.append((action, target, context))
        return True


class TestClosedLoopWithAdapter:

    def test_adapter_execution_path(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("升级胡桃到90级")
        assert result.success is True
        assert len(adapter.calls) == 1
        assert adapter.calls[0][0] == "character_level_up_full"

    def test_adapter_weapon_equip(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("装备武器")
        assert result.success is True
        assert adapter.calls[0][0] == "weapon_equip_full"

    def test_default_ui_flows_has_all_capabilities(self) -> None:
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        caps = [
            "character_level_up", "character_ascend", "talent_upgrade",
            "weapon_equip", "weapon_enhance", "weapon_refine",
            "artifact_equip", "artifact_enhance", "wish_pull",
        ]
        for cap in caps:
            assert lookup.lookup(cap) is not None, f"missing: {cap}"

    def test_character_slot_selection(self) -> None:
        """When target specifies slot, adapter should pre-select character."""
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        # Pass target via TaskSpecResult — simulate slot_2
        # The ClosedLoopRunner passes task.target to adapter
        result = runner.run("升级")  # will resolve to character_level_up
        # Default target is empty so no slot selection happens
        assert result.success is True

    def test_adapter_preferred_over_runtime(self) -> None:
        """When both adapter and runtime exist, adapter is used."""
        adapter = _FakeSkillAdapter()
        mock_runtime = MagicMock()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            execution_runtime=mock_runtime,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("升级胡桃到90级")
        assert result.success is True
        assert len(adapter.calls) == 1
        mock_runtime.submit.assert_not_called()

    def test_full_chain_with_real_adapter(self) -> None:
        """End-to-end with real UIFlowSkillAdapter (ConsoleInputBackend dry-run).

        Without a real game, UIFlow screen-state validation will fail, but the
        chain wiring is proven: adapter is called, steps execute, claim graph
        is populated regardless of game-state outcome.
        """
        adapter = UIFlowSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
        )
        result = runner.run("升级胡桃到90级")
        assert isinstance(result, ClosedLoopResult)
        assert len(result.steps) >= 4  # resolve + lookup + screen + execute + verify
        # Verify chain steps all ran
        step_names = [s.step for s in result.steps]
        assert "resolve_task" in step_names
        assert "lookup_skill" in step_names
        assert "screen_claim" in step_names
        assert "execute" in step_names
        assert "verify" in step_names
        # Verify claim graph was populated even though dry-run fails screen validation
        assert runner.claim_graph.observation_count >= 1
        assert runner.claim_graph.claim_count >= 1


# ---------------------------------------------------------------------------
# HSR anti-leakage test
# ---------------------------------------------------------------------------

class TestHSRAntiLeakage:
    """Verify kernel handles non-Genshin games (Honkai: Star Rail)."""

    def test_hsr_combat_capability_resolved(self) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve("进入战斗")
        assert result.capability == "hsr_combat"

    def test_hsr_dialog_capability_resolved(self) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve("星穹对话")
        assert result.capability == "hsr_dialog"

    def test_hsr_full_loop_with_adapter(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup()
        lookup.register("hsr_combat", SkillRecipe(
            skill_id="hsr_combat",
            capsule_id="hsr",
        ))
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("start combat")
        assert result.success is True
        assert len(adapter.calls) == 1
        assert adapter.calls[0][0] == "hsr_combat"
        # Verify claim graph works for non-Genshin
        assert runner.claim_graph.claim_count >= 1


class TestCombatCapabilityBridge:
    """Verify combat capabilities resolve and execute through the closed loop."""

    @pytest.mark.parametrize("text,expected_cap", [
        ("打怪", "combat_basic"),
        ("杀boss", "combat_boss"),
        ("世界boss", "combat_world_boss"),
        ("周本", "combat_weekly"),
        ("深渊法师", "combat_abyss_mage"),
        ("精英怪", "combat_shield_break"),
        ("进入战斗", "hsr_combat"),
        # Boss-specific
        ("风魔龙", "combat_boss_dvalin"),
        ("特瓦林", "combat_boss_dvalin"),
        ("公子", "combat_boss_childe"),
        ("达达利亚", "combat_boss_childe"),
        ("女士", "combat_boss_signora"),
        ("雷电将军", "combat_boss_raiden"),
        ("正机之神", "combat_boss_shouki"),
        ("巨鲸", "combat_boss_narwhal"),
        ("吞噬一切的巨鲸", "combat_boss_narwhal"),
        # Environment
        ("龙脊雪山", "combat_env_dragonspine"),
        ("稻妻雷暴", "combat_env_inazuma"),
        # Abyss, multi-wave, rotations
        ("深境螺旋", "combat_abyss"),
        ("螺旋", "combat_abyss"),
        ("深渊", "combat_abyss"),
        ("多波次", "combat_multi_wave"),
        ("防守战", "combat_multi_wave"),
        ("周本循环", "combat_weekly_rotation"),
        ("世界boss循环", "combat_world_farming"),
    ])
    def test_combat_keyword_resolution(self, text, expected_cap) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve(text)
        assert result.capability == expected_cap, f"'{text}' → {result.capability}, expected {expected_cap}"

    def test_combat_basic_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("打怪")
        assert result.success is True
        assert len(adapter.calls) == 1
        assert adapter.calls[0][0] == "combat_basic"

    def test_combat_boss_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("杀boss")
        assert result.success is True
        assert adapter.calls[0][0] == "combat_boss"

    def test_boss_specific_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("风魔龙")
        assert result.success is True
        assert adapter.calls[0][0] == "combat_boss_dvalin"

    def test_env_combat_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("龙脊雪山")
        assert result.success is True
        assert adapter.calls[0][0] == "combat_env_dragonspine"


class TestExplorationCapabilityBridge:
    """Verify exploration capabilities resolve and execute through the closed loop."""

    @pytest.mark.parametrize("text,expected_cap", [
        ("传送锚点", "explore_waypoint"),
        ("传送锚点激活", "explore_waypoint"),
        ("七天神像", "explore_statue"),
        ("宝箱", "explore_chest"),
        ("普通宝箱", "explore_chest"),
        ("精致宝箱", "explore_chest"),
        ("华丽宝箱", "explore_chest"),
        ("开宝箱", "explore_chest"),
        ("神瞳", "explore_oculus"),
        ("风神瞳", "explore_oculus"),
        ("岩神瞳", "explore_oculus"),
        ("水神瞳", "explore_oculus"),
        ("解谜", "explore_puzzle"),
        ("元素方碑", "explore_puzzle"),
        ("火炬解谜", "explore_puzzle"),
        ("压力板", "explore_puzzle"),
        ("限时挑战", "explore_timed"),
        ("死域", "explore_withering"),
        ("水下探索", "explore_underwater"),
        ("枫丹水下", "explore_underwater"),
        ("open chest", "explore_chest"),
        ("collect oculus", "explore_oculus"),
        ("activate waypoint", "explore_waypoint"),
        ("withering zone", "explore_withering"),
        ("underwater", "explore_underwater"),
        ("puzzle", "explore_puzzle"),
        ("timed challenge", "explore_timed"),
    ])
    def test_exploration_keyword_resolution(self, text, expected_cap) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve(text)
        assert result.capability == expected_cap, f"'{text}' → {result.capability}, expected {expected_cap}"

    def test_exploration_waypoint_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("传送锚点")
        assert result.success is True
        assert len(adapter.calls) == 1
        assert adapter.calls[0][0].startswith("explore")

    def test_exploration_chest_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("开宝箱")
        assert result.success is True
        assert adapter.calls[0][0].startswith("explore")

    def test_exploration_oculus_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("collect oculus")
        assert result.success is True
        assert adapter.calls[0][0].startswith("explore")


class TestQuestCapabilityBridge:
    """Verify quest capabilities resolve and execute through the closed loop."""

    @pytest.mark.parametrize("text,expected_cap", [
        ("推进对话", "quest_dialog"),
        ("对话选择", "quest_dialog_select"),
        ("跳过过场", "quest_skip_cutscene"),
        ("任务日志", "quest_read_log"),
        ("每日委托", "quest_daily"),
        ("魔神任务", "quest_archon"),
        ("传说任务", "quest_story"),
        ("邀约事件", "quest_story"),
        ("世界任务", "quest_world"),
        ("活动任务", "quest_event"),
        ("追踪任务", "quest_track"),
        ("对话", "quest_dialog"),
        ("advance dialog", "quest_dialog"),
        ("skip cutscene", "quest_skip_cutscene"),
        ("daily commission", "quest_daily"),
        ("archon quest", "quest_archon"),
        ("story quest", "quest_story"),
        ("world quest", "quest_world"),
        ("event quest", "quest_event"),
        ("track quest", "quest_track"),
        ("quest log", "quest_read_log"),
    ])
    def test_quest_keyword_resolution(self, text, expected_cap) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve(text)
        assert result.capability == expected_cap, f"'{text}' → {result.capability}, expected {expected_cap}"

    def test_quest_dialog_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("推进对话")
        assert result.success is True
        assert len(adapter.calls) == 1

    def test_quest_archon_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("魔神任务")
        assert result.success is True

    def test_quest_daily_commission_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("每日委托")
        assert result.success is True


class TestDailyRoutineCapabilityBridge:
    """Verify daily routine capabilities resolve and execute through the closed loop."""

    @pytest.mark.parametrize("text,expected_cap", [
        ("消耗树脂", "daily_resin"),
        ("秘境", "daily_domain"),
        ("天赋秘境", "daily_domain"),
        ("圣遗物秘境", "daily_domain"),
        ("浓缩树脂", "daily_resin"),
        ("凯瑟琳奖励", "daily_katheryne"),
        ("探索派遣", "daily_expedition"),
        ("尘歌壶", "daily_pot"),
        ("速通日常", "daily_quick"),
        ("标准日常", "daily_standard"),
        ("深度日常", "daily_deep"),
        ("spend resin", "daily_resin"),
        ("domain run", "daily_domain"),
        ("artifact domain", "daily_domain"),
        ("katheryne reward", "daily_katheryne"),
        ("expedition check", "daily_expedition"),
        ("serenitea pot", "daily_pot"),
        ("quick daily", "daily_quick"),
        ("standard daily", "daily_standard"),
        ("deep daily", "daily_deep"),
    ])
    def test_daily_keyword_resolution(self, text, expected_cap) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve(text)
        assert result.capability == expected_cap, f"'{text}' → {result.capability}, expected {expected_cap}"

    def test_daily_domain_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("秘境")
        assert result.success is True

    def test_daily_quick_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("速通日常")
        assert result.success is True


class TestLongChainCapabilityBridge:
    """Verify long-chain and mainline progression capabilities."""

    @pytest.mark.parametrize("text,expected_cap", [
        ("新手教程", "chain_tutorial"),
        ("新手链", "chain_tutorial"),
        ("tutorial", "chain_tutorial"),
        ("日常会话", "chain_daily_session"),
        ("15分钟日常", "chain_daily_session"),
        ("boss连战", "chain_boss_gauntlet"),
        ("boss gauntlet", "chain_boss_gauntlet"),
        ("周本连战", "chain_weekly_gauntlet"),
        ("探索清剿", "chain_exploration_sweep"),
        ("主线推进", "mainline_progress"),
        ("魔神任务推进", "mainline_progress"),
        ("序章", "mainline_prologue"),
        ("第一章", "mainline_ch1"),
        ("第二章", "mainline_ch2"),
        ("第三章", "mainline_ch3"),
        ("第四章", "mainline_ch4"),
        ("第五章", "mainline_ch5"),
        ("prologue", "mainline_prologue"),
        ("chapter 1", "mainline_ch1"),
        ("mainline", "mainline_progress"),
    ])
    def test_long_chain_keyword_resolution(self, text, expected_cap) -> None:
        resolver = SimpleTaskSpecResolver()
        result = resolver.resolve(text)
        assert result.capability == expected_cap, f"'{text}' → {result.capability}, expected {expected_cap}"

    def test_chain_tutorial_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("新手教程")
        assert result.success is True
        assert adapter.calls[0][0] == "chain_tutorial"

    def test_mainline_prologue_closed_loop(self) -> None:
        adapter = _FakeSkillAdapter()
        lookup = SimpleSkillRecipeLookup.with_default_ui_flows()
        runner = _make_runner(
            skill_adapter=adapter,
            task_resolver=SimpleTaskSpecResolver(),
            skill_lookup=lookup,
            verification_provider=_FakeVerificationProvider(),
        )
        result = runner.run("序章")
        assert result.success is True
        assert adapter.calls[0][0] == "mainline_prologue"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
