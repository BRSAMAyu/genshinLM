"""Tests for interaction/dialog_branch_analyzer.py: consequence tracking."""
from __future__ import annotations

from interaction.dialog_branch_analyzer import (
    ConsequenceTracker,
    DialogBranchAnalyzer,
)


class TestConsequenceTracker:
    def test_record_choice_returns_hash(self):
        tracker = ConsequenceTracker()
        h = tracker.record_choice(
            quest_id="q001", npc_name="katheryne",
            dialog_text="Do you accept?", options=["Yes", "No"],
            selected_index=0,
        )
        assert h.startswith("q001_")

    def test_record_consequence(self):
        tracker = ConsequenceTracker()
        h = tracker.record_choice("q001", "npc", "text", ["A", "B"], 0)
        tracker.record_consequence("q001", h, "quest_accepted", "accepted main quest")
        cons = tracker.get_consequences("q001")
        assert len(cons) == 1
        assert cons[0].outcome == "quest_accepted"

    def test_get_quest_choices(self):
        tracker = ConsequenceTracker()
        tracker.record_choice("q001", "a", "t1", ["X"], 0)
        tracker.record_choice("q002", "b", "t2", ["Y"], 0)
        tracker.record_choice("q001", "c", "t3", ["Z"], 0)
        assert len(tracker.get_quest_choices("q001")) == 2
        assert len(tracker.get_quest_choices("q002")) == 1

    def test_get_last_choice_hash(self):
        tracker = ConsequenceTracker()
        assert tracker.get_last_choice_hash("q001") is None
        tracker.record_choice("q001", "npc", "text", ["A"], 0)
        h = tracker.get_last_choice_hash("q001")
        assert h is not None

    def test_trim_on_overflow(self):
        tracker = ConsequenceTracker(max_history=5)
        for i in range(10):
            tracker.record_choice(f"q{i:03d}", "n", "t", ["A"], 0)
        assert len(tracker.get_quest_choices("q000")) == 0  # trimmed
        assert tracker.stats()["total_choices"] == 5

    def test_stats(self):
        tracker = ConsequenceTracker()
        tracker.record_choice("q001", "n", "t", ["A"], 0)
        tracker.record_consequence("q001", "h", "outcome")
        s = tracker.stats()
        assert s["total_choices"] == 1
        assert s["total_consequences"] == 1


class TestDialogBranchAnalyzerWithTracker:
    def test_analyze_with_tracker_records(self):
        tracker = ConsequenceTracker()
        analyzer = DialogBranchAnalyzer(tracker=tracker)
        idx = analyzer.analyze_choices(
            ["接受委托", "拒绝"],
            context={"quest_id": "q001", "npc_name": "katheryne", "dialog_text": "accept?"},
        )
        assert idx == 0
        choices = tracker.get_quest_choices("q001")
        assert len(choices) == 1
        assert choices[0].selected_index == 0

    def test_analyze_without_tracker(self):
        analyzer = DialogBranchAnalyzer()
        idx = analyzer.analyze_choices(["Yes", "No"])
        assert idx == 0

    def test_analyze_prefers_accept_keywords(self):
        tracker = ConsequenceTracker()
        analyzer = DialogBranchAnalyzer(tracker=tracker)
        idx = analyzer.analyze_choices(
            ["No thanks", "当然可以"],
            context={"quest_id": "q002", "npc_name": "npc", "dialog_text": "help?"},
        )
        assert idx == 1

    def test_empty_choices_returns_zero(self):
        analyzer = DialogBranchAnalyzer()
        assert analyzer.analyze_choices([]) == 0

    def test_no_context_no_record(self):
        tracker = ConsequenceTracker()
        analyzer = DialogBranchAnalyzer(tracker=tracker)
        analyzer.analyze_choices(["Yes", "No"])
        assert tracker.stats()["total_choices"] == 0
