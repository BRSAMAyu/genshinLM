"""Tests for agent_kernel/operator_agent.py"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import pytest

from agent_kernel.operator_agent import (
    OperatorAgent,
    OperatorSession,
    SimpleOperatorAgent,
    _match_override,
    _match_policy,
    _new_session,
)
from agent_kernel.types import (
    CapsulePatchProposal,
    RuntimeOverride,
    TaskSpec,
)


# ---------------------------------------------------------------------------
# Test keyword registry (mirrors Genshin Capsule data)
# ---------------------------------------------------------------------------

_TEST_TASK_KEYWORDS: dict[str, str] = {
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent() -> OperatorAgent:
    return OperatorAgent(task_keywords=_TEST_TASK_KEYWORDS)


@pytest.fixture
def simple_agent() -> SimpleOperatorAgent:
    return SimpleOperatorAgent(task_keywords=_TEST_TASK_KEYWORDS)


@pytest.fixture
def fresh_session() -> OperatorSession:
    return _new_session()


# ---------------------------------------------------------------------------
# Frozen/slots enforcement
# ---------------------------------------------------------------------------

class TestFrozenSlots:

    def test_operator_session_is_frozen(self, fresh_session: OperatorSession) -> None:
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            fresh_session.current_task = None  # type: ignore[assignment]

    def test_operator_session_is_frozen_after_mutation(self, fresh_session: OperatorSession) -> None:
        task = TaskSpec(task_id="test", objective="test_obj")
        new_session = fresh_session.start_task(task)
        with pytest.raises(Exception):
            new_session.current_task = None  # type: ignore[assignment]

    def test_runtime_override_is_frozen(self) -> None:
        override = RuntimeOverride(
            override_id="o1",
            target_parameter="confidence_threshold",
            new_value="0.5",
            reason="test",
        )
        with pytest.raises(Exception):
            override.new_value = "0.8"  # type: ignore[assignment]

    def test_task_spec_is_frozen(self) -> None:
        task = TaskSpec(task_id="t1", objective="test")
        with pytest.raises(Exception):
            task.objective = "other"  # type: ignore[assignment]

    def test_capsule_patch_proposal_is_frozen(self) -> None:
        patch = CapsulePatchProposal(
            proposal_id="p1",
            capsule_id="c1",
            yaml_path="a/b",
            patch_data=(("x", "y"),),
        )
        with pytest.raises(Exception):
            patch.capsule_id = "c2"  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

class TestIntentParsing:

    @pytest.mark.parametrize("text,expected", [
        # Chinese task requests
        ("升级胡桃到90级", "set_goal"),
        ("突破钟离", "set_goal"),
        ("打怪", "set_goal"),
        ("开宝箱", "set_goal"),
        ("做日常任务", "set_goal"),
        ("推进主线", "set_goal"),
        # English task requests
        ("level up hutao", "set_goal"),
        ("ascend zhongli", "set_goal"),
        ("fight monster", "set_goal"),
        ("open chest", "set_goal"),
        ("do daily quest", "set_goal"),
        ("advance mainline", "set_goal"),
    ])
    def test_set_goal_intent(self, agent: OperatorAgent, text: str, expected: str) -> None:
        assert agent._parse_intent(text) == expected

    @pytest.mark.parametrize("text,expected", [
        # Chinese policy changes
        ("不要消耗稀有资源", "adjust_policy"),
        ("跳过所有对话", "adjust_policy"),
        ("谨慎模式", "adjust_policy"),
        ("安全模式", "adjust_policy"),
        # English policy changes
        ("no rare resources", "adjust_policy"),
        ("skip all dialog", "adjust_policy"),
        ("cautious mode", "adjust_policy"),
        ("dry run", "adjust_policy"),
    ])
    def test_adjust_policy_intent(self, agent: OperatorAgent, text: str, expected: str) -> None:
        assert agent._parse_intent(text) == expected

    @pytest.mark.parametrize("text,expected", [
        # Chinese override requests
        ("把置信度调到0.2", "adjust_param"),
        ("设置超时时间为5秒", "adjust_param"),
        ("把重试次数调为3", "adjust_param"),
        # English override requests
        ("set confidence to 0.3", "adjust_param"),
        ("set timeout to 10 sec", "adjust_param"),
        ("set retries to 5", "adjust_param"),
    ])
    def test_adjust_param_intent(self, agent: OperatorAgent, text: str, expected: str) -> None:
        assert agent._parse_intent(text) == expected

    @pytest.mark.parametrize("text,expected", [
        # Chinese explanation
        ("当前在做什么", "explain"),
        ("在做什么", "explain"),
        ("怎么回事", "explain"),
        # English explanation
        ("what are you doing", "explain"),
        ("current state", "explain"),
        ("what's happening", "explain"),
    ])
    def test_explain_intent(self, agent: OperatorAgent, text: str, expected: str) -> None:
        assert agent._parse_intent(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("确认", "confirm"),
        ("确定", "confirm"),
        ("好的", "confirm"),
        ("confirm", "confirm"),
        ("yes", "confirm"),
        ("ok", "confirm"),
        ("proceed", "confirm"),
        ("取消", "abort"),
        ("停止", "abort"),
        ("cancel", "abort"),
        ("no", "abort"),
        ("abort", "abort"),
    ])
    def test_confirm_abort_intent(self, agent: OperatorAgent, text: str, expected: str) -> None:
        assert agent._parse_intent(text) == expected

    @pytest.mark.parametrize("text", [
        "随便吧",
        "无所谓",
        "whatever",
        "not sure",
        "",
    ])
    def test_unknown_intent(self, agent: OperatorAgent, text: str) -> None:
        assert agent._parse_intent(text) == "unknown"


# ---------------------------------------------------------------------------
# Keyword matching helpers
# ---------------------------------------------------------------------------

class TestKeywordMatching:

    def test_match_task_keyword_chinese(self, agent: OperatorAgent) -> None:
        capability, conf = agent._match_task_keyword("升级胡桃")
        assert capability == "character_level_up"
        assert conf == 0.8

    def test_match_task_keyword_english(self, agent: OperatorAgent) -> None:
        capability, conf = agent._match_task_keyword("ascend zhongli")
        assert capability == "character_ascend"
        assert conf == 0.8

    def test_match_task_keyword_unknown(self, agent: OperatorAgent) -> None:
        capability, conf = agent._match_task_keyword("foobar")
        assert capability == "unknown"
        assert conf == 0.3

    def test_match_policy_chinese(self) -> None:
        result = _match_policy("不要消耗稀有资源")
        assert result is not None
        assert result[0] == "resource_policy"
        assert result[1] == "no_rare_consumables"

    def test_match_policy_english(self) -> None:
        result = _match_policy("skip all dialog")
        assert result is not None
        assert result[0] == "dialog_policy"
        assert result[1] == "skip_all"

    def test_match_policy_no_match(self) -> None:
        result = _match_policy("random text")
        assert result is None

    def test_match_override_confidence_chinese(self) -> None:
        result = _match_override("把置信度调到0.2")
        assert result is not None
        assert result[0] == "confidence_threshold"
        assert result[1] == "0.2"

    def test_match_override_confidence_english(self) -> None:
        result = _match_override("set confidence to 0.5")
        assert result is not None
        assert result[0] == "confidence_threshold"
        assert result[1] == "0.5"

    def test_match_override_timeout_chinese(self) -> None:
        result = _match_override("超时设置为10秒")
        assert result is not None
        assert result[0] == "timeout_sec"
        assert result[1] == "10"

    def test_match_override_no_match(self) -> None:
        result = _match_override("do something")
        assert result is None


# ---------------------------------------------------------------------------
# OperatorSession state tracking
# ---------------------------------------------------------------------------

class TestOperatorSession:

    def test_new_session_has_id(self, fresh_session: OperatorSession) -> None:
        assert fresh_session.session_id.startswith("sess_")
        assert len(fresh_session.session_id) > 0

    def test_new_session_has_created_at(self, fresh_session: OperatorSession) -> None:
        assert fresh_session.created_at > 0

    def test_start_task_returns_new_session(self, fresh_session: OperatorSession) -> None:
        task = TaskSpec(task_id="task_123", objective="test_obj")
        new_session = fresh_session.start_task(task)
        assert new_session is not fresh_session
        assert new_session.current_task is task
        assert fresh_session.current_task is None

    def test_start_task_updates_history(self, fresh_session: OperatorSession) -> None:
        task = TaskSpec(task_id="task_456", objective="explore")
        new_session = fresh_session.start_task(task)
        assert len(new_session.state_history) > len(fresh_session.state_history)
        last_entry = new_session.state_history[-1]
        assert "task_started" in last_entry[1]

    def test_add_pending_override(self, fresh_session: OperatorSession) -> None:
        override = RuntimeOverride(
            override_id="ovr_abc",
            target_parameter="confidence",
            new_value="0.5",
            reason="test",
        )
        new_session = fresh_session.add_pending_override(override)
        assert len(new_session.pending_overrides) == 1
        assert new_session.pending_overrides[0] == override

    def test_confirm_action_removes_pending(self, fresh_session: OperatorSession) -> None:
        override = RuntimeOverride(
            override_id="ovr_def",
            target_parameter="timeout",
            new_value="5",
            reason="test",
        )
        session_with_override = fresh_session.add_pending_override(override)
        confirmed = session_with_override.confirm_action()
        assert len(confirmed.pending_overrides) == 0

    def test_confirm_action_updates_history(self, fresh_session: OperatorSession) -> None:
        override = RuntimeOverride(
            override_id="ovr_ghi",
            target_parameter="retries",
            new_value="3",
            reason="test",
        )
        session_with_override = fresh_session.add_pending_override(override)
        confirmed = session_with_override.confirm_action()
        last_entry = confirmed.state_history[-1]
        assert "override_confirmed" in last_entry[1]

    def test_confirm_action_empty_session(self, fresh_session: OperatorSession) -> None:
        result = fresh_session.confirm_action()
        assert result is fresh_session  # no-op

    def test_abort_action_removes_pending(self, fresh_session: OperatorSession) -> None:
        override = RuntimeOverride(
            override_id="ovr_jkl",
            target_parameter="freq",
            new_value="60",
            reason="test",
        )
        session_with_override = fresh_session.add_pending_override(override)
        aborted = session_with_override.abort_action()
        assert len(aborted.pending_overrides) == 0

    def test_abort_action_empty_session(self, fresh_session: OperatorSession) -> None:
        result = fresh_session.abort_action()
        assert result is fresh_session

    def test_add_confirmed_patch(self, fresh_session: OperatorSession) -> None:
        patch = CapsulePatchProposal(
            proposal_id="patch_xyz",
            capsule_id="test_capsule",
            yaml_path="a/b/c",
            patch_data=(("key", "value"),),
            reason="test patch",
        )
        new_session = fresh_session.add_confirmed_patch(patch)
        assert len(new_session.confirmed_patches) == 1
        assert new_session.confirmed_patches[0] == patch

    def test_get_status_summary(self, fresh_session: OperatorSession) -> None:
        summary = fresh_session.get_status_summary()
        assert "session_id" in summary
        assert "current_task" in summary
        assert "pending_overrides_count" in summary
        assert "confirmed_patches_count" in summary
        assert summary["pending_overrides_count"] == 0

    def test_get_status_summary_with_task(self, fresh_session: OperatorSession) -> None:
        task = TaskSpec(task_id="task_summary", objective="combat")
        session_with_task = fresh_session.start_task(task)
        summary = session_with_task.get_status_summary()
        assert "combat" in summary["current_task"]


# ---------------------------------------------------------------------------
# OperatorAgent handle_user_message
# ---------------------------------------------------------------------------

class TestOperatorAgentHandleMessage:

    def test_handle_task_request_chinese(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("升级胡桃到90级", {})
        assert response["display_message"] != ""
        assert response["technical_action"]["intent"] == "set_goal"
        assert response["patch_draft"] is None

    def test_handle_task_request_english(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("level up hutao", {})
        assert response["display_message"] != ""
        assert response["technical_action"]["intent"] == "set_goal"

    def test_handle_policy_change(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("不要消耗稀有资源", {})
        assert response["technical_action"]["intent"] == "adjust_policy"
        assert response["technical_action"]["field"] == "resource_policy"
        assert response["technical_action"]["value"] == "no_rare_consumables"

    def test_handle_confirm(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("确认", {})
        assert response["technical_action"]["intent"] == "confirm"

    def test_handle_abort(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("取消", {})
        assert response["technical_action"]["intent"] == "abort"

    def test_handle_explain(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("当前在做什么", {"current_task": "combat"})
        assert response["technical_action"]["intent"] == "explain"
        assert response["display_message"] != ""

    def test_handle_unknown_intent(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("随便吧", {})
        assert response["technical_action"]["intent"] == "unknown"


# ---------------------------------------------------------------------------
# OperatorAgent propose_override
# ---------------------------------------------------------------------------

class TestOperatorAgentProposeOverride:

    def test_propose_override_confidence(self, agent: OperatorAgent) -> None:
        override = agent.propose_override("把置信度调到0.2", {})
        assert override is not None
        assert override.target_parameter == "confidence_threshold"
        assert override.new_value == "0.2"
        assert override.source == "user"
        assert override.scope == "session"

    def test_propose_override_timeout(self, agent: OperatorAgent) -> None:
        override = agent.propose_override("设置超时时间为5秒", {})
        assert override is not None
        assert override.target_parameter == "timeout_sec"
        assert override.new_value == "5"

    def test_propose_override_no_match(self, agent: OperatorAgent) -> None:
        override = agent.propose_override("升级胡桃", {})
        assert override is None

    def test_propose_override_english(self, agent: OperatorAgent) -> None:
        override = agent.propose_override("set confidence to 0.3", {})
        assert override is not None
        assert override.target_parameter == "confidence_threshold"
        assert override.new_value == "0.3"


# ---------------------------------------------------------------------------
# OperatorAgent propose_capsule_patch
# ---------------------------------------------------------------------------

class TestOperatorAgentProposeCapsulePatch:

    def test_propose_patch_on_success(self, agent: OperatorAgent) -> None:
        override = RuntimeOverride(
            override_id="ovr_test",
            target_parameter="confidence_threshold",
            new_value="0.5",
            reason="test",
        )
        patch = agent.propose_capsule_patch(override, "success")
        assert patch is not None
        assert patch.capsule_id == "runtime_params"
        assert patch.yaml_path == "parameters/confidence_threshold"

    def test_propose_patch_on_failure(self, agent: OperatorAgent) -> None:
        override = RuntimeOverride(
            override_id="ovr_fail",
            target_parameter="timeout_sec",
            new_value="10",
            reason="test",
        )
        patch = agent.propose_capsule_patch(override, "failed")
        assert patch is None

    def test_propose_patch_on_partial(self, agent: OperatorAgent) -> None:
        override = RuntimeOverride(
            override_id="ovr_partial",
            target_parameter="max_retries",
            new_value="3",
            reason="test",
        )
        patch = agent.propose_capsule_patch(override, "partial")
        assert patch is None


# ---------------------------------------------------------------------------
# OperatorAgent explain_current_state
# ---------------------------------------------------------------------------

class TestOperatorAgentExplainState:

    def test_explain_with_task(self, agent: OperatorAgent) -> None:
        state = {"current_task": {"objective": "character_level_up"}, "execution_mode": "dry_run"}
        explanation = agent.explain_current_state(state)
        assert "character_level_up" in explanation
        assert "试运行" in explanation

    def test_explain_no_task(self, agent: OperatorAgent) -> None:
        state: dict = {}
        explanation = agent.explain_current_state(state)
        assert "无活跃任务" in explanation

    def test_explain_with_progress(self, agent: OperatorAgent) -> None:
        state = {"current_task": "combat", "progress": "50%", "execution_mode": "safe_window"}
        explanation = agent.explain_current_state(state)
        assert "50%" in explanation


# ---------------------------------------------------------------------------
# SimpleOperatorAgent
# ---------------------------------------------------------------------------

class TestSimpleOperatorAgent:

    def test_inherits_from_operator_agent(self, simple_agent: SimpleOperatorAgent) -> None:
        assert isinstance(simple_agent, OperatorAgent)

    def test_priority_inference_high(self, simple_agent: SimpleOperatorAgent) -> None:
        priority = simple_agent._infer_priority("尽快升级胡桃")
        assert priority == 80

    def test_priority_inference_high_en(self, simple_agent: SimpleOperatorAgent) -> None:
        priority = simple_agent._infer_priority("upgrade hutao asap")
        assert priority == 80

    def test_priority_inference_normal(self, simple_agent: SimpleOperatorAgent) -> None:
        priority = simple_agent._infer_priority("升级胡桃")
        assert priority == 50

    def test_target_extraction(self, simple_agent: SimpleOperatorAgent) -> None:
        target = simple_agent._extract_target("升级胡桃到90级")
        assert target == "胡桃"

    def test_target_extraction_english(self, simple_agent: SimpleOperatorAgent) -> None:
        target = simple_agent._extract_target("level up hutao")
        assert target == "hutao"

    def test_handle_set_goal_with_target(self, simple_agent: SimpleOperatorAgent) -> None:
        response = simple_agent.handle_user_message("升级胡桃到90级", {})
        assert response["technical_action"]["intent"] == "set_goal"
        assert response["technical_action"]["target"] == "胡桃"

    def test_handle_set_goal_with_high_priority(self, simple_agent: SimpleOperatorAgent) -> None:
        response = simple_agent.handle_user_message("马上突破钟离", {})
        task = response["technical_action"]["task"]
        assert task.priority == 80


# ---------------------------------------------------------------------------
# Integration: full session flow
# ---------------------------------------------------------------------------

class TestFullSessionFlow:

    def test_confirm_abort_flow(self, agent: OperatorAgent) -> None:
        # Step 1: User requests parameter adjustment
        response = agent.handle_user_message("把置信度调到0.2", {})
        assert response["technical_action"]["intent"] == "adjust_param"
        pending_count = len(agent.session.pending_overrides)
        assert pending_count == 1

        # Step 2: User confirms
        confirm_response = agent.handle_user_message("确认", {})
        assert confirm_response["technical_action"]["intent"] == "confirm"
        assert confirm_response["technical_action"]["result"] == "confirmed"
        assert len(agent.session.pending_overrides) == 0

    def test_full_flow_with_abort(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("设置超时为5秒", {})
        assert response["technical_action"]["intent"] == "adjust_param"

        abort_response = agent.handle_user_message("取消", {})
        assert abort_response["technical_action"]["intent"] == "abort"
        assert abort_response["technical_action"]["result"] == "aborted"
        assert len(agent.session.pending_overrides) == 0

    def test_confirm_no_pending(self, agent: OperatorAgent) -> None:
        response = agent.handle_user_message("确认", {})
        assert response["technical_action"]["result"] == "no_pending"


# ---------------------------------------------------------------------------
# No game-specific imports (verify module is game-agnostic)
# ---------------------------------------------------------------------------

class TestNoGameImports:

    def test_operator_agent_module_has_no_genshin_imports(self) -> None:
        """Verify the operator_agent module does not import any game-specific code."""
        import agent_kernel.operator_agent as module
        source_file = module.__file__
        assert source_file is not None
        with open(source_file, encoding="utf-8") as f:
            content = f.read()
        # Should not import genshin, hsr, or other game-specific modules
        forbidden = ["genshin", "hsr", "honkai", "starrail", "star_rail"]
        for keyword in forbidden:
            assert keyword not in content.lower(), f"Found '{keyword}' in operator_agent.py"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestCompanionAgentProtocol:

    def test_operator_agent_implements_protocol(self, agent: OperatorAgent) -> None:
        """Verify OperatorAgent implements the CompanionAgent protocol."""
        from agent_kernel.protocols import CompanionAgent
        assert isinstance(agent, CompanionAgent)

    def test_has_required_methods(self, agent: OperatorAgent) -> None:
        """Verify OperatorAgent has all CompanionAgent protocol methods."""
        assert hasattr(agent, "handle_user_message")
        assert hasattr(agent, "propose_override")
        assert hasattr(agent, "propose_capsule_patch")
        assert hasattr(agent, "explain_current_state")

    def test_method_signatures(self, agent: OperatorAgent) -> None:
        """Verify method signatures match protocol."""
        import inspect
        sig = inspect.signature(agent.handle_user_message)
        params = list(sig.parameters.keys())
        assert "message" in params
        assert "current_context" in params

        sig2 = inspect.signature(agent.propose_override)
        params2 = list(sig2.parameters.keys())
        assert "user_text" in params2
        assert "current_state" in params2

        sig3 = inspect.signature(agent.explain_current_state)
        params3 = list(sig3.parameters.keys())
        assert "state" in params3


# ---------------------------------------------------------------------------
# Kernel/Capsule boundary: keyword injection
# ---------------------------------------------------------------------------

class TestKeywordInjection:

    def test_kernel_agent_has_no_default_task_keywords(self) -> None:
        """Kernel OperatorAgent ships with empty task keywords by default."""
        bare_agent = OperatorAgent()
        assert bare_agent._task_keywords == {}

    def test_kernel_agent_ignores_game_specific_text(self) -> None:
        """Without Capsule keywords, game-specific text yields 'unknown'."""
        bare_agent = OperatorAgent()
        cap, conf = bare_agent._match_task_keyword("升级胡桃")
        assert cap == "unknown"
        assert conf == 0.3

    def test_injected_keywords_enable_matching(self) -> None:
        """Capsule-injected keywords restore matching capability."""
        capsule_kw = {"升级": "character_level_up", "战斗": "combat"}
        agent_with_kw = OperatorAgent(task_keywords=capsule_kw)
        cap, conf = agent_with_kw._match_task_keyword("升级胡桃")
        assert cap == "character_level_up"
        assert conf == 0.8

    def test_genshin_capsule_keywords_loadable(self) -> None:
        """Verify the Genshin Capsule keyword module loads and provides data."""
        from data.genshin_operator_keywords import GENSHIN_TASK_KEYWORDS
        assert len(GENSHIN_TASK_KEYWORDS) >= 20
        assert "升级" in GENSHIN_TASK_KEYWORDS
        assert GENSHIN_TASK_KEYWORDS["升级"] == "character_level_up"
        assert "level up" in GENSHIN_TASK_KEYWORDS

    def test_full_agent_with_genshin_capsule(self) -> None:
        """End-to-end: Kernel agent + Genshin Capsule keywords = full matching."""
        from data.genshin_operator_keywords import GENSHIN_TASK_KEYWORDS
        full_agent = OperatorAgent(task_keywords=GENSHIN_TASK_KEYWORDS)
        response = full_agent.handle_user_message("升级胡桃到90级", {})
        assert response["technical_action"]["intent"] == "set_goal"
        assert response["technical_action"]["task"].objective == "character_level_up"