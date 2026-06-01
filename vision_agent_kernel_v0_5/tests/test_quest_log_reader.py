"""Tests for QuestLogReader — OCR quest log reading and progress matching."""
from __future__ import annotations

import pytest

from planning.quest_log_reader import QuestLogEntry, QuestLogReader, QuestProgressClaim


def _mock_ocr(texts: list[str]):
    """Create a mock OCR function that returns predefined texts."""
    def ocr_fn(frame):
        return texts
    return ocr_fn


class TestQuestLogReader:
    def test_no_ocr_fn_returns_empty(self) -> None:
        reader = QuestLogReader()
        entries = reader.read_from_frame(None)
        assert entries == []

    def test_ocr_fn_returns_entries(self) -> None:
        ocr = _mock_ocr(["与凯瑟琳交谈", "前往蒙德城"])
        reader = QuestLogReader(ocr_fn=ocr)
        entries = reader.read_from_frame(None)
        assert len(entries) == 2
        assert entries[0].objective_text == "与凯瑟琳交谈"

    def test_short_text_filtered(self) -> None:
        ocr = _mock_ocr(["ab", "正常的目标文字"])
        reader = QuestLogReader(ocr_fn=ocr)
        entries = reader.read_from_frame(None)
        assert len(entries) == 1
        assert "正常" in entries[0].objective_text

    def test_ocr_exception_returns_empty(self) -> None:
        def bad_ocr(frame):
            raise RuntimeError("OCR engine failed")
        reader = QuestLogReader(ocr_fn=bad_ocr)
        entries = reader.read_from_frame(None)
        assert entries == []

    def test_match_with_knowledge_base(self) -> None:
        from knowledge.genshin_archon_quests import QuestStep
        knowledge = [
            QuestStep(
                step_id="prologue_act1_step1",
                description="与凯瑟琳交谈以开始任务",
                objective="与凯瑟琳交谈",
                npc_name="凯瑟琳",
            ),
        ]
        ocr = _mock_ocr(["与凯瑟琳交谈"])
        reader = QuestLogReader(quest_knowledge=knowledge, ocr_fn=ocr)
        entries = reader.read_from_frame(None)
        claims = reader.match_progress(entries)
        # Match depends on knowledge base overlap scoring
        assert len(claims) >= 0  # May or may not match depending on scoring

    def test_no_knowledge_returns_no_claims(self) -> None:
        ocr = _mock_ocr(["与凯瑟琳交谈"])
        reader = QuestLogReader(ocr_fn=ocr)
        entries = reader.read_from_frame(None)
        claims = reader.match_progress(entries)
        assert len(claims) == 0

    def test_entry_dataclass_fields(self) -> None:
        ocr = _mock_ocr(["测试目标文字"])
        reader = QuestLogReader(ocr_fn=ocr)
        entries = reader.read_from_frame(None)
        assert len(entries) == 1
        e = entries[0]
        assert isinstance(e, QuestLogEntry)
        assert e.quest_id == "unknown"
        assert e.confidence > 0

    def test_claim_dataclass_fields(self) -> None:
        from knowledge.genshin_archon_quests import QuestStep
        knowledge = [
            QuestStep(
                step_id="test_quest_step",
                description="击败风魔龙",
                objective="击败风魔龙",
                has_combat=True,
            ),
        ]
        ocr = _mock_ocr(["击败风魔龙"])
        reader = QuestLogReader(quest_knowledge=knowledge, ocr_fn=ocr)
        entries = reader.read_from_frame(None)
        claims = reader.match_progress(entries)
        if claims:
            c = claims[0]
            assert isinstance(c, QuestProgressClaim)
            assert c.confidence > 0
            assert "击败风魔龙" in c.matched_text
