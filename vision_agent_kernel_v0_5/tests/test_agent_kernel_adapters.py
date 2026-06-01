"""Tests for AgentKernel production adapters."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from agent_kernel.adapters import (
    VLMPerceptionProvider,
    VLMSuccessChecker,
    LLMPlanner,
    GenshinExecutionProvider,
)
from agent_kernel.types import (
    ActionPrimitive,
    ActionPlan,
    AgentGoal,
    SemanticObservation,
    StepResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_frame() -> np.ndarray:
    return np.zeros((1080, 1920, 3), dtype=np.uint8)


def _mock_vlm_provider() -> MagicMock:
    mock = MagicMock()
    mock.describe_image.return_value = MagicMock(description="角色详情页", confidence=0.85)
    mock.ground_ui.return_value = MagicMock(
        candidates=[
            {"bbox_norm": [0.82, 0.82, 0.88, 0.88], "confidence": 0.9, "label": "升级", "type": "button"},
        ]
    )
    return mock


def _mock_classifier() -> MagicMock:
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class _ScreenState:
        state: str
        confidence: float
        indicators: dict[str, bool]

    mock = MagicMock()
    mock.classify.return_value = _ScreenState(
        state="character_detail", confidence=0.85, indicators={}
    )
    return mock


def _mock_ocr() -> MagicMock:
    mock = MagicMock()
    mock.detect_text.return_value = [MagicMock(text="钟离 Lv.80")]
    return mock


# ---------------------------------------------------------------------------
# VLMPerceptionProvider
# ---------------------------------------------------------------------------

class TestVLMPerceptionProvider:

    def test_observe_returns_observation(self) -> None:
        provider = VLMPerceptionProvider(
            screen_classifier=_mock_classifier(),
            vlm_provider=_mock_vlm_provider(),
        )
        frame = _fake_frame()
        obs = provider.observe(frame)
        assert isinstance(obs, SemanticObservation)
        assert obs.screen_state == "character_detail"
        assert obs.vlm_confidence == 0.85

    def test_observe_with_ocr(self) -> None:
        provider = VLMPerceptionProvider(
            screen_classifier=_mock_classifier(),
            vlm_provider=_mock_vlm_provider(),
            ocr_provider=_mock_ocr(),
        )
        obs = provider.observe(_fake_frame())
        assert "钟离" in obs.raw_ocr_text

    def test_describe_scene_calls_vlm(self) -> None:
        provider = VLMPerceptionProvider(
            screen_classifier=_mock_classifier(),
            vlm_provider=_mock_vlm_provider(),
        )
        result = provider.describe_scene(_fake_frame(), "当前界面有什么？")
        assert result == "角色详情页"
        provider._vlm.describe_image.assert_called_once()

    def test_locate_element_returns_actionable_element(self) -> None:
        provider = VLMPerceptionProvider(
            screen_classifier=_mock_classifier(),
            vlm_provider=_mock_vlm_provider(),
        )
        el = provider.locate_element(_fake_frame(), "升级按钮")
        assert el is not None
        assert el.label == "升级"
        assert el.element_type == "button"
        assert el.confidence == 0.9

    def test_locate_element_no_candidates(self) -> None:
        mock_vlm = _mock_vlm_provider()
        mock_vlm.ground_ui.return_value = MagicMock(candidates=[])
        provider = VLMPerceptionProvider(
            screen_classifier=_mock_classifier(),
            vlm_provider=mock_vlm,
        )
        el = provider.locate_element(_fake_frame(), "missing")
        assert el is None

    def test_locate_element_invalid_bbox(self) -> None:
        mock_vlm = _mock_vlm_provider()
        mock_vlm.ground_ui.return_value = MagicMock(
            candidates=[{"bbox_norm": "invalid", "confidence": 0.5, "label": "x"}]
        )
        provider = VLMPerceptionProvider(
            screen_classifier=_mock_classifier(),
            vlm_provider=mock_vlm,
        )
        el = provider.locate_element(_fake_frame(), "x")
        assert el is None

    def test_observe_ocr_error_handled(self) -> None:
        mock_ocr = MagicMock()
        mock_ocr.detect_text.side_effect = RuntimeError("OCR unavailable")
        provider = VLMPerceptionProvider(
            screen_classifier=_mock_classifier(),
            vlm_provider=_mock_vlm_provider(),
            ocr_provider=mock_ocr,
        )
        obs = provider.observe(_fake_frame())
        assert obs.raw_ocr_text == ""


# ---------------------------------------------------------------------------
# VLMSuccessChecker
# ---------------------------------------------------------------------------

class TestVLMSuccessChecker:

    def test_check_keyword_match_returns_true(self) -> None:
        checker = VLMSuccessChecker(vlm_provider=MagicMock(), threshold=0.7)
        obs = SemanticObservation(
            timestamp=1.0,
            scene_description="升级成功，角色已升到90级",
            actionable_elements=(),
            screen_state="success",
            vlm_confidence=0.85,
        )
        achieved, conf = checker.check(obs, "角色是否已经升到90级")
        assert achieved is True
        assert conf >= 0.7

    def test_check_no_keyword_match_returns_false(self) -> None:
        checker = VLMSuccessChecker(vlm_provider=MagicMock(), threshold=0.7)
        obs = SemanticObservation(
            timestamp=1.0,
            scene_description="角色详情页",
            actionable_elements=(),
            screen_state="character_detail",
            vlm_confidence=0.5,
        )
        achieved, conf = checker.check(obs, "角色是否已经升到90级")
        assert achieved is False

    def test_check_with_frame_calls_vlm(self) -> None:
        mock_vlm = _mock_vlm_provider()
        mock_vlm.describe_image.return_value = MagicMock(description="YES — 升级完成", confidence=0.9)
        checker = VLMSuccessChecker(vlm_provider=mock_vlm, threshold=0.7)
        achieved, conf = checker.check_with_frame(_fake_frame(), "升级完成了吗？")
        assert achieved is True

    def test_check_with_frame_no_answer(self) -> None:
        mock_vlm = _mock_vlm_provider()
        mock_vlm.describe_image.return_value = MagicMock(description="NO", confidence=0.9)
        checker = VLMSuccessChecker(vlm_provider=mock_vlm, threshold=0.7)
        achieved, conf = checker.check_with_frame(_fake_frame(), "升级完成了吗？")
        assert achieved is False

    def test_check_with_frame_vlm_error(self) -> None:
        mock_vlm = _mock_vlm_provider()
        mock_vlm.describe_image.side_effect = RuntimeError("VLM unavailable")
        checker = VLMSuccessChecker(vlm_provider=mock_vlm)
        achieved, conf = checker.check_with_frame(_fake_frame(), "升级完成了吗？")
        assert achieved is False
        assert conf == 0.0


# ---------------------------------------------------------------------------
# LLMPlanner
# ---------------------------------------------------------------------------

class TestLLMPlanner:

    def test_plan_returns_action_plan(self) -> None:
        mock_llm = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.provider = "glm"
        mock_proposal.skill_chain = ["explore_current_region", "ui_interact"]
        mock_llm.plan.return_value = mock_proposal

        planner = LLMPlanner(planner=mock_llm)
        obs = SemanticObservation(
            timestamp=1.0,
            scene_description="当前在蒙德城",
            actionable_elements=(),
        )
        goal = AgentGoal(goal_id="g1", description="探索当前区域", success_criteria="完成")
        plan = planner.plan(obs, goal, memory=None)

        assert isinstance(plan, ActionPlan)
        assert plan.goal_id == "g1"
        assert plan.confidence == 0.75
        assert len(plan.steps) == 2

    def test_plan_includes_memory_context(self) -> None:
        mock_llm = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.provider = "mock"
        mock_proposal.skill_chain = ["test_skill"]
        mock_llm.plan.return_value = mock_proposal

        mock_memory = MagicMock()
        mock_memory.recall.return_value = []

        planner = LLMPlanner(planner=mock_llm)
        obs = SemanticObservation(timestamp=1.0, scene_description="test", actionable_elements=())
        goal = AgentGoal(goal_id="g1", description="test goal", success_criteria="done")
        planner.plan(obs, goal, memory=mock_memory)
        mock_memory.recall.assert_called_once()

    def test_replan_includes_failure_context(self) -> None:
        mock_llm = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.provider = "mock"
        mock_proposal.skill_chain = ["retry_skill"]
        mock_llm.plan.return_value = mock_proposal

        planner = LLMPlanner(planner=mock_llm)
        obs = SemanticObservation(timestamp=1.0, scene_description="test", actionable_elements=())
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        failure = StepResult(step_id="s1", success=False, error="升级按钮不可点击")
        plan = planner.replan(obs, goal, failure, memory=None)

        assert isinstance(plan, ActionPlan)
        # Verify plan was called with failure context
        call_args = mock_llm.plan.call_args
        assert "升级按钮不可点击" in call_args.kwargs.get("goal", "") or \
               "升级按钮不可点击" in str(call_args)

    def test_plan_fallback_on_error(self) -> None:
        mock_llm = MagicMock()
        mock_llm.plan.side_effect = RuntimeError("LLM unavailable")

        planner = LLMPlanner(planner=mock_llm)
        obs = SemanticObservation(timestamp=1.0, scene_description="test", actionable_elements=())
        goal = AgentGoal(goal_id="g1", description="test", success_criteria="done")
        plan = planner.plan(obs, goal, memory=None)

        assert isinstance(plan, ActionPlan)
        assert plan.confidence == 0.0
        assert plan.steps == ()


# ---------------------------------------------------------------------------
# GenshinExecutionProvider
# ---------------------------------------------------------------------------

class TestGenshinExecutionProvider:

    def test_execute_click_with_controller(self) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.click_target.return_value = True

        provider = GenshinExecutionProvider(controller=mock_ctrl)
        provider.set_last_frame(_fake_frame())

        primitive = ActionPrimitive(primitive_type="click", target="升级按钮")
        result = provider.execute(primitive)

        assert result.success is True
        mock_ctrl.click_target.assert_called_once()

    def test_execute_key_press(self) -> None:
        mock_backend = MagicMock()
        mock_ctrl = MagicMock()

        provider = GenshinExecutionProvider(controller=mock_ctrl, input_backend=mock_backend)
        provider.set_last_frame(_fake_frame())

        primitive = ActionPrimitive(primitive_type="key_press", target="Escape", reason="关闭菜单")
        result = provider.execute(primitive)

        assert result.success is True
        mock_backend.key_press.assert_called_once_with("Escape", "关闭菜单")

    def test_execute_wait(self) -> None:
        mock_ctrl = MagicMock()
        provider = GenshinExecutionProvider(controller=mock_ctrl)
        provider.set_last_frame(_fake_frame())

        primitive = ActionPrimitive(primitive_type="wait", target="2")
        result = provider.execute(primitive)
        assert result.success is True

    def test_execute_no_frame(self) -> None:
        mock_ctrl = MagicMock()
        provider = GenshinExecutionProvider(controller=mock_ctrl)
        # No frame set

        primitive = ActionPrimitive(primitive_type="click", target="btn")
        result = provider.execute(primitive)
        assert result.success is False
        assert "no_frame" in result.error

    def test_execute_scroll(self) -> None:
        mock_backend = MagicMock()
        mock_ctrl = MagicMock()

        provider = GenshinExecutionProvider(controller=mock_ctrl, input_backend=mock_backend)
        provider.set_last_frame(_fake_frame())

        primitive = ActionPrimitive(primitive_type="scroll", target="up")
        result = provider.execute(primitive)
        assert result.success is True
        mock_backend.mouse_scroll.assert_called_once()

    def test_locate_and_click(self) -> None:
        mock_ctrl = MagicMock()
        mock_ctrl.click_target.return_value = True

        provider = GenshinExecutionProvider(controller=mock_ctrl)
        provider.set_last_frame(_fake_frame())

        result = provider.locate_and_click("升级按钮")
        assert result.success is True

    def test_press_key_standalone(self) -> None:
        mock_backend = MagicMock()
        mock_ctrl = MagicMock()

        provider = GenshinExecutionProvider(controller=mock_ctrl, input_backend=mock_backend)
        result = provider.press_key("M", "打开地图")
        assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])