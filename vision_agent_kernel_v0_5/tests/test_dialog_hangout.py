"""Tests for hangout event branch detection and multi-turn dialog management."""
from __future__ import annotations

import pytest

from interaction.dialog_hangout import (
    DialogPhase,
    DialogSession,
    DialogTurn,
    HangoutBranch,
    HangoutBranchDetector,
    HangoutEnding,
    HangoutEndingState,
    MultiTurnDialogManager,
)


# ---------------------------------------------------------------------------
# HangoutBranchDetector (D-06)
# ---------------------------------------------------------------------------
class TestHangoutBranchDetector:
    def test_detect_branch_with_signal(self) -> None:
        det = HangoutBranchDetector()
        branch = det.detect_branch("你觉得呢", ["一起去吧", "不了谢谢"])
        assert branch is not None
        assert len(branch.options) == 2
        assert branch.is_critical

    def test_no_branch_single_option(self) -> None:
        det = HangoutBranchDetector()
        assert det.detect_branch("text", ["only one"]) is None

    def test_no_branch_no_signal(self) -> None:
        det = HangoutBranchDetector()
        assert det.detect_branch("普通对话", ["选项A", "选项B"]) is None

    def test_recommend_good_ending(self) -> None:
        det = HangoutBranchDetector()
        branch = HangoutBranch(
            branch_id="test",
            description="test",
            options=["一起去吧", "算了"],
            target_endings={0: "good", 1: "bad"},
        )
        assert det.recommend_choice(branch, "good") == 0

    def test_recommend_default_first(self) -> None:
        det = HangoutBranchDetector()
        branch = HangoutBranch(
            branch_id="test",
            description="test",
            options=["A", "B"],
            target_endings={},
        )
        assert det.recommend_choice(branch, "good") == 0

    def test_record_and_check_endings(self) -> None:
        det = HangoutBranchDetector()
        det.record_ending("amber", "ending_1")
        state = det.get_or_create_state("amber")
        assert "ending_1" in state.unlocked_endings

    def test_completion_rate(self) -> None:
        det = HangoutBranchDetector()
        det.record_ending("amber", "ending_1")
        det.record_ending("amber", "ending_2")
        state = det.get_or_create_state("amber")
        assert state.completion_rate == pytest.approx(2 / 6)

    def test_all_endings_unlocked(self) -> None:
        det = HangoutBranchDetector()
        for i in range(1, 7):
            det.record_ending("amber", f"ending_{i}")
        state = det.get_or_create_state("amber")
        assert state.all_endings_unlocked

    def test_next_target_ending(self) -> None:
        det = HangoutBranchDetector()
        det.record_ending("amber", "ending_1")
        target = det.get_next_target_ending("amber")
        assert target == "ending_2"

    def test_next_target_all_done(self) -> None:
        det = HangoutBranchDetector()
        for i in range(1, 7):
            det.record_ending("amber", f"ending_{i}")
        assert det.get_next_target_ending("amber") is None

    def test_get_or_create_state(self) -> None:
        det = HangoutBranchDetector()
        s1 = det.get_or_create_state("amber")
        s2 = det.get_or_create_state("amber")
        assert s1 is s2
        assert s1.character == "amber"


class TestHangoutEndingState:
    def test_empty_state(self) -> None:
        state = HangoutEndingState(character="test")
        assert state.completion_rate == 0.0
        assert not state.all_endings_unlocked
        assert len(state.unlocked_endings) == 0


# ---------------------------------------------------------------------------
# MultiTurnDialogManager (D-09)
# ---------------------------------------------------------------------------
class TestMultiTurnDialogManager:
    def test_start_session(self) -> None:
        mgr = MultiTurnDialogManager()
        session = mgr.start_session("Katheryne", "daily_commissions")
        assert session.started
        assert session.npc_name == "Katheryne"
        assert session.quest_context == "daily_commissions"

    def test_add_turn(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("NPC")
        turn = mgr.add_turn("NPC", "你好旅行者，最近怎么样？", ["还好", "不太好"])
        assert turn is not None
        assert turn.turn_number == 1
        assert turn.phase == DialogPhase.GREETING

    def test_multiple_turns(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("NPC")
        mgr.add_turn("NPC", "你好旅行者", ["你好"])
        mgr.add_turn("NPC", "能帮我收集材料吗？", ["接受", "不了"])
        session = mgr.get_session("NPC")
        assert session is not None
        assert session.turn_count == 2

    def test_end_session(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("NPC")
        mgr.add_turn("NPC", "你好")
        session = mgr.end_session("NPC")
        assert session is not None
        assert session.completed
        assert mgr.get_session("NPC") is None

    def test_end_nonexistent(self) -> None:
        mgr = MultiTurnDialogManager()
        assert mgr.end_session("nobody") is None

    def test_add_turn_no_session(self) -> None:
        mgr = MultiTurnDialogManager()
        assert mgr.add_turn("nobody", "text") is None

    def test_quest_acceptance_detection(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("NPC")
        mgr.add_turn("NPC", "请帮帮我完成任务", ["接受任务", "不了"], selected=0)
        session = mgr.get_session("NPC")
        assert session is not None
        assert session.quest_accepted

    def test_quest_rejection(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("NPC")
        mgr.add_turn("NPC", "请帮帮我完成任务", ["接受任务", "不了"], selected=1)
        session = mgr.get_session("NPC")
        assert session is not None
        assert not session.quest_accepted

    def test_info_extraction(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("NPC")
        mgr.add_turn("NPC", "你需要前往璃月港找到钟离")
        session = mgr.get_session("NPC")
        assert session is not None
        assert any("前往" in info for info in session.key_info_extracted)

    def test_phase_detection_greeting(self) -> None:
        mgr = MultiTurnDialogManager()
        assert mgr.detect_phase("你好旅行者，好久不见") == DialogPhase.GREETING

    def test_phase_detection_quest(self) -> None:
        mgr = MultiTurnDialogManager()
        assert mgr.detect_phase("能帮我完成这个任务吗") == DialogPhase.QUEST_OFFER

    def test_phase_detection_commerce(self) -> None:
        mgr = MultiTurnDialogManager()
        assert mgr.detect_phase("这个多少钱") == DialogPhase.COMMERCE

    def test_phase_detection_farewell(self) -> None:
        mgr = MultiTurnDialogManager()
        assert mgr.detect_phase("再见，保重") == DialogPhase.FAREWELL

    def test_phase_detection_unknown(self) -> None:
        mgr = MultiTurnDialogManager()
        assert mgr.detect_phase("...") == DialogPhase.UNKNOWN

    def test_npc_history(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("Katheryne")
        mgr.add_turn("Katheryne", "你好")
        mgr.end_session("Katheryne")
        mgr.start_session("Katheryne")
        mgr.add_turn("Katheryne", "你好旅行者")
        mgr.end_session("Katheryne")
        history = mgr.get_npc_history("Katheryne")
        assert len(history) == 2

    def test_replace_existing_session(self) -> None:
        mgr = MultiTurnDialogManager()
        mgr.start_session("NPC")
        mgr.add_turn("NPC", "first session")
        mgr.start_session("NPC")  # Should auto-end previous
        history = mgr.get_npc_history("NPC")
        assert len(history) == 1
        assert mgr.get_session("NPC") is not None


class TestDialogSession:
    def test_current_turn_empty(self) -> None:
        session = DialogSession(npc_name="test")
        assert session.current_turn is None

    def test_current_turn(self) -> None:
        session = DialogSession(npc_name="test")
        turn = DialogTurn(turn_number=1, npc_text="hello")
        session.turns.append(turn)
        assert session.current_turn is turn

    def test_turn_count(self) -> None:
        session = DialogSession(npc_name="test")
        assert session.turn_count == 0
        session.turns.append(DialogTurn(turn_number=1))
        session.turns.append(DialogTurn(turn_number=2))
        assert session.turn_count == 2
