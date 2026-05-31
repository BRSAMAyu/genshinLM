"""Tests for Phase 5: Quest log reader + Dialog choice arbiter."""
from __future__ import annotations

import time
from typing import Any

import pytest

from planning.dialog_choice_arbiter import (
    DialogChoice,
    DialogChoiceArbiter,
    DialogChoiceClaim,
)
from planning.quest_log_reader import QuestLogEntry, QuestLogReader, QuestProgressClaim


class TestDialogChoice:
    def test_frozen(self):
        c = DialogChoice(
            index=0, text="Accept Quest", bbox_norm=(0.5, 0.6, 0.7, 0.7)
        )
        assert c.index == 0
        assert c.text == "Accept Quest"
        assert c.clickable is True


class TestDialogChoiceClaim:
    def test_defaults(self):
        claim = DialogChoiceClaim(
            claim_id="test", frame_id=1, timestamp=time.perf_counter()
        )
        assert claim.selected_index == -1
        assert claim.confidence == 0.0
        assert claim.choices == ()


class TestDialogChoiceArbiter:
    def test_no_vlm_picks_first(self):
        arbiter = DialogChoiceArbiter(vlm_arbiter_fn=None)
        choices = [
            DialogChoice(index=0, text="Accept", bbox_norm=(0.5, 0.6, 0.7, 0.7)),
            DialogChoice(index=1, text="Decline", bbox_norm=(0.5, 0.7, 0.7, 0.8)),
        ]
        claim = arbiter.select_choice(None, choices)
        assert claim.selected_index == 0
        assert claim.confidence == 0.3  # degraded confidence when no VLM

    def test_vlm_call_count_tracked(self):
        arbiter = DialogChoiceArbiter(
            vlm_arbiter_fn=lambda f, ctx: "0",
            vlm_confidence_threshold=0.9,
        )
        choices = [
            DialogChoice(index=0, text="A", bbox_norm=(0.5, 0.5, 0.6, 0.6)),
            DialogChoice(index=1, text="B", bbox_norm=(0.5, 0.6, 0.6, 0.7)),
        ]
        # Call 3 times - each below threshold → 3 VLM calls
        for _ in range(3):
            arbiter.select_choice(None, choices)
        assert arbiter.vlm_call_count == 3

    def test_vlm_limit_enforced(self):
        arbiter = DialogChoiceArbiter(
            vlm_arbiter_fn=lambda f, ctx: "0",
            vlm_confidence_threshold=0.9,
        )
        choices = [
            DialogChoice(index=0, text="A", bbox_norm=(0.5, 0.5, 0.6, 0.6)),
        ]
        # Call 25 times - should cap at 20
        for _ in range(25):
            arbiter.select_choice(None, choices)
        assert arbiter.vlm_call_count == 20

    def test_reset_vlm_counter(self):
        arbiter = DialogChoiceArbiter(
            vlm_arbiter_fn=lambda f, ctx: "0",
            vlm_confidence_threshold=0.9,
        )
        choices = [
            DialogChoice(index=0, text="A", bbox_norm=(0.5, 0.5, 0.6, 0.6)),
        ]
        arbiter.select_choice(None, choices)
        arbiter.select_choice(None, choices)
        assert arbiter.vlm_call_count == 2
        arbiter.reset_vlm_counter()
        assert arbiter.vlm_call_count == 0

    def test_vlm_response_parsing(self):
        arbiter = DialogChoiceArbiter(vlm_arbiter_fn=lambda f, ctx: "Option 2 is best")
        choices = [
            DialogChoice(index=i, text=f"Option {i}", bbox_norm=(0.5, 0.5 + i*0.1, 0.6, 0.6 + i*0.1))
            for i in range(5)
        ]
        claim = arbiter.select_choice(None, choices)
        # "Option 2" in response should parse to index 2
        assert claim.selected_index in range(5)


class TestQuestLogEntry:
    def test_frozen(self):
        entry = QuestLogEntry(
            quest_id="AQ001", step_index=1, objective_text="Talk to Katheryne"
        )
        assert entry.quest_id == "AQ001"


class TestQuestProgressClaim:
    def test_defaults(self):
        claim = QuestProgressClaim(
            quest_id="AQ001", step_index=1, status="in_progress"
        )
        assert claim.confidence == 0.5
        assert claim.matched_text == ""


class TestQuestLogReader:
    def test_no_ocr_returns_empty(self):
        reader = QuestLogReader(ocr_fn=None)
        entries = reader.read_from_frame(None)
        assert entries == []

    def test_parse_line_filters_short(self):
        reader = QuestLogReader(ocr_fn=None)
        entry = reader._parse_line("ab")
        assert entry is None

    def test_parse_line_valid(self):
        reader = QuestLogReader(ocr_fn=None)
        entry = reader._parse_line("1. Talk to Katheryne in Mondstadt")
        assert entry is not None
        assert "katheryne" in entry.objective_text.lower()
        assert entry.quest_id == "unknown"  # no knowledge base by default

    def test_match_progress_no_entries(self):
        reader = QuestLogReader()
        claims = reader.match_progress([])
        assert claims == []

    def test_auto_detect_no_ocr(self):
        reader = QuestLogReader(ocr_fn=None)
        from core.state_bus import StateBus
        bus = StateBus()
        reader._state_bus = bus
        claims = reader.auto_detect_and_publish(None)
        assert claims == []